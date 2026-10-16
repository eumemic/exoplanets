"""When could the counted full-sky candidates have been found, and how strong are they in any one sector? For each
candidate in tiers A, B and N (the SNR >= 9 search), the search's per-transit depths give the SNR of the transits
observed by the end of a given sector (inverse-variance mean depth over its error), the best single-sector SNR, and
whether any sector with transits has a SPOC 2-minute light curve. Cutting the transits this way ignores how fewer
sectors would change the detrending and the period search. Built by the rules findability_transits, findability and
spoc_recheck in rules.py; the numbers validation/findability.md quotes come from findability.json and the recheck table.

- transits(): validation/findability_transits.csv.gz, one row per transit, from the search's candidate tables (column
  events): each candidate's transits come from the pass that found it (catalog column `search`: the full-sky search's
  tables, or the QLP re-search's), with the sector from data/tess_schedule/TESS_orbit_times.csv
  (https://tess.mit.edu/public/files/TESS_orbit_times.csv) and the light-curve source of that sector from the
  candidate's vetting.json.
- summary(): validation/findability.csv (one row per candidate) and validation/findability.json (the counts, from the
  unrounded SNRs; the CSV rounds them to 0.01, which can move a signal at 8.996 across 9).
- recheck_table(): validation/spoc_2min_recheck.csv, the re-measurements in SPOC's 2-minute light curves
  (results_public/products/spoc_2min.csv, made by spoc_recheck.py) of the candidates with 2-minute data, with each
  candidate's tier and the search's SNR of its 2-minute transits through Sector 96.
"""
import json

import numpy as np
import pandas as pd

# ends of the prime mission, the first extended mission, years 5 and 6, and the second extended mission
CUTS = (26, 55, 69, 83, 96)


def sector_windows(schedule_csv):
    from astropy.time import Time
    s = pd.read_csv(schedule_csv, comment="#")
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


def transits(catalog_csv, cands_files, research_files, vetting_files, schedule_csv, out_csv, tiers, match_rel):
    a = pd.read_csv(catalog_csv)
    k = a[a.tier.isin(tiers)][["TIC", "P_d", "tier", "search"]]
    read = lambda fs: pd.concat([pd.read_csv(f, usecols=["tic", "period", "events"]) for f in fs], ignore_index=True)
    c = read(cands_files)
    c = c[c.tic.isin(k.TIC)]
    cr = read(research_files) if research_files else c.iloc[:0]
    cr = cr[cr.tic.isin(k.TIC)]
    prov = {}
    for f in vetting_files:
        j = json.load(open(f))
        prov.setdefault(j["tic"], []).append((j["period"], {s["sector"]: s["prov"] for s in j.get("per_sector") or []}))
    win = sector_windows(schedule_csv)
    rows, missing = [], []
    for r in k.itertuples():
        src = cr if r.search == "QLP re-search" else c
        m = src[(src.tic == r.TIC) & ((src.period / r.P_d - 1).abs() < match_rel)]
        if not len(m):
            missing.append(f"TIC {r.TIC} P {r.P_d}")
            continue
        m = m.iloc[(m.period / r.P_d - 1).abs().argmin()]
        pv = next((v for p, v in prov.get(r.TIC, []) if abs(p / r.P_d - 1) < match_rel), {})
        for epoch, t, depth, err, cov in json.loads(m.events):
            s = sector_of(t, win)
            rows.append(dict(TIC=r.TIC, P_d=r.P_d, tier=r.tier, search=r.search, epoch=epoch, t_btjd=t,
                             depth_ppm=depth, err_ppm=err, coverage=cov, sector=s, prov=pv.get(s, "")))
    if missing:
        raise ValueError(f"{len(missing)} candidates have no events in the search's tables: " + ", ".join(missing))
    out = pd.DataFrame(rows)
    # mtime 0: the same table always gives the same file
    out.to_csv(out_csv, index=False, compression={"method": "gzip", "mtime": 0})
    return out


def snr(d, e):
    w = 1 / e ** 2
    return float(np.sum(w * d) / np.sqrt(np.sum(w))) if len(d) else 0.0


def summary(transits_csv, out_csv):
    tr = pd.read_csv(transits_csv)
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
    x.round({c: 2 for c in x.columns if c.startswith(("snr", "best"))}).to_csv(out_csv, index=False)
    return numbers(x)


def numbers(x):
    """The counts validation/findability.md quotes, from the unrounded per-candidate table. Fractions are of all the
    candidates, except first_by_s96, which is of the first pass's."""
    n = len(x)
    cnt = lambda m: dict(n=int(m.sum()), frac=float(m.sum() / n))
    first, research = x.search == "full-sky search", x.search == "QLP re-search"
    late = (x.snr >= 9) & (x.snr_to_s96 < 9)
    below = x[x.snr < 9]
    return dict(
        candidates=n, first=int(first.sum()), research=int(research.sum()),
        sectors=dict(median=float(x.n_sectors.median()), p10=float(x.n_sectors.quantile(.1)),
                     p90=float(x.n_sectors.quantile(.9))),
        best_sector=dict(median=float(x.best_sector_snr.median()), below_7_1=cnt(x.best_sector_snr < 7.1),
                         below_9=cnt(x.best_sector_snr < 9)),
        through={str(c): cnt(x[f"snr_to_s{c}"] >= 9) for c in CUTS},
        late=dict(n=int(late.sum()), research=int((late & research).sum()), first=int((late & first).sum())),
        first_by_s96=float((x[first].snr_to_s96 >= 9).mean()),
        below_9=dict(n=len(below), min=float(below.snr.min()) if len(below) else None,
                     max=float(below.snr.max()) if len(below) else None),
        ffi_only=cnt(~x.two_min), two_min=int(x.two_min.sum()))


def recheck_table(measurements_csv, findability_csv, out_csv):
    """The recheck rows of the candidates with 2-minute data; a candidate without a measurement is left out (the check
    spoc_measured lists them)."""
    m = pd.read_csv(measurements_csv, dtype={"sectors_2min": str})
    f = pd.read_csv(findability_csv)
    f = f[f.two_min][["TIC", "P_d", "tier", "snr_2min_to_s96"]].rename(columns={"snr_2min_to_s96": "snr_search"})
    x = f.merge(m.drop(columns=["T0_BJD", "measured"]), on=["TIC", "P_d"], how="inner")
    cols = ["TIC", "P_d", "tier", "sectors_2min", "T14_h", "snr_search", "n_2min_transits", "edge_transits", "beta_T14",
            "snr_white", "box_h_white", "snr_red", "box_h_red", "snr_cdpp", "box_h_cdpp", "tces_on_star", "tces_on_transit"]
    x = x[cols].sort_values(["TIC", "P_d"])
    x.to_csv(out_csv, index=False, lineterminator="\n")
    return x


def recheck_numbers(recheck_csv):
    """The counts validation/findability.md quotes from the recheck table."""
    s = pd.read_csv(recheck_csv, dtype={"sectors_2min": str})
    rest = s[s.n_2min_transits >= 2]
    est = {k: dict(reach=int((rest[k] >= 7.1).sum()), max=float(rest[k].max()))
           for k in ("snr_search", "snr_white", "snr_red", "snr_cdpp")}
    top = rest.loc[rest.snr_red.idxmax()]
    sectors = top.sectors_2min.split(",")
    return dict(
        candidates=len(s), few=int((s.n_2min_transits < 2).sum()), rest=len(rest), **est,
        ratio_red=float((rest.snr_red / rest.snr_search).median()),
        ratio_white=float((rest.snr_white / rest.snr_search).median()),
        tces_on_star=int(s.tces_on_star.sum()), tces_on_transit=int(s.tces_on_transit.sum()),
        tce_on_transit_tics=sorted(int(t) for t in s[s.tces_on_transit > 0].TIC),
        strongest=dict(TIC=int(top.TIC), tier=str(top.tier), P_d=float(top.P_d), snr_red=float(top.snr_red),
                       snr_cdpp=float(top.snr_cdpp),
                       sectors=", ".join(sectors[:-1]) + " and " + sectors[-1] if len(sectors) > 1 else sectors[0]))


def recheck_problems(measurements_csv, findability_csv, transits_csv, catalog_csv, tol, last_sector=96):
    """{(TIC, P_d): reason} for each candidate with 2-minute data whose re-measurement is missing or used another
    ephemeris (tolerances as the freshness parameters) or other sectors than its SPOC 2-minute transit sectors through
    last_sector. spoc_recheck.py measures these."""
    import catalog_checks as cc
    m = pd.read_csv(measurements_csv, dtype={"sectors_2min": str}).set_index(["TIC", "P_d"])
    f = pd.read_csv(findability_csv)
    tr = pd.read_csv(transits_csv)
    tr = tr[(tr.prov == "SPOC") & (tr.sector <= last_sector)]
    want = {k: ",".join(str(s) for s in sorted(g.sector.unique())) for k, g in tr.groupby(["TIC", "P_d"])}
    cat = pd.read_csv(catalog_csv).set_index(["TIC", "P_d"])
    out = {}
    for k in zip(f[f.two_min].TIC, f[f.two_min].P_d):
        if k not in m.index:
            out[k] = "not measured"
            continue
        r, c = m.loc[k], cat.loc[k]
        diff = cc.same_ephemeris(dict(P=k[1], T0=r.T0_BJD, dur=r.T14_h), dict(P=k[1], T0=c.T0_BJD, dur=c.T14_h), tol)
        if str(r.sectors_2min) != want.get(k, "nan") and not (pd.isna(r.sectors_2min) and k not in want):
            diff.append(f"sectors {r.sectors_2min} -> {want.get(k, 'none')}")
        if diff:
            out[k] = "; ".join(diff)
    return out
