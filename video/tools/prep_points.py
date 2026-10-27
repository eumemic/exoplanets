"""Positions for the points the sky map highlights: the 546 candidates and the signals matching known
planets or candidates (TOIs, CTOIs, TCEs) that the full-sky search found again.

Writes public/data/points.json: {"candidates": [...], "known": [...], "labels": [...]}, positions in ecliptic
degrees.
usage: prep_points.py
"""
import json
import pathlib

import numpy as np
import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

REPO = pathlib.Path(__file__).resolve().parents[2]      # the repository root, which video/ sits in
ROOT = pathlib.Path(__file__).parent.parent

cat = pd.concat([pd.read_parquet(REPO / f"data/catalogs/shard{k}.parquet", columns=["ID", "ra", "dec", "Teff", "Tmag"])
                 for k in range(8)])
extra = []
for name in ["targets.parquet", "toi_hosts.parquet", "faint_t1.parquet", "faint_t2.parquet", "tce_hosts.parquet",
             "controls.parquet", "tic_small_dwarfs.parquet", "faint_targets.parquet"]:
    f = pd.read_parquet(REPO / "data/catalogs" / name)
    idc = "ID" if "ID" in f.columns else ("tic" if "tic" in f.columns else f.columns[0])
    if {"ra", "dec"} <= set(f.columns):
        extra.append(f.rename(columns={idc: "ID"})[["ID", "ra", "dec"] + [c for c in ["Teff", "Tmag"] if c in f.columns]])
    else:
        print(f"{name}: no ra/dec ({list(f.columns)[:12]})")
pos = pd.concat([cat] + extra).astype({"ID": "int64"}).drop_duplicates("ID").set_index("ID")


def ecl(df):
    df = df.join(pos, on="TIC", how="left")
    missing = df.ra.isna().sum()
    if missing:
        print(f"  {missing} without a position: {df.TIC[df.ra.isna()].tolist()[:20]}")
    c = SkyCoord(df.ra.to_numpy() * u.deg, df.dec.to_numpy() * u.deg).barycentrictrueecliptic
    df["lon"], df["lat"] = np.round(c.lon.deg, 4), np.round(c.lat.deg, 4)
    return df


full = pd.read_csv(REPO / "results_public/candidates_allsky.csv")
full = full[full.tier.isin(["M", "S", "N", "L1"])][["TIC", "P_d", "Rp_Re", "tier", "MES"]]
early = pd.read_csv(REPO / "results_public/tiers_earlier_candidates.csv")
early = early[early.tier.isin(["M", "S"])][["TIC", "P_d", "Rp_Re", "tier"]]
print(f"candidates: {len(full)} full-sky, {len(early)} earlier")
# tier L1 came from the weakest signals (SNR 7.5-9), picked out by the false-alarm classifier
full["src"] = np.where(full.tier == "L1", "filter", "allsky")
cands = ecl(pd.concat([full, early.assign(src="earlier")], ignore_index=True))
r = cands.Rp_Re
print(f"  radius 1-3.88 R_E: {((r >= 1) & (r <= 3.88)).sum()} of {len(cands)} ({((r >= 1) & (r <= 3.88)).mean():.1%}); "
      f"< 1: {(r < 1).sum()}; > 3.88: {(r > 3.88).sum()}; NaN: {r.isna().sum()}")

known = []
for d in ["shard0", "shard1", "shard2", "shard3", "shard4", "shard5", "shard6", "as"]:
    f = pd.read_csv(REPO / "results_cloud" / d / "cands_allsky.csv", usecols=["tic", "period", "snr", "known_status", "known_detail"])
    k = f[f.known_status == "known"]
    print(f"{d}: {len(f):,} signals past the pre-filters, {len(k):,} known")
    known.append(k)
known = pd.concat(known, ignore_index=True).rename(columns={"tic": "TIC"})
kind = known.known_detail.str.extract(r"^([a-z]+)")[0]
print(f"known matches: {len(known):,} signals on {known.TIC.nunique():,} stars; kinds {kind.value_counts().to_dict()}")
n_known = len(known)
known = ecl(known.drop_duplicates("TIC"))

labels = []
for name, tic in [("TOI-700", 150428135), ("L 98-59", 307210830), ("TIC 4206066", 4206066)]:
    row = ecl(pd.DataFrame({"TIC": [tic]})).iloc[0]
    labels.append({"name": name, "tic": tic, "lon": row.lon, "lat": row.lat})
print(labels)

out = {
    "candidates": [{"tic": int(t.TIC), "lon": t.lon, "lat": t.lat, "r": None if np.isnan(t.Rp_Re) else round(t.Rp_Re, 3),
                    "p": round(t.P_d, 4), "tier": t.tier, "src": t.src} for t in cands.itertuples()],
    "known": [[t.lon, t.lat] for t in known.itertuples() if not np.isnan(t.lon)],
    "known_signals": n_known,
    "labels": labels,
}
json.dump(out, open(ROOT / "public" / "data" / "points.json", "w"))
print(f"wrote {len(out['candidates'])} candidates, {len(out['known'])} known stars")
