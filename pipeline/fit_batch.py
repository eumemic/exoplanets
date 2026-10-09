"""Transit fits (fit_transit.py) for a list of signals in parallel, each with its own masks.

Usage: python fit_batch.py LIST.csv --stars STARS.parquet [--procs 63] [--steps 2500]
LIST columns: tic, period, t0, duration_h, masks ("P,t0,dur_h;..." other signals to mask, may be
empty). Writes results/fit_tic<TIC>_P<period>.json; signals that already have a fit are skipped.
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from common import RESULTS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("list")
    ap.add_argument("--stars", required=True)
    ap.add_argument("--procs", type=int, default=(os.cpu_count() or 8) - 1)
    ap.add_argument("--steps", type=int, default=2500)
    a = ap.parse_args()
    lst = pd.read_csv(a.list, dtype={"masks": str})
    jobs = []
    for r in lst.itertuples():
        if (RESULTS / f"fit_tic{r.tic}_P{r.period:.3f}.json").exists():
            continue
        masks = [m for m in str(r.masks).split(";") if m and m != "nan"]
        jobs.append([sys.executable, "fit_transit.py", str(r.tic), f"{r.period}", f"{r.t0}", f"{r.duration_h}",
                     "--steps", str(a.steps), "--stars", a.stars] + (["--mask", *masks] if masks else []))
    print(f"{len(lst)} signals, {len(jobs)} to fit", flush=True)
    env = dict(os.environ, OMP_NUM_THREADS="1", NUMBA_NUM_THREADS="1")
    with ThreadPoolExecutor(a.procs) as ex:
        codes = list(ex.map(lambda j: subprocess.run(j, env=env, stdout=subprocess.DEVNULL,
                                                     stderr=subprocess.DEVNULL).returncode, jobs))
    print(f"fits: {codes.count(0)} ok, {len(codes) - codes.count(0)} failed", flush=True)
    print("FIT_BATCH_DONE", flush=True)


if __name__ == "__main__":
    main()
