"""What a rule's function receives: its declared inputs, outputs and parameters. Asking for anything undeclared is
an error, so the declarations, which decide when the rule reruns, cannot drift from what the rule uses.

This module is part of every rule's code hash: a change here can change any rule's output."""
import fnmatch
from pathlib import Path

GLOB = set("*?[")


def is_glob(p):
    return any(c in GLOB for c in p)


def _match(pat, parts):
    if not pat:
        return not parts
    if pat[0] == "**":
        return any(_match(pat[1:], parts[i:]) for i in range(len(parts) + 1))
    return bool(parts) and fnmatch.fnmatchcase(parts[0], pat[0]) and _match(pat[1:], parts[1:])


def match(pattern, rel):
    """True if the glob pattern matches the relative path as Path.glob would: a wildcard stays within one component of
    the path, and ** stands for any number of components."""
    return _match(pattern.rstrip("/").split("/"), rel.split("/"))


def covers(pattern, rel):
    """True if a declared path or pattern covers the relative path: the same path, a match of the pattern, or a path
    inside a declared directory or inside a directory the pattern matches."""
    if is_glob(pattern):
        parts = rel.split("/")
        return any(match(pattern, "/".join(parts[:i])) for i in range(len(parts), 0, -1))
    return rel == pattern or rel.startswith(pattern.rstrip("/") + "/")


def overlap(a, b):
    """True if two declared paths or patterns can name the same file, or one can lie inside the other. Two components
    that both have wildcards are taken to overlap, so the answer errs towards True."""
    for x, y in zip(a.rstrip("/").split("/"), b.rstrip("/").split("/")):
        if x == "**" or y == "**":
            return True
        gx, gy = is_glob(x), is_glob(y)
        if gx and gy:
            continue
        if (gx and not fnmatch.fnmatchcase(y, x)) or (gy and not fnmatch.fnmatchcase(x, y)) or (not gx and not gy and x != y):
            return False
    return True


def base(pattern):
    """The directory above a pattern's first component with a wildcard (the pattern itself if it has none)."""
    parts = pattern.rstrip("/").split("/")
    if is_glob(pattern):
        parts = parts[:next(i for i, x in enumerate(parts) if is_glob(x))]
    return "/".join(parts)


class RunContext:
    def __init__(self, root, rule, params, outputs=None):
        self.root = Path(root)
        self.rule = rule
        self._params = params
        self._outputs = outputs or {o: self.root / o for o in rule.outputs}

    def input(self, rel):
        """The absolute path of a declared input (a file, a directory, or a file matched by a declared pattern)."""
        if not any(covers(p, rel) for p in self.rule.inputs):
            raise KeyError(f"rule {self.rule.name}: {rel} is not a declared input")
        return self.root / rel

    def inputs(self, pattern):
        """The files matching a declared glob pattern, sorted."""
        if pattern not in self.rule.inputs:
            raise KeyError(f"rule {self.rule.name}: {pattern} is not a declared input pattern")
        return sorted(self.root.glob(pattern))

    def output(self, rel):
        """The absolute path of a declared output, or of a path inside an output directory or matched by an output
        pattern. Its parent directory is created."""
        if rel in self._outputs:
            p = self._outputs[rel]
        elif any(covers(o, rel) for o in self.rule.outputs):
            p = self.root / rel
        else:
            raise KeyError(f"rule {self.rule.name}: {rel} is not a declared output")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def params(self):
        """All declared parameters, {dotted key: value}."""
        return dict(self._params)

    def param(self, key):
        if key not in self._params:
            raise KeyError(f"rule {self.rule.name}: parameter {key} is not declared")
        return self._params[key]
