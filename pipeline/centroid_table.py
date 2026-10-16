"""results_public/products/centroids.csv: the per-sector centroid results that replace the published centroid columns of
catalog rows, with the ephemeris each measurement used. Built by the rule centroid_table in rules.py.

The measurements come from the store (centroid_store.py, kind centroid): each signal key's latest entry, holding the
signal list row it ran with, the centroid_sectors.py file and the TIC stars within 2' of the target with their TIC
dispositions (so that artifacts and duplicates are not taken for stars). The test is centroid_test.py's. A catalog row
(table, TIC, P_d) takes the measurement with the same TIC and the closest period within a relative difference of
match_rel. Rows without one keep their published values. Column store is the entry's key, batch the batch that measured
it, code the hash of the measurement's code and packages (stage_code.py; empty for a legacy entry).
"""
import collections
import csv

import pandas as pd

import centroid_store
import centroid_test
import stage_code
import store as st

COLUMNS = ["table", "TIC", "P_d", "key", "batch", "period", "t0_btjd", "duration_h", "sectors_requested", "cs_sectors",
           "cs_offset_arcsec", "cs_pa_deg", "cs_p_target", "cs_neighbour", "cs_neighbour_sep_arcsec", "cs_p_neighbour", "n_failed",
           "store", "code"]


def _g2(x):
    """Two significant figures, as the catalog writes centroid p-values."""
    return "" if pd.isna(x) else repr(float(f"{x:.2g}"))


def _r1(x):
    return "" if pd.isna(x) else repr(round(float(x), 1))


def build(store_root, catalog_rows, out_csv, match_rel=0.002):
    store = st.Store(store_root)
    latest = centroid_store.latest(store)            # key -> (store key, request, result)
    by_tic = collections.defaultdict(list)
    for k, (_, _, res) in latest.items():
        by_tic[int(res["signal"]["tic"])].append((float(res["signal"]["period"]), k))
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
    for key in sorted(owner):
        skey, req, res = latest[key]
        L = pd.DataFrame([res["signal"]]).astype({"tic": int, "period": float, "t0": float, "duration_h": float,
                                                  "depth_ppm": float, "P_d": float})
        per, stars = centroid_test.load_json(L, store.path("centroid", skey))
        disp = pd.DataFrame(res["stars"], columns=["key", "tic", "east", "north", "sep", "Tmag", "disposition"])
        disp["tic"] = disp["tic"].astype(int)
        if len(stars):
            stars = stars.drop(columns=[c for c in ("disposition",) if c in stars]).merge(
                disp[["key", "tic", "disposition"]], on=["key", "tic"], how="left")
        res_t = centroid_test.analyse(L, per, stars).set_index("key")
        r = L.iloc[0]
        x = res_t.loc[key] if key in res_t.index else None
        row = owner[key]
        out.append(dict(
            table=row[0], TIC=row[1], P_d=row[2], key=key, batch=res["batch"], period=repr(float(r.period)),
            t0_btjd=repr(float(r.t0)), duration_h=repr(float(r.duration_h)), sectors_requested=r.sectors,
            cs_sectors="" if x is None else int(x.n_sectors), cs_offset_arcsec="" if x is None else _r1(x.offset),
            cs_pa_deg="" if x is None else _r1(x.pa_deg), cs_p_target="" if x is None else _g2(x.p_target),
            cs_neighbour="" if x is None or pd.isna(x.get("best_neighbour")) else int(x.best_neighbour),
            cs_neighbour_sep_arcsec="" if x is None else _r1(x.get("best_neighbour_sep")),
            cs_p_neighbour="" if x is None else _g2(x.get("p_best_neighbour")),
            n_failed="" if x is None else int(x.n_failed), store=skey, code=stage_code.of_requests({"centroid": req})))
    out.sort(key=lambda r: (r["table"], int(r["TIC"]), float(r["P_d"])))
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out
