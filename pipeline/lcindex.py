"""The light curves behind the catalog as dated lists, so that a change at MAST (a redelivered product, a new version, a
product withdrawn) becomes a list of results to redo.

- results_public/products/lightcurves_searched.csv (rule lightcurves_searched): for every star of the catalog, the
  products the searches used, one per sector (tic, sector, prov, exptime, uri): the light-curve list of the QLP
  re-search where it searched the star again (fixed QLP reader), else the full-sky search's or the earlier searches'.
  Every result made before a snapshot changed a product (the legacy ones included) was made from these.
- results_public/products/lightcurves_current.csv: the same stars' products at MAST on a date (column checked): for
  each sector and source, the highest version. Written by `python lcindex.py refresh`, a query of MAST, so a deliberate
  step whose consequences then propagate.
- results_public/products/lightcurves.csv (rule lightcurves): the products new work uses: the searched list with each
  product replaced by the same source's file in the snapshot when that is another file (a redelivery), and without the
  sectors the source no longer has. Sectors new in the snapshot are not added: they need a search update. The cloud
  runner (cloud.py) gives fits and TRICERATOPS folds these lists, and their requests record them; fits.csv and
  triceratops.csv carry the hash of the list each result was made from (list_hash; empty for a legacy result, made from
  the searched list), and a result whose list is not the star's list now is stale (check fits_current; tri_plan.py).
- results_public/products/redo.csv (rule redo): for every catalog row on a star whose lists differ, by sector:
  redelivered (the source's product is another file now), removed (the source no longer has the sector), new (a sector
  no search had, numbered as MAST numbers it); and the stages to redo: fit and TRICERATOPS (the runner redoes them when
  stale), search, vetting and pixel follow-up (by hand: they are not stored products yet). Products are compared by
  file name: a product replaced under the same name is not seen.

Usage: python lcindex.py refresh      (queries MAST for the catalog's stars; writes lightcurves_current.csv)
"""
import csv
import glob
import os
import sys
from datetime import date

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CURRENT = os.path.join(ROOT, "results_public", "products", "lightcurves_current.csv")
COLS = ["tic", "sector", "prov", "exptime", "uri"]
SOURCES = ["SPOC", "TESS-SPOC", "QLP"]      # the sources the light-curve lists use (no list has TGLC)
MANIFESTS_NEW = "results_cloud/qfull_kits/manifest_shard*.parquet"
MANIFESTS_OLD = ["results_cloud/manifests_allsky/manifest_shard*.parquet"] + [
    f"data/catalogs/{n}.parquet" for n in ("manifest_prelim", "manifest_toi", "manifest_tce", "manifest_faint_t1",
                                           "manifest_faint_t2")]


def _name(uri):
    return str(uri).rsplit("/", 1)[-1]


def manifest_rows(tics, root=ROOT):
    """The light-curve list of each star: the re-search manifests where they have the star, else the others."""
    ids = [int(t) for t in set(tics)]
    rd = lambda f: pd.read_parquet(f, filters=[("tic", "in", ids)])
    new = pd.concat([rd(f) for f in sorted(glob.glob(os.path.join(root, MANIFESTS_NEW)))])
    old = pd.concat([rd(f) for pat in MANIFESTS_OLD for f in sorted(glob.glob(os.path.join(root, pat)))])
    new = new[[c for c in new.columns if not c.startswith("__")]]
    old = old[[c for c in old.columns if not c.startswith("__")]]
    return pd.concat([new, old[~old.tic.isin(set(new.tic))]]).drop_duplicates(["tic", "sector", "prov"])


def _ranked(m):
    from common import PROV_RANK
    ver = m["uri"].str.extract(r"_v(\d+)_l+c\.fits$", expand=False).fillna("0").astype(int)
    m = m.assign(_rank=m["prov"].map(PROV_RANK).fillna(9), _ver=ver)
    return m.sort_values(["tic", "sector", "_rank", "_ver"], ascending=[True, True, True, False])


def latest(m):
    """The highest version of each source's product for a star and sector."""
    return _ranked(m).drop_duplicates(["tic", "sector", "prov"]).drop(columns=["_rank", "_ver"])


def catalog_tics(allsky_csv, earlier_csv):
    return sorted({int(r["TIC"]) for f in (allsky_csv, earlier_csv) for r in csv.DictReader(open(f, newline=""))})


def searched(allsky_csv, earlier_csv, out_csv, root=ROOT):
    m = manifest_rows(catalog_tics(allsky_csv, earlier_csv), root)
    dup = m.duplicated(["tic", "sector"]).sum()
    if dup:      # download.py would load two products for the sector into one
        raise ValueError(f"{dup} star sectors have more than one product in the light-curve lists")
    m = m[COLS].sort_values(["tic", "sector"])
    m.to_csv(out_csv, index=False, lineterminator="\n")
    return m


def apply_snapshot(m, current):
    """The lists m (COLS) with each product replaced by the same source's file in the snapshot (a DataFrame of
    lightcurves_current.csv, or None) when that is another file, and without the sectors the source no longer has
    (stars the snapshot does not cover are left as they are)."""
    if current is None:
        return m
    now = {(int(r.tic), int(r.sector), r.prov): (r.uri, r.exptime) for r in current.itertuples()}
    seen = set(current.tic.astype(int))
    out = []
    for r in m.itertuples(index=False):
        r = r._asdict()
        if int(r["tic"]) in seen:
            hit = now.get((int(r["tic"]), int(r["sector"]), r["prov"]))
            if hit is None:
                continue
            if _name(hit[0]) != _name(r["uri"]):
                r["uri"], r["exptime"] = hit
        out.append(r)
    return pd.DataFrame(out, columns=m.columns)


def lists(tics, current_csv=CURRENT, root=ROOT):
    """The light-curve lists new work uses for the stars (COLS)."""
    m = manifest_rows(tics, root)[COLS]
    current = pd.read_csv(current_csv) if current_csv and os.path.exists(current_csv) else None
    return apply_snapshot(m, current)


def current_lists(searched_csv, current_csv, out_csv):
    m = apply_snapshot(pd.read_csv(searched_csv), pd.read_csv(current_csv) if os.path.exists(current_csv) else None)
    m.sort_values(["tic", "sector"]).to_csv(out_csv, index=False, lineterminator="\n")
    return m


def list_hash(rows):
    """Hash of a light-curve list: rows of (sector, ..., uri) or dicts with sector and uri; by sector and file name."""
    from dag.hashing import sha256_json
    pairs = sorted((int(r["sector"]), _name(r["uri"])) if isinstance(r, dict) else (int(r[0]), _name(r[-1])) for r in rows)
    return sha256_json(pairs)[:16]


def star_hashes(path):
    """{tic: list_hash} of a list file."""
    return {int(t): list_hash(g.to_dict("records")) for t, g in pd.read_csv(path).groupby("tic")}


def refresh(tics, out_csv=CURRENT):
    """The products at MAST now for the stars (index_products.query, in batches)."""
    from concurrent.futures import ThreadPoolExecutor
    import index_products
    ids = sorted(set(int(t) for t in tics))
    batches = [ids[i:i + index_products.BATCH] for i in range(0, len(ids), index_products.BATCH)]
    with ThreadPoolExecutor(4) as ex:
        parts = list(ex.map(index_products.query, batches))
    m = pd.concat(parts, ignore_index=True).rename(columns={"target_name": "tic", "provenance_name": "prov",
                                                            "sequence_number": "sector", "t_exptime": "exptime",
                                                            "dataURL": "uri"})
    m["tic"] = m["tic"].astype(int)
    m = m[m["uri"].str.endswith(("lc.fits", "llc.fits"))]
    m = m[m["prov"].isin(SOURCES) & ~((m["prov"] == "SPOC") & (m["exptime"] < 100))]   # SPOC 20 s: the searches use 120 s
    m = latest(m)[COLS].sort_values(["tic", "sector", "prov"])
    m["checked"] = date.today().isoformat()
    m.to_csv(out_csv, index=False, lineterminator="\n")
    return m


def redo(allsky_csv, earlier_csv, searched_csv, lists_csv, current_csv, fits_csv, triceratops_csv, out_csv, folder_tiers):
    """The catalog rows on stars whose lists differ (see the module's doc), with the stages to redo."""
    u, c = pd.read_csv(searched_csv), pd.read_csv(current_csv)
    now = {}
    for r in c.itertuples():
        now.setdefault(int(r.tic), {}).setdefault(int(r.sector), {})[r.prov] = _name(r.uri)
    star = {}
    for tic, g in u.groupby("tic"):
        b = now.get(int(tic))
        if b is None:
            continue
        x = dict(redelivered=[], removed=[], new=sorted(set(b) - set(g.sector.astype(int))))
        for r in g.itertuples():
            here = b.get(int(r.sector), {})
            if r.prov not in here:
                x["removed"].append(int(r.sector))
            elif here[r.prov] != _name(r.uri):
                x["redelivered"].append(int(r.sector))
        if any(x.values()):
            star[int(tic)] = x
    was, cur = star_hashes(searched_csv), star_hashes(lists_csv)
    made = {}
    for stage, path in (("fit", fits_csv), ("TRICERATOPS", triceratops_csv)):
        for r in csv.DictReader(open(path, newline="")):
            made[(stage, r["table"], r["TIC"], r["P_d"])] = r.get("lightcurves") or was.get(int(r["TIC"]))
    checked = str(c["checked"].iloc[0]) if "checked" in c and len(c) else ""
    out = []
    for table, path in (("candidates_allsky", allsky_csv), ("tiers_earlier_candidates", earlier_csv)):
        for r in csv.DictReader(open(path, newline="")):
            tic = int(r["TIC"])
            x = star.get(tic)
            stale = [s for s in ("fit", "TRICERATOPS") if (s, table, r["TIC"], r["P_d"]) in made
                     and made[(s, table, r["TIC"], r["P_d"])] != cur.get(tic)]
            if x is None and not stale:
                continue
            x = x or dict(redelivered=[], removed=[], new=[])
            stages = stale + (["search", "vetting", "pixel follow-up"] if x["redelivered"] or x["removed"] else
                              ["search update"] if x["new"] else [])
            out.append(dict(table=table, TIC=r["TIC"], P_d=r["P_d"], tier=r["tier"],
                            folder="yes" if table == "tiers_earlier_candidates" or r["tier"] in folder_tiers else "",
                            **{k: " ".join(map(str, sorted(v))) for k, v in x.items()}, redo=", ".join(stages),
                            checked=checked))
    cols = ["table", "TIC", "P_d", "tier", "folder", "redelivered", "removed", "new", "redo", "checked"]
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out


def stale_fits(redo_csv):
    """The rows whose fit was made from a light-curve list that is not the star's list now."""
    return [r for r in csv.DictReader(open(redo_csv, newline="")) if "fit" in r["redo"].split(", ")]


def main():
    if sys.argv[1:] != ["refresh"]:
        sys.exit(__doc__)
    tics = catalog_tics(os.path.join(ROOT, "results_public", "candidates_allsky.csv"),
                        os.path.join(ROOT, "results_public", "tiers_earlier_candidates.csv"))
    m = refresh(tics)
    print(f"{len(m)} products for {m.tic.nunique()} of {len(tics)} stars -> {os.path.relpath(CURRENT, ROOT)}")


if __name__ == "__main__":
    main()
