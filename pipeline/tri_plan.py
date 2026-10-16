"""results_public/products/triceratops_plan.csv: every catalog row whose tier can depend on TRICERATOPS
(catalog.needs_triceratops, column needed) or that shows a TRICERATOPS result, the inputs a current result must have run
with, and whether the result in use (triceratops.csv) is current. Built by the rule triceratops_plan in rules.py; the
check triceratops_current fails while any row is pending (needed, and missing or out of date) or stale (shown in the
catalog but out of date), and the cloud runner (cloud.py) runs those rows.

The inputs of a signal, as every TRICERATOPS batch since 15 October has made them:
- the ephemeris and duration: the catalog's (full sky) or the transit registry's (earlier searches), and the depth;
- masks: every other signal on the star, from both tables and the TOI catalog (data/known/toi.csv), as
  "P,t0 (BTJD),duration (h)" joined by ";";
- drop: the eclipsing-binary scenarios on the target ("EB,EBx2P") where Gaia's radial velocities exclude them.
A result is current while its ephemeris, duration and depth match within the freshness tolerances and every other
catalog signal of the star is masked at its current ephemeris (masks of TOIs are not compared: the TOI catalog is a
dated snapshot, and a TOI's period is not ours to keep current), and its fold was made from the star's light-curve
list now (lcindex.py: a result that did not record its list was made from the searched list), and the code and
packages of its stages are those now (stage_code.py; a legacy result did not record them). Status: current, legacy
(current, from a batch that did not keep all of its inputs), or pending with the reason.
"""
import csv
import json
import math
import os

import catalog
import catalog_checks as cc

COLUMNS = ["table", "TIC", "P_d", "tier", "needed", "key", "tic", "period", "t0", "duration_h", "depth_ppm", "masks", "drop",
           "status", "reason"]
RV_EXCLUDES_EB = "Gaia RVs exclude an EB on the target"


def _rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def known_signals(allsky, earlier, eph, toi, match_rel):
    """{tic: [(P, t0 BTJD, duration h, source)]}: the catalog's signals (the registry's ephemeris for the earlier
    searches) and the TOIs with a period, epoch and duration."""
    out = {}
    for r in allsky:
        out.setdefault(int(r["TIC"]), []).append((_f(r["P_d"]), _f(r["T0_BJD"]) - 2457000, _f(r["T14_h"]), "catalog"))
    for r in earlier:
        e = _registry(eph, r, match_rel)
        if e:
            out.setdefault(int(r["TIC"]), []).append((_f(e["period_d"]), _f(e["T0_BJD_TDB"]) - 2457000, _f(e["duration_h"]), "catalog"))
    for t in toi:
        p, t0, d = _f(t.get("Period (days)")), _f(t.get("Epoch (BJD)")), _f(t.get("Duration (hours)"))
        if p > 0 and math.isfinite(t0) and math.isfinite(d):
            out.setdefault(int(float(t["TIC ID"])), []).append((p, t0 - 2457000, d, "toi"))
    return out


def _registry(eph, r, match_rel):
    hits = [e for e in eph.get(int(r["TIC"]), []) if abs(_f(e["period_d"]) / _f(r["P_d"]) - 1) < match_rel]
    return hits[0] if hits else None


def item(table, r, eph, signals, match_rel):
    """The inputs a TRICERATOPS run of this row takes (the columns of an fpp_fleet.py signal list)."""
    if table == "candidates_allsky":
        P, t0, dur, depth = _f(r["P_d"]), _f(r["T0_BJD"]) - 2457000, _f(r["T14_h"]), r["depth_ppm"]
    else:
        e = _registry(eph, r, match_rel)
        if e is None:
            return None
        P, t0, dur, depth = _f(e["period_d"]), _f(e["T0_BJD_TDB"]) - 2457000, _f(e["duration_h"]), e["depth_ppm"]
    tic = int(r["TIC"])
    others = [s for s in signals.get(tic, []) if abs(s[0] / P - 1) > match_rel]
    return dict(key=f"tic{tic}_P{P:.4f}", tic=tic, period=repr(P), t0=repr(t0), duration_h=repr(dur), depth_ppm=depth,
                masks=";".join(f"{p:.7f},{t:.6f},{d:.3f}" for p, t, d, _ in others),
                drop="EB,EBx2P" if r["rv_flag"] == RV_EXCLUDES_EB else "", _others=others)


def status(it, used, tol, match_rel, lists=None, code_now=None):
    """(status, reason) of the result in use against the inputs the row needs now; lists: ({tic: hash of the searched
    list}, {tic: hash of the list now}) (lcindex.star_hashes); code_now: {kind: hash} (stage_code.json)."""
    if used is None:
        return "pending", "no result"
    cur = dict(P=_f(it["period"]), T0=_f(it["t0"]) + 2457000, dur=_f(it["duration_h"]), depth=_f(it["depth_ppm"]))
    was = dict(P=_f(used["period"]), T0=_f(used["t0_btjd"]) + 2457000, dur=_f(used["duration_h"]), depth=_f(used["depth_ppm"]))
    diff = cc.same_ephemeris(was, cur, tol)
    masks = [tuple(map(float, m.split(","))) for m in used["masks"].split(";") if m]
    for p, t0, d, src in it["_others"]:
        if src != "catalog":
            continue
        hit = [m for m in masks if abs(m[0] / p - 1) < match_rel]
        if not hit:
            diff.append(f"the star's {p:.5f} d signal was not masked")
            continue
        dd = cc.same_ephemeris(dict(P=hit[0][0], T0=hit[0][1] + 2457000, dur=hit[0][2]), dict(P=p, T0=t0 + 2457000, dur=d), tol)
        if dd:
            diff.append(f"mask of the {p:.5f} d signal: " + ", ".join(dd))
    if (used["drop"] or "") != it["drop"]:
        diff.append(f"drop {used['drop'] or 'none'} -> {it['drop'] or 'none'}")
    if lists is not None:
        tic = int(it["tic"])
        if (used.get("lightcurves") or lists[0].get(tic)) != lists[1].get(tic):
            diff.append("light curves: the star's list has changed since it ran (redo.csv)")
    if code_now is not None:
        import stage_code
        ch = stage_code.changed(used.get("code"), code_now)
        if ch:
            diff.append(f"the code or packages of {', '.join(ch)} changed since it ran")
    if diff:
        return "pending", "; ".join(diff)
    return ("legacy" if used.get("legacy") == "yes" else "current"), ""


def build(allsky_csv, earlier_csv, ephemerides_csv, toi_csv, triceratops_csv, out_csv, P, tol, match_rel, lists=None,
          code_now=None):
    allsky, earlier = _rows(allsky_csv), _rows(earlier_csv)
    eph = {}
    for e in _rows(ephemerides_csv):
        eph.setdefault(int(e["TIC"]), []).append(e)
    with open(toi_csv, newline="") as fh:
        toi = list(csv.DictReader(line for line in fh if not line.startswith("#")))
    signals = known_signals(allsky, earlier, eph, toi, match_rel)
    used = {(r["table"], r["TIC"], r["P_d"]): r for r in _rows(triceratops_csv)}
    by_tic = {}
    for r in used.values():
        by_tic.setdefault((r["table"], r["TIC"]), []).append(r)

    def lookup(table, r):
        """The result in use for a catalog row: by its period, or (after a refit moved the published period away from
        the measurement table's) the result of the same star with the closest period within match_rel."""
        u = used.get((table, r["TIC"], r["P_d"]))
        if u is None:
            near = [(abs(_f(x["P_d"]) / _f(r["P_d"]) - 1), x) for x in by_tic.get((table, r["TIC"]), [])]
            near = [x for d, x in sorted(near, key=lambda t: t[0]) if d < match_rel]
            u = near[0] if near else None
        return u
    out = []
    for table, rows in (("candidates_allsky", allsky), ("tiers_earlier_candidates", earlier)):
        for r in rows:
            need, u = catalog.needs_triceratops(r, P, table), lookup(table, r)
            if not need and u is None:
                continue
            it = item(table, r, eph, signals, match_rel)
            if it is None:
                st, why = "pending", "not in the transit registry (no ephemeris)"
                it = dict(key="", tic=r["TIC"], period="", t0="", duration_h="", depth_ppm="", masks="", drop="")
            else:
                st, why = status(it, u, tol, match_rel, lists, code_now)
            if not need and st == "pending":
                st = "stale"
            out.append(dict({k: v for k, v in it.items() if not k.startswith("_")}, table=table, TIC=r["TIC"], P_d=r["P_d"],
                            tier=r["tier"], needed="yes" if need else "", status=st, reason=why))
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out


def items(keys, allsky_csv, earlier_csv, ephemerides_csv, toi_csv, match_rel):
    """The inputs of named signal keys of either table, whether or not the plan lists them (for runs the tiers do not
    need, such as contrast-curve runs of a tier C signal quoted in a draft). {key: item}."""
    allsky, earlier = _rows(allsky_csv), _rows(earlier_csv)
    eph = {}
    for e in _rows(ephemerides_csv):
        eph.setdefault(int(e["TIC"]), []).append(e)
    with open(toi_csv, newline="") as fh:
        toi = list(csv.DictReader(line for line in fh if not line.startswith("#")))
    signals = known_signals(allsky, earlier, eph, toi, match_rel)
    out = {}
    folders = os.path.join(os.path.dirname(os.path.abspath(earlier_csv)), "..", "candidates")
    for table, rows in (("candidates_allsky", allsky), ("tiers_earlier_candidates", earlier)):
        for r in rows:
            it = item(table, r, eph, signals, match_rel)
            fit = os.path.join(folders, r.get("candidate_id", ""), "transit_fit.json")
            if it is None and table == "tiers_earlier_candidates" and os.path.exists(fit):
                with open(fit) as fh:                # not registered (never counted): the folder's transit fit
                    j = json.load(fh)
                e = dict(period_d=j["P"][1], T0_BJD_TDB=j["t0"][1] + 2457000, duration_h=round(j["T14_h"][1], 2),
                         depth_ppm=round(j["depth_ppm"]))
                it = item(table, r, {int(r["TIC"]): [e]}, signals, match_rel)
            if it and it["key"] in keys:
                out[it["key"]] = {k: v for k, v in it.items() if not k.startswith("_")}
    return out
