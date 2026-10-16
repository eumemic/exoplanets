"""results_public/products/triceratops.csv: for each catalog row with a TRICERATOPS result, the result it uses, the
inputs that result ran with (ephemeris, depth, masks of the star's other signals, scenario drops, cadence, exposure,
points, sectors, MOLUSC survivors) and the summaries of its runs. Built by the rule triceratops_table in rules.py.

The results come from fpp_pool.py batches (results_public/products/triceratops_batches.csv, in order: a later batch's
result for a signal replaces an earlier one). Each batch directory holds the signal list it ran with (list.csv), the
folds, every run (runs.jsonl) and one <key>_fpp.json per signal. A catalog row (table, TIC, P_d) takes the key with the
same TIC and the closest period within a relative difference of match_rel; keys left over (older periods from before a
refit) are not used. A used result must pass the checks of fpp_check.py; a result in which TRICERATOPS never evaluated
the target (every scenario equally likely, as for a target without a TIC parallax) is kept as degenerate, with its
values empty.
"""
import collections
import csv
import json
import os

import numpy as np

import fpp_check

COLUMNS = ["table", "TIC", "P_d", "key", "batch", "period", "t0_btjd", "duration_h", "depth_ppm", "masks", "drop", "exptime_min",
           "n_points", "sectors", "n_scenarios", "runs", "FPP_mean", "NFPP_mean", "NFPP_max", "runs_g", "FPP_g_mean",
           "NFPP_g_mean", "NFPP_g_max", "molusc_survivors", "degenerate"]


def _read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def build(batches_csv, results_root, catalog_rows, out_csv, runs=10, min_survivors=20000, phase_bin_min=2.0, match_rel=0.002):
    """catalog_rows: [(table, TIC, P_d)] with TIC and P_d as written in the measurement tables."""
    batches = sorted(_read_csv(batches_csv), key=lambda r: int(r["order"]))
    latest = {}                                     # key -> batch directory of its latest result
    for b in batches:
        d = os.path.join(results_root, b["batch"])
        for f in sorted(os.listdir(d)):
            if f.endswith("_fpp.json"):
                latest[f[:-9]] = b["batch"]
    by_tic = collections.defaultdict(list)
    for k in latest:
        tic, per = k[3:].split("_P")
        by_tic[int(tic)].append((float(per), k))
    use, owner = {}, {}                             # catalog row -> key; key -> catalog row
    for row in catalog_rows:
        p = float(row[2])
        hits = [(abs(per - p), k) for per, k in by_tic.get(int(row[1]), []) if abs(per / p - 1) < match_rel]
        if not hits:
            continue
        k = min(hits)[1]
        if k in owner:
            raise ValueError(f"TRICERATOPS result {k} matches two catalog rows: {owner[k]} and {row}")
        use[row], owner[k] = k, row
    chosen = {k: latest[k] for k in owner}
    lists = {b["batch"]: {r["key"]: r for r in _read_csv(os.path.join(results_root, b["batch"], "list.csv"))} for b in batches}
    n_runs = collections.defaultdict(collections.Counter)
    blended, degenerate = collections.Counter(), set()
    for b in batches:
        with open(os.path.join(results_root, b["batch"], "runs.jsonl")) as fh:
            for line in fh:
                r = json.loads(line)
                if chosen.get(r["key"]) != b["batch"] or "error" in r:
                    continue
                n_runs[r["key"]][r["mode"]] += 1
                names = [s for _, s, _ in r["probs"]]
                if not names or "" in names:
                    degenerate.add(r["key"])
                if any(s in fpp_check.BLENDED and v > 0 for _, s, v in r["probs"]):
                    blended[r["key"]] += 1
    rows, problems = [], []
    for row, key in use.items():
        batch = chosen[key]
        d = os.path.join(results_root, batch)
        with open(os.path.join(d, f"{key}_fpp.json")) as fh:
            j = json.load(fh)
        sig = lists[batch].get(key)
        if sig is None:
            problems.append(f"{key} ({batch}): not in the batch's list.csv")
            continue
        gaia = "FPP_m_mean" in j
        if key not in degenerate:
            if n_runs[key]["d"] != runs or (gaia and n_runs[key]["m"] != runs):
                problems.append(f"{key} ({batch}): runs {dict(n_runs[key])}, expected {runs} per mode")
            if not blended[key]:
                problems.append(f"{key} ({batch}): no blended-star scenario in any run (no field-star population)")
            if gaia and j.get("molusc_survivors", 0) < min_survivors:
                problems.append(f"{key} ({batch}): {j.get('molusc_survivors')} MOLUSC survivors (a cut-off file)")
        f = np.load(os.path.join(d, "folds", f"{key}.npz"))
        cad = int(f["cadence_s"])
        width = cad / 86400 if cad < 540 else phase_bin_min / 1440
        dur = float(sig["duration_h"]) / 24
        edges = np.arange(-3 * dur, 3 * dur + 1e-9, width)
        if np.bincount(np.digitize(f["time"], edges)).max() > 1:
            problems.append(f"{key} ({batch}): more than one point per phase bin in the fold")
        deg = key in degenerate
        rows.append(dict(
            table=row[0], TIC=row[1], P_d=row[2], key=key, batch=batch, period=sig["period"], t0_btjd=sig["t0"], duration_h=sig["duration_h"],
            depth_ppm=sig["depth_ppm"], masks=sig.get("masks", ""), drop=sig.get("drop", ""),
            exptime_min=repr(float(j["exptime_min"])), n_points=int(j["n_points"]), sectors=j["sectors"],
            n_scenarios=int(j["n_scenarios"]), runs=int(j["runs"]),
            FPP_mean="" if deg else repr(float(j["FPP_mean"])), NFPP_mean="" if deg else repr(float(j["NFPP_mean"])),
            NFPP_max="" if deg else repr(float(j["NFPP_max"])), runs_g=len(j["FPP_m"]) if gaia else "",
            FPP_g_mean="" if deg or not gaia else repr(float(j["FPP_m_mean"])),
            NFPP_g_mean="" if deg or not gaia else repr(float(j["NFPP_m_mean"])),
            NFPP_g_max="" if deg or not gaia else repr(float(j["NFPP_m_max"])),
            molusc_survivors=int(j["molusc_survivors"]) if gaia else "", degenerate="yes" if deg else ""))
    if problems:
        raise ValueError(f"{len(problems)} TRICERATOPS results fail the checks:\n" + "\n".join(problems[:50]))
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return rows
