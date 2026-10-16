"""The TIC entries near each catalog star that cannot be the source of a transit-like signal although their light is
real, as a dated snapshot: extended sources (galaxies, from the 2MASS extended source catalog) and the point sources the
TIC lists within 1" of a galaxy without a parallax (the galaxy's core as Gaia saw it). TIC artifacts and duplicates are
handled by their TIC disposition, which TRICERATOPS and the centroid measurements carry, so they are not listed here.

- results_public/products/tic_fields.csv: every catalog star whose TIC field (all entries within 2') has been checked,
  with the date (checked) and the number of entries, galaxies and cores found.
- results_public/products/tic_nonstellar.csv: the galaxies and cores: the catalog star (tic), the entry (id), kind
  (galaxy or core), its separation from the star (sep_arcsec), its T magnitude and the date.

TRICERATOPS's target setups (fpp_core.setup_target, through cloud.py) give the ones within NEARBY_ARCSEC no scenarios,
keeping their light in the aperture, and the per-sector centroid test (centroid_table.py) does not take any of them as
a possible source. The check tic_fields_complete fails while a catalog star has no checked field.

Usage: python ticfield.py refresh [--missing]   (queries MAST; --missing: only the stars not checked yet)
"""
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FIELDS = os.path.join(ROOT, "results_public", "products", "tic_fields.csv")
NONSTELLAR = os.path.join(ROOT, "results_public", "products", "tic_nonstellar.csv")
RADIUS_ARCMIN = 2.0
CORE_ARCSEC = 1.0
NEARBY_ARCSEC = 31.0          # TRICERATOPS evaluates neighbours within 30" (fpp_pool --nearby-max-arcsec)
FIELD_COLS = ["tic", "checked", "entries", "galaxies", "cores"]
NONSTELLAR_COLS = ["tic", "id", "kind", "sep_arcsec", "Tmag", "checked"]


def classify(field, tic):
    """The galaxies and cores among one star's TIC entries (a DataFrame with ID, ra, dec, Tmag, objType, plx, sep_arcsec)."""
    f = field[field.ID.astype(int) != int(tic)]
    gal = f[f.objType.astype(str).str.upper() == "EXTENDED"]
    out = [dict(id=int(g.ID), kind="galaxy", sep_arcsec=round(float(g.sep_arcsec), 2), Tmag=g.Tmag) for g in gal.itertuples()]
    pts = f[(f.objType.astype(str).str.upper() == "STAR") & f.plx.isna()]
    seen = set()
    for g in gal.itertuples():
        d = np.hypot((pts.ra - g.ra) * np.cos(np.radians(g.dec)), pts.dec - g.dec) * 3600
        for c in pts[d < CORE_ARCSEC].itertuples():
            if int(c.ID) not in seen:
                seen.add(int(c.ID))
                out.append(dict(id=int(c.ID), kind="core", sep_arcsec=round(float(c.sep_arcsec), 2), Tmag=c.Tmag))
    return out


def query(tic):
    """All TIC entries within RADIUS_ARCMIN of a star, with their separation from it."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Catalogs
    for k in range(6):
        try:
            t = Catalogs.query_criteria(catalog="Tic", ID=int(tic)).to_pandas().iloc[0]
            c = SkyCoord(t["ra"] * u.deg, t["dec"] * u.deg)
            nb = Catalogs.query_region(c, radius=RADIUS_ARCMIN * u.arcmin, catalog="TIC").to_pandas()
            nb = nb[["ID", "ra", "dec", "Tmag", "objType", "plx"]].copy()
            nb["sep_arcsec"] = SkyCoord(nb.ra.values * u.deg, nb.dec.values * u.deg).separation(c).arcsec
            return nb
        except Exception as ex:
            print(f"retry {tic} {k}: {ex}", file=sys.stderr, flush=True)
            time.sleep(10 * (k + 1))
    raise RuntimeError(f"TIC query failed for {tic}")


def write(fields, nonstellar, fields_csv=FIELDS, nonstellar_csv=NONSTELLAR):
    for path, rows, cols, key in ((fields_csv, fields, FIELD_COLS, ["tic"]),
                                  (nonstellar_csv, nonstellar, NONSTELLAR_COLS, ["tic", "id"])):
        df = pd.DataFrame(rows, columns=cols).sort_values(key)
        df.to_csv(path, index=False, lineterminator="\n")


def build(frames, checked):
    """fields and nonstellar rows from {tic: DataFrame of its TIC entries}."""
    fields, non = [], []
    for tic, f in sorted(frames.items()):
        rows = classify(f, tic)
        fields.append(dict(tic=int(tic), checked=checked, entries=int(len(f)), galaxies=sum(r["kind"] == "galaxy" for r in rows),
                           cores=sum(r["kind"] == "core" for r in rows)))
        non += [dict(r, tic=int(tic), checked=checked) for r in rows]
    return fields, non


def catalog_tics(allsky_csv, earlier_csv):
    return sorted({int(r["TIC"]) for f in (allsky_csv, earlier_csv) for r in csv.DictReader(open(f, newline=""))})


def not_hosts(nonstellar_csv, tic, max_arcsec=NEARBY_ARCSEC):
    """The galaxy and core entries within max_arcsec of a star, sorted."""
    rows = _rows(nonstellar_csv)
    return sorted(int(r["id"]) for r in rows if int(r["tic"]) == int(tic) and float(r["sep_arcsec"]) <= max_arcsec)


def by_star(nonstellar_csv, max_arcsec=None):
    """{tic: [entry ids]} of the galaxies and cores (within max_arcsec if given)."""
    out = {}
    for r in _rows(nonstellar_csv):
        if max_arcsec is None or float(r["sep_arcsec"]) <= max_arcsec:
            out.setdefault(int(r["tic"]), []).append(int(r["id"]))
    return {k: sorted(v) for k, v in out.items()}


def galaxy_neighbours(nonstellar_csv, catalog_csvs):
    """Catalog rows whose per-sector centroid test names a galaxy or a galaxy's core as the neighbour that fits best."""
    bad = by_star(nonstellar_csv)
    out = []
    for path in catalog_csvs:
        for r in _rows(path):
            n = str(r.get("cs_neighbour") or "")
            if n.isdigit() and int(n) in bad.get(int(r["TIC"]), []):
                out.append(f"TIC {r['TIC']} P {r['P_d']} ({r['tier']}): TIC {n}")
    return out


def problems(fields_csv, allsky_csv, earlier_csv):
    have = {int(r["tic"]) for r in _rows(fields_csv)}
    return [t for t in catalog_tics(allsky_csv, earlier_csv) if t not in have]


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    if sys.argv[1:2] != ["refresh"]:
        sys.exit(__doc__)
    tics = catalog_tics(os.path.join(ROOT, "results_public", "candidates_allsky.csv"),
                        os.path.join(ROOT, "results_public", "tiers_earlier_candidates.csv"))
    fields = [dict(r, tic=int(r["tic"])) for r in _rows(FIELDS)]
    non = [dict(r, tic=int(r["tic"]), id=int(r["id"])) for r in _rows(NONSTELLAR)]
    if "--missing" in sys.argv:
        have = {int(r["tic"]) for r in fields}
        tics = [t for t in tics if t not in have]
    else:
        fields, non = [], []
    with ThreadPoolExecutor(6) as ex:
        frames = dict(zip(tics, ex.map(query, tics)))
    f, n = build(frames, date.today().isoformat())
    keep = {int(t) for t in tics}
    write([r for r in fields if int(r["tic"]) not in keep] + f, [r for r in non if int(r["tic"]) not in keep] + n)
    print(f"{len(tics)} stars checked: {sum(r['galaxies'] for r in f)} galaxies and {sum(r['cores'] for r in f)} cores")


if __name__ == "__main__":
    main()
