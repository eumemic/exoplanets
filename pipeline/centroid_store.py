"""Per-sector centroid measurements (centroid_sectors.py) in the store (store.py), kind centroid: one entry per signal
and measurement, with the signal row it was measured with (ephemeris, sectors requested, position), the measurement
file, and the TIC stars within 2' with their TIC dispositions (looked up once, when the batch came in, so that TIC
artifacts and duplicates are never taken for stars).

The batches measured before the store (results_public/products/centroid_batches.csv) are imported as legacy entries:
they did not record the code, the packages or the cutouts. They keep their batch order (seq); each signal key's entry
with the highest seq is used (centroid_table.py).

New measurements come from cloud batches (cloud.py plan --centroids): their request holds the signal (position,
ephemeris, sectors), the code of centroid_sectors.py and the packages; the TIC dispositions of the stars near the target
are looked up from MAST when the measurement is ingested.

Usage: python centroid_store.py import
"""
import csv
import json
import os
import sys

import store as st

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results_cloud")
BATCHES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results_public", "products", "centroid_batches.csv")


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def import_batch(store, results_root, batch, order):
    d = os.path.join(results_root, batch)
    stars = {}
    for r in _rows(os.path.join(d, "stars.csv")):
        stars.setdefault(r["key"], []).append(r)
    n = 0
    for r in _rows(os.path.join(d, "list.csv")):
        f = os.path.join(d, "cs", f"{r['key']}.json")
        if not os.path.exists(f):
            continue
        req = dict(kind="centroid", signal_key=r["key"], tic=int(r["tic"]), signal=r, legacy=["code", "packages", "cutouts"],
                   source=dict(batch=batch, order=order))
        res = dict(seq=order, batch=batch, signal=r, stars=stars.get(r["key"], []), content=st.file_content(f))
        store.put("centroid", req, res, files={f"{r['key']}.json": f})
        n += 1
    return n


def import_batches(store, results_root=RESULTS, batches_csv=BATCHES):
    return {b["batch"]: import_batch(store, results_root, b["batch"], int(b["order"]))
            for b in sorted(_rows(batches_csv), key=lambda r: int(r["order"]))}


def latest(store):
    """{signal key: (store key, request, result)}: each signal's entry with the highest seq."""
    out = {}
    for k, (req, res, chk) in store.entries("centroid").items():
        if chk is not None and not chk.get("passed"):
            continue
        sk = req["signal_key"]
        if sk not in out or res["seq"] > out[sk][2]["seq"]:
            out[sk] = (k, req, res)
    return out


STAGE_CODE = [("centroid_sectors", None)]
LIST_COLUMNS = ["set", "tier", "tic", "P_d", "period", "t0", "duration_h", "depth_ppm", "sectors", "MES", "source_tic", "ra",
                "dec", "key"]


def code_hash(index=None):
    from dag.codehash import CodeIndex
    idx = index or CodeIndex([os.path.dirname(os.path.abspath(__file__))])
    parts, effects = {}, {}
    for m, f in STAGE_CODE:
        p, e, _ = idx.closure(m, f)
        parts.update(p)
        effects.update(e)
    return st.sha256_json({"parts": parts, "effects": effects})


def request(row, code, env):
    """row: a centroid_sectors.py list row (LIST_COLUMNS)."""
    return dict(kind="centroid", signal_key=row["key"], tic=int(row["tic"]), ra=str(row["ra"]), dec=str(row["dec"]),
                period=str(row["period"]), t0=str(row["t0"]), duration_h=str(row["duration_h"]), sectors=str(row["sectors"]),
                code=code, env=env)


def ingest_item(store, d, plan_item, batch, seq, env_lock="requirements.txt"):
    """Store one measurement of a cloud batch: d holds <key>.json and item.json (cloud_worker.py). Returns (key,
    problems)."""
    import pandas as pd
    import centroid_test
    row, info = plan_item["item"], json.load(open(os.path.join(d, "item.json")))
    problems = []
    if info["env"].get(env_lock) != plan_item["env"]:
        problems.append(f"the instance's packages do not match {env_lock}")
    if info.get("commit") != plan_item["commit"]:
        problems.append(f"code: the instance ran commit {info.get('commit')}, the plan {plan_item['commit']}")
    f = os.path.join(d, f"{row['key']}.json")
    L = pd.DataFrame([row]).astype({"tic": int, "depth_ppm": float})
    per, stars = centroid_test.load_json(L, d)
    if len(stars):
        stars = centroid_test.add_dispositions(L, stars)
    stars_rows = [{k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()} for r in
                  stars.astype(object).where(stars.notna(), "").to_dict("records")] if len(stars) else []
    res = dict(seq=seq, batch=batch, signal={k: str(v) for k, v in row.items()}, stars=stars_rows,
               content=st.file_content(f))
    key = store.put("centroid", plan_item["request"], res, check=dict(passed=not problems, problems=problems),
                    files={f"{row['key']}.json": f})
    return key, problems


def main():
    if sys.argv[1:] != ["import"]:
        sys.exit(__doc__)
    s = st.Store()
    for b, n in import_batches(s).items():
        print(f"{b}: {n} measurements")


if __name__ == "__main__":
    main()
