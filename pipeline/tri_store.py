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
    """{signal key: (store key, request, result)}: each signal's entry with the highest seq (batch order, then ingest
    time), among those whose checks passed (a legacy entry has none: the table's own checks apply)."""
    out = {}
    for k, (req, res, chk) in store.entries("tri").items():
        if chk is not None and not chk.get("passed"):
            continue
        sk = req["signal_key"]
        if sk not in out or res["seq"] > out[sk][2]["seq"]:
            out[sk] = (k, req, res)
    return out


# requests of new runs ------------------------------------------------------------------------------------------------
PIPE = os.path.dirname(os.path.abspath(__file__))
# the code each stage runs, as (module, function or None for the whole module) in pipeline/
STAGE_CODE = {
    "fold": [("export_fold", None), ("fpp_fleet", "fold")],
    "tri_setup": [("fpp_core", "setup_target"), ("fpp_pool", "_setup_one"), ("fpp_pool", "setup"), ("fpp_fleet", "cutouts"),
                  ("s3cut", "cut")],
    "molusc": [("molusc_batch", "one"), ("molusc_batch", "main")],
    "tri": [("fpp_pool", "_run_one"), ("fpp_pool", "run"), ("fpp_pool", "merge"), ("fpp_pool", "mean_probs")],
}
LOCKS = {"fold": "requirements.txt", "tri_setup": "requirements-triceratops.txt", "molusc": "requirements.txt",
         "tri": "requirements-triceratops.txt"}
SEED_RULE = "numpy seed = first 4 bytes (little-endian) of sha256('<key>|<mode>|<k>|stock')"


def code_hash(kind, index=None):
    """The hash of the functions a stage runs (dag.codehash: comments and docstrings do not count)."""
    from dag.codehash import CodeIndex
    idx = index or CodeIndex([PIPE])
    parts, effects = {}, {}
    for m, f in STAGE_CODE[kind]:
        p, e, _ = idx.closure(m, f)
        parts.update(p)
        effects.update(e)
    return st.sha256_json({"parts": parts, "effects": effects})


def env_hash(kind):
    """The packages: the hash of the lock file the instance's environment is checked against."""
    return st.file_content(os.path.join(PIPE, "..", LOCKS[kind]))


def fold_request(item, lightcurves, code, env, phase_bin_min=2.0):
    """item: a signal-list row (key, tic, period, t0, duration_h, masks); lightcurves: [[sector, uri], ...] of the star."""
    return dict(kind="fold", signal_key=item["key"], tic=int(item["tic"]),
                signal=dict(period=str(item["period"]), t0_btjd=str(item["t0"]), duration_h=str(item["duration_h"]),
                            masks=str(item.get("masks") or "")),
                cadence="single", phase_bin_min=phase_bin_min, lightcurves=sorted(lightcurves), code=code, env=env)


def molusc_request(tic, gaia_row, mass, molusc_code, code, env, draws=200000):
    """gaia_row: the Gaia DR3 columns MOLUSC reads (molusc_batch.GAIA_COLS); molusc_code: hash of MOLUSC's files."""
    import molusc_batch
    return dict(kind="molusc", tic=int(tic), gaia={k: gaia_row[k] for k in molusc_batch.GAIA_COLS}, mass=float(mass),
                draws=draws, seed=molusc_batch.molusc_seed(tic), molusc=molusc_code, code=code, env=env)


def setup_request(tic, sectors, depth_ppm, cutouts, code, env):
    """The target setup: TRICERATOPS queries the TIC around the star and the field-star population when it is set up,
    so those answers are outputs (stored with the entry), and cutouts are the trimmed FFI cutouts' content."""
    return dict(kind="tri_setup", tic=int(tic), sectors=str(sectors), depth_ppm=str(depth_ppm), nearby_max_arcsec=30,
                cutouts=cutouts, code=code, env=env)


def tri_request(item, fold, setup, molusc, runs, draws, code, env):
    return dict(kind="tri", signal_key=item["key"], tic=int(item["tic"]), depth_ppm=str(item["depth_ppm"]),
                drop=str(item.get("drop") or ""), fold=fold, setup=setup, molusc=molusc, runs=runs, draws=draws,
                seeds=SEED_RULE, code=code, env=env)


def main():
    if sys.argv[1:] != ["import"]:
        sys.exit(__doc__)
    s = st.Store()
    for b, n in import_batches(s).items():
        print(f"{b}: {n} results")


if __name__ == "__main__":
    main()


def _gz_content(path):
    import gzip
    with gzip.open(path, "rb") as fh:
        return st.sha256_bytes(fh.read())


def ingest_item(store, d, plan_item, batch, seq, n_runs=10, min_survivors=20000, phase_bin_min=2.0):
    """Store one finished item of a cloud batch (cloud.py): d is its unpacked archive (cloud_worker.py), plan_item the
    plan's entry for it (the signal row, the fold and MOLUSC requests, and the code and package hashes). Every entry is
    written; the tri entry's check.json says whether the result passed fpp_check.gate and was made with the planned
    code and packages. Returns (tri key, problems)."""
    import numpy as np
    import fpp_check
    it, info = plan_item["item"], json.load(open(os.path.join(d, "item.json")))
    problems = []
    for kind in ("fold", "tri_setup", "molusc", "tri"):
        if info["env"].get(LOCKS[kind]) != plan_item["env"][kind]:
            problems.append(f"{kind}: the instance's packages do not match {LOCKS[kind]}")
    if info.get("commit") != plan_item["commit"]:
        problems.append(f"code: the instance ran commit {info.get('commit')}, the plan {plan_item['commit']}")
    with open(os.path.join(d, "fpp.json")) as fh:
        j = json.load(fh)
    fold_npz = os.path.join(d, "fold.npz")
    fres = dict(content=st.npz_content(fold_npz), exptime_min=j.get("exptime_min"), n_points=j.get("n_points"),
                sectors=j.get("sectors"))
    fold_key = store.put("fold", plan_item["fold_request"], fres, files={"fold.npz": fold_npz})
    cuts = sorted(glob.glob(os.path.join(d, "cuts", "*.fits")))
    sfiles = {"state.pkl": os.path.join(d, "state.pkl")}
    if os.path.exists(os.path.join(d, "population.csv")):
        sfiles["population.csv"] = os.path.join(d, "population.csv")
    sfiles.update({f"cut_{os.path.basename(c)}": c for c in cuts})
    sreq = setup_request(it["tic"], info["sectors"], it["depth_ppm"], st.sha256_json([st.file_content(c) for c in cuts]),
                         plan_item["code"]["tri_setup"], plan_item["env"]["tri_setup"])
    scontent = st.sha256_json([st.file_content(sfiles[k]) for k in sorted(sfiles)])
    setup_key = store.put("tri_setup", sreq, dict(content=scontent, population="population.csv" in sfiles), files=sfiles)
    molusc = molusc_key = None
    kept = os.path.join(d, "molusc.csv.gz")
    if os.path.exists(kept) and plan_item.get("molusc_request"):
        minfo = json.load(open(os.path.join(d, "molusc.json"))) if os.path.exists(os.path.join(d, "molusc.json")) else {}
        molusc = _gz_content(kept)
        molusc_key = store.put("molusc", plan_item["molusc_request"], dict(content=molusc, survivors=minfo.get("survivors"),
                                                                          info=minfo), files={"molusc.csv.gz": kept})
    runs = [json.loads(line) for line in open(os.path.join(d, "runs.jsonl"))]
    f = np.load(fold_npz)
    found, deg = fpp_check.gate(j, runs, f["time"], int(f["cadence_s"]), it["duration_h"], n_runs, min_survivors, phase_bin_min)
    problems += found
    treq = tri_request(it, fres["content"], scontent, molusc, n_runs, j.get("draws"), plan_item["code"]["tri"],
                       plan_item["env"]["tri"])
    signal = dict(period=str(it["period"]), t0_btjd=str(it["t0"]), duration_h=str(it["duration_h"]),
                  depth_ppm=str(it["depth_ppm"]), masks=str(it.get("masks") or ""), drop=str(it.get("drop") or ""))
    res = dict(seq=seq, batch=batch, signal=signal, fold_key=fold_key, setup_key=setup_key, molusc_key=molusc_key, fpp=j,
               runs=runs, degenerate=deg)
    key = store.put("tri", treq, res, check=dict(passed=not problems, problems=problems, instance=info.get("check")),
                    files={"fpp.json": os.path.join(d, "fpp.json")})
    return key, problems
