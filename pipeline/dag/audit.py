"""Catch a rule reading or writing files it did not declare.

Python reports every open(), os.open(), os.listdir(), os.scandir() and glob.glob() to audit hooks (PEP 578). While a
rule runs, the hook checks each path against the rule's declarations:
- reading inside the repository requires a declared input or one of the rule's outputs;
- reading outside it is allowed only from the Python installation and system and cache directories (fonts, time zones,
  matplotlib and astropy caches) or from the rule's `allow_reads`; a file in a temporary directory may be read only
  if the rule wrote it in the same run, since a file left there earlier is exactly the kind of hidden input this
  exists to catch;
- writing is allowed only to declared outputs (files, directories, or the paths an output pattern matches, and
  temporary files next to them) and to the system temporary directory.
Files read by compiled code that bypasses Python's file functions (for example pyarrow reading Parquet) are not seen.
"""
import os
import sys
import tempfile
from pathlib import Path

from .context import base, covers, is_glob

_ACTIVE = None
_INSTALLED = False
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
HOME = str(Path.home())
SYSTEM_READ = ["/dev/", "/proc/", "/sys/", "/System/", "/Library/", "/usr/", "/etc/", "/private/etc/",
               "/private/var/db/", "/opt/homebrew/", "/var/db/"]
CACHE_DIRS = [f"{HOME}/.matplotlib", f"{HOME}/.cache", f"{HOME}/.config/matplotlib", f"{HOME}/.astropy",
              f"{HOME}/Library/Caches", f"{HOME}/Library/Fonts", f"{HOME}/.local/share/fonts"]
INTERNAL = (".venv", ".venv-trice", ".git", ".dag-cache")


def _hook(event, args):
    w = _ACTIVE
    if w is None or w.busy:
        return
    w.busy = True
    try:
        if event == "open":
            path, mode, flags = args
            if isinstance(path, (str, bytes, os.PathLike)):
                writing = (mode is not None and any(c in str(mode) for c in "wax+")) or bool((flags or 0) & WRITE_FLAGS)
                w.access(os.fsdecode(path), "write" if writing else "read")
        elif event in ("os.listdir", "os.scandir"):
            if args and isinstance(args[0], (str, bytes, os.PathLike)):
                w.listing(os.fsdecode(args[0]))
        elif event == "glob.glob":
            w.listing(os.path.dirname(os.fsdecode(args[0])) or ".")
        elif event in ("os.remove", "os.rmdir", "shutil.rmtree", "os.mkdir"):
            if args and isinstance(args[0], (str, bytes, os.PathLike)):
                w.access(os.fsdecode(args[0]), "mkdir" if event == "os.mkdir" else "write")
        elif event in ("os.rename", "shutil.move", "shutil.copyfile"):
            for x in args[:2]:
                if isinstance(x, (str, bytes, os.PathLike)):
                    w.access(os.fsdecode(x), "write" if x is args[1] or event != "shutil.copyfile" else "read")
    finally:
        w.busy = False


def install():
    global _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED = True


class Watch:
    def __init__(self, root, rule, input_patterns, output_patterns, code_dirs=()):
        self.root = os.path.realpath(root)
        self.code_dirs = [os.path.realpath(c) for c in code_dirs]       # Python lists these when it imports
        self.rule = rule
        self.inputs = list(input_patterns)
        self.outputs = [o.rstrip("/") for o in output_patterns]       # relative to the root; files, directories, patterns
        self.written = set()
        self.violations = []
        self.busy = False
        tmp = os.path.realpath(tempfile.gettempdir())
        prefixes = {os.path.realpath(p) for p in (sys.prefix, sys.base_prefix, sys.exec_prefix)}
        # a file in the temporary directory may be read only if this run wrote it
        self.read_ok_prefixes = [*prefixes, *SYSTEM_READ, *CACHE_DIRS]
        self.write_ok_prefixes = [tmp, *CACHE_DIRS, "/dev/null"]
        self.allow = [a if os.path.isabs(a) else os.path.join(self.root, a) for a in getattr(rule, "allow_reads", ())]

    def __enter__(self):
        global _ACTIVE
        install()
        _ACTIVE = self
        return self

    def __exit__(self, *exc):
        global _ACTIVE
        _ACTIVE = None
        return False

    def _rel(self, p):
        if p == self.root:
            return ""
        if p.startswith(self.root + os.sep):
            return p[len(self.root) + 1:]
        return None

    def _output(self, rel):
        """rel is an output, lies inside one or is matched by an output pattern, or is a temporary file next to an
        output file."""
        return rel is not None and any(covers(o, rel) or (not is_glob(o) and rel.startswith(o + ".")) for o in self.outputs)

    def access(self, path, kind):
        p = os.path.realpath(os.path.join(os.getcwd(), path))
        rel = self._rel(p)
        if kind in ("write", "mkdir"):
            parent = kind == "mkdir" and rel is not None and any(
                rel == "" or base(o) == rel or base(o).startswith(rel + "/") for o in self.outputs)
            if parent or self._output(rel) or (rel is None and self._under(p, self.write_ok_prefixes)):
                self.written.add(p)
                return
            self.violations.append(("write", p))
            return
        if p in self.written or self._output(rel):
            return
        if rel is not None:
            if rel.split(os.sep)[0] in INTERNAL or "__pycache__" in rel or rel.endswith(".py"):
                return                                       # Python internals; code is hashed separately
            if any(covers(pat, rel) for pat in self.inputs):
                return
        elif self._under(p, self.read_ok_prefixes):
            return
        if any(p == a or p.startswith(a.rstrip("/") + "/") for a in self.allow):
            return
        self.violations.append(("read", p))

    def listing(self, path):
        p = os.path.realpath(os.path.join(os.getcwd(), path))
        rel = self._rel(p)
        if rel is None or rel.split(os.sep)[0] in INTERNAL or "__pycache__" in rel or self._under(p, self.code_dirs):
            return
        for pat in self.inputs:
            b = base(pat)
            if rel == "" or rel == b or rel.startswith(b + "/") or b.startswith(rel + "/"):
                return
        # an output directory, a directory inside one, or the directory in which an output pattern finds its paths
        if self._output(rel) or any(is_glob(o) and base(o) == rel for o in self.outputs):
            return
        self.violations.append(("list", p))

    @staticmethod
    def _under(p, prefixes):
        return any(p == x.rstrip("/") or p.startswith(x.rstrip("/") + "/") for x in prefixes)
