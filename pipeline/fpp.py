"""TRICERATOPS false-positive probability (run with .venv-trice).

Usage: python fpp.py TIC FOLD.npz DEPTH_PPM [--runs N] [--draws N]
Uses a 3x3-pixel aperture centred on the target in each sector. The FPP is a Monte Carlo
estimate that scatters by tens of percent between runs (TIC 61816225: 0.012-0.065 over 14
runs), so several runs are averaged and their spread is reported.
The Gaia field-star query is the slow part of the setup (~4 min); its result is cached next to
the fold file and reused. With --state, the whole target setup is cached too (fpp_core.save_state).
The model exposure comes from the fold (export_fold.py --single-cadence writes it, with one sub-exposure per
2 minutes; older folds of every sector were modelled with 10 minutes and TRICERATOPS's default of 20
sub-exposures), unless --nsamples is given.
With --molusc, the same number of runs is repeated with TRICERATOPS's bound companions drawn from the
MOLUSC survivors (molusc_batch.py) and without the scenarios in --drop (e.g. EB,EBx2P where Gaia RVs
exclude a stellar companion eclipsing the target); these are reported as FPP_m and NFPP_m.
fpp_pool.py runs the same calculation for many signals at once.
"""
import argparse
import json
import os

import numpy as np

import fpp_core as fc

ap = argparse.ArgumentParser()
ap.add_argument("tic", type=int)
ap.add_argument("fold")
ap.add_argument("depth_ppm", type=float)
ap.add_argument("--runs", type=int, default=10)
ap.add_argument("--draws", type=int, default=200000)
ap.add_argument("--sectors", help="comma-separated subset used for the field geometry")
ap.add_argument("--cc", help="contrast curve CSV (sep_arcsec,dmag) for unresolved-companion limits")
ap.add_argument("--cc-filt", default="TESS")
ap.add_argument("--tag", default="")
ap.add_argument("--cutouts", help="directory of FFI cutouts tess-sSSSS-*.fits (from s3cut.py) to use instead of TESScut")
ap.add_argument("--gaia-vizier", action="store_true", help="query the Gaia DR3 field stars at VizieR instead of the ESA archive")
ap.add_argument("--molusc", help="MOLUSC survivors (_kept.csv) for a second set of runs with Gaia companion limits")
ap.add_argument("--drop", default="", help="comma-separated scenarios to drop in the --molusc runs")
ap.add_argument("--nearby-max-arcsec", type=float,
                help="evaluate nearby-star scenarios only for neighbours within this separation (centroid-excluded beyond)")
ap.add_argument("--nsamples", type=int, help="sub-exposures per point (default: one per 2 minutes of the fold's exposure)")
ap.add_argument("--state", help="pickle of the target setup to reuse (written if missing)")
a = ap.parse_args()
if a.cutouts:
    fc.use_local_cutouts()
if a.gaia_vizier:
    fc.use_vizier_gaia()
d = np.load(a.fold)
sectors = sorted(set(int(s) for s in d["sectors"]))
if a.sectors:
    sectors = [int(s) for s in a.sectors.split(",")]
if a.state and os.path.exists(a.state):
    target = fc.load_state(a.state)
else:
    target = fc.setup_target(a.tic, sectors, os.path.dirname(os.path.abspath(a.fold)), a.depth_ppm, cutouts=a.cutouts,
                             nearby_max_arcsec=a.nearby_max_arcsec)
    if a.state:
        fc.save_state(target, a.state)
exptime = fc.fold_exptime(d)
# folds without an exposure are the earlier all-sector folds: keep TRICERATOPS's default of 20 for them
nsamples = a.nsamples or (fc.auto_nsamples(exptime) if "exptime" in d.files else 20)
print(f"model exposure {exptime * 1440:.2f} min, {nsamples} sub-exposures per point, {len(d['time'])} points")


def runs(molusc_file=None, drop=()):
    fpps, nfpps = [], []
    for r in range(a.runs):
        f, n = fc.run_once(target, d, N=a.draws, exptime=exptime, nsamples=nsamples, molusc_file=molusc_file, drop=drop,
                           cc=a.cc, cc_filt=a.cc_filt)
        fpps.append(f); nfpps.append(n)
        print(f"run {r}{' (MOLUSC)' if molusc_file else ''}: FPP={f:.4f} NFPP={n:.2e}", flush=True)
    print(target.probs.sort_values("prob", ascending=False).head(6).to_string())
    return fpps, nfpps


fpps, nfpps = runs()
res = dict(tic=a.tic, FPP_mean=float(np.mean(fpps)), FPP_sd=float(np.std(fpps, ddof=1)) if len(fpps) > 1 else None,
           FPP_sem=float(np.std(fpps, ddof=1) / np.sqrt(len(fpps))) if len(fpps) > 1 else None,
           FPP=fpps, NFPP=nfpps, NFPP_mean=float(np.mean(nfpps)), NFPP_max=float(np.max(nfpps)), runs=a.runs, draws=a.draws,
           exptime_min=exptime * 1440, nsamples=nsamples, n_points=int(len(d["time"])))
out = a.fold.replace(".npz", f"_fpp{a.tag}.json")
with open(out, "w") as fh:            # written now so the default runs survive a failure in the MOLUSC runs
    json.dump(res, fh)
if a.molusc:
    import pandas as pd
    fc.use_molusc_reader()
    m = pd.read_csv(a.molusc)
    # TRICERATOPS keeps companions with periastron beyond 10 au and pads the rest of its N draws with q = 0
    n_used = int((m["semi-major axis(AU)"] * (1 - m["eccentricity"]) > 10).sum())
    assert n_used <= a.draws, "MOLUSC must simulate no more companions than TRICERATOPS draws"
    drop = [x for x in a.drop.split(",") if x]
    fm, nm = runs(a.molusc, drop)
    res.update(FPP_m_mean=float(np.mean(fm)), FPP_m_sem=float(np.std(fm, ddof=1) / np.sqrt(len(fm))) if len(fm) > 1 else None,
               FPP_m=fm, NFPP_m=nm, NFPP_m_mean=float(np.mean(nm)), NFPP_m_max=float(np.max(nm)), molusc_survivors=len(m),
               molusc_used=n_used, drop=drop)
print(json.dumps(res))
with open(out, "w") as fh:
    json.dump(res, fh)
