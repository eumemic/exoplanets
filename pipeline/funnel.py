"""Stage counts of a search run, from its output tables, for results_public/funnel_allsky.csv (read by the website).

A run is made of parts, each a directory of outputs written by run_shard.py, collect.py, vet.py, followup.py and
finalize_shard.py: a signals table (every signal found), a candidates table (the signals passing the pre-filters, with
known_status), a vetted table and a follow-up summary (followup*/summary.csv, with the pixel flags). File patterns are
relative to each part's directory, or absolute (then globbed once). The parts' counts are added.

Stages, per SNR band (hi: SNR >= 9; low: 7.5 <= SNR < 9; "all" for the first two):
  stars          stars searched (distinct TIC IDs in the signals tables, or in --stars-files lists)
  signals        signals found
  prefilter      signals passing the pre-filters (at least 3 good transits, no transit over 60% of the signal, duration
                 0.25-2.5 times the expected, at most 30% negative transits, no repeat or rotation alias; one row per
                 star and period): the candidates table, or computed from the signals table when there is none
  vetted         of those, vetted (light curves re-read, transit-masked detrending, LEO-Vetter)
  known          matching a known planet, TOI, CTOI or SPOC TCE on the star
  reported       reported elsewhere (the literature check)
  neighbour      matching a known signal on a star within 2.5'
  ours           matching one of this project's published signals (a re-search finds them again)
  leo_pass       not matched, and passing every LEO-Vetter test
  cuts           ... and MES >= 7.1, per-sector chi2/dof <= 5, Rp <= 20 R_earth
  offset         ... of those, a difference-image centroid more than 15" from the target
  no_image       ... no usable difference image (and no offset)
  close_nb       ... only a TIC star within 15" that could produce the depth
  clean          ... none of these
  clean_mes_lt10, clean_mes_10_12, clean_mes_ge12
                 the clean ones by MES (below 10, 10-12, 12 and above), for the false-alarm rates

Usage:
  python funnel.py PASS DIR [DIR ...] [--signals PAT] [--cands PAT] [--vetted PAT] [--followup PAT]
                   [--stars-files PAT] [--bands hi low] [--no-totals] [--out ../results_public/funnel_allsky.csv]
Prints the counts; with --out, replaces that file's rows for PASS and these bands (columns pass, band, stage, count).
"""
import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

STAGES = ["stars", "signals", "prefilter", "vetted", "known", "reported", "neighbour", "ours", "leo_pass", "cuts",
          "offset", "no_image", "close_nb", "clean", "clean_mes_lt10", "clean_mes_10_12", "clean_mes_ge12"]
BANDS = {"hi": (9.0, np.inf), "low": (7.5, 9.0)}
PREFILTER_COLS = ["tic", "period", "bls_snr", "duration_h", "exp_duration_h", "n_good_events", "max_ses_frac",
                  "repeat", "rot_alias", "frac_neg_events"]


def files(pattern, dirs):
    if not pattern:
        return []
    if Path(pattern).is_absolute():
        return sorted(glob.glob(pattern))
    return sorted(f for d in dirs for f in glob.glob(str(Path(d) / pattern)))


def prefilter(df):
    """collect.py's selection (without the SNR cut), one row per star and period."""
    r = df["duration_h"] / df["exp_duration_h"]
    sel = ((df["n_good_events"] >= 3) & (df["max_ses_frac"] <= 0.6) & ~df["repeat"].astype(bool)
           & ~df["rot_alias"].astype(bool) & (r > 0.25) & (r < 2.5) & (df["frac_neg_events"] <= 0.3))
    df = df[sel].copy()
    df["pkey"] = df["period"].round(2)
    return df.sort_values("bls_snr", ascending=False).drop_duplicates(["tic", "pkey"])


def pixel_class(flags):
    f = set(flags.split(",")) if isinstance(flags, str) and flags else set()
    if "offset" in f:
        return "offset"
    if "no_pixel" in f:
        return "no_image"
    if "close_nb" in f:
        return "close_nb"
    return "clean"


def counts(a):
    out = {}
    sig = files(a.signals, a.dirs)
    if not a.no_totals:
        if a.stars_files:
            stars = set()
            for f in files(a.stars_files, a.dirs):
                stars |= {int(x) for x in open(f).read().split()}
            out[("all", "stars")] = len(stars)
        elif sig:
            stars, n = set(), 0
            for f in sig:
                n += pq.ParquetFile(f).metadata.num_rows
                stars |= set(pq.read_table(f, columns=["tic"]).column("tic").to_pylist())
            out[("all", "stars")], out[("all", "signals")] = len(stars), n
    cf = files(a.cands, a.dirs)
    cands = pd.concat([pd.read_csv(f, usecols=["tic", "bls_snr", "known_status"]) for f in cf]) if cf else None
    vet = pd.concat([pd.read_csv(f, usecols=["tic", "rank", "bls_snr", "known_status", "n_fail", "MES", "chi2_sec", "rp"])
                     for f in files(a.vetted, a.dirs)], ignore_index=True)
    fu = pd.concat([pd.read_csv(f"{x}/summary.csv", usecols=["tic", "rank", "flags"]) for x in files(a.followup, a.dirs)],
                   ignore_index=True).drop_duplicates(["tic", "rank"])
    for b in a.bands:
        lo, hi = BANDS[b]
        vb = vet[(vet.bls_snr >= lo) & (vet.bls_snr < hi)]
        if cands is not None:
            c = cands[(cands.bls_snr >= lo) & (cands.bls_snr < hi)]
            out[(b, "prefilter")] = len(c)
        elif sig:
            out[(b, "prefilter")] = sum(len(prefilter(pd.read_parquet(f, columns=PREFILTER_COLS,
                                                                      filters=[("bls_snr", ">=", lo), ("bls_snr", "<", hi)])))
                                        for f in sig)
            c = vb
        else:
            c = vb
        out[(b, "vetted")] = len(vb)
        for s in ("known", "reported", "neighbour", "ours"):
            out[(b, s)] = int((c.known_status == s).sum())
        v = vb[(vb.known_status == "new") & (vb.n_fail == 0)]
        out[(b, "leo_pass")] = len(v)
        v = v[(v.MES >= 7.1) & (v.chi2_sec <= 5) & (v.rp <= 20)]
        out[(b, "cuts")] = len(v)
        cls = v.merge(fu, on=["tic", "rank"], how="left")["flags"].map(pixel_class).values
        for s in ("offset", "no_image", "close_nb", "clean"):
            out[(b, s)] = int((cls == s).sum())
        mes = v["MES"].values[cls == "clean"]
        out[(b, "clean_mes_lt10")] = int((mes < 10).sum())
        out[(b, "clean_mes_10_12")] = int(((mes >= 10) & (mes < 12)).sum())
        out[(b, "clean_mes_ge12")] = int((mes >= 12).sum())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pass_name")
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--signals", default="signals*.parquet")
    ap.add_argument("--cands", default="cands*.csv")
    ap.add_argument("--vetted", default="vetted*.csv")
    ap.add_argument("--followup", default="followup*")
    ap.add_argument("--stars-files", help="lists of the TIC IDs searched (e.g. the inverted runs' inv_searched.txt)")
    ap.add_argument("--bands", nargs="+", default=["hi"], choices=list(BANDS))
    ap.add_argument("--no-totals", action="store_true", help="skip stars and signals (counted with another band)")
    ap.add_argument("--out")
    a = ap.parse_args()
    tot = counts(a)
    rows = [{"pass": a.pass_name, "band": b, "stage": s, "count": tot[(b, s)]}
            for b in ["all"] + a.bands for s in STAGES if (b, s) in tot]
    x = pd.DataFrame(rows)
    print(x.to_string(index=False))
    if a.out:
        p = Path(a.out)
        old = pd.read_csv(p) if p.exists() else x.iloc[:0]
        old = old[~((old["pass"] == a.pass_name) & old.band.isin(x.band.unique()))]
        pd.concat([old, x], ignore_index=True).to_csv(p, index=False)


if __name__ == "__main__":
    main()
