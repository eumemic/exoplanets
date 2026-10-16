"""results_public/products/centroids.csv: the per-sector centroid results that replace the published centroid columns of
catalog rows, with the ephemeris each measurement used. Built by the rule centroid_table in rules.py.

The measurements come from centroid_sectors.py batches (results_public/products/centroid_batches.csv, in order: a later
batch's result replaces an earlier one). A batch directory holds the signal list it ran with (list.csv), one JSON file
per signal (cs/<key>.json) and the TIC stars within 2' of each target with their TIC dispositions (stars.csv, looked up
once with centroid_test.py's add_dispositions, so that artifacts and duplicates are not taken for stars). The test is
centroid_test.py's. A catalog row (table, TIC, P_d) takes the measurement with the same TIC and the closest period within
a relative difference of match_rel. Rows without one keep their published values.
"""
import collections
import csv
import os

import pandas as pd

import centroid_test

COLUMNS = ["table", "TIC", "P_d", "key", "batch", "period", "t0_btjd", "duration_h", "sectors_requested", "cs_sectors",
           "cs_offset_arcsec", "cs_pa_deg", "cs_p_target", "cs_neighbour", "cs_neighbour_sep_arcsec", "cs_p_neighbour", "n_failed"]


def _g2(x):
    """Two significant figures, as the catalog writes centroid p-values."""
    return "" if pd.isna(x) else repr(float(f"{x:.2g}"))


def _r1(x):
    return "" if pd.isna(x) else repr(round(float(x), 1))


def build(batches_csv, results_root, catalog_rows, out_csv, match_rel=0.002):
    with open(batches_csv, newline="") as fh:
        batches = sorted(csv.DictReader(fh), key=lambda r: int(r["order"]))
    latest = {}                                      # key -> (batch, list row)
    for b in batches:
        d = os.path.join(results_root, b["batch"])
        L = pd.read_csv(os.path.join(d, "list.csv"))
        for r in L.itertuples():
            if os.path.exists(os.path.join(d, "cs", f"{r.key}.json")):
                latest[r.key] = (b["batch"], r)
    by_tic = collections.defaultdict(list)
    for k, (_, r) in latest.items():
        by_tic[int(r.tic)].append((float(r.period), k))
    use, owner = {}, {}
    for row in catalog_rows:
        p = float(row[2])
        hits = [(abs(per - p), k) for per, k in by_tic.get(int(row[1]), []) if abs(per / p - 1) < match_rel]
        if hits:
            k = min(hits)[1]
            if k in owner:
                raise ValueError(f"centroid measurement {k} matches two catalog rows: {owner[k]} and {row}")
            use[row], owner[k] = k, row
    out = []
    for batch in sorted({latest[k][0] for k in owner}):
        d = os.path.join(results_root, batch)
        L = pd.read_csv(os.path.join(d, "list.csv"))
        L = L[L.key.isin([k for k in owner if latest[k][0] == batch])]
        per, stars = centroid_test.load_json(L, os.path.join(d, "cs"))
        disp = pd.read_csv(os.path.join(d, "stars.csv"))
        stars = stars.drop(columns=[c for c in ("disposition",) if c in stars]).merge(
            disp[["key", "tic", "disposition"]], on=["key", "tic"], how="left")
        res = centroid_test.analyse(L, per, stars).set_index("key")
        for r in L.itertuples():
            x = res.loc[r.key] if r.key in res.index else None
            row = owner[r.key]
            out.append(dict(
                table=row[0], TIC=row[1], P_d=row[2], key=r.key, batch=batch, period=repr(float(r.period)),
                t0_btjd=repr(float(r.t0)), duration_h=repr(float(r.duration_h)), sectors_requested=r.sectors,
                cs_sectors="" if x is None else int(x.n_sectors), cs_offset_arcsec="" if x is None else _r1(x.offset),
                cs_pa_deg="" if x is None else _r1(x.pa_deg), cs_p_target="" if x is None else _g2(x.p_target),
                cs_neighbour="" if x is None or pd.isna(x.get("best_neighbour")) else int(x.best_neighbour),
                cs_neighbour_sep_arcsec="" if x is None else _r1(x.get("best_neighbour_sep")),
                cs_p_neighbour="" if x is None else _g2(x.get("p_best_neighbour")),
                n_failed="" if x is None else int(x.n_failed)))
    out.sort(key=lambda r: (r["table"], int(r["TIC"]), float(r["P_d"])))
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out
