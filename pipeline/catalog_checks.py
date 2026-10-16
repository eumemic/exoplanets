"""Checks on the catalog's inputs that the build cannot correct by itself; each returns a list of problems (empty if
none). Run by the checks in rules.py.

- triceratops_inputs_current: every TRICERATOPS result the catalog uses ran on the signal's current ephemeris, depth and
  masks (the star's other signals at their current ephemerides). A refit after the run makes the result stale.
- counted_measured_centroids: every counted candidate has per-sector centroid measurements (the test itself needs at
  least two sectors).
- centroid_inputs_current: every centroid measurement in results_public/products/centroids.csv used the signal's
  current ephemeris.
- folders_complete: every full-sky row in a folder tier has its folder with the vetting files, and each folder's
  triceratops_gaia.json is there exactly when the row has a TRICERATOPS result, with the catalog's values.
- markdown_tables: every table in a document has as many cells in each row as in its header (GitHub does not show a
  table whose delimiter row differs).
"""
import csv
import math
import os


def _rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def _phase_min(t0a, t0b, period):
    """Offset between two epochs of the same period, in minutes, modulo the period."""
    return ((((t0a - t0b) / period) + 0.5) % 1 - 0.5) * period * 1440


def same_ephemeris(used, current, tol):
    """Differences beyond the tolerances between the ephemeris a result used and the current one, in words."""
    out = []
    if abs(used["P"] - current["P"]) > tol["period_d"]:
        out.append(f"period {used['P']} -> {current['P']}")
    ph = _phase_min(used["T0"], current["T0"], current["P"])
    if abs(ph) > tol["phase_min"]:
        out.append(f"epoch moved {ph:.2f} min")
    if abs(used["dur"] - current["dur"]) > tol["duration_h"]:
        out.append(f"duration {used['dur']} -> {current['dur']} h")
    if "depth" in current and abs(used["depth"] - current["depth"]) > tol["depth_ppm"]:
        out.append(f"depth {used['depth']} -> {current['depth']} ppm")
    return out


def triceratops_inputs_current(products_csv, measurements_allsky, ephemerides_csv, tol, match_rel):
    cat = {}
    for r in _rows(measurements_allsky):
        cat[("candidates_allsky", r["TIC"], r["P_d"])] = dict(P=_f(r["P_d"]), T0=_f(r["T0_BJD"]), dur=_f(r["T14_h"]),
                                                              depth=_f(r["depth_ppm"]))
    # every current signal by star, for the masks: the full-sky rows and the registered earlier-search signals
    by_star = {}
    for (_, tic, _), v in cat.items():
        by_star.setdefault(tic, []).append(v)
    reg = {}
    for r in _rows(ephemerides_csv):
        v = dict(P=_f(r["period_d"]), T0=_f(r["T0_BJD_TDB"]), dur=_f(r["duration_h"]), depth=_f(r["depth_ppm"]))
        reg.setdefault(r["TIC"], []).append(v)
    problems = []
    for p in _rows(products_csv):
        used = dict(P=_f(p["period"]), T0=_f(p["t0_btjd"]) + 2457000, dur=_f(p["duration_h"]), depth=_f(p["depth_ppm"]))
        key = (p["table"], p["TIC"], p["P_d"])
        if p["table"] == "candidates_allsky":
            current = cat[key]
            siblings = [v for v in by_star[p["TIC"]] if abs(v["P"] / current["P"] - 1) > match_rel]
        else:
            hits = [v for v in reg.get(p["TIC"], []) if abs(v["P"] / _f(p["P_d"]) - 1) < match_rel]
            if len(hits) != 1:
                problems.append(f"{p['table']} TIC {p['TIC']} P {p['P_d']}: {len(hits)} registry ephemerides match")
                continue
            current = hits[0]
            siblings = [v for v in reg.get(p["TIC"], []) if abs(v["P"] / current["P"] - 1) > match_rel]
        diff = same_ephemeris(used, current, tol)
        masks = [tuple(map(float, m.split(","))) for m in p["masks"].split(";") if m]
        for s in siblings:
            hit = [m for m in masks if abs(m[0] / s["P"] - 1) < match_rel]
            if not hit:
                diff.append(f"the star's {s['P']:.5f} d signal was not masked")
                continue
            d = same_ephemeris(dict(P=hit[0][0], T0=hit[0][1] + 2457000, dur=hit[0][2]), dict(P=s["P"], T0=s["T0"], dur=s["dur"]), tol)
            if d:
                diff.append(f"mask of the {s['P']:.5f} d signal: " + ", ".join(d))
        if diff:
            problems.append(f"{p['table']} TIC {p['TIC']} P {p['P_d']} ({p['batch']}): " + "; ".join(diff))
    return problems


def counted_measured_centroids(table_csv, counted):
    return [f"TIC {r['TIC']} P {r['P_d']} (tier {r['tier']}): no per-sector centroid measurement"
            for r in _rows(table_csv) if r["tier"] in counted and not r["cs_sectors"]]


def centroid_inputs_current(centroids_csv, measurements_allsky, tol):
    cat = {(r["TIC"], r["P_d"]): dict(P=_f(r["P_d"]), T0=_f(r["T0_BJD"]), dur=_f(r["T14_h"]))
           for r in _rows(measurements_allsky)}
    problems = []
    for c in _rows(centroids_csv):
        if c["table"] != "candidates_allsky":
            continue
        used = dict(P=_f(c["period"]), T0=_f(c["t0_btjd"]) + 2457000, dur=_f(c["duration_h"]))
        diff = same_ephemeris(used, cat[(c["TIC"], c["P_d"])], tol)
        if diff:
            problems.append(f"TIC {c['TIC']} P {c['P_d']} ({c['batch']}): " + "; ".join(diff))
    return problems


def markdown_tables(path):
    """Tables whose rows do not all have the header's number of cells (markers and code blocks excluded)."""
    import re
    problems, in_code = [], False
    lines = open(path).read().split("\n")
    i = 0
    while i < len(lines):
        if lines[i].startswith("```"):
            in_code = not in_code
        if not in_code and lines[i].startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            cells = lambda l: len(re.sub(r"<!--.*?-->", "", l).strip().strip("|").split("|"))
            n, j = cells(lines[i]), i + 1
            while j < len(lines) and lines[j].startswith("|"):
                if cells(lines[j]) != n:
                    problems.append(f"{path}:{j + 1}: {cells(lines[j])} cells, the header at line {i + 1} has {n}")
                j += 1
            i = j
            continue
        i += 1
    return problems


def folders_complete(root, catalog_csv, triceratops_csv, folder_tiers):
    import json
    base = os.path.join(root, "candidates", "allsky")
    have = set(os.listdir(base))
    tri = {(r["TIC"], r["P_d"]): r for r in _rows(triceratops_csv) if r["table"] == "candidates_allsky"}
    problems = []
    for r in _rows(catalog_csv):
        d = os.path.join(base, r["candidate_id"])
        if r["candidate_id"] not in have:
            if r["tier"] in folder_tiers:
                problems.append(f"{r['candidate_id']} (tier {r['tier']}): no folder")
            continue
        for f in ("vetting.json", "vetting.png", "followup.json"):
            if not os.path.exists(os.path.join(d, f)):
                problems.append(f"{r['candidate_id']}: no {f}")
        t = tri.get((r["TIC"], r["P_d"]))
        g = os.path.join(d, "triceratops_gaia.json")
        if t and t["degenerate"] != "yes":
            if not os.path.exists(g):
                problems.append(f"{r['candidate_id']}: no triceratops_gaia.json")
            elif abs(json.load(open(g))["FPP_mean"] - float(t["FPP_mean"])) > 1e-12:
                problems.append(f"{r['candidate_id']}: triceratops_gaia.json is not the result the catalog uses")
        elif os.path.exists(g):
            problems.append(f"{r['candidate_id']}: triceratops_gaia.json without a TRICERATOPS result in the catalog")
    return problems
