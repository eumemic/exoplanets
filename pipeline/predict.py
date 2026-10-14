"""Predicted transit times for every counted candidate (tiers A, B, N and L1 of the full-sky search, tiers A and
B of the earlier searches), with 1-sigma uncertainties, flagged where they fall inside published TESS orbit
windows. Committing these files before the data exist makes the predictions a timestamped, falsifiable test.

The fitted t0 is usually the first transit in the data, where t0 and P are strongly correlated, so adding their
marginal errors in quadrature would misstate the uncertainty. Instead the errors are propagated from the
information-weighted centre of the transits t_c (sector weights 1/err^2 from the per-sector depths in
vetting.json), where the correlation vanishes: sigma(t)^2 = sigma_c^2 + ((t - t_c) / P)^2 sigma_P^2. sigma_c is
the larger of two estimates: the t0 marginal with the period term removed, and sigma_P times the weighted
spread of the transit epochs (the variance of a linear ephemeris fit).

The files are append-only: candidates registered by an earlier run keep their rows unchanged (only the tier column
is updated, so candidates that leave the counted tiers stay listed with their new tier), and newly counted candidates
are added with predictions starting at the time of the run.

Usage: python predict.py [--until 2027-06-30]
Reads results_public/, candidates/ (fits and vetting), data/catalogs/*.parquet (coordinates) and
data/tess_schedule/TESS_orbit_times.csv (https://tess.mit.edu/public/files/TESS_orbit_times.csv). Writes
candidates/ephemerides.csv (one row per candidate) and candidates/predictions.csv (one row per transit).
"""
import argparse
import glob
import json

import astropy.units as u
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from astropy.coordinates import EarthLocation, SkyCoord
from astropy.time import Time
from tess_stars2px import tess_stars2px_function_entry as ts2px

from common import CAT, DATA, ROOT

COUNTED = [("candidates_allsky.csv", "candidates/allsky", ("A", "B", "N", "L1")),
           ("tiers_earlier_candidates.csv", "candidates", ("A", "B"))]


def orbit_windows():
    """One row per orbit segment (BTDB); the schedule times are UTC."""
    w = pd.read_csv(DATA / "tess_schedule" / "TESS_orbit_times.csv", comment="#")
    lo = Time(list(w["Start of Orbit"]), scale="utc").tdb.jd - 2457000
    hi = Time(list(w["End of Orbit"]), scale="utc").tdb.jd - 2457000
    return pd.DataFrame(dict(sector=w["Sector"].astype(int), lo=lo, hi=hi))


def planned_sectors(sectors, first_sector, last_sector):
    """Real TESS sectors on the schedule among the sectors tess-point returns for a star.

    tess-point also returns special pointings numbered from 1751 (the 3I/ATLAS pointing in 0.9.5.post1), which
    are not regular sectors and are absent from the orbit schedule. Bounding the sectors above by the last
    sector of the schedule drops them, and any later special pointing, without a list of their numbers.
    """
    return sorted(set(int(x) for x in sectors if first_sector <= x <= last_sector))


def coordinates(tics):
    out = []
    for f in sorted(CAT.glob("*.parquet")):
        if {"ID", "ra", "dec", "Tmag"} <= set(pq.read_schema(f).names):
            d = pd.read_parquet(f, columns=["ID", "ra", "dec", "Tmag"])
            out.append(d[d["ID"].isin(tics)])
    return pd.concat(out).drop_duplicates("ID").set_index("ID")


def load_fit(folder, tic, P):
    """The fit and vetting files in the candidate's folder (folder names round the search period)."""
    dirs = glob.glob(str(ROOT / folder / f"TIC{tic}_P*"))
    fits = [(d, json.load(open(f"{d}/transit_fit.json"))) for d in dirs if glob.glob(f"{d}/transit_fit.json")]
    d, fit = min(fits, key=lambda x: abs(x[1]["P"][1] / P - 1))
    assert abs(fit["P"][1] / P - 1) < 5e-3, (tic, P, fit["P"][1])
    return fit, json.load(open(f"{d}/vetting.json"))


def centre(fit, vet, wins):
    """Information-weighted mean and variance of the transit times in the data (BTDB)."""
    P, t0 = fit["P"][1], fit["t0"][1]
    t, w = [], []
    for s in vet["per_sector"]:
        if not np.isfinite(s.get("err_ppm") or np.nan):
            continue
        tt = []
        for lo, hi in wins.loc[wins["sector"] == s["sector"], ["lo", "hi"]].values:
            tt += list(t0 + P * np.arange(np.ceil((lo - t0) / P), np.floor((hi - t0) / P) + 1))
        t += tt
        w += [1 / s["err_ppm"] ** 2 / max(len(tt), 1)] * len(tt)
    if not t:
        return t0, 0.0
    t, w = np.array(t), np.array(w)
    tc = np.sum(w * t) / np.sum(w)
    return tc, np.sum(w * (t - tc) ** 2) / np.sum(w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="2027-06-30")
    a = ap.parse_args()
    now = Time.now().tdb.jd - 2457000
    until = Time(a.until).tdb.jd - 2457000
    wins = orbit_windows()
    sector_end = wins.groupby("sector")["hi"].max()
    first_sector = int(sector_end[sector_end > now].index.min())
    last_sector = int(sector_end.index.max())
    cands = []
    for f, folder, tiers in COUNTED:
        c = pd.read_csv(ROOT / "results_public" / f)
        cands.append(c[c["tier"].isin(tiers)].assign(folder=folder))
    cands = pd.concat(cands, ignore_index=True)
    eph_f, pred_f = ROOT / "candidates" / "ephemerides.csv", ROOT / "candidates" / "predictions.csv"
    old_eph = pd.read_csv(eph_f) if eph_f.exists() else pd.DataFrame(columns=["TIC", "period_d"])
    old_rows = pd.read_csv(pred_f, dtype={"tess_sector": str}) if pred_f.exists() else pd.DataFrame()
    if "registered" not in old_eph:
        old_eph["registered"] = "2026-10-10"

    def match(tab, tic, P, col):
        return (tab["TIC"] == tic) & ((tab[col] / P - 1).abs() < 2e-3)

    cands = cands[[not match(old_eph, r.TIC, r.P_d, "period_d").any() for r in cands.itertuples()]]
    stars = coordinates(set(cands["TIC"]))
    geocentre = EarthLocation.from_geocentric(0, 0, 0, unit=u.m)
    eph, rows = [], []
    for r in cands.itertuples():
        fit, vet = load_fit(r.folder, r.TIC, r.P_d)
        P, t0 = fit["P"][1], fit["t0"][1]
        eP = (fit["P"][2] - fit["P"][0]) / 2
        et0 = (fit["t0"][2] - fit["t0"][0]) / 2
        tc, spread = centre(fit, vet, wins)
        var_c = max(et0 ** 2 - ((tc - t0) / P * eP) ** 2, spread / P ** 2 * eP ** 2)

        def sigma(t):
            return np.sqrt(var_c + ((t - tc) / P * eP) ** 2)

        star = stars.loc[r.TIC]
        on_star = planned_sectors(ts2px(r.TIC, star["ra"], star["dec"])[3], first_sector, last_sector)
        n_ref = round((tc - t0) / P)
        t_ref = t0 + n_ref * P
        n = np.arange(np.ceil((now - t_ref) / P), np.floor((until - t_ref) / P) + 1)
        t = t_ref + n * P
        # a transit counts as observed if its mid-time is inside an orbit segment of a sector that covers the star
        sec = np.zeros(len(t), int)
        for s, lo, hi in wins[wins["sector"].isin(on_star)].values:
            sec[(t >= lo) & (t <= hi)] = s
        bjd = Time(t + 2457000, format="jd", scale="tdb", location=geocentre)
        utc = (bjd - bjd.light_travel_time(SkyCoord(star["ra"], star["dec"], unit="deg"))).utc.iso
        for k in range(len(t)):
            rows.append(dict(TIC=r.TIC, tier=r.tier, period_d=round(P, 6), epoch=int(n[k]),
                             tc_BJD_TDB=round(t[k] + 2457000, 4), tc_UTC=utc[k][:16],
                             sigma_min=round(sigma(t[k]) * 1440, 1), duration_h=round(fit["T14_h"][1], 2),
                             tess_sector=sec[k] or ""))
        eph.append(dict(TIC=r.TIC, tier=r.tier, ra=round(star["ra"], 6), dec=round(star["dec"], 6),
                        Tmag=round(star["Tmag"], 2), period_d=round(P, 7), period_err_d=float(f"{eP:.2g}"),
                        T0_BJD_TDB=round(t_ref + 2457000, 5), T0_err_min=round(sigma(t_ref) * 1440, 1),
                        duration_h=round(fit["T14_h"][1], 2), depth_ppm=round(fit["depth_ppm"]),
                        Rp_Re=round(fit["Rp"][1], 2), next_tc_BJD_TDB=round(t[0] + 2457000, 4),
                        next_tc_sigma_min=round(sigma(t[0]) * 1440, 1),
                        tess_transits_scheduled=int((sec > 0).sum()),
                        tess_sectors_planned=",".join(map(str, on_star)), registered=Time.now().utc.iso[:10]))
    new_eph, new_rows = pd.DataFrame(eph), pd.DataFrame(rows)
    eph = pd.concat([old_eph, new_eph], ignore_index=True)
    rows = pd.concat([old_rows, new_rows], ignore_index=True)
    # current tier of every registered candidate, counted or not
    tiers = pd.concat([pd.read_csv(ROOT / "results_public" / f)[["TIC", "P_d", "tier"]] for f, _, _ in COUNTED])
    eph["tier"] = [next(iter(tiers.loc[match(tiers, r.TIC, r.period_d, "P_d"), "tier"]), r.tier) for r in eph.itertuples()]
    key = dict(zip(zip(eph["TIC"], eph["period_d"].round(5)), eph["tier"]))
    rows["tier"] = [key.get((t, round(P, 5)), x) for t, P, x in zip(rows["TIC"], rows["period_d"], rows["tier"])]
    eph.to_csv(eph_f, index=False)
    rows.to_csv(pred_f, index=False)
    print(f"{len(new_eph)} candidates added ({len(new_rows)} transits from now through {a.until}); {len(eph)} registered in all, "
          f"{int(eph['tier'].isin([t for _, _, ts in COUNTED for t in ts]).sum())} of them counted now")


if __name__ == "__main__":
    main()
