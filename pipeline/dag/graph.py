"""Rules, the dependency graph between them, and the runner.

A rule is a Python function declared with @rule(inputs=..., outputs=..., params=...). Its stamp is the hash of
- the code it depends on (codehash.CodeIndex: the functions it reaches, the third-party distributions they import),
- the values of the parameters it declares (params.toml),
- the contents of its inputs (files, directories, and the files matched by glob patterns).
An output is a file, a directory, or a glob pattern (the paths it matches, hashed together like a pattern input); no
two rules' outputs may name the same files. Rule B depends on rule A when one of B's inputs can name one of A's outputs
or a file inside one. A rule is up to date when its stamp equals the one in the lock and its outputs still have the
hashes the lock recorded. Because the stamp uses the contents of the inputs, an upstream rule that reruns but writes
identical files leaves everything after it up to date.
A check is a rule without outputs whose function raises if the data are wrong; the lock records whether it passed.

Private rules (for files that are not published) are declared in a rules file outside the repository's published
part, with their code next to it; they are loaded only where that file exists, their lock entries go to a
private lock beside it, and `check --ci` leaves them out. A published rule may not use a private rule's output.

Two kinds of output are also inputs (`inplace`):
- "template": a hand-written document with generated numbers (dag/markers.py). The prose, with every marker emptied,
  is an input: editing it reruns the rule, which fills the markers again. A generated value edited by hand is put back.
- "ledger": an append-only file the rule extends (the transit registry). Its content is an input, the stamp is taken
  after the rule has run, and an edit by hand stops the build as for any other output.
"""
import importlib.util
import os
import sys
import time
import traceback
from pathlib import Path

from . import params as P
from .audit import Watch
from .codehash import CodeIndex, Environment
from .context import RunContext, is_glob, overlap
from .hashing import FileHasher, sha256_bytes, sha256_json
from .lock import Lock
from .markers import template as doc_template

_REGISTRY = None
# the decorators that declare rules: they register a function but do not change what it computes, so they are left
# out of rules' code hashes (their arguments, the declared inputs, outputs and parameters, are part of the hash)
REGISTRATION = ("dag.rule", "dag.check", "dag.graph.rule", "dag.graph.check")


class Rule:
    def __init__(self, func, name, inputs, outputs, params, is_check, allow_reads, inplace=None):
        self.func, self.name = func, name
        self.inputs, self.outputs, self.params = list(inputs), list(outputs), list(params)
        self.is_check, self.allow_reads = is_check, list(allow_reads)
        self.inplace = dict(inplace or {})
        for path, mode in self.inplace.items():
            if path not in self.outputs or mode not in ("template", "ledger") or (mode == "template" and is_glob(path)):
                raise ValueError(f"rule {name}: in-place file {path} must be an output, as 'template' (a file) or 'ledger'")
        for p in self.inputs + self.outputs:
            if os.path.isabs(p) or ".." in Path(p).parts:
                raise ValueError(f"rule {name}: paths are relative to the repository root, without '..': {p}")
        self.module = None          # set by Project: the module name as the code index knows it
        self.private = False        # set by Project for the rules of a private rules file


def _register(func, name, inputs, outputs, params, is_check, allow_reads, inplace=None):
    r = Rule(func, name or func.__name__, inputs, outputs, params, is_check, allow_reads, inplace)
    if _REGISTRY is not None:
        _REGISTRY.append(r)
    func.dag_rule = r
    return func


def rule(*, inputs=(), outputs=(), params=(), name=None, allow_reads=(), inplace=None):
    if not outputs:
        raise ValueError("a rule needs outputs; use @check for a rule that only tests")
    return lambda f: _register(f, name, inputs, outputs, params, False, allow_reads, inplace)


def check(*, inputs=(), params=(), name=None, allow_reads=()):
    return lambda f: _register(f, name, inputs, (), params, True, allow_reads)


class Status:
    def __init__(self, state, reasons=()):
        self.state, self.reasons = state, list(reasons)

    @property
    def ok(self):
        return self.state == "ok"


class BuildError(Exception):
    pass


class Project:
    def __init__(self, root, rules=("pipeline/rules.py",), code_paths=("pipeline",), params="pipeline/params.toml",
                 lock="dag.lock.json", cache=".dag-cache", private_rules=("results_cloud/glue/build/private_rules.py",),
                 private_lock="results_cloud/glue/build/dag.lock.json"):
        self.root = Path(root).resolve()
        private_rules = [self.root / p for p in private_rules if (self.root / p).exists()]
        self.code_paths = [self.root / c for c in code_paths]
        private_dirs = sorted({p.parent for p in private_rules} - set(self.code_paths))   # private code is next to its rules
        clash = sorted(set(CodeIndex(self.code_paths).paths) & set(CodeIndex(private_dirs).paths))
        if clash:
            raise BuildError(f"private modules have the names of published ones: {', '.join(clash)}")
        self.code_paths += private_dirs
        self.code = CodeIndex(self.code_paths)
        self.hasher = FileHasher(self.root / cache / "hashes.json")
        self.env = Environment(self.hasher)
        pp = self.root / params
        self.params = P.load(pp) if pp.exists() else {}
        self.lock = Lock(self.root / lock)
        self.private_lock = Lock(self.root / private_lock)
        self.rules = {}
        for rf in rules:
            self._load(self.root / rf)
        for rf in private_rules:
            self._load(rf, private=True)
        self._index()
        self._stamps = {}
        self._details = {}          # rule -> pattern -> {file: hash}, the files behind each glob input
        self.details_dir = self.root / cache / "inputs"

    # loading ---------------------------------------------------------------------------------------------------
    def _module_name(self, path):
        for c in self.code_paths:
            try:
                rel = Path(path).resolve().relative_to(c)
            except ValueError:
                continue
            parts = list(rel.with_suffix("").parts)
            return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        raise BuildError(f"{path} is not under the code paths {self.code_paths}")

    def _load(self, path, private=False):
        global _REGISTRY
        for c in reversed(self.code_paths):
            if str(c) not in sys.path:
                sys.path.insert(0, str(c))
        # the project's own modules are loaded fresh, so a changed file is never served from an earlier import
        for name in list(sys.modules):
            if name == "dag" or name.startswith("dag."):
                continue
            f = getattr(sys.modules[name], "__file__", None)
            if name in self.code.paths or (f and any(Path(f).resolve().is_relative_to(c) for c in self.code_paths)):
                del sys.modules[name]
        modname = self._module_name(path)
        spec = importlib.util.spec_from_file_location(modname, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[modname] = mod
        prev, _REGISTRY = _REGISTRY, []
        try:
            spec.loader.exec_module(mod)
            found = _REGISTRY
        finally:
            _REGISTRY = prev
        for r in found:
            if r.name in self.rules:
                raise BuildError(f"two rules are named {r.name}")
            r.module = self._module_name(r.func.__code__.co_filename)
            r.private = private
            self.rules[r.name] = r

    def _index(self):
        self.owner = {}
        for r in self.rules.values():
            for o in r.outputs:
                for o2, owner in self.owner.items():
                    if overlap(o, o2):
                        raise BuildError(f"{o} ({r.name}) and {o2} ({owner}) can name the same files")
                self.owner[o] = r.name
        self.deps = {}
        for r in self.rules.values():
            # the input is that output, lies inside an output directory, or can match what an output pattern matches
            self.deps[r.name] = {owner for pat in r.inputs for o, owner in self.owner.items()
                                 if owner != r.name and overlap(pat, o)}
            private = sorted(d for d in self.deps[r.name] if self.rules[d].private)
            if private and not r.private:
                raise BuildError(f"the published rule {r.name} uses outputs of the private rules {', '.join(private)}")
        self.order, state = [], {}

        def visit(n, path):
            if state.get(n) == 1:
                raise BuildError("dependency cycle: " + " -> ".join(path + [n]))
            if state.get(n) == 2:
                return
            state[n] = 1
            for m in sorted(self.deps[n]):
                visit(m, path + [n])
            state[n] = 2
            self.order.append(n)

        for n in sorted(self.rules):
            visit(n, [])

    def lock_of(self, name):
        return self.private_lock if self.rules[name].private else self.lock

    # stamps ----------------------------------------------------------------------------------------------------
    def input_hashes(self, r):
        """{input: hash}. A glob pattern gets one hash over the paths and contents of the files it matches (None if it
        matches nothing), so the lock stays small; the per-file hashes go to the local cache, for `explain`."""
        out = {}
        for pat in r.inputs:
            if is_glob(pat):
                files = self.matched(pat)
                out[pat] = sha256_json(sorted(files.items())) if files else None
                self._details.setdefault(r.name, {})[pat] = files
            else:
                out[pat] = self.hasher.path(self.root / pat)
        for path, mode in r.inplace.items():
            out[f"{path} ({mode})"] = self.inplace_hash(path, mode)
        return out

    def matched(self, pattern):
        """{path: hash} of the files and directories a glob pattern matches."""
        return {h.relative_to(self.root).as_posix(): self.hasher.path(h) for h in sorted(self.root.glob(pattern))}

    def path_hash(self, path):
        """The hash of a file or directory, or one hash over everything a pattern matches; None if there is nothing."""
        if is_glob(path):
            files = self.matched(path)
            return sha256_json(sorted(files.items())) if files else None
        return self.hasher.path(self.root / path)

    def inplace_hash(self, path, mode):
        if mode == "ledger":
            return self.path_hash(path)
        p = self.root / path
        if not p.exists():
            return None
        return sha256_bytes(doc_template(p.read_text()).encode())

    def code_info(self, r, with_env=True):
        parts, effects, external = self.code.closure(r.module, r.func.__name__, ignore=REGISTRATION)
        cparts, ceffects, cext = self.code.closure("dag.context", "RunContext")
        parts.update(cparts)
        effects.update(ceffects)
        if not with_env:
            return {"parts": parts, "effects": effects}
        return {"parts": parts, "effects": effects, "env": self.env.describe(sorted(set(external) | set(cext)))}

    def stamp(self, r):
        info = {"code": self.code_info(r), "params": P.select(self.params, r.params), "inputs": self.input_hashes(r)}
        return sha256_json(info), info

    def _glob_details(self, name):
        import json
        f = self.details_dir / f"{name}.json"
        try:
            old = json.loads(f.read_text()) if f.exists() else {}
        except ValueError:
            old = {}
        return {"old": old, "new": self._details.get(name, {})}

    def output_hashes(self, r):
        return {o: self.path_hash(o) for o in r.outputs}

    # status ----------------------------------------------------------------------------------------------------
    def status(self, name, _memo=None):
        memo = {} if _memo is None else _memo
        if name in memo:
            return memo[name]
        r = self.rules[name]
        entry = self.lock_of(name).get(name)
        st, info = self.stamp(r)
        outs = self.output_hashes(r)
        reasons = []
        edited = [o for o, h in outs.items() if entry and h is not None and entry["outputs"].get(o) not in (None, h)
                  and not (r.inplace.get(o) == "template" and entry["inputs"].get(f"{o} (template)")
                           != info["inputs"].get(f"{o} (template)"))]       # a prose edit: the rule reruns
        missing = [o for o, h in outs.items() if h is None]
        waiting = [d for d in sorted(self.deps[name]) if not self.status(d, memo).ok]
        if edited:
            s = Status("edited", [f"{o} differs from what the build wrote; it was changed outside the build" for o in edited])
        elif entry is None:
            s = Status("new", ["never built"])
        elif st != entry["stamp"]:
            s = Status("stale", explain_change(entry, info, self._glob_details(name)))
        elif missing:
            s = Status("missing", [f"{o} does not exist" for o in missing])
        elif r.is_check and entry.get("result") != "passed":
            s = Status("failed", [entry.get("message", "failed")])
        else:
            s = Status("ok")
        if waiting and s.ok:
            s = Status("waiting", [])
        if waiting:
            s.reasons.append("after " + ", ".join(waiting) + " (not up to date)")
        if r.is_check is False and s.state == "new" and any(h is not None for h in outs.values()):
            s.reasons.append("outputs exist and will be overwritten")
        memo[name] = s
        return s

    def check_lock(self, name):
        """Problems with a rule's lock entry that can be seen on any machine: outputs that differ from what the build
        wrote, and inputs, parameters or code that changed since. The installed packages are not compared, since they
        differ between machines; inputs that are not present here (private data) are listed as not checked."""
        r, entry = self.rules[name], self.lock_of(name).get(name)
        if entry is None:
            return ["never built"], []
        problems, unchecked = [], []
        for o, h in self.output_hashes(r).items():
            if h != entry["outputs"].get(o):
                problems.append(f"{o} differs from what the build wrote" if h else f"{o} does not exist")
        now = self.input_hashes(r)
        for k in sorted(set(entry["inputs"]) | set(now)):
            if k not in entry["inputs"]:
                problems.append(f"new input {k}")
            elif now.get(k) is None and entry["inputs"][k] is not None:
                unchecked.append(k)
            elif now.get(k) != entry["inputs"][k]:
                problems.append(f"input {k} changed")
        if P.select(self.params, r.params) != entry["params"]:
            problems.append("parameters changed")
        code = self.code_info(r, with_env=False)
        if code["parts"] != entry["code"]["parts"] or code["effects"] != entry["code"]["effects"]:
            problems.append("code changed: " + ", ".join(k for k in sorted(set(code["parts"]) | set(entry["code"]["parts"]))
                                                          if code["parts"].get(k) != entry["code"]["parts"].get(k)))
        if r.is_check and entry.get("result") != "passed":
            problems.append(entry.get("message", "check failed"))
        return problems, unchecked

    # running ---------------------------------------------------------------------------------------------------
    def select(self, targets=None):
        if not targets:
            return list(self.order)
        want, stack = set(), list(targets)
        while stack:
            n = stack.pop()
            if n not in self.rules:
                raise BuildError(f"no rule named {n}")
            if n not in want:
                want.add(n)
                stack += self.deps[n]
        return [n for n in self.order if n in want]

    def run(self, targets=None, discard_edits=False, dry_run=False, log=print):
        ran, failed_checks = [], []
        for name in self.select(targets):
            s = self.status(name)
            if s.ok or s.state == "waiting":
                continue
            regen = [o for o in self.rules[name].outputs if self.rules[name].inplace.get(o) == "template"]
            if s.state == "edited" and regen and all(any(o in x for o in regen) for x in s.reasons):
                log(f"{name}: generated values were edited by hand in {', '.join(regen)}; they are generated again")
            elif s.state == "edited" and not discard_edits:
                raise BuildError(f"{name}: " + "; ".join(s.reasons) + ". Restore the file, or rerun with --discard-edits "
                                 "to overwrite it.")
            if dry_run:
                log(f"would run {name}: " + "; ".join(s.reasons[:6]) + (f"; and {len(s.reasons) - 6} more" if len(s.reasons) > 6 else ""))
                continue
            log(f"running {name}: " + "; ".join(s.reasons[:6]) + (f"; and {len(s.reasons) - 6} more" if len(s.reasons) > 6 else ""))
            ok = self.execute(self.rules[name], log)
            ran.append(name)
            if not ok:
                failed_checks.append(name)
        if not dry_run and not targets:             # entries of rules that no longer exist
            loaded_private = any(r.private for r in self.rules.values())
            for lock, private in ((self.lock, False), (self.private_lock, True)):
                if private and not loaded_private:
                    continue
                for name in [n for n in lock.data["rules"] if n not in self.rules]:
                    lock.remove(name)
                    log(f"removed {name} from the lock: the rule no longer exists")
                lock.save()
        self.hasher.save()
        return ran, failed_checks

    def _saved_outputs(self, r):
        """The content of a rule's file outputs before it runs (not of in-place, directory or pattern outputs), so that a
        run that fails leaves them as the lock records them."""
        if r.inplace:
            return {}
        out = {}
        for o in r.outputs:
            p = self.root / o
            if not any(ch in o for ch in "*?[") and not p.is_dir():
                out[p] = p.read_bytes() if p.exists() else None
        return out

    def execute(self, r, log=print):
        saved = self._saved_outputs(r)
        try:
            return self._execute(r, log)
        except BuildError:
            for p, data in saved.items():
                if data is None:
                    p.unlink(missing_ok=True)
                elif not p.exists() or p.read_bytes() != data:
                    p.write_bytes(data)
            raise

    def _execute(self, r, log=print):
        st0, info = self.stamp(r)
        ctx = RunContext(self.root, r, P.select(self.params, r.params))
        result, message = "passed", ""
        t0 = time.time()
        with Watch(self.root, r, r.inputs, r.outputs, self.code_paths) as w:
            try:
                r.func(ctx)
            except Exception as ex:
                if not r.is_check:
                    raise BuildError(f"rule {r.name} failed:\n{traceback.format_exc()}") from ex
                result, message = "failed", f"{type(ex).__name__}: {ex}"
        if w.violations:
            listed = "\n".join(f"  {k} {p}" for k, p in sorted(set(w.violations))[:40])
            raise BuildError(f"rule {r.name} used files it does not declare:\n{listed}")
        st1, info1 = self.stamp(r)
        if r.inplace:                               # the stamp of an in-place rule is taken after it has run
            fixed = {k: v for k, v in info["inputs"].items() if not any(k == f"{p} ({m})" for p, m in r.inplace.items())}
            fixed1 = {k: v for k, v in info1["inputs"].items() if not any(k == f"{p} ({m})" for p, m in r.inplace.items())}
            if fixed != fixed1 or info1["code"] != info["code"]:
                raise BuildError(f"rule {r.name}: its inputs or code changed while it ran; run it again")
            st0, info = st1, info1
        elif st1 != st0:
            raise BuildError(f"rule {r.name}: its inputs or code changed while it ran; run it again")
        outs = self.output_hashes(r)
        missing = [o for o, h in outs.items() if h is None]
        if missing:
            raise BuildError(f"rule {r.name} did not write its declared outputs: {', '.join(missing)}")
        entry = {"stamp": st0, "code": info["code"], "params": info["params"], "inputs": info["inputs"], "outputs": outs}
        if r.is_check:
            entry["result"] = result
            if message:
                entry["message"] = message[:2000]
        self.lock_of(r.name).set(r.name, entry)
        self.lock_of(r.name).save()
        if self._details.get(r.name):
            import json
            self.details_dir.mkdir(parents=True, exist_ok=True)
            (self.details_dir / f"{r.name}.json").write_text(json.dumps(self._details[r.name]))
        self.hasher.save()
        log(f"  {r.name}: {result if r.is_check else 'done'} in {time.time() - t0:.1f} s" + (f" ({message})" if message else ""))
        return result == "passed"


def explain_change(old, new, details=None):
    """Why a stamp changed, in words: which inputs, parameters, functions or distributions differ from the lock.
    details: {"old": {pattern: {file: hash}}, "new": {...}} for the glob inputs, when the local cache has them."""
    out = []
    oi, ni = old.get("inputs", {}), new["inputs"]
    for k in sorted(set(oi) | set(ni)):
        if k not in oi:
            out.append(f"new input {k}")
        elif k not in ni:
            out.append(f"input {k} no longer matched")
        elif oi[k] != ni[k]:
            out.append(f"input {k} changed" if ni[k] is not None else f"input {k} is missing")
            if details and k in details.get("old", {}) and k in details.get("new", {}):
                o, n = details["old"][k], details["new"][k]
                ch = sorted(f for f in set(o) | set(n) if o.get(f) != n.get(f))
                out[-1] += f" ({len(ch)} files: " + ", ".join(ch[:3]) + (", …" if len(ch) > 3 else "") + ")"
    op, np_ = old.get("params", {}), new["params"]
    for k in sorted(set(op) | set(np_)):
        if op.get(k) != np_.get(k):
            out.append(f"parameter {k}: {op.get(k)!r} -> {np_.get(k)!r}")
    oc, nc = old.get("code", {}), new["code"]
    opart, npart = oc.get("parts", {}), nc["parts"]
    for k in sorted(set(opart) | set(npart)):
        if opart.get(k) != npart.get(k):
            out.append(f"code {k} " + ("added" if k not in opart else "removed" if k not in npart else "changed"))
    oeff, neff = oc.get("effects", {}), nc["effects"]
    for k in sorted(set(oeff) | set(neff)):
        if oeff.get(k) != neff.get(k):
            out.append(f"module {k} " + ("now used" if k not in oeff else "no longer used" if k not in neff
                                         else "changed its module-level statements"))
    oe, ne = oc.get("env", {}), nc["env"]
    if oe.get("python") != ne.get("python"):
        out.append(f"Python {oe.get('python')} -> {ne.get('python')}")
    od, nd = oe.get("dists", {}), ne.get("dists", {})
    for k in sorted(set(od) | set(nd)):
        if od.get(k) != nd.get(k):
            a, b = od.get(k), nd.get(k)
            out.append(f"package {k}: " + (f"{a['version']} -> {b['version']}" if a and b and a["version"] != b["version"]
                                            else "added" if not a else "removed" if not b else "installed files changed"))
    return out or ["stamp changed"]
