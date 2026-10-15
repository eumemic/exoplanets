"""Prepare TRICERATOPS inputs for many signals on one machine, then set up their targets (fpp_pool.py setup).

Usage: python fpp_fleet.py LIST.csv --stars STARS.parquet --out DIR [--procs 63] [--molusc DIR]
LIST columns: key, tic, period, t0 (BTJD), duration_h, depth_ppm, masks ("P,t0,dur_h;..." other signals and TOIs on
the star), drop (scenarios to drop in the MOLUSC runs, may be empty). Light curves must be downloaded first
(download.py). For each signal this writes a single-cadence fold (export_fold.py --single-cadence, 10- and 30-minute
data binned in phase to 2 minutes), cuts the FFIs of
its three most informative sectors of that cadence from the S3 cubes (s3cut.py) for the field geometry, and writes
DIR/jobs.csv for fpp_pool.py, whose `setup` it then runs; `fpp_pool.py run` follows once the MOLUSC survivors exist.
"""
import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from s3cut import cut

HERE = os.path.dirname(os.path.abspath(__file__))
TRICE_PY = os.path.join(HERE, "..", ".venv-trice", "bin", "python")
N_PIX = 22          # TRICERATOPS's cutout size: 2 * search_radius + 2 pixels
ENV = dict(os.environ, OMP_NUM_THREADS="1", NUMBA_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
# 10- and 30-minute data are binned in phase to 2 minutes: unbinned, an ultra-short-period signal has thousands of points
# and one TRICERATOPS run takes 20 minutes; bins far narrower than the exposure leave the model unchanged
PHASE_BIN_MIN = 2.0


def fold(r, out):
    path = os.path.join(out, "folds", f"{r.key}.npz")
    if not os.path.exists(path):
        masks = [m for m in str(r.masks).split(";") if m and m != "nan"]
        with open(path.replace(".npz", ".log"), "w") as log:
            subprocess.run([sys.executable, "export_fold.py", str(int(r.tic)), repr(float(r.period)), repr(float(r.t0)),
                            repr(float(r.duration_h)), path, "--single-cadence", "--phase-bin-min", str(PHASE_BIN_MIN)]
                           + (["--mask", *masks] if masks else []),
                           stdout=log, stderr=subprocess.STDOUT, env=ENV, cwd=HERE)
    if not os.path.exists(path):
        return r.key, None
    d = np.load(path)
    ranked = [int(s) for s in d["sectors_ranked"]] or sorted(set(int(s) for s in d["sectors"]))
    return r.key, ranked[:3]


def trim(path, n=50):
    """Keep the first n cadences of an FFI cutout. TRICERATOPS uses only its WCS and the mean image, and a full cutout
    holds every cadence of the sector (about 90 MB for 200-second sectors)."""
    from astropy.io import fits
    with fits.open(path) as h:
        if len(h[1].data) <= n:
            return
        h[1].data = h[1].data[:n]
        h.writeto(path + ".tmp", overwrite=True)
    os.replace(path + ".tmp", path)


def cutouts(job):
    tic, ra, dec, want, out = job
    cdir = os.path.join(out, "cuts", f"tic{tic}")
    for attempt in range(3):          # S3 reads fail now and then when many cutouts run at once
        try:
            files = cut(tic, ra, dec, N_PIX, cdir, set(want))
            for f in files:
                trim(f)
            return tic, {int(os.path.basename(f)[6:10]) for f in files}
        except Exception as ex:
            print(f"cutouts {tic} attempt {attempt + 1} failed: {ex!r}", flush=True)
            time.sleep(15 * (attempt + 1))
    return tic, set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("list")
    ap.add_argument("--stars", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--molusc", default="", help="directory where molusc_batch.py writes tic<TIC>_kept.csv.gz")
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)
    os.makedirs(os.path.join(a.out, "folds"), exist_ok=True)
    lst = pd.read_csv(a.list, dtype={"masks": str, "drop": str}, keep_default_na=False)
    stars = pd.read_parquet(a.stars).set_index("ID")
    t0 = time.time()
    with ThreadPoolExecutor(a.procs) as ex:
        geo = dict(ex.map(lambda r: fold(r, a.out), lst.itertuples()))
    ok = {k: v for k, v in geo.items() if v}
    print(f"folds: {len(ok)} of {len(lst)} ({time.time() - t0:.0f} s)", flush=True)
    want = {}
    for r in lst.itertuples():
        if r.key in ok:
            want.setdefault(int(r.tic), set()).update(ok[r.key])
    t0 = time.time()
    with ThreadPoolExecutor(min(a.procs, 32)) as ex:
        have = dict(ex.map(cutouts, [(t, float(stars.loc[t, "ra"]), float(stars.loc[t, "dec"]), sorted(w), a.out)
                                     for t, w in want.items()]))
    print(f"cutouts: {sum(bool(v) for v in have.values())} of {len(want)} stars ({time.time() - t0:.0f} s)", flush=True)
    jobs = []
    for r in lst.itertuples():
        if r.key not in ok:
            continue
        secs = [s for s in ok[r.key] if s in have.get(int(r.tic), set())]
        if not secs:
            print(f"{r.key}: no cutouts for sectors {ok[r.key]}", flush=True)
            continue
        jobs.append(dict(key=r.key, tic=int(r.tic), fold=os.path.join(a.out, "folds", f"{r.key}.npz"), depth_ppm=r.depth_ppm,
                         sectors=",".join(map(str, sorted(secs))), cutouts=os.path.join(a.out, "cuts", f"tic{int(r.tic)}"),
                         molusc=os.path.join(os.path.abspath(a.molusc), f"tic{int(r.tic)}_kept.csv.gz") if a.molusc else "",
                         drop=r.drop))
    pd.DataFrame(jobs).to_csv(os.path.join(a.out, "jobs.csv"), index=False)
    print(f"{len(jobs)} jobs", flush=True)
    subprocess.run([TRICE_PY, "fpp_pool.py", "setup", os.path.join(a.out, "jobs.csv"), "--out", a.out, "--procs", str(a.procs)],
                   env=ENV, cwd=HERE, check=True)
    print("FLEET_PREP_DONE", flush=True)


if __name__ == "__main__":
    main()
