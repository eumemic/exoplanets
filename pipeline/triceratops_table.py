"""results_public/products/triceratops.csv: for each catalog row with a TRICERATOPS result, the result it uses, the
inputs that result ran with (ephemeris, depth, masks of the star's other signals, scenario drops, cadence, exposure,
points, sectors, MOLUSC survivors) and the summaries of its runs. Built by the rule triceratops_table in rules.py.

The results come from the store (tri_store.py; entries of kind tri, with their folds), where each signal key's latest
entry is used (the batches run before the store keep their order). A catalog row (table, TIC, P_d) takes the key with
the same TIC and the closest period within a relative difference of match_rel; keys left over (older periods from before
a refit) are not used. A used result must pass the checks of fpp_check.py; a result in which TRICERATOPS never evaluated
the target (every scenario equally likely, as for a target without a TIC parallax) is kept as degenerate, with its
values empty. Column store is the entry's key, batch the batch that computed it, legacy is yes for a result
imported from a batch that did not keep all of its inputs, and lightcurves the hash of the light-curve list its fold was
made from (lcindex.list_hash; empty for a fold that did not record it, made from the searched list), and code the hashes
of the code and packages of its stages (stage_code.py; empty for a legacy result).
"""
import collections
import csv
import json
import os

import numpy as np

import fpp_check
import lcindex
import stage_code
import store as st
import tri_store

COLUMNS = ["table", "TIC", "P_d", "key", "batch", "period", "t0_btjd", "duration_h", "depth_ppm", "masks", "drop", "exptime_min",
           "n_points", "sectors", "n_scenarios", "runs", "FPP_mean", "NFPP_mean", "NFPP_max", "runs_g", "FPP_g_mean",
           "NFPP_g_mean", "NFPP_g_max", "molusc_survivors", "degenerate", "store", "legacy", "lightcurves", "code"]


def _request(store, kind, key):
    p = os.path.join(store.path(kind, key), "request.json")
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


def build(store_root, catalog_rows, out_csv, runs=10, min_survivors=20000, phase_bin_min=2.0, match_rel=0.002):
    """catalog_rows: [(table, TIC, P_d)] with TIC and P_d as written in the measurement tables."""
    store = st.Store(store_root)
    latest = tri_store.latest(store)                # signal key -> (store key, request, result)
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
    rows, problems = [], []
    for row, key in use.items():
        skey, req, res = latest[key]
        batch, j, sig = res["batch"], res["fpp"], req.get("signal") or res.get("signal")
        if sig is None:
            problems.append(f"{key} ({batch}): not in the batch's list.csv")
            continue
        if res["fold_key"] is None:
            problems.append(f"{key} ({batch}): no fold")
            continue
        f = np.load(os.path.join(store.path("fold", res["fold_key"]), "fold.npz"))
        found, deg = fpp_check.gate(j, res["runs"], f["time"], int(f["cadence_s"]), sig["duration_h"], runs, min_survivors,
                                    phase_bin_min)
        problems += [f"{key} ({batch}): {x}" for x in found]
        gaia = "FPP_m_mean" in j
        stages = {k: _request(store, k, res.get(f)) for k, f in (("fold", "fold_key"), ("tri_setup", "setup_key"),
                                                                  ("molusc", "molusc_key")) if res.get(f)}
        fold_req = stages.get("fold") or {}
        rows.append(dict(
            table=row[0], TIC=row[1], P_d=row[2], key=key, batch=batch, period=sig["period"], t0_btjd=sig["t0_btjd"],
            duration_h=sig["duration_h"], depth_ppm=sig["depth_ppm"], masks=sig["masks"], drop=sig["drop"],
            exptime_min=repr(float(j["exptime_min"])), n_points=int(j["n_points"]), sectors=j["sectors"],
            n_scenarios=int(j["n_scenarios"]), runs=int(j["runs"]),
            FPP_mean="" if deg else repr(float(j["FPP_mean"])), NFPP_mean="" if deg else repr(float(j["NFPP_mean"])),
            NFPP_max="" if deg else repr(float(j["NFPP_max"])), runs_g=len(j["FPP_m"]) if gaia else "",
            FPP_g_mean="" if deg or not gaia else repr(float(j["FPP_m_mean"])),
            NFPP_g_mean="" if deg or not gaia else repr(float(j["NFPP_m_mean"])),
            NFPP_g_max="" if deg or not gaia else repr(float(j["NFPP_m_max"])),
            molusc_survivors=int(j["molusc_survivors"]) if gaia else "", degenerate="yes" if deg else "", store=skey,
            legacy="yes" if req.get("legacy") else "",
            lightcurves=lcindex.list_hash(fold_req["lightcurves"]) if fold_req.get("lightcurves") else "",
            code="" if req.get("legacy") else stage_code.of_requests(dict(stages, tri=req))))
    if problems:
        raise ValueError(f"{len(problems)} TRICERATOPS results fail the checks:\n" + "\n".join(problems[:50]))
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return rows
