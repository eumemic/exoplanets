"""The clean SNR 7.5-9 signals of the inverted-light-curve runs, both passes, for validation/inverted_clean_low.csv.

The catalog's SNR 7.5-9 set combines the first pass with the QLP re-search, which adds signals but replaces none, and
the re-search does not list a signal already in the catalog. The false alarms expected in that set (doc_numbers.py)
need the same union of the inverted runs: the first pass's clean signals, plus the re-search's clean signals that do
not repeat a first-pass inverted signal the catalog would hold (SNR >= 9 outside the offset class, or SNR 7.5-9 clean),
matched as the re-search matches the real catalog: same star, period within 0.5%.

"Clean" is funnel.py's definition: not matched to a known object, every LEO-Vetter test passed, MES >= 7.1,
chi2/dof <= 5, Rp <= 20 R_earth, and no offset, close-neighbour or missing-image flag. Run by hand after an inverted
run, like funnel.py (its inputs are the runs' output tables, which are not in the repository).

Usage:
  python inverted_clean.py --first ../results_cloud/inv1 ... --research ../results_cloud/qfull/exo-qinv0/results ...
"""
import argparse
import glob

import pandas as pd

from funnel import pixel_class

COLS = ["tic", "rank", "period", "bls_snr", "MES", "known_status", "n_fail", "chi2_sec", "rp"]
LOW, HIGH = 7.5, 9.0


def run(dirs):
    """Signals passing the cuts, with their pixel class."""
    vet = pd.concat([pd.read_csv(f, usecols=COLS) for d in dirs for f in glob.glob(f"{d}/vetted*.csv")],
                    ignore_index=True)
    fu = pd.concat([pd.read_csv(f, usecols=["tic", "rank", "flags"]) for d in dirs
                    for f in glob.glob(f"{d}/followup*/summary.csv")], ignore_index=True).drop_duplicates(["tic", "rank"])
    v = vet[(vet.known_status == "new") & (vet.n_fail == 0) & (vet.MES >= 7.1) & (vet.chi2_sec <= 5) & (vet.rp <= 20)
            & (vet.bls_snr >= LOW)]
    v = v.merge(fu, on=["tic", "rank"], how="left")
    v["cls"] = v["flags"].map(pixel_class)
    return v


def table(first_dirs, research_dirs):
    a, b = run(first_dirs), run(research_dirs)
    low = lambda v: v[(v.bls_snr < HIGH) & (v.cls == "clean")]
    held = a[((a.bls_snr >= HIGH) & (a.cls != "offset")) | ((a.bls_snr < HIGH) & (a.cls == "clean"))]
    out = [low(a).assign(**{"pass": "first", "repeats": ""})]
    r = low(b).copy()
    m = r.merge(held[["tic", "period"]], on="tic", suffixes=("", "_first"))
    m = m[(m.period / m.period_first - 1).abs() < 0.005]
    rep = m.groupby(["tic", "rank"]).period_first.first()
    r["repeats"] = [f"{rep[k]:.6f}" if k in rep.index else "" for k in zip(r.tic, r["rank"])]
    out.append(r.assign(**{"pass": "QLP re-search"}))
    t = pd.concat(out, ignore_index=True)
    return t[["pass", "tic", "rank", "period", "bls_snr", "MES", "repeats"]].round({"period": 6, "bls_snr": 3, "MES": 3})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", nargs="+", required=True)
    ap.add_argument("--research", nargs="+", required=True)
    ap.add_argument("--out", default="../validation/inverted_clean_low.csv")
    a = ap.parse_args()
    t = table(a.first, a.research)
    t.to_csv(a.out, index=False)
    new = t[(t["pass"] == "first") | (t.repeats == "")]
    print(f"{(t['pass'] == 'first').sum()} first-pass, {(t['pass'] != 'first').sum()} re-search "
          f"({(t.repeats != '').sum()} repeats): {len(new)} in the union -> {a.out}")


if __name__ == "__main__":
    main()
