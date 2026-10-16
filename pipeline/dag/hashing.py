"""Content hashes: files, directories and JSON-like values, all as sha256 hex digests.

File hashes are cached by (size, mtime_ns), so a status check over many large files reads only the ones that changed.
The cache is a plain JSON file outside version control; a stale or missing cache only costs time, never correctness,
because an entry is used only when the file's size and modification time still match it.
"""
import hashlib
import json
import math
import os
from pathlib import Path


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _canon(x):
    """A JSON-compatible copy of x with a single spelling for each value: dict keys sorted, tuples as lists, floats
    in their shortest round-trip form, and NaN and infinities as tagged objects (JSON has no form for them, and a
    plain string would collide with the string "nan")."""
    if isinstance(x, dict):
        return {str(k): _canon(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple)):
        return [_canon(v) for v in x]
    if isinstance(x, bool) or x is None or isinstance(x, (int, str)):
        return x
    if isinstance(x, float):
        return x if math.isfinite(x) else {"__float__": repr(x)}
    if hasattr(x, "tolist"):          # numpy scalars and arrays
        return _canon(x.tolist())
    raise TypeError(f"cannot hash a value of type {type(x).__name__}")


def canonical_json(x):
    return json.dumps(_canon(x), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(x):
    return sha256_bytes(canonical_json(x).encode())


class FileHasher:
    """sha256 of file contents, with a cache keyed by path, size and mtime_ns."""

    def __init__(self, cache_path=None):
        self.cache_path = Path(cache_path) if cache_path else None
        self.cache, self.dirty = {}, False
        if self.cache_path and self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text())
            except (OSError, ValueError):
                self.cache = {}

    def file(self, path):
        p = Path(path)
        st = p.stat()
        key = str(p.resolve())
        hit = self.cache.get(key)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
            return hit[2]
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        d = h.hexdigest()
        self.cache[key] = [st.st_size, st.st_mtime_ns, d]
        self.dirty = True
        return d

    def dir(self, path):
        """Hash of a directory tree: its files' relative paths and contents, in sorted order."""
        root = Path(path)
        entries = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for f in sorted(filenames):
                fp = Path(dirpath) / f
                entries.append([fp.relative_to(root).as_posix(), self.file(fp)])
        return sha256_json(entries)

    def path(self, path):
        """The file or directory hash, or None if the path does not exist."""
        p = Path(path)
        if p.is_dir():
            return self.dir(p)
        if p.exists():
            return self.file(p)
        return None

    def save(self):
        if self.cache_path and self.dirty:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cache))
            os.replace(tmp, self.cache_path)
            self.dirty = False
