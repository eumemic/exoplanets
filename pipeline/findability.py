"""When could the counted full-sky candidates have been found, and how strong are they in any one sector? For each
candidate in tiers A, B and N (the SNR >= 9 search), the search's per-transit depths give the SNR of the transits
observed by the end of a given sector (inverse-variance mean depth over its error), the best single-sector SNR, and
whether any sector with transits has a SPOC 2-minute light curve. Cutting the transits this way ignores how fewer
sectors would change the detrending and the period search.

Usage:
  python findability.py transits --cands ../results/allsky_*/cands_allsky.csv [--cands-research ../results/q*/cands_q*.csv]
      Writes validation/findability_transits.csv.gz, one row per transit, from the search's candidate tables (column
      events): each candidate's transits come from the pass that found it (catalog column `search`: the full-sky
      search's tables, or the QLP re-search's), with the sector from data/tess_schedule/TESS_orbit_times.csv
      (https://tess.mit.edu/public/files/TESS_orbit_times.csv) and the light-curve source of that sector from the
      candidate's vetting.json.
  python findability.py
      Reads validation/findability_transits.csv.gz, writes validation/findability.csv (one row per candidate) and
      prints the numbers quoted in validation/findability.md.
"""
import argparse
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TRANSITS = ROOT / "validation" / "findability_transits.csv.gz"
SUMMARY = ROOT / "validation" / "findability.csv"
# ends of the prime mission, the first extended mission, years 5 and 6, and the second extended mission
CUTS = (26, 55, 69, 83, 96)


def sector_windows():
    from astropy.time import Time
    s = pd.read_csv(ROOT / "data" / "tess_schedule" / "TESS_orbit_times.csv", comment="#")
    s = s.dropna(subset=["Start of Orbit", "End of Orbit"])
    s["t0"] = Time(list(s["Start of Orbit"])).jd - 2457000
    s["t1"] = Time(list(s["End of Orbit"])).jd - 2457000
    return s.groupby("Sector").agg(t0=("t0", "min"), t1=("t1", "max")).reset_index()


def sector_of(t, win):
    """The sector whose window contains t, else the nearest one."""
    inside = (win.t0.values <= t) & (win.t1.values >= t)
    if inside.any():
        return int(win.Sector.values[np.argmax(inside)])
    return int(win.Sector.values[np.argmin(np.minimum(np.abs(win.t0.values - t), np.abs(win.t1.values - t)))])


def build_transits(cands_files, research_files=()):
    a = pd.read_csv(ROOT / "results_public" / "candidates_allsky.csv")
    k = a[a.tier.isin(["A", "B", "N"])][["TIC", "P_d", "tier", "search"]]
    read = lambda fs: pd.concat([pd.read_csv(f, usecols=["tic", "period", "events"]) for f in fs], ignore_index=True)
    c = read(cands_files)
    c = c[c.tic.isin(k.TIC)]
    cr = read(research_files) if research_files else c.iloc[:0]
    cr = cr[cr.tic.isin(k.TIC)]
    prov = {}
    for f in glob.glob(str(ROOT / "candidates" / "allsky" / "*" / "vetting.json")):
        j = json.load(open(f))
        prov.setdefault(j["tic"], []).append((j["period"], {s["sector"]: s["prov"] for s in j.get("per_sector") or []}))
    win = sector_windows()
    rows = []
    for r in k.itertuples():
        src = cr if r.search == "QLP re-search" else c
        m = src[(src.tic == r.TIC) & ((src.period / r.P_d - 1).abs() < 2e-3)]
        if not len(m):
            print("no search events for TIC", r.TIC, r.P_d)
            continue
        m = m.iloc[(m.period / r.P_d - 1).abs().argmin()]
        pv = next((v for p, v in prov.get(r.TIC, []) if abs(p / r.P_d - 1) < 2e-3), {})
        for epoch, t, depth, err, cov in json.loads(m.events):
            s = sector_of(t, win)
            rows.append(dict(TIC=r.TIC, P_d=r.P_d, tier=r.tier, search=r.search, epoch=epoch, t_btjd=t,
                             depth_ppm=depth, err_ppm=err, coverage=cov, sector=s, prov=pv.get(s, "")))
    out = pd.DataFrame(rows)
    out.to_csv(TRANSITS, index=False)
    print(f"{len(out)} transits of {out.groupby(['TIC', 'P_d']).ngroups} candidates -> {TRANSITS.relative_to(ROOT)}")


def snr(d, e):
    w = 1 / e ** 2
    return float(np.sum(w * d) / np.sqrt(np.sum(w))) if len(d) else 0.0


def summary():
    tr = pd.read_csv(TRANSITS)
    tr = tr[tr.err_ppm > 0]
    rows = []
    for (tic, P, tier, search), g in tr.groupby(["TIC", "P_d", "tier", "search"]):
        d, e, s = g.depth_ppm.values, g.err_ppm.values, g.sector.values
        two = (g.prov == "SPOC").values
        rows.append(dict(TIC=tic, P_d=P, tier=tier, search=search, n_transits=len(g), n_sectors=len(set(s)), snr=snr(d, e),
                         best_sector_snr=max(snr(d[s == x], e[s == x]) for x in set(s)),
                         **{f"snr_to_s{n}": snr(d[s <= n], e[s <= n]) for n in CUTS},
                         two_min=bool(two.any()), n_2min_transits_to_s96=int((two & (s <= 96)).sum()),
                         snr_2min_to_s96=snr(d[two & (s <= 96)], e[two & (s <= 96)])))
    x = pd.DataFrame(rows)
    x.round({c: 2 for c in x.columns if c.startswith(("snr", "best"))}).to_csv(SUMMARY, index=False)
    n = len(x)
    pct = lambda k: f"{k} ({k / n:.0%})"
    print(f"{n} candidates (tiers A, B, N) -> {SUMMARY.relative_to(ROOT)}")
    print(f"sectors with transits: median {x.n_sectors.median():.0f} "
          f"(10-90%: {x.n_sectors.quantile(.1):.0f}-{x.n_sectors.quantile(.9):.0f})")
    print(f"best single-sector SNR: median {x.best_sector_snr.median():.1f}; "
          f"below 7.1: {pct((x.best_sector_snr < 7.1).sum())}; below 9: {pct((x.best_sector_snr < 9).sum())}")
    for c in CUTS:
        print(f"SNR >= 9 with the transits through Sector {c}: {pct((x[f'snr_to_s{c}'] >= 9).sum())}")
    print(f"SNR >= 9 only with Sectors 97+: {((x.snr >= 9) & (x.snr_to_s96 < 9)).sum()}; "
          f"SNR < 9 from these transits: {(x.snr < 9).sum()}")
    print(f"FFI only in the sectors with transits: {pct((~x.two_min).sum())}; with 2-minute data: {x.two_min.sum()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", nargs="?", default="summary", choices=["transits", "summary"])
    ap.add_argument("--cands", nargs="+", help="the full-sky search's candidate tables (transits step)")
    ap.add_argument("--cands-research", nargs="*", default=[], help="the QLP re-search's candidate tables")
    a = ap.parse_args()
    if a.step == "transits":
        build_transits(a.cands, a.cands_research)
    else:
        summary()
