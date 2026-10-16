"""TRICERATOPS results in the store (store.py), by stage:

- fold (one signal): the single-cadence light curve TRICERATOPS models (export_fold.py), from the ephemeris, the masks
  of the star's other signals, the light curves and the binning;
- tri_setup (one star, its sectors and the signal's depth): the target object (fpp_core.setup_target) with its
  field-star population, the TIC stars within 30" and the FFI cutouts of the field;
- molusc (one star): the simulated bound companions that Gaia does not rule out (molusc_batch.py);
- tri (one signal): the runs with the default priors and, where the star has MOLUSC survivors, with the Gaia limits,
  each seeded from the signal's key, the mode and the run number (fpp_pool.py).
A tri request cites the content of the fold, setup and MOLUSC entries it used, not their keys, so an earlier stage that
is redone and comes out the same leaves the runs current.

The batches run before the store (results_public/products/triceratops_batches.csv) are imported as legacy entries:
their requests record the signal, ephemeris, masks, drops, depth and sectors they ran with, but not the light curves,
the code, or (for all but the last batch) the field-star population and the MOLUSC file, which were not kept. They
keep their place in the batch order (`seq`), so the selection is the one the batches gave: for each signal key, the
entry with the highest seq.

Usage: python tri_store.py import     (legacy import of every batch in triceratops_batches.csv; entries already
                                       present are left as they are)
"""
import csv
import glob
import json
import os
import sys

import store as st

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results_cloud")
BATCHES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results_public", "products", "triceratops_batches.csv")
LEGACY_NOT_KEPT = ["lightcurves", "code", "packages", "star", "cutouts"]


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def _masks(s):
    return sorted([float(x) for x in m.split(",")] for m in (s or "").split(";") if m and m != "nan")


def _signal(r):
    return dict(tic=int(r["tic"]), period=r["period"], t0_btjd=r["t0"], duration_h=r["duration_h"],
                depth_ppm=r["depth_ppm"], masks=r.get("masks", "") or "", drop=r.get("drop", "") or "")


def import_batch(store, results_root, batch, order):
    """Legacy entries for every result of one batch directory; returns the number of tri entries."""
    d = os.path.join(results_root, batch)
    lst = {r["key"]: r for r in _rows(os.path.join(d, "list.csv"))}
    jobs = {r["key"]: r for r in _rows(os.path.join(d, "jobs.csv"))}
    runs = {}
    with open(os.path.join(d, "runs.jsonl")) as fh:
        for line in fh:
            r = json.loads(line)
            runs.setdefault(r["key"], []).append(r)
    n = 0
    for f in sorted(glob.glob(os.path.join(d, "*_fpp.json"))):
        key = os.path.basename(f)[:-9]
        tic = int(key[3:].split("_P")[0])
        with open(f) as fh:
            j = json.load(fh)
        sig = _signal(lst[key]) if key in lst else None
        source = {"batch": batch, "order": order}
        legacy = list(LEGACY_NOT_KEPT)
        # fold
        fold_npz = os.path.join(d, "folds", f"{key}.npz")
        fold = None
        if os.path.exists(fold_npz):
            req = dict(kind="fold", signal_key=key, tic=tic, signal=sig, legacy=legacy + ["binning"], source=source)
            fold_res = dict(content=st.npz_content(fold_npz), exptime_min=j.get("exptime_min"), n_points=j.get("n_points"),
                            sectors=j.get("sectors"))
            fold = dict(key=store.put("fold", req, fold_res, files={"fold.npz": fold_npz}), content=fold_res["content"])
        # target setup, with its field-star population where the batch kept it
        setup = None
        job = jobs.get(key)
        if job:
            secs = job["sectors"]
            pkl = os.path.join(d, "states", f"{tic}_{secs.replace(',', '-')}.pkl")
            pops = sorted(glob.glob(os.path.join(d, "cache", str(tic), "*gaia_background.csv")))
            if os.path.exists(pkl):
                files = {"state.pkl": pkl, **({"population.csv": pops[0]} if pops else {})}
                content = st.sha256_json([st.file_content(p) for p in files.values()])
                req = dict(kind="tri_setup", tic=tic, sectors=secs, depth_ppm=job["depth_ppm"], nearby_max_arcsec=30,
                           legacy=legacy + ([] if pops else ["population"]), source=source)
                setup = dict(key=store.put("tri_setup", req, dict(content=content, population=bool(pops)), files=files),
                             content=content)
        # MOLUSC survivors, where the batch kept them
        molusc = None
        kept = os.path.join(d, "molusc", f"tic{tic}_kept.csv.gz")
        if os.path.exists(kept):
            meta = os.path.join(d, "molusc", f"tic{tic}_molusc.json")
            info = json.load(open(meta)) if os.path.exists(meta) else {}
            req = dict(kind="molusc", tic=tic, draws=200000, legacy=["gaia", "seed", "code", "packages"], source=source)
            res = dict(content=st.file_content(kept), survivors=info.get("survivors", j.get("molusc_survivors")), info=info)
            molusc = dict(key=store.put("molusc", req, res, files={"molusc.csv.gz": kept}), content=res["content"])
        # the runs
        missing = [x for x, v in (("fold", fold), ("setup", setup)) if v is None]
        if "FPP_m_mean" in j and molusc is None:
            missing.append("molusc")
        req = dict(kind="tri", signal_key=key, tic=tic, signal=sig, fold=fold and fold["content"],
                   setup=setup and setup["content"], molusc=molusc and molusc["content"], runs=j.get("runs"),
                   draws=j.get("draws"), legacy=legacy + missing, source=source)
        res = dict(seq=order, batch=batch, fold_key=fold and fold["key"], setup_key=setup and setup["key"],
                   molusc_key=molusc and molusc["key"], fpp=j, runs=runs.get(key, []))
        store.put("tri", req, res, files={"fpp.json": f})
        n += 1
    return n


def import_batches(store, results_root=RESULTS, batches_csv=BATCHES):
    out = {}
    for b in sorted(_rows(batches_csv), key=lambda r: int(r["order"])):
        out[b["batch"]] = import_batch(store, results_root, b["batch"], int(b["order"]))
    return out


def latest(store):
    """{signal key: (store key, request, result)}: each signal's entry with the highest seq (batch order)."""
    out = {}
    for k, (req, res, _) in store.entries("tri").items():
        sk = req["signal_key"]
        if sk not in out or res["seq"] > out[sk][2]["seq"]:
            out[sk] = (k, req, res)
    return out


def main():
    if sys.argv[1:] != ["import"]:
        sys.exit(__doc__)
    s = st.Store()
    for b, n in import_batches(s).items():
        print(f"{b}: {n} results")


if __name__ == "__main__":
    main()
