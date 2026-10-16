"""The hash of the code a function depends on, at the level of functions rather than files.

A rule's results can change only if the code it runs changes. Hashing whole files would mark every rule that imports
a module stale whenever anything in that module changes. Instead, CodeIndex follows the names a function uses:

- functions, classes and module-level assignments of the same module;
- `module.name` through `import module [as alias]`;
- `name` through `from module import name`;

within the project's own modules (the .py files under the search paths). The index transitively collects the
definitions reached. Each definition is hashed by its syntax tree, with docstrings removed and without line numbers,
so editing comments, docstrings or layout changes nothing.

Third-party code enters through the installed distributions the closure imports, followed through their declared
requirements. Each distribution is identified by name, version and, for packages installed from a repository, the
commit. Any installed file whose content no longer matches the distribution's RECORD (a file patched in place) adds
its own hash. The Python version is part of the hash too.

The analysis is conservative where it cannot follow the code:
- statements at module level that are not definitions (side effects) belong to every closure that uses the module;
- a module used as a value (`f(module)`, `getattr(module, x)`) brings in the whole module;
- `globals()`, `vars()`, `eval`, `exec` or `__import__` inside a function bring in its whole module.
"""
import ast
import base64
import copy
import importlib.metadata as md
import json
import re
import sys
from pathlib import Path

from .hashing import sha256_json

# Calls that reach names the analysis cannot see. The code is only parsed here, never executed.
DYNAMIC = {"globals", "vars", "eval", "exec", "__import__"}


class _StripDocstrings(ast.NodeTransformer):
    def _strip(self, node):
        self.generic_visit(node)
        b = node.body
        if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
            node.body = b[1:] or [ast.Pass()]
        return node

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = visit_Module = _strip


def node_hash(node):
    n = _StripDocstrings().visit(copy.deepcopy(node))
    return sha256_json(ast.dump(n, include_attributes=False))


def _is_main_guard(node):
    t = node.test if isinstance(node, ast.If) else None
    return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "__name__"
            and len(t.comparators) == 1 and isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value == "__main__")


def _bound_names(node):
    """Names a top-level statement binds: definitions, assignment targets and import aliases, at any depth of an
    if/try/with block (not inside function or class bodies)."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(n.name)
        elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                out += [x.id for x in ast.walk(t) if isinstance(x, ast.Name)]
    return out


class Module:
    def __init__(self, name, path):
        self.name, self.path = name, Path(path)
        self.tree = ast.parse(self.path.read_text(), filename=str(path))
        self.defs = {}        # name -> [statement nodes that bind it]
        self.imports = {}     # alias -> ("mod", module) | ("from", module, name)
        self.stars = []       # modules imported with *
        self.effects = []     # top-level statements that are not plain definitions or imports
        # the package that relative imports start from
        self.package = name if self.path.name == "__init__.py" else (name.rsplit(".", 1)[0] if "." in name else "")
        for node in self.tree.body:
            self._top(node, effect_ok=True)

    def _resolve_relative(self, node):
        if not node.level:
            return node.module or ""
        parts = self.package.split(".") if self.package else []
        base = parts[:len(parts) - (node.level - 1)] if node.level > 1 else parts
        return ".".join(base + ([node.module] if node.module else []))

    def _import(self, node):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    self.imports[a.asname] = ("mod", a.name)
                else:
                    top = a.name.split(".")[0]
                    self.imports[top] = ("mod", top)
        else:
            mod = self._resolve_relative(node)
            for a in node.names:
                if a.name == "*":
                    self.stars.append(mod)
                else:
                    self.imports[a.asname or a.name] = ("from", mod, a.name)

    def _top(self, node, effect_ok):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return                                          # module docstring
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self._import(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self.defs.setdefault(node.name, []).append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for n in _bound_names(node):
                self.defs.setdefault(n, []).append(node)
            if any(not isinstance(t, ast.Name) for t in (node.targets if isinstance(node, ast.Assign) else [node.target])):
                self.effects.append(node)                   # e.g. os.environ["X"] = ... at import
        elif _is_main_guard(node):
            return                                          # does not run on import
        else:
            # if/try/with/for blocks and bare calls: imports and definitions inside them resolve to the whole block,
            # which is also a side effect of importing the module
            for n in ast.walk(node):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    self._import(n)
            for n in _bound_names(node):
                self.defs.setdefault(n, []).append(node)
            self.effects.append(node)


def _refs(node):
    """Names a node uses: ("name", id) for bare names and ("attr", base, attr) for base.attr, where the base name is
    used only through that attribute."""
    attr_bases = set()
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            out.append(("attr", n.value.id, n.attr))
            attr_bases.add(id(n.value))
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and id(n) not in attr_bases:
            out.append(("name", n.id))
    return out


def _dynamic_uses(node):
    """True if the node calls globals(), vars(), eval(), exec() or __import__()."""
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in DYNAMIC for n in ast.walk(node))


def _getattr_on(node):
    """Names passed as the first argument of getattr/setattr/hasattr calls."""
    return {n.args[0].id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in ("getattr", "setattr", "hasattr") and n.args and isinstance(n.args[0], ast.Name)}


class CodeIndex:
    """The project's own modules: every .py file under the search paths, named as Python would import them with
    those paths on sys.path (pipeline/fpp_core.py -> fpp_core, pipeline/dag/hashing.py -> dag.hashing)."""

    def __init__(self, search_paths):
        self.paths = {}
        for root in map(Path, search_paths):
            for p in sorted(root.rglob("*.py")):
                rel = p.relative_to(root).with_suffix("")
                parts = list(rel.parts)
                if any(x.startswith(".") or x == "__pycache__" for x in parts):
                    continue
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                    if not parts:
                        continue
                self.paths.setdefault(".".join(parts), p)
        self._mods = {}

    def is_local(self, name):
        return name in self.paths

    def module(self, name):
        if name not in self.paths:
            return None
        if name not in self._mods:
            self._mods[name] = Module(name, self.paths[name])
        return self._mods[name]

    def closure(self, module, name, ignore=()):
        """The definitions function `name` of `module` depends on: {"module.name": hash}, the module side effects
        {module: hash}, and the top-level names of third-party modules used. Definitions named in `ignore`
        ("module.name") are not followed: the build's own @rule and @check decorators, which register a function
        but do not change what it computes."""
        parts, effects, external = {}, {}, set()
        seen = {tuple(x.rsplit(".", 1)) for x in ignore}
        stack = [(module, name)]
        while stack:
            m, n = stack.pop()
            if (m, n) in seen:
                continue
            seen.add((m, n))
            mod = self.module(m)
            if mod is None:
                _external(m, external)
                continue
            if m not in effects:
                effects[m] = sha256_json([node_hash(s) for s in mod.effects])
                for s in mod.effects:                       # what the side effects use is a dependency too
                    stack += self._resolve(mod, _refs(s), external)
            if n is None:                                   # the whole module
                stack += [(m, d) for d in mod.defs]
                stack += [(s, None) for s in mod.stars]
                for alias, imp in mod.imports.items():
                    stack += self._resolve(mod, [("name", alias)], external)
                continue
            if n in mod.defs:
                nodes = mod.defs[n]
                parts[f"{m}.{n}"] = sha256_json([node_hash(x) for x in nodes])
                for x in nodes:
                    if _dynamic_uses(x):
                        stack.append((m, None))
                    for base in _getattr_on(x):
                        imp = mod.imports.get(base)
                        if imp and imp[0] == "mod":
                            stack.append((imp[1], None))
                    stack += self._resolve(mod, _refs(x), external)
            elif n in mod.imports:
                stack += self._resolve(mod, [("name", n)], external)
            else:
                if self.is_local(f"{m}.{n}"):
                    stack.append((f"{m}.{n}", None))        # a submodule reached as an attribute of its package
                stack += [(s, n) for s in mod.stars]
        return parts, effects, sorted(external)

    def _resolve(self, mod, refs, external):
        """Turn the names used in `mod` into (module, name) pairs to visit; record third-party modules."""
        out = []
        for r in refs:
            base = r[1]
            if base in mod.defs:
                out.append((mod.name, base))
                continue
            imp = mod.imports.get(base)
            if imp is None:
                if mod.stars:
                    out += [(s, base) for s in mod.stars]
                continue                                    # a builtin, a local variable or a parameter
            if imp[0] == "mod":
                target = imp[1]
                if not self.is_local(target):
                    _external(target, external)
                elif r[0] == "attr":
                    sub = f"{target}.{r[2]}"
                    out.append((sub, None) if self.is_local(sub) else (target, r[2]))
                else:
                    out.append((target, None))              # the module used as a value
            else:
                _, target, name = imp
                sub = f"{target}.{name}" if target else name
                if self.is_local(sub):                      # `from package import submodule`
                    out.append((sub, r[2]) if r[0] == "attr" else (sub, None))
                elif self.is_local(target):
                    out.append((target, name))
                else:
                    _external(target, external)
        return out


def _external(module, external):
    top = module.split(".")[0]
    if top and top not in sys.stdlib_module_names:
        external.add(top)


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


_REQ = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


class Environment:
    """Identity of the installed third-party code: distributions by version (and commit for packages installed from
    a repository), plus the hashes of any installed files that differ from their RECORD."""

    def __init__(self, hasher):
        self.hasher = hasher
        self._top = None
        self._dists = {_norm(d.metadata["Name"]): d for d in md.distributions() if d.metadata["Name"]}
        self._fp = {}

    def dists_for(self, top_modules):
        if self._top is None:
            self._top = md.packages_distributions()
        todo = [_norm(d) for t in top_modules for d in self._top.get(t, [])]
        seen = set()
        while todo:
            d = todo.pop()
            if d in seen or d not in self._dists:
                continue
            seen.add(d)
            for req in self._dists[d].requires or []:
                if "extra ==" in req.replace("extra==", "extra =="):
                    continue                                # optional extras are not installed by default
                m = _REQ.match(req)
                if m:
                    todo.append(_norm(m.group(1)))
        return sorted(seen)

    def fingerprint(self, dist):
        if dist in self._fp:
            return self._fp[dist]
        d = self._dists[dist]
        fp = {"version": d.version}
        try:
            du = json.loads(d.read_text("direct_url.json") or "null")
        except (OSError, ValueError):
            du = None
        if du and du.get("vcs_info"):
            fp["commit"] = du["vcs_info"].get("commit_id")
        modified = {}
        for f in d.files or []:
            if not f.hash or f.hash.mode != "sha256" or "__pycache__" in f.parts:
                continue
            p = Path(f.locate())
            if not p.is_file():
                modified[str(f)] = None
                continue
            h = base64.urlsafe_b64encode(bytes.fromhex(self.hasher.file(p))).rstrip(b"=").decode()
            if h != f.hash.value:
                modified[str(f)] = h
        if modified:
            fp["modified"] = modified
        self._fp[dist] = fp
        return fp

    def describe(self, top_modules):
        return {"python": sys.version.split()[0], "dists": {d: self.fingerprint(d) for d in self.dists_for(top_modules)}}
