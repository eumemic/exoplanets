"""Match a signal against known planets/candidates/TCEs on the same star and on neighbours,
against published lists outside ExoFOP (literature.py), and against this project's own published
candidates (results_public/candidates*.csv), so a re-detection is not counted as new."""
from functools import lru_cache

import numpy as np
import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

from common import DATA, ROOT

K = DATA / "known"
HARMONICS = (1 / 3, 1 / 2, 2 / 3, 1, 3 / 2, 2, 3)
# Literature periods are numbers scraped from paper text, so only close aliases count.
HARMONICS_LIT = (1 / 2, 1, 2)
# epoch_check: a known period p/q times ours (q <= EPOCH_MAX_Q, within EPOCH_RATIO_TOL) is an alias of the same signal
EPOCH_MAX_Q = 7
EPOCH_RATIO_TOL = 1e-3


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
    # transit epochs in BTJD, for epoch_check (the planet table has none)
    toi["t0"] = toi["Epoch (BJD)"] - 2457000
    ctoi["t0"] = ctoi["Transit Epoch (BJD)"] - 2457000
    ps["t0"] = ps["pl_tranmid"] - 2457000 if "pl_tranmid" in ps else np.nan
    tce["t0"] = tce["tce_time0bt"]
    out = {}
    for name, df, label in (("toi", toi, "TOI"), ("ctoi", ctoi, "CTOI"),
                            ("planet", ps, "pl_name"), ("tce", tce, "file")):
        d = df[["tic", "period", "ra_deg", "dec_deg", "t0"]].copy()
        d["label"] = df[label].astype(str).values
        d = d[np.isfinite(d["tic"])]
        d["tic"] = d["tic"].astype(np.int64)
        out[name] = d.reset_index(drop=True)
    if (K / "literature.parquet").exists():
        out["literature"] = pd.read_parquet(K / "literature.parquet")
    ours = [pd.read_csv(f, usecols=["TIC", "P_d"]).assign(label=f.stem)
            for f in sorted((ROOT / "results_public").glob("candidates*.csv"))]
    if ours:
        d = pd.concat(ours).rename(columns={"TIC": "tic", "P_d": "period"})
        d["ra_deg"], d["dec_deg"] = np.nan, np.nan
        out["ours"] = d[["tic", "period", "ra_deg", "dec_deg", "label"]].reset_index(drop=True)
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


def simple_ratio(r, max_q=EPOCH_MAX_Q, tol=EPOCH_RATIO_TOL):
    """(p, q) with p/q within tol of r and q <= max_q, or None."""
    for q in range(1, max_q + 1):
        p = round(r * q)
        if p >= 1 and abs(r * q / p - 1) < tol:
            return p, q
    return None


def epoch_check(tic, period, t0, dur_h, ra, dec, period_err=None, span=None, radius_arcmin=2.5, skip=()):
    """Known objects (TOIs, CTOIs, TCEs, planets with an epoch) on this TIC or within radius_arcmin whose epoch falls
    inside one of this signal's transits and whose period is missing (a single transit) or a simple ratio p/q of ours
    that is not one of HARMONICS (check() reports those): single-transit CTOIs and long-period aliases built from two
    or three transits. t0 in BTJD. The window is half the duration plus 3 sigma of the period error propagated to the
    known epoch; without period_err, the period is taken to be known to half a duration over `span` days."""
    res = {"same_star_epoch_match": [], "neighbour_epoch_match": []}
    half = 0.5 * dur_h / 24
    if period_err is None:
        period_err = half * period / span / 3 if span and span > period else 0.0
    for name, d in tables().items():
        if name in skip or "t0" not in d:
            continue
        same = (d["tic"] == tic).values
        near = (np.abs(d["dec_deg"] - dec) < radius_arcmin / 60).values & ~same
        d, same = d[same | near], same[same | near]
        if not len(d):
            continue
        sep = SkyCoord(d["ra_deg"].values * u.deg, d["dec_deg"].values * u.deg).separation(
            SkyCoord(ra * u.deg, dec * u.deg)).arcmin
        for (_, r), s, is_same in zip(d.iterrows(), sep, same):
            if not np.isfinite(r["t0"]) or not (is_same or s < radius_arcmin):
                continue
            n = np.round((r["t0"] - t0) / period)
            if abs(r["t0"] - t0 - n * period) > half + 3 * period_err * abs(n):
                continue
            if np.isfinite(r["period"]) and r["period"] > 0:
                if period_match(period, r["period"]) is not None:
                    continue
                pq = simple_ratio(r["period"] / period)
                if pq is None:
                    continue
                how = f"x{pq[0]}/{pq[1]}" if pq[1] > 1 else f"x{pq[0]}"
            else:
                how = "single transit"
            if is_same:
                res["same_star_epoch_match"].append(f"{name}:{r['label']}:P={r['period']:.4f}:{how}")
            else:
                res["neighbour_epoch_match"].append(f"{name}:TIC{r['tic']}:{r['label']}:{s:.2f}':{how}")
    return res
