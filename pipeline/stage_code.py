"""The code and packages of each stored stage, so that a stored result made by other code is out of date.

results_public/products/stage_code.json (rule stage_code) holds, for each kind of stored result (fold, tri_setup, molusc,
tri, fit, centroid), a short hash of the stage's code now (dag.codehash: the functions it runs, traced through imports)
and of the lock file of its packages. Each result table records the same hashes for the result in use (column code of
triceratops.csv, fits.csv and centroids.csv, "kind=hash" joined by spaces; empty for a legacy result, which did not
record its code). A result is out of date when a stage of it has another hash now: tri_plan.py lists such TRICERATOPS
results as pending, and the checks fits_current and centroid_inputs_current fail on fits and centroid measurements.
"""
import json
import os

from dag.hashing import sha256_json

PIPE = os.path.dirname(os.path.abspath(__file__))
KINDS = ("fold", "tri_setup", "molusc", "tri", "fit", "centroid", "molusc_sample")


def short(code, env):
    return sha256_json([code, env])[:12]


def current():
    """{kind: short hash} of the code and packages now."""
    import centroid_store
    import fit_store
    import tri_store
    from dag.codehash import CodeIndex
    idx = CodeIndex([PIPE])
    out = {k: short(tri_store.code_hash(k, idx), tri_store.env_hash(k)) for k in tri_store.STAGE_CODE}
    out["fit"] = short(fit_store.code_hash(idx), tri_store.env_hash("fold"))
    out["centroid"] = short(centroid_store.code_hash(idx), tri_store.env_hash("fold"))
    return out


def write(out_json):
    with open(out_json, "w") as fh:
        json.dump(current(), fh, indent=1, sort_keys=True)
        fh.write("\n")


def of_requests(reqs):
    """The code column of a result: reqs is {kind: request} of its stages; "" if any of them did not record its code."""
    if not reqs or any(r is None or r.get("legacy") or "code" not in r for r in reqs.values()):
        return ""
    return " ".join(f"{k}={short(r['code'], r['env'])}" for k, r in sorted(reqs.items()))


def changed(code, now):
    """The stages of a code column whose code or packages differ from now ({kind: short hash})."""
    return sorted(k for k, v in (x.split("=", 1) for x in (code or "").split()) if now.get(k) != v)
