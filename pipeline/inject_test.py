"""Injection-recovery: compare coherent vs semi-coherent search on synthetic transits.

Usage: python inject_test.py N_STARS [--snr 10] [--procs 10]
"""
import argparse
import json
import random
from multiprocessing import Pool

import numpy as np
import pandas as pd

import search
from common import CAT, RESULTS, load_star


def inject(sectors, P, t0, depth, dur):
    out = []
    for s in sectors:
        s = dict(s)
        ph = ((s["time"] - t0 + 0.5 * P) % P) - 0.5 * P
        x = np.abs(ph) / (0.5 * dur)
        # trapezoid with 15% ingress/egress
        shape = np.clip((1 - x) / 0.15, 0, 1)
        s["flux"] = s["flux"] * (1 - depth * shape)
        out.append(s)
    return out


def run(args):
    tic, star, P, snr_target, semi, seed = args
    rng = np.random.default_rng(seed)
    sectors = load_star(tic)
    t = np.concatenate([s["time"] for s in sectors])
    rho = float(np.clip(star["rho"] if np.isfinite(star["rho"]) else 2.0, 0.3, 30))
    dur = search.expected_duration(P, rho) * rng.uniform(0.6, 1.0)
    t0 = t.min() + rng.uniform(0, P)
    ph = ((t - t0 + 0.5 * P) % P) - 0.5 * P
    n_in = np.sum(np.abs(ph) < 0.5 * dur)
    noise = np.median([search.robust_std(np.diff(s["flux"])) / np.sqrt(2) for s in sectors])
    depth = snr_target * noise / np.sqrt(max(n_in, 1))
    inj = inject(sectors, P, t0, depth, dur)
    search.SEMICOHERENT = semi
    orig = search.load_star
    search.load_star = lambda _tic: inj
    try:
        _, res = search.search_star((tic, star))
    finally:
        search.load_star = orig
    hit = any(abs(s["period"] / (P * h) - 1) < 0.003 for s in res.get("signals", []) for h in (0.5, 1, 2))
    best = max((s["bls_snr"] for s in res.get("signals", [])
                if any(abs(s["period"] / (P * h) - 1) < 0.003 for h in (0.5, 1, 2))), default=0)
    return dict(tic=tic, P=P, depth_ppm=depth * 1e6, n_in=int(n_in), semi=semi, hit=hit,
                rec_snr=best, runtime=res.get("runtime_s"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int)
    ap.add_argument("--snr", type=float, default=10)
    ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--semi-only", action="store_true")
    a = ap.parse_args()
    stars = pd.read_parquet(CAT / "targets.parquet").set_index("ID")
    done = [int(f.stem) for f in (RESULTS / "search").glob("*.json")]
    random.seed(1)
    pick = random.sample(done, a.n)
    jobs = []
    for i, tic in enumerate(pick):
        P = float(np.exp(np.random.default_rng(i).uniform(np.log(1.0), np.log(15.0))))
        for semi in ((True,) if a.semi_only else (False, True)):
            jobs.append((tic, stars.loc[tic].to_dict(), P, a.snr, semi, i))
    with Pool(a.procs) as pool:
        rows = pool.map(run, jobs, chunksize=1)
    df = pd.DataFrame(rows)
    if a.semi_only:
        prev = pd.read_csv(RESULTS / f"inject_snr{a.snr:g}.csv")
        df = pd.concat([prev[~prev["semi"]], df], ignore_index=True)
    df.to_csv(RESULTS / f"inject_snr{a.snr:g}.csv", index=False)
    print(df.groupby("semi").agg(recovered=("hit", "mean"), n=("hit", "size"),
                                 median_runtime=("runtime", "median")))
    w = df.pivot_table(index=["tic", "P"], columns="semi", values="hit").dropna()
    print("coherent only:", int(((w[False] == 1) & (w[True] == 0)).sum()),
          " semi only:", int(((w[False] == 0) & (w[True] == 1)).sum()))


if __name__ == "__main__":
    main()
