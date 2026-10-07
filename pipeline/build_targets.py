"""Build the target list: small TIC dwarfs (from fetch_targets.py) that QLP observed in
Sectors 97-105, with Gaia Catalogue of Nearby Stars columns (RUWE etc.) attached where available.

Inputs (downloaded if missing): data/catalogs/tic_small_dwarfs.parquet (fetch_targets.py),
QLP target lists for Sectors 97-105, and the GCNS red-star subset from VizieR.
Output: data/catalogs/targets.parquet, sorted by distance.
"""
import numpy as np
import pandas as pd
import requests
from astropy import units as u
from astropy.coordinates import SkyCoord

from common import CAT, DATA

QLP_SECTORS = range(97, 106)
TEFF_MAX = 5300
GCNS_QUERY = ('SELECT t.GaiaEDR3, t.RA_ICRS, t.DE_ICRS, t.Plx, t.pmRA, t.pmDE, t."Gmag", t.BPmag, '
              't.RPmag, t.RUWE, t.IPDfmp, t.RV, t.e_RV FROM "J/A+A/649/A6/table1c" AS t '
              'WHERE t."Gmag" < 13.6 AND t.BPmag - t.RPmag > 0.85')


def qlp_lists():
    d = DATA / "qlp_target_lists"
    d.mkdir(parents=True, exist_ok=True)
    parts = []
    for s in QLP_SECTORS:
        f = d / f"s{s:04d}.csv"
        if not f.exists():
            r = requests.get(f"https://archive.stsci.edu/hlsps/qlp/target_lists/s{s:04d}.csv", timeout=600)
            r.raise_for_status()
            f.write_bytes(r.content)
        q = pd.read_csv(f, comment="#", header=None, names=["tic", "ra", "dec"], usecols=[0])
        q["sector"] = s
        parts.append(q)
    return pd.concat(parts, ignore_index=True)


def gcns():
    f = CAT / "gcns_red.csv"
    if not f.exists():
        r = requests.post("https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync",
                          data=dict(REQUEST="doQuery", LANG="ADQL", FORMAT="csv", MAXREC=1000000,
                                    QUERY=GCNS_QUERY), timeout=900)
        r.raise_for_status()
        f.write_bytes(r.content)
    return pd.read_csv(f)


def main():
    tic = pd.read_parquet(CAT / "tic_small_dwarfs.parquet")
    tic["ID"] = tic["ID"].astype(np.int64)
    q = qlp_lists()
    recent = q.groupby("tic")["sector"].apply(lambda s: ",".join(map(str, sorted(s)))).rename("qlp_recent")
    t = tic.merge(recent, left_on="ID", right_index=True, how="inner")
    t = t[((t["Teff"] <= TEFF_MAX) | t["Teff"].isna()) & (t["rad"] > 0.1)].copy()

    # Attach Gaia (GCNS, < 100 pc) astrometric-binarity columns by position at epoch 2000.
    g = gcns()
    dt = -16.0
    ra0 = g["RA_ICRS"] + np.nan_to_num(g["pmRA"]) * dt / 3.6e6 / np.cos(np.radians(g["DE_ICRS"]))
    de0 = g["DE_ICRS"] + np.nan_to_num(g["pmDE"]) * dt / 3.6e6
    idx, sep, _ = SkyCoord(t["ra"].values * u.deg, t["dec"].values * u.deg).match_to_catalog_sky(
        SkyCoord(ra0.values * u.deg, de0.values * u.deg))
    ok = sep.arcsec < 2.5
    for col, new in (("GaiaEDR3", "source_id"), ("Plx", "parallax"), ("RUWE", "ruwe"),
                     ("IPDfmp", "IPDfmp"), ("RV", "radial_velocity"), ("e_RV", "e_RV")):
        t[new] = np.where(ok, g[col].values[idx], np.nan)
    t["bp_rp"] = np.where(ok, (g["BPmag"] - g["RPmag"]).values[idx], np.nan)
    t["phot_g_mean_mag"] = np.where(ok, g["Gmag"].values[idx], np.nan)
    t = t.sort_values("d")
    t.to_parquet(CAT / "targets.parquet")
    print(f"{len(t)} targets ({ok.sum()} with GCNS columns) -> {CAT / 'targets.parquet'}")


if __name__ == "__main__":
    main()
