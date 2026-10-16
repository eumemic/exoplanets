"""Results of the expensive per-item stages, stored under the hash of what determines them (the request).

An entry is ROOT/<kind>/<key[:2]>/<key>/ with
- request.json: what determines the result: the contents of the inputs (hashes of the files or rows they come from,
  not the keys of the stages that made them, so an earlier stage that reruns and comes out the same changes nothing
  after it), the parameters, the code (dag.codehash, the functions the stage runs), the packages and the seed. The key
  is the SHA-256 of its canonical JSON. A legacy entry, imported from a batch that did not keep all of its inputs, has
  "legacy": [the inputs it lacks] and "source": where it came from; it is used while the inputs it records are current.
- result.json: what later stages and the catalog read, with "content", the hash of the entry's canonical content
  (for a fold, its arrays), which later requests cite;
- check.json: the stage's checks and whether they passed (a failing entry is kept for diagnosis and never used);
- the files.
Entries are written once: putting a different result under an existing key is an error, and the same result (the same
"content", whatever else differs, such as where the large files are kept or when the entry came in) is a no-op. Writes go to a temporary directory that is renamed into place, so an interrupted write leaves nothing.
Batch ingest writes the store (tri_store.py); the build's rules only read it.
"""
import json
import os
import shutil
import tempfile

import numpy as np

from dag.hashing import canonical_json, sha256_bytes, sha256_json

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results_cloud", "store")


def key_of(request):
    return sha256_json(request)


def npz_content(path):
    """Hash of a .npz file's arrays (names, dtypes, shapes and bytes), independent of the zip container's metadata."""
    with np.load(path, allow_pickle=False) as d:
        return sha256_json([[k, str(d[k].dtype), list(d[k].shape), sha256_bytes(np.ascontiguousarray(d[k]).tobytes())]
                            for k in sorted(d.files)])


def file_content(path):
    with open(path, "rb") as fh:
        return sha256_bytes(fh.read())


class Store:
    def __init__(self, root=ROOT):
        self.root = os.path.abspath(root)

    def path(self, kind, key):
        return os.path.join(self.root, kind, key[:2], key)

    def has(self, kind, key):
        return os.path.exists(os.path.join(self.path(kind, key), "result.json"))

    def get(self, kind, key):
        """(request, result, check) of an entry, or None."""
        d = self.path(kind, key)
        if not os.path.exists(os.path.join(d, "result.json")):
            return None
        out = []
        for f in ("request.json", "result.json", "check.json"):
            p = os.path.join(d, f)
            out.append(json.load(open(p)) if os.path.exists(p) else None)
        return tuple(out)

    def put(self, kind, request, result, check=None, files=None):
        """Store an entry; files: {name in the entry: source path}. Returns the key."""
        if request.get("kind") != kind:
            raise ValueError(f"request kind {request.get('kind')!r} is not {kind!r}")
        key = key_of(request)
        d = self.path(kind, key)
        if os.path.exists(d):
            old = self.get(kind, key)
            same = old is not None and (canonical_json(old[1]) == canonical_json(result) or (
                old[1].get("content") is not None and old[1].get("content") == result.get("content")))
            if not same:
                raise ValueError(f"{kind} {key[:12]}: a different result is already stored for this request")
            return key                              # the same content (where it is stored or when it came in may differ)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        tmp = tempfile.mkdtemp(prefix=f".{key[:12]}-", dir=os.path.dirname(d))
        try:
            for name, src in (files or {}).items():
                shutil.copyfile(src, os.path.join(tmp, name))
            for name, obj in (("request.json", request), ("result.json", result), ("check.json", check)):
                if obj is not None:
                    with open(os.path.join(tmp, name), "w") as fh:
                        fh.write(canonical_json(obj) + "\n")
            os.rename(tmp, d)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        return key

    def keys(self, kind):
        base = os.path.join(self.root, kind)
        if not os.path.isdir(base):
            return []
        return sorted(k for p in os.listdir(base) if len(p) == 2 for k in os.listdir(os.path.join(base, p))
                      if not k.startswith("."))

    def entries(self, kind):
        """{key: (request, result, check)} of every entry of a kind."""
        return {k: self.get(kind, k) for k in self.keys(kind)}
