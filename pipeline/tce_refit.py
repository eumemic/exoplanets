"""Re-measure unpromoted SPOC TCEs on our light curves, which add sectors after the TCE was
made (up to Sector 107). For each TCE on a star, strongest first: BLS on a grid within 0.5% of
the TCE period, transit statistics, then mask it before the next TCE. TOIs on the star are
masked first. Output has the same format as search.py, so collect/vet/followup work unchanged.

Usage: python tce_refit.py [--procs N] [--out results/search_tce]
"""
import argparse
import json
import os
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

import search
from common import CAT, DATA, RESULTS, load_star, tic_path


def refit(t, y, dy, P0, rho, span, width=0.005):
    """BLS around P0 (+-width in period) on a grid fine enough for the full baseline."""
    from astropy.timeseries import BoxLeastSquares

    D = search.expected_duration(P0, rho)
    df = 0.25 * D / (P0 * span)               # frequency step: <= D/4 timing drift over the span
    f0 = 1 / P0
    n = int(np.ceil(width * f0 / df))
    periods = np.sort(1 / (f0 + np.arange(-n, n + 1) * df))
    durs = np.geomspace(max(0.3 * D, 0.4 / 24), min(2.5 * D, 0.3 * P0, 12 / 24), 12)
    r = BoxLeastSquares(t, y, dy).power(periods, durs, objective="likelihood", method="fast", oversample=10)
    i = int(np.argmax(r.power))
    return (float(r.period[i]), float(r.transit_time[i]), float(r.duration[i]), float(r.depth[i]),
            float(np.sqrt(2 * max(r.power[i], 0))))


def refit_star(args):
    tic, star, tces, tois = args
    t_start = time.time()
    try:
        sectors = load_star(tic)
        rho = star.get("rho")
        if not np.isfinite(rho) or rho <= 0:
            rho = star["mass"] / star["rad"] ** 3 if np.isfinite(star["mass"]) else 1.5
        rho = float(np.clip(rho, 0.3, 30))
        window = float(np.clip(3.0 * search.expected_duration(30.0, rho), 0.5, 1.0))
        prep = search.prepare(sectors, window)
        if not prep:
            return tic, {"tic": tic, "error": "no usable data"}

        def binned(minutes):
            tb, yb, eb = [], [], []
            for p in prep:
                if p["exptime"] < 0.9 * minutes * 60:
                    a, b, c = search.bin_sector(p["t"], p["r"], p["e"], minutes / 1440)
                else:
                    a, b, c = p["t"], p["r"], p["e"]
                tb.append(a); yb.append(b); eb.append(c)
            t, y, e = np.concatenate(tb), np.concatenate(yb), np.concatenate(eb)
            o = np.argsort(t)
            return t[o], y[o], e[o]

        tf, yf, ef = binned(search.BIN_FINE)
        tu = np.concatenate([p["t"] for p in prep]); ru = np.concatenate([p["r"] for p in prep])
        eu = np.concatenate([p["e"] for p in prep])
        o = np.argsort(tu); tu, ru, eu = tu[o], ru[o], eu[o]
        span = tf.max() - tf.min()
        mf, mu = np.ones(len(tf), bool), np.ones(len(tu), bool)
        for toi in tois:
            mf &= ~search.toi_windows(tf, toi)
            mu &= ~search.toi_windows(tu, toi)
        result = dict(tic=int(tic), rho=rho, window=window, n_points=int(len(tf)), span=float(span),
                      sectors=[p["sector"] for p in prep], provs=[p["prov"] for p in prep],
                      noise_ppm=float(search.robust_std(ru) * 1e6), masked_tois=tois, signals=[])
        for k, tce in enumerate(sorted(tces, key=lambda x: -x["tce_model_snr"])):
            if mf.sum() < 100:
                break
            P, t0, dur, dep, snr = refit(tf[mf], yf[mf], ef[mf], tce["tce_period"], rho, span)
            st = search.event_stats(tu[mu], ru[mu], eu[mu], P, t0, dur)
            result["signals"].append(dict(
                rank=k + 1, period=P, t0=t0, duration_h=dur * 24, bls_depth_ppm=dep * 1e6, bls_snr=snr,
                coarse_snr=snr, sde=np.nan, exp_duration_h=float(search.expected_duration(P, rho) * 24),
                repeat=False, rot_alias=False, tce_period=tce["tce_period"], tce_snr=tce["tce_model_snr"],
                tce_file=tce["file"], **st))
            mf &= np.abs(((tf - t0 + 0.5 * P) % P) - 0.5 * P) > dur
            mu &= np.abs(((tu - t0 + 0.5 * P) % P) - 0.5 * P) > dur
        result["runtime_s"] = round(time.time() - t_start, 1)
        return tic, result
    except Exception as ex:
        return tic, {"tic": int(tic), "error": f"refit: {ex!r}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--out", default=str(RESULTS / "search_tce"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tces = pd.read_csv(CAT / "tce_targets.csv")
    stars = pd.read_parquet(CAT / "tce_hosts.parquet").set_index("ID")
    toi_table = pd.read_csv(DATA / "known" / "toi.csv")
    todo = []
    for tic, g in tces.groupby("ticid"):
        if os.path.exists(f"{a.out}/{tic}.json") or not tic_path(tic).exists():
            continue
        todo.append((int(tic), stars.loc[tic].to_dict(), g.to_dict("records"), search.star_tois(tic, toi_table)))
    print(f"{len(todo)} stars to refit", flush=True)
    t0 = time.time()
    with Pool(a.procs) as pool:
        for i, (tic, res) in enumerate(pool.imap_unordered(refit_star, todo, chunksize=1), 1):
            with open(f"{a.out}/{tic}.json", "w") as fh:
                json.dump(res, fh, default=float)
            if i % 200 == 0 or i == len(todo):
                print(f"{i}/{len(todo)}  {i / (time.time() - t0):.2f} stars/s", flush=True)


if __name__ == "__main__":
    main()
