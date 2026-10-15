"""Is the mean of a signal's per-sector difference-image centroids consistent with the target, and with which other star?
Reads the per-sector centroids of centroid_sectors.py (offsets east and north of the target, arcsec) and, for each
signal, tests whether the mean offset over sectors is consistent with the target and with each TIC star within 2'
that is bright enough to cause the dip (a total eclipse of that star would dilute to at least the observed depth).
TIC entries flagged ARTIFACT or DUPLICATE are not stars (Paegert et al. 2021) and are left out when the stars file
has their dispositions (--add-dispositions looks them up).

The test treats the per-sector offsets as scattered isotropically about the source with a common, unknown spread:
F = (n |mean - s|^2 / 2) / (RSS / (2(n - 1))) follows F(2, 2(n - 1)) if the source is at s, where RSS is the
scatter of the n offsets about their mean (floored at FLOOR arcsec per axis, since the PRF fits have systematic
errors of about that size even at high SNR). It needs at least 2 sectors. The false-alarm rate of the target test
is measured on confirmed and known planets, and its power on signals known to come from neighbouring stars.

Usage: python centroid_test.py [--dir ../results/cs]
With --dir, reads the JSON files of centroid_sectors.py and also writes their contents as
validation/centroid_sectors_per_sector.csv.gz (one row per sector, failed sectors with an error) and
validation/centroid_sectors_stars.csv.gz (the TIC stars within 2' of each target, offsets in arcsec); without it,
reads those two files, so the test can be rerun from the repository alone. The signals are those of
validation/centroid_sectors_list.csv. Writes validation/centroid_sectors.csv (one row per signal).
"""
import argparse
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import f as f_dist

ROOT = Path(__file__).resolve().parent.parent
FLOOR = 1.0                      # arcsec per axis
MAX_OFFSET = 60.0                # a fit this far from the target failed; such sectors are dropped
PHANTOM = ("ARTIFACT", "DUPLICATE")


def p_source(v, s, floor=FLOOR):
    n = len(v)
    if n < 2:
        return np.nan
    m = v.mean(axis=0)
    rss = max(float(np.sum((v - m) ** 2)), 2 * (n - 1) * floor ** 2)
    F = (n * float(np.sum((m - s) ** 2)) / 2) / (rss / (2 * (n - 1)))
    return float(f_dist.sf(F, 2, 2 * (n - 1)))


def load_json(L, d):
    """Per-sector rows and star rows from the JSON files of centroid_sectors.py."""
    per, stars = [], []
    for key in L.key:
        f = Path(d) / f"{key}.json"
        if not f.exists():
            continue
        j = json.load(open(f))
        for s in j.get("sectors", []):
            per.append(dict(key=key, sector=s["sector"], east=round(s["east"], 3), north=round(s["north"], 3),
                            quality=round(s["quality"], 3), offset_arc=round(s["offset_arc"], 3), error=""))
        for sec, err in (j.get("errors") or {}).items():
            per.append(dict(key=key, sector=int(sec), error=err))
        if "fatal" in j:
            per.append(dict(key=key, error=j["fatal"]))
        for st in j.get("stars") or []:
            stars.append(dict(key=key, **st))
    return pd.DataFrame(per), pd.DataFrame(stars)


def add_dispositions(L, stars):
    """TIC disposition of every star that could cause a signal's dip (the only ones the test uses), from MAST."""
    from astroquery.mast import Catalogs
    t = stars.merge(L[["key", "tic", "depth_ppm"]].rename(columns={"tic": "host"}), on="key")
    t0 = t[t.tic == t.host].set_index("key").Tmag
    cap = t[(t.tic != t.host) & (10 ** (-0.4 * (t.Tmag - t.key.map(t0))) >= t.depth_ppm * 1e-6)]
    ids = sorted(set(cap.tic.astype(int)))
    disp = {}
    for i in range(0, len(ids), 500):
        q = Catalogs.query_criteria(catalog="TIC", ID=ids[i:i + 500]).to_pandas()
        disp.update(zip(q.ID.astype(int), q.disposition))
    stars["disposition"] = stars.tic.map(disp)
    return stars


def analyse(L, per, stars, floor=FLOOR):
    rows = []
    P = {k: g for k, g in per.groupby("key")}
    S = {k: g for k, g in stars.groupby("key")}
    for r in L.itertuples():
        if r.key not in P:
            continue
        g = P[r.key]
        ok = g[(g.error.fillna("") == "") & g.east.notna()]
        ok = ok[np.hypot(ok.east, ok.north) <= MAX_OFFSET]
        v = ok[["east", "north"]].to_numpy(float)
        st = S.get(r.key, pd.DataFrame(columns=["tic", "east", "north", "sep", "Tmag"]))
        if "disposition" in st:                  # TIC artifacts and duplicates are not stars (Paegert et al. 2021)
            st = st[~st["disposition"].isin(PHANTOM)]
        tgt = st[st.tic == r.tic]
        t_mag = float(tgt.Tmag.iloc[0]) if len(tgt) else np.nan
        cap = st[(st.tic != r.tic) & (10 ** (-0.4 * (st.Tmag - t_mag)) >= r.depth_ppm * 1e-6)]
        m = v.mean(axis=0) if len(v) else np.array([np.nan, np.nan])
        row = dict(key=r.key, set=r.set, tier=r.tier, tic=r.tic, P_d=r.P_d, n_sectors=len(v),
                   n_failed=int((g.error.fillna("") != "").sum()), mean_east=m[0], mean_north=m[1],
                   offset=float(np.hypot(*m)), pa_deg=float(np.degrees(np.arctan2(m[0], m[1])) % 360) if len(v) else np.nan,
                   scatter=float(np.sqrt(np.sum((v - m) ** 2) / (2 * (len(v) - 1)))) if len(v) > 1 else np.nan,
                   p_target=p_source(v, np.zeros(2), floor), n_capable=len(cap))
        if len(cap) and len(v) >= 2:
            ps = np.array([p_source(v, np.array([c.east, c.north]), floor) for c in cap.itertuples()])
            k = int(np.argmax(ps))
            row.update(best_neighbour=int(cap.tic.iloc[k]), best_neighbour_sep=float(cap.sep.iloc[k]),
                       best_neighbour_Tmag=float(cap.Tmag.iloc[k]), p_best_neighbour=float(ps[k]),
                       n_neighbours_consistent=int((ps >= 0.01).sum()))
        if r.set == "cal_neighbour" and len(v) >= 2:
            src = st[st.tic == r.source_tic]
            row["p_source"] = p_source(v, src[["east", "north"]].to_numpy(float)[0], floor) if len(src) else np.nan
            row["source_sep"] = float(src.sep.iloc[0]) if len(src) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default=str(ROOT / "validation" / "centroid_sectors_list.csv"))
    ap.add_argument("--dir", help="JSON files of centroid_sectors.py")
    ap.add_argument("--floor", type=float, default=FLOOR)
    ap.add_argument("--add-dispositions", action="store_true",
                    help="look up the TIC disposition of every capable star and store it in the stars file")
    a = ap.parse_args()
    L = pd.read_csv(a.list)
    V = ROOT / "validation"
    if a.dir:
        per, stars = load_json(L, a.dir)
        per.to_csv(V / "centroid_sectors_per_sector.csv.gz", index=False)
        stars.to_csv(V / "centroid_sectors_stars.csv.gz", index=False)
    else:
        per = pd.read_csv(V / "centroid_sectors_per_sector.csv.gz")
        stars = pd.read_csv(V / "centroid_sectors_stars.csv.gz")
    if a.add_dispositions:
        stars = add_dispositions(L, stars)
        stars.to_csv(V / "centroid_sectors_stars.csv.gz", index=False)
    x = analyse(L, per, stars, a.floor)
    x.round(4).to_csv(V / "centroid_sectors.csv", index=False)
    t = x[x.n_sectors >= 2]
    print(f"signals {len(x)}, with >= 2 sectors {len(t)}; floor {a.floor} arcsec")
    for s, g in t.groupby("set"):
        line = f"{s:14s} n={len(g):4d}  p_target < 0.01: {(g.p_target < 0.01).mean():6.1%}  < 0.001: {(g.p_target < 0.001).mean():6.1%}"
        if s == "cal_neighbour":
            line += f"  source consistent (p >= 0.01): {(g.p_source >= 0.01).mean():.1%}"
        print(line)
    c = t[t.set == "cal_target"]
    print("known planets, target rejected at p < 0.001 by number of sectors:",
          {k: f"{(g.p_target < 0.001).sum()}/{len(g)}" for k, g in c.groupby(pd.cut(c.n_sectors, [1, 2, 4, 8, 99]), observed=True)})
    nb = t[t.set == "cal_neighbour"]
    print("neighbour-caused signals by source separation (arcsec): target rejected at p < 0.001 / source consistent")
    for k, g in nb.groupby(pd.cut(nb.source_sep, [0, 15, 30, 60, 120]), observed=True):
        print(f"  {k}: n={len(g)}  {(g.p_target < 0.001).mean():.0%} / {(g.p_source >= 0.01).mean():.0%}")
    flagged = t[t.set.str.startswith("cand") & (t.p_target < 0.001)]
    print(f"candidates with the target rejected at p < 0.001: {len(flagged)}")
    print(flagged[["tic", "P_d", "tier", "n_sectors", "offset", "pa_deg", "scatter", "p_target", "best_neighbour",
                   "best_neighbour_sep", "best_neighbour_Tmag", "p_best_neighbour"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
