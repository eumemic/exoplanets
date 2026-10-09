"""TRICERATOPS false-positive probabilities for a list of signals, in parallel inside AWS: per star,
FFI cutouts from the S3 cubes (s3cut.py), then for each signal a phase-folded light curve
(export_fold.py) and fpp.py on those cutouts. Resumable: signals with a result are skipped.

Usage: python fpp_batch.py LIST.csv --stars STARS.parquet --out DIR [--procs 40] [--runs 10]
                            [--nearby-max-arcsec 30]
LIST columns: tic, rank, period, t0, duration_h, depth_ppm, sectors ("s1,s2,..." for the field
geometry), masks ("P,t0,dur_h;..." other signals to mask in the fold, may be empty).
Writes DIR/tic<TIC>_P<period, 0.01 d>.npz, _fpp.json (fpp.py's result) and .log, named as
candidate_table.py expects.
"""
import argparse
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from s3cut import cut

TRICE_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".venv-trice", "bin", "python")
N_PIX = 22          # TRICERATOPS's cutout size: 2 * search_radius + 2 pixels
ENV = dict(os.environ, OMP_NUM_THREADS="1", NUMBA_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")


def one_star(job):
    tic, rows, star, a = job
    cuts = f"{a.out}/cuts/tic{tic}"
    done = 0
    try:
        for r in rows:
            base = f"{a.out}/tic{tic}_P{r['period']:.2f}"
            if os.path.exists(base + "_fpp.json"):
                done += 1
                continue
            with open(base + ".log", "w") as log:
                if not os.path.exists(base + ".npz"):
                    masks = [m for m in str(r["masks"]).split(";") if m and m != "nan"]
                    subprocess.run([sys.executable, "export_fold.py", str(tic), repr(float(r["period"])), repr(float(r["t0"])),
                                    repr(float(r["duration_h"])), base + ".npz"] + (["--mask", *masks] if masks else []),
                                   stdout=log, stderr=subprocess.STDOUT, env=ENV)
                if not os.path.exists(base + ".npz"):
                    continue
                want = {int(s) for s in str(r["sectors"]).split(",")}
                have = {int(os.path.basename(f)[6:10]) for f in cut(tic, star["ra"], star["dec"], N_PIX, cuts, want)}
                secs = sorted(want & have)
                if not secs:
                    print("no cutouts for", sorted(want), file=log, flush=True)
                    continue
                subprocess.run([TRICE_PY, "fpp.py", str(tic), base + ".npz", f"{r['depth_ppm']:.1f}",
                                "--sectors", ",".join(map(str, secs)), "--cutouts", cuts, "--runs", str(a.runs),
                                "--draws", str(a.draws), "--gaia-vizier", "--nearby-max-arcsec", str(a.nearby_max_arcsec)], stdout=log, stderr=subprocess.STDOUT, env=ENV)
            done += os.path.exists(base + "_fpp.json")
    finally:
        shutil.rmtree(cuts, ignore_errors=True)
    return tic, done, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("list")
    ap.add_argument("--stars", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=40)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--draws", type=int, default=200000)
    ap.add_argument("--nearby-max-arcsec", type=float, default=30.0,
                    help="nearby-star scenarios only within this separation (the centroid excludes sources beyond)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    lst = pd.read_csv(a.list, dtype={"sectors": str, "masks": str})
    stars = pd.read_parquet(a.stars).set_index("ID")
    jobs = [(int(t), [r for _, r in g.iterrows()], stars.loc[int(t)], a) for t, g in lst.groupby("tic")]
    print(f"{len(lst)} signals on {len(jobs)} stars", flush=True)
    n_ok = n = 0
    with ThreadPoolExecutor(a.procs) as ex:
        for i, (tic, done, total) in enumerate(ex.map(one_star, jobs), 1):
            n_ok += done; n += total
            if i % 20 == 0 or i == len(jobs):
                print(f"{i}/{len(jobs)} stars, {n_ok}/{n} signals with an FPP", flush=True)
    print("FPP_BATCH_DONE", flush=True)


if __name__ == "__main__":
    main()
