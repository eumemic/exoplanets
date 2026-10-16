"""Transit fits (fit_transit.py) in the store (store.py), kind fit, and results_public/products/fits.csv, the fit each
catalog row uses. Built by the rule fit_table in rules.py; catalog.py takes the row's fitted columns from it.

A fit's request holds the signal (key, the starting ephemeris and duration, the masks of the star's other signals), the
light-curve list of the star, the hash of its TIC row (the stellar-density prior and limb darkening come from it), the
number of steps, the seed, the code and the packages. The fits made before the store are imported as legacy entries:
for each catalog row with fitted values, the fit file (the candidate's folder first, then the search's result
directories) whose medians reproduce the row's period, epoch, duration, radius and impact parameter at the catalog's
precision; a row for which no file does keeps its measured values and is listed (fits.csv has no row for it). A fit
that fails the checks of problems() (a sampler that did not converge) is not used: its row has no fitted values.

The columns a fit gives a row: P_d (the period median, 6 decimals), P_err (half the 16-84% interval, 6 decimals),
T0_BJD (the epoch median + 2457000, 5 decimals), T14_h, Rp_Re and b (medians, 2 decimals). Each signal key's
entry with the highest seq is used, among those whose checks passed. Column lightcurves is the hash of the light-curve
list the fit was made from (lcindex.list_hash; empty for a legacy fit, made from the searched list): a fit whose list is
not the star's list now is stale (lcindex.py; check fits_current).

Usage: python fit_store.py import
"""
import csv
import glob
import json
import math
import os
import sys

import lcindex
import store as st

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
COLUMNS = ["table", "TIC", "P_d", "candidate_id", "key", "batch", "store", "legacy", "lightcurves", "check", "P_fit", "P_err",
           "T0_BJD", "T14_h", "Rp_Re", "b"]


def _rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def values(fit):
    """The catalog columns a fit gives, written as the catalog writes them (the shortest form of the rounded value)."""
    p = fit["P"]
    r = lambda x, nd: repr(round(float(x), nd))
    return dict(P_fit=r(p[1], 6), P_err=r((p[2] - p[0]) / 2, 6), T0_BJD=r(fit["t0"][1] + 2457000, 5),
                T14_h=r(fit["T14_h"][1], 2), Rp_Re=r(fit["Rp"][1], 2), b=r(fit["b"][1], 2))


def problems(fit):
    """Signs of a fit whose sampler did not converge: a period interval that is not a small fraction of the period, an
    epoch interval wider than the period, a duration interval outside 0-48 h, or medians outside the priors."""
    out = []
    try:
        P, t0, T14, b, k = fit["P"], fit["t0"], fit["T14_h"], fit["b"], fit["k"]
    except KeyError as ex:
        return [f"no {ex.args[0]}"]
    if not (P[0] > 0 and P[2] - P[0] < 0.01 * P[1]):
        out.append(f"period interval {P[0]:.3g} to {P[2]:.3g} d")
    if not (t0[2] - t0[0] < P[1]):
        out.append("epoch interval wider than the period")
    if not (T14[0] > 0 and T14[2] < 48):
        out.append(f"duration interval {T14[0]:.3g} to {T14[2]:.3g} h")
    if not (0 <= b[1] <= 1.3 and 0 < k[1] < 0.3):
        out.append(f"median b {b[1]:.3g} or k {k[1]:.3g} outside the priors")
    return out


def reproduces(fit, row, table):
    """True if the fit's medians give the row's fitted values at the catalog's precision."""
    try:
        v = values(fit)
    except (KeyError, IndexError, TypeError):
        return False
    cols = (("P_d", "P_fit", 1.01e-6), ("T0_BJD", "T0_BJD", 1.01e-5), ("T14_h", "T14_h", 0.0101), ("Rp_Re", "Rp_Re", 0.0101),
            ("b", "b", 0.0101)) if table == "candidates_allsky" else (("Rp_Re", "Rp_Re", 0.0101), ("b", "b", 0.0101))
    return all(abs(_f(row[a]) - _f(v[b])) <= tol for a, b, tol in cols)


def signal_key(row):
    return f"tic{int(row['TIC'])}_P{_f(row['P_d']):.4f}"


def import_legacy(store, root=ROOT):
    """Legacy entries for the fits behind the catalog's fitted values. Returns (imported, rows without a fit file)."""
    files = {}
    for f in sorted(glob.glob(os.path.join(root, "results_cloud", "**", "fit_tic*_P*.json"), recursive=True)
                    + glob.glob(os.path.join(root, "results", "**", "fit_tic*_P*.json"), recursive=True)):
        tic = os.path.basename(f)[7:].split("_P")[0]
        files.setdefault(tic, []).append(f)
    n, missing = 0, []
    for table, path, base in (("candidates_allsky", "results_public/products/measurements_allsky.csv", "candidates/allsky"),
                              ("tiers_earlier_candidates", "results_public/products/measurements_earlier.csv", "candidates")):
        for r in _rows(os.path.join(root, path)):
            if not r["b"]:
                continue
            folder = os.path.join(root, base, r["candidate_id"], "transit_fit.json")
            cands = ([folder] if os.path.exists(folder) else []) + files.get(r["TIC"], [])
            hit = None
            for f in cands:
                try:
                    j = json.load(open(f))
                except ValueError:
                    continue
                if reproduces(j, r, table):
                    hit = (f, j)
                    break
            if hit is None:
                missing.append(f"{table} TIC {r['TIC']} P {r['P_d']}")
                continue
            req = dict(kind="fit", signal_key=signal_key(r), tic=int(r["TIC"]), table=table,
                       legacy=["lightcurves", "star", "steps", "seed", "code", "packages"],
                       source=os.path.relpath(hit[0], root))
            res = dict(seq=0, batch="legacy", signal=dict(table=table, TIC=r["TIC"], P_d=r["P_d"]), fit=hit[1],
                       content=st.file_content(hit[0]))
            store.put("fit", req, res, files={"transit_fit.json": hit[0]})
            n += 1
    return n, missing


def latest(store):
    """{(table, signal key): (store key, request, result)}: each signal's fit with the highest seq."""
    out = {}
    for k, (req, res, chk) in store.entries("fit").items():
        if chk is not None and not chk.get("passed"):
            continue
        sk = (req.get("table") or res["signal"]["table"], req["signal_key"])
        if sk not in out or res["seq"] > out[sk][2]["seq"]:
            out[sk] = (k, req, res)
    return out


def table(store_root, rows, out_csv):
    """rows: [(table, TIC, P_d, candidate_id)] of the measurement tables; writes the fit each uses."""
    store = st.Store(store_root)
    fits = latest(store)
    out = []
    for t, tic, p, cid in rows:
        hit = fits.get((t, signal_key(dict(TIC=tic, P_d=p))))
        if hit is None:
            continue
        k, req, res = hit
        bad = problems(res["fit"])
        vals = {c: "" for c in COLUMNS[COLUMNS.index("P_fit"):]} if bad else values(res["fit"])
        out.append(dict(table=t, TIC=tic, P_d=p, candidate_id=cid, key=req["signal_key"], batch=res["batch"], store=k,
                        legacy="yes" if req.get("legacy") else "",
                        lightcurves=lcindex.list_hash(req["lightcurves"]) if req.get("lightcurves") else "",
                        check="failed: " + "; ".join(bad) if bad else "passed",
                        **vals))
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out


STAGE_CODE = [("fit_transit", None)]


def code_hash(index=None):
    from dag.codehash import CodeIndex
    idx = index or CodeIndex([os.path.dirname(os.path.abspath(__file__))])
    parts, effects = {}, {}
    for m, f in STAGE_CODE:
        pp, e, _ = idx.closure(m, f)
        parts.update(pp)
        effects.update(e)
    return st.sha256_json({"parts": parts, "effects": effects})


def request(table, item, lightcurves, star, code, env, steps=3000):
    """item: the signal (key as signal_key(row) of the measurement row, tic, period, t0 (BTJD), duration_h, masks)."""
    import fit_transit
    return dict(kind="fit", signal_key=item["key"], tic=int(item["tic"]), table=table,
                start=dict(period=str(item["period"]), t0_btjd=str(item["t0"]), duration_h=str(item["duration_h"])),
                masks=str(item.get("masks") or ""), lightcurves=sorted(lightcurves), star=star, steps=steps,
                seed=fit_transit.fit_seed(item["tic"], float(item["period"])), code=code, env=env)


def ingest_item(store, d, plan_item, batch, seq, env_lock="requirements.txt"):
    """Store one fit of a cloud batch: d holds fit.json and item.json (cloud_worker.py). Returns (key, problems)."""
    info = json.load(open(os.path.join(d, "item.json")))
    found = []
    if info["env"].get(env_lock) != plan_item["env"]:
        found.append(f"the instance's packages do not match {env_lock}")
    if info.get("commit") != plan_item["commit"]:
        found.append(f"code: the instance ran commit {info.get('commit')}, the plan {plan_item['commit']}")
    f = os.path.join(d, "fit.json")
    fit = json.load(open(f))
    found += problems(fit)
    req = plan_item["request"]
    res = dict(seq=seq, batch=batch, signal=dict(table=req["table"], TIC=str(req["tic"]), P_d=plan_item["row_P_d"]), fit=fit,
               content=st.file_content(f))
    key = store.put("fit", req, res, check=dict(passed=not found, problems=found), files={"transit_fit.json": f})
    return key, found


def main():
    if sys.argv[1:] != ["import"]:
        sys.exit(__doc__)
    n, missing = import_legacy(st.Store())
    print(f"{n} fits imported; {len(missing)} rows with fitted values but no fit file that reproduces them")
    for m in missing[:30]:
        print("  ", m)


if __name__ == "__main__":
    main()
