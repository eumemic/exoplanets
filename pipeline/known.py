"""Match a signal against known planets/candidates/TCEs on the same star and on neighbours, and
against published lists outside ExoFOP (literature.py)."""
from functools import lru_cache

import numpy as np
import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

from common import DATA

K = DATA / "known"
HARMONICS = (1 / 3, 1 / 2, 2 / 3, 1, 3 / 2, 2, 3)
# Literature periods are numbers scraped from paper text, so only close aliases count.
HARMONICS_LIT = (1 / 2, 1, 2)


def _sexa(ra, dec):
    c = SkyCoord(ra, dec, unit=(u.hourangle, u.deg))
    return c.ra.deg, c.dec.deg


@lru_cache(None)
def tables():
    toi = pd.read_csv(K / "toi.csv")
    toi["ra_deg"], toi["dec_deg"] = _sexa(toi["RA"].values, toi["Dec"].values)
    toi = toi.rename(columns={"TIC ID": "tic", "Period (days)": "period"})
    ctoi = pd.read_csv(K / "ctoi.csv")
    ctoi = ctoi.rename(columns={"TIC ID": "tic", "Period (days)": "period",
                                "RA": "ra_deg", "Dec": "dec_deg"})
    ps = pd.read_csv(K / "pscomppars.csv")
    ps["tic"] = pd.to_numeric(ps["tic_id"].astype(str).str.replace("TIC ", ""), errors="coerce")
    ps = ps.rename(columns={"pl_orbper": "period", "ra": "ra_deg", "dec": "dec_deg"})
    tce = pd.read_parquet(K / "tce_all.parquet").rename(columns={"ticid": "tic", "tce_period": "period"})
    try:
        pos = pd.read_parquet(K / "tce_tic.parquet")[["ID", "ra", "dec"]]
        pos = pos.rename(columns={"ID": "tic", "ra": "ra_deg", "dec": "dec_deg"})
        tce = tce.merge(pos, on="tic", how="left")
    except FileNotFoundError:
        tce["ra_deg"] = np.nan
        tce["dec_deg"] = np.nan
    out = {}
    for name, df, label in (("toi", toi, "TOI"), ("ctoi", ctoi, "CTOI"),
                            ("planet", ps, "pl_name"), ("tce", tce, "file")):
        d = df[["tic", "period", "ra_deg", "dec_deg"]].copy()
        d["label"] = df[label].astype(str).values
        d = d[np.isfinite(d["tic"])]
        d["tic"] = d["tic"].astype(np.int64)
        out[name] = d.reset_index(drop=True)
    if (K / "literature.parquet").exists():
        out["literature"] = pd.read_parquet(K / "literature.parquet")
    return out


def period_match(p1, p2, tol=0.003, harmonics=HARMONICS):
    """Return the harmonic ratio p2/p1 within tolerance, or None."""
    if not (np.isfinite(p1) and np.isfinite(p2)) or p2 <= 0:
        return None
    for h in harmonics:
        if abs(p2 / (p1 * h) - 1) < tol:
            return h
    return None


def check(tic, period, ra, dec, radius_arcmin=2.5, skip=()):
    """Known objects on this TIC (any period) and period matches on neighbours; tables named in
    `skip` (e.g. "tce" when the signals come from TCEs) are ignored."""
    res = {"same_star": [], "same_star_period_match": [], "neighbour_period_match": []}
    for name, d in tables().items():
        if name in skip:
            continue
        harm = HARMONICS_LIT if name == "literature" else HARMONICS
        same = d[d["tic"] == tic]
        for _, r in same.iterrows():
            h = period_match(period, r["period"], harmonics=harm)
            entry = f"{name}:{r['label']}" if name == "literature" else f"{name}:{r['label']}:P={r['period']:.4f}"
            if entry not in res["same_star"]:
                res["same_star"].append(entry)
            if h is not None and f"{name}:{r['label']}:x{h:.3g}" not in res["same_star_period_match"]:
                res["same_star_period_match"].append(f"{name}:{r['label']}:x{h:.3g}")
        near = d[(np.abs(d["dec_deg"] - dec) < radius_arcmin / 60) & (d["tic"] != tic)]
        if len(near):
            sep = SkyCoord(near["ra_deg"].values * u.deg, near["dec_deg"].values * u.deg).separation(
                SkyCoord(ra * u.deg, dec * u.deg)).arcmin
            for (_, r), s in zip(near.iterrows(), sep):
                if s < radius_arcmin:
                    h = period_match(period, r["period"], harmonics=harm)
                    if h is not None:
                        res["neighbour_period_match"].append(
                            f"{name}:TIC{r['tic']}:{r['label']}:{s:.2f}':x{h:.3g}")
    return res
