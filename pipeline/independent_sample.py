"""Freeze clean low-band signals whose score_h membership changes at 0.80."""
import argparse
from pathlib import Path

import pandas as pd
import numpy as np


def build_sample(table, released, grouped, catalog):
    keys = ["tic", "rank", "label", "inv_set", "band", "cls"]
    for scores in (released, grouped):
        if not table[keys].equals(scores[keys]):
            raise ValueError("Classifier tables must have identical signal keys and row order")
        if not np.isfinite(scores.score_h).all():
            raise ValueError("Every signal must have a finite holdout score")
    clean = table.label.eq("real") & table.band.eq("low") & table.cls.eq("clean")
    changed = clean & released.score_h.ge(.8).ne(grouped.score_h.ge(.8))
    rows = []
    for i, signal in table[changed].iterrows():
        match = catalog[catalog.TIC.eq(signal.tic)
                        & ((catalog.P_d / signal.period - 1).abs() < .003)]
        if len(match) != 1:
            raise ValueError(f"Expected one catalog ephemeris for TIC {signal.tic}, P={signal.period}")
        ephemeris = match.iloc[0]
        rows.append(dict(tic=int(signal.tic), period_d=ephemeris.P_d,
                         t0_btjd=ephemeris.T0_BJD - 2457000,
                         duration_h=ephemeris.T14_h, depth_ppm=ephemeris.depth_ppm,
                         tier=ephemeris.tier, rank=int(signal['rank']),
                         score_original=released.loc[i, "score_h"],
                         score_grouped=grouped.loc[i, "score_h"],
                         direction="enter" if grouped.loc[i, "score_h"] >= .8 else "leave"))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", default="validation/false_alarm_classifier_table.csv.gz")
    ap.add_argument("--released", default="validation/false_alarm_classifier_scores.csv.gz")
    ap.add_argument("--grouped", required=True)
    ap.add_argument("--catalog", default="results_public/candidates_allsky.csv")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    sample = build_sample(*(pd.read_csv(path) for path in
                            (args.table, args.released, args.grouped, args.catalog)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(args.out, index=False)
    print(f"Saved {len(sample)} signals to {args.out}")


if __name__ == "__main__":
    main()
