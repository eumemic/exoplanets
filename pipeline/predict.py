"""Predicted transit times for every candidate, with 1-sigma uncertainties, flagged where they
fall inside published TESS orbit windows. Committing this file before the data exist makes the
predictions a timestamped, falsifiable test.

Usage: python predict.py [--until 2027-06-30]
Writes candidates/predictions.csv and adds upcoming TESS sectors to results/candidates.csv.
"""
import argparse
import glob
import json

import numpy as np
import pandas as pd
from astropy.time import Time
from tess_stars2px import tess_stars2px_function_entry as ts2px

from common import CAT, DATA, RESULTS, ROOT


def orbit_windows():
    f = DATA / "tess_schedule" / "TESS_orbit_times.csv"
    w = pd.read_csv(f, comment="#")
    start = Time(list(w["Start of Orbit"])).jd - 2457000
    end = Time(list(w["End of Orbit"])).jd - 2457000
    return list(zip(w["Sector"], start, end))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="2027-06-30")
    a = ap.parse_args()
    now = Time.now().jd - 2457000
    until = Time(a.until).jd - 2457000
    wins = orbit_windows()
    c = pd.read_csv(RESULTS / "candidates.csv")
    stars = pd.read_parquet(CAT / "targets.parquet").set_index("ID")
    rows, upcoming = [], []
    for r in c.itertuples():
        fit = next(json.load(open(f)) for f in glob.glob(str(RESULTS / f"fit_tic{r.TIC}_P*.json"))
                   if abs(json.load(open(f))["P"][1] / r.P_d - 1) < 1e-3)
        P, t0 = fit["P"][1], fit["t0"][1]
        eP = (fit["P"][2] - fit["P"][0]) / 2
        et0 = (fit["t0"][2] - fit["t0"][0]) / 2
        star = stars.loc[r.TIC]
        on_star = set(int(x) for x in ts2px(r.TIC, star["ra"], star["dec"])[3])
        n = np.arange(np.ceil((now - t0) / P), np.floor((until - t0) / P) + 1)
        for k in n:
            tc = t0 + k * P
            # only sectors whose field of view contains this star, and only inside orbit windows
            sector = next((s for s, lo, hi in wins if lo <= tc <= hi and s in on_star), None)
            rows.append(dict(TIC=r.TIC, period_d=round(P, 6), epoch=int(k), tc_BJD_TDB=round(tc + 2457000, 4),
                             tc_UTC=Time(tc + 2457000, format="jd", scale="tdb").utc.iso[:16],
                             sigma_min=round(np.hypot(et0, k * eP) * 1440, 1),
                             duration_h=round(fit["T14_h"][1], 2),
                             tess_sector=sector if sector is not None else ""))
        upcoming.append(",".join(str(x) for x in sorted(on_star) if x >= 108))
    c["upcoming_tess_sectors"] = upcoming
    c.to_csv(RESULTS / "candidates.csv", index=False)
    out = ROOT / "candidates" / "predictions.csv"
    out.parent.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"{len(rows)} predicted transits -> {out}; in published TESS windows: "
          f"{sum(1 for x in rows if x['tess_sector'] != '')} (schedule published through Sector 110)")


if __name__ == "__main__":
    main()
