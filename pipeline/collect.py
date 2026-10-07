"""Collect search JSONs into one table and select signals worth vetting.

Usage: python collect.py [--search results/search] [--snr 9]
Writes results/signals.parquet (all) and results/cands.csv (selected).
"""
import argparse
import glob
import json

import numpy as np
import pandas as pd

from common import CAT, RESULTS
from known import check as known_check


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", nargs="+",
                    default=[str(RESULTS / "search"), str(RESULTS / "search_semi")])
    ap.add_argument("--snr", type=float, default=9.0)
    ap.add_argument("--out", default=str(RESULTS / "cands.csv"))
    a = ap.parse_args()
    rows, errors = [], 0
    files = [f for d in a.search for f in glob.glob(f"{d}/*.json")]
    for f in files:
        r = json.load(open(f))
        if "error" in r:
            errors += 1
            continue
        n_new = sum(1 for s in r["sectors"] if s >= 97)
        for s in r["signals"]:
            d = {k: v for k, v in s.items() if k != "events"}
            d.update(tic=r["tic"], method="semi" if "search_semi" in f else "coherent",
                     rho=r["rho"], n_sectors=len(r["sectors"]), n_new_sectors=n_new,
                     span=r["span"], noise_ppm=r["noise_ppm"], events=json.dumps(s["events"]))
            rows.append(d)
    df = pd.DataFrame(rows)
    df.to_parquet(str(RESULTS / "signals.parquet"))
    print(f"{df.tic.nunique()} stars, {len(df)} signals, {errors} errors")
    dur_ratio = df["duration_h"] / df["exp_duration_h"]
    sel = ((df["bls_snr"] >= a.snr) & (df["n_good_events"] >= 3) & (df["max_ses_frac"] <= 0.6)
           & ~df["repeat"].astype(bool) & ~df["rot_alias"].astype(bool)
           & (dur_ratio > 0.25) & (dur_ratio < 2.5) & (df["frac_neg_events"] <= 0.3))
    c = df[sel].sort_values("bls_snr", ascending=False).copy()
    # The same signal found by both methods: keep the higher-SNR row.
    c["pkey"] = c["period"].round(2)
    c = c.drop_duplicates(["tic", "pkey"]).drop(columns="pkey")
    c["rank"] = c["rank"] + np.where(c["method"] == "semi", 10, 0)  # unique vetting file names
    stars = pd.read_parquet(CAT / "targets.parquet").set_index("ID")
    status, detail = [], []
    for _, r in c.iterrows():
        k = known_check(int(r.tic), r.period, float(stars.loc[r.tic, "ra"]), float(stars.loc[r.tic, "dec"]))
        if k["same_star_period_match"]:
            status.append("known"); detail.append(k["same_star_period_match"][0])
        elif k["neighbour_period_match"]:
            status.append("neighbour"); detail.append(k["neighbour_period_match"][0])
        else:
            status.append("new"); detail.append(";".join(k["same_star"][:3]))
    c["known_status"], c["known_detail"] = status, detail
    c.to_csv(a.out, index=False)
    print(c["known_status"].value_counts().to_dict())
    print(f"{len(c)} signals selected (SNR >= {a.snr}) from {c.tic.nunique()} stars -> {a.out}")
    print(pd.cut(df["bls_snr"], [0, 7, 8, 9, 10, 12, 15, 20, 50, 1e9]).value_counts().sort_index())


if __name__ == "__main__":
    main()
