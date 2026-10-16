"""What a rule's function receives: its declared inputs, outputs and parameters. Asking for anything undeclared is
an error, so the declarations, which decide when the rule reruns, cannot drift from what the rule uses.

This module is part of every rule's code hash: a change here can change any rule's output."""
import fnmatch
from pathlib import Path

GLOB = set("*?[")


def is_glob(p):
    return any(c in GLOB for c in p)


def covers(pattern, rel):
    """True if a declared input pattern covers the relative path: the same path, a path inside a declared directory,
    or a match of a glob pattern."""
    if is_glob(pattern):
        return fnmatch.fnmatchcase(rel, pattern)
    return rel == pattern or rel.startswith(pattern.rstrip("/") + "/")


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
        if rel not in self._outputs:
            raise KeyError(f"rule {self.rule.name}: {rel} is not a declared output")
        p = self._outputs[rel]
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def params(self):
        """All declared parameters, {dotted key: value}."""
        return dict(self._params)

    def param(self, key):
        if key not in self._params:
            raise KeyError(f"rule {self.rule.name}: parameter {key} is not declared")
        return self._params[key]
