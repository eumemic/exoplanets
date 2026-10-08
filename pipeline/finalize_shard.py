"""After a shard's search, vetting and pixel checks: select the signals that pass every check
(no prior match, all LEO-Vetter tests, MES >= 7.1, per-sector chi2/dof <= 5, no centroid offset
or capable neighbour within 15", Rp <= 20 R_earth) and fit each one's transit in parallel, with TOIs
and other selected signals on the same star masked.

Usage: python finalize_shard.py STARS.parquet [--vetted ../results/vetted_allsky.csv]
                                [--vet-dir ../results/vet_allsky] [--followup ../results/followup_allsky]
                                [--out ../results/clean_allsky.csv] [--procs 63]
Writes the selection (candidate_table.py list format) and results/fit_tic*_P*.json.
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from common import DATA

PY = sys.executable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stars")
    ap.add_argument("--vetted", default="../results/vetted_allsky.csv")
    ap.add_argument("--vet-dir", default="../results/vet_allsky")
    ap.add_argument("--followup", default="../results/followup_allsky")
    ap.add_argument("--out", default="../results/clean_allsky.csv")
    ap.add_argument("--procs", type=int, default=(os.cpu_count() or 8) - 1)
    ap.add_argument("--rmax", type=float, default=20.0)
    a = ap.parse_args()
    v = pd.read_csv(a.vetted)
    p0 = v[(v["known_status"] == "new") & (v["n_fail"] == 0) & (v["MES"] >= 7.1) & (v["chi2_sec"] <= 5)
           & (v["rp"] <= a.rmax)]
    f = pd.read_csv(f"{a.followup}/summary.csv")
    f["flags"] = f["flags"].fillna("")
    c = p0.merge(f[["tic", "rank", "flags"]], on=["tic", "rank"])
    c = c[c["flags"] == ""].copy()
    print(f"{len(v)} vetted, {len(p0)} new passing every LEO-Vetter test and the cuts, {len(c)} clean", flush=True)
    toi = pd.read_csv(DATA / "known" / "toi.csv")
    jobs = []
    for r in c.itertuples():
        masks = [f"{t['Period (days)']:.7f},{t['Epoch (BJD)'] - 2457000:.6f},{t['Duration (hours)']:.3f}"
                 for _, t in toi[toi["TIC ID"] == r.tic].iterrows() if t["Period (days)"] > 0]
        masks += [f"{o.period:.7f},{o.t0:.6f},{o.duration_h:.3f}"
                  for o in c[(c["tic"] == r.tic) & (c["rank"] != r.rank)].itertuples()]
        jobs.append([PY, "fit_transit.py", str(r.tic), f"{r.period}", f"{r.t0}", f"{r.duration_h}",
                     "--steps", "2500", "--stars", a.stars] + (["--mask", *masks] if masks else []))
    env = dict(os.environ, OMP_NUM_THREADS="1", NUMBA_NUM_THREADS="1")
    with ThreadPoolExecutor(a.procs) as ex:
        codes = list(ex.map(lambda j: subprocess.run(j, env=env, stdout=subprocess.DEVNULL,
                                                     stderr=subprocess.DEVNULL).returncode, jobs))
    print(f"fits: {codes.count(0)} ok, {len(codes) - codes.count(0)} failed", flush=True)
    c.assign(vet_dir=a.vet_dir.replace("../", ""), followup_dir=a.followup.replace("../", ""),
             stars=a.stars.replace("../", ""), notes="all-sky FGKM dwarfs")[
        ["tic", "rank", "vet_dir", "followup_dir", "stars", "notes", "period", "rp", "MES"]].to_csv(a.out, index=False)
    print("FINALIZE_DONE", flush=True)


if __name__ == "__main__":
    main()
