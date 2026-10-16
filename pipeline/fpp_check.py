"""Checks on fpp_pool.py results before they are used. TRICERATOPS can return a result that looks like an answer when
something went wrong, so each final result (with several directories, later ones override earlier ones) is checked for:
  - ten runs in each mode (default, and Gaia-limited where the job had MOLUSC survivors), or --runs;
  - a blended-star scenario (DTP, DEB, DEBx2P, BTP, BEB, BEBx2P) above 1e-6 in at least one run. Without a field-star
    population TRICERATOPS skips them all without an error (runs.jsonl keeps every scenario above 1e-6);
  - no degenerate run: scenarios without names, as when calc_probs stops early for a target without a mass, radius,
    Teff or parallax and leaves every scenario equally likely;
  - MOLUSC survivors not far below the usual range (a run cut off part way leaves a short file);
  - at most one point per phase bin in the fold (export_fold.py --single-cadence: 2-minute and 200-second data binned to
    their cadence, longer cadences to --phase-bin-min), which needs the signal list for the durations.
Usage: python fpp_check.py DIR [DIR ...] --list LIST.csv [--list ...] [--expect KEYS.txt] [--only KEYS.txt] [--runs 10]
Exits with status 1 if any check fails.
"""
import argparse
import collections
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

BLENDED = {"DTP", "DEB", "DEBx2P", "BTP", "BEB", "BEBx2P"}


def gate(fpp, runs, fold_time, cadence_s, duration_h, n_runs=10, min_survivors=20000, phase_bin_min=2.0):
    """The checks of one signal's result: fpp (its <key>_fpp.json), runs (its runs.jsonl records), the fold's times and
    cadence, and the signal's duration. Returns (problems, degenerate); a degenerate result (the target not evaluated)
    skips the checks on the runs, since it is kept without values."""
    n, blended, degenerate = collections.Counter(), 0, False
    for r in runs:
        if "error" in r:
            continue
        n[r["mode"]] += 1
        names = [s for _, s, _ in r["probs"]]
        if not names or "" in names:
            degenerate = True
        if any(s in BLENDED and v > 0 for _, s, v in r["probs"]):
            blended += 1
    problems = []
    gaia = "FPP_m_mean" in fpp
    if not degenerate:
        if n["d"] != n_runs or (gaia and n["m"] != n_runs):
            problems.append(f"runs {dict(n)}, expected {n_runs} per mode")
        if not blended:
            problems.append("no blended-star scenario in any run (no field-star population)")
        if gaia and fpp.get("molusc_survivors", 0) < min_survivors:
            problems.append(f"{fpp.get('molusc_survivors')} MOLUSC survivors (a cut-off file)")
    width = cadence_s / 86400 if cadence_s < 540 else phase_bin_min / 1440
    dur = float(duration_h) / 24
    edges = np.arange(-3 * dur, 3 * dur + 1e-9, width)
    if np.bincount(np.digitize(fold_time, edges)).max() > 1:
        problems.append("more than one point per phase bin in the fold")
    return problems, degenerate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--list", action="append", required=True, help="signal list with key and duration_h columns")
    ap.add_argument("--expect", help="file of keys that must have a result")
    ap.add_argument("--only", help="file of keys to check (others, e.g. superseded results, are ignored)")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--phase-bin-min", type=float, default=2.0)
    ap.add_argument("--min-survivors", type=int, default=20000,
                    help="fewest MOLUSC survivors (of 200,000 simulated companions; 30,000-180,000 when complete)")
    a = ap.parse_args()
    lst = pd.concat([pd.read_csv(f) for f in a.list]).drop_duplicates("key", keep="last").set_index("key")
    src = {}
    for d in a.dirs:
        for f in glob.glob(os.path.join(d, "*_fpp.json")):
            src[os.path.basename(f)[:-9]] = d
    if a.only:
        keep = set(open(a.only).read().split())
        src = {k: d for k, d in src.items() if k in keep}
    runs = collections.defaultdict(collections.Counter)
    blended, degenerate = collections.Counter(), set()
    for d in a.dirs:
        for line in open(os.path.join(d, "runs.jsonl")):
            r = json.loads(line)
            if src.get(r["key"]) != d:
                continue
            runs[r["key"]][r["mode"]] += 1
            names = [s for _, s, _ in r["probs"]]
            if not names or "" in names:
                degenerate.add(r["key"])
            if any(s in BLENDED and v > 0 for _, s, v in r["probs"]):
                blended[r["key"]] += 1
    bad_runs, no_blended, unbinned, few_companions = [], [], [], []
    for k, d in sorted(src.items()):
        j = json.load(open(os.path.join(d, f"{k}_fpp.json")))
        if "molusc_survivors" in j and j["molusc_survivors"] < a.min_survivors:
            few_companions.append((k, j["molusc_survivors"]))
        if runs[k]["d"] != a.runs or ("FPP_m_mean" in j and runs[k]["m"] != a.runs):
            bad_runs.append((k, dict(runs[k])))
        if not blended[k] and k not in degenerate:
            no_blended.append(k)
        f = np.load(os.path.join(d, "folds", f"{k}.npz"))
        cad = int(f["cadence_s"])
        width = cad / 86400 if cad < 540 else a.phase_bin_min / 1440
        dur = lst.loc[k, "duration_h"] / 24
        edges = np.arange(-3 * dur, 3 * dur + 1e-9, width)
        if np.bincount(np.digitize(f["time"], edges)).max() > 1:
            unbinned.append((k, cad, len(f["time"])))
    missing = sorted(set(open(a.expect).read().split()) - set(src)) if a.expect else []
    print(f"results: {len(src)}")
    print("not", a.runs, "runs per mode:", bad_runs or "none")
    print("no blended-star scenario in any run:", no_blended or "none")
    print("degenerate (target not evaluated):", sorted(degenerate) or "none")
    print("folds with more than one point per phase bin:", unbinned or "none")
    print("MOLUSC survivors below", a.min_survivors, "(a cut-off file):", few_companions or "none")
    if a.expect:
        print("expected keys without a result:", missing or "none")
    sys.exit(1 if bad_runs or no_blended or degenerate or unbinned or few_companions or missing else 0)


if __name__ == "__main__":
    main()
