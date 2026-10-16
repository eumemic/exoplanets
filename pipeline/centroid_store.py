"""Per-sector centroid measurements (centroid_sectors.py) in the store (store.py), kind centroid: one entry per signal
and measurement, with the signal row it was measured with (ephemeris, sectors requested, position), the measurement
file, and the TIC stars within 2' with their TIC dispositions (looked up once, when the batch came in, so that TIC
artifacts and duplicates are never taken for stars).

The batches measured before the store (results_public/products/centroid_batches.csv) are imported as legacy entries:
they did not record the code, the packages or the cutouts. They keep their batch order (seq); each signal key's entry
with the highest seq is used (centroid_table.py).

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


def main():
    if sys.argv[1:] != ["import"]:
        sys.exit(__doc__)
    s = st.Store()
    for b, n in import_batches(s).items():
        print(f"{b}: {n} measurements")


if __name__ == "__main__":
    main()
