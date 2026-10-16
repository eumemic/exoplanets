"""Checks on the catalog's inputs that the build cannot correct by itself; each returns a list of problems (empty if
none). Run by the checks in rules.py.

- counted_measured_centroids: every counted candidate has per-sector centroid measurements (the test itself needs at
  least two sectors).
- centroid_inputs_current: every centroid measurement in results_public/products/centroids.csv used the signal's
  current ephemeris.
- folders_complete: every row in a folder tier has its folder with the vetting files, and each folder's
  triceratops_gaia.json is there exactly when the row has a TRICERATOPS result, with the catalog's values (for the
  full-sky folders in candidates/allsky/ and the earlier searches' in candidates/).
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


def _cells(line):
    """The number of cells GitHub finds in a table row: it splits the row at every bar not escaped with a backslash,
    even inside code spans and comments."""
    s = line.strip().replace("\\|", "")
    return s.strip("|").count("|") + 1


def markdown_tables(path):
    """Tables with a row whose number of cells differs from the header's, counted as GitHub counts them (a bar inside a
    marker or a code span must be escaped, \\|), outside code blocks."""
    import re
    problems, in_code = [], False
    lines = open(path).read().split("\n")
    i = 0
    while i < len(lines):
        if lines[i].startswith("```"):
            in_code = not in_code
        if not in_code and lines[i].startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            n, j = _cells(lines[i]), i + 1
            while j < len(lines) and lines[j].startswith("|"):
                if _cells(lines[j]) != n:
                    problems.append(f"{path}:{j + 1}: {_cells(lines[j])} cells, the header at line {i + 1} has {n}")
                j += 1
            i = j
            continue
        i += 1
    return problems


def folders_complete(root, base, catalog_csv, triceratops_csv, table, required, folder_tiers=None):
    """Problems with the candidate folders under base: a row in a folder tier (any row if folder_tiers is None) without
    its folder, a folder without the required files, and a triceratops_gaia.json that is missing, extra, or not the
    result the catalog uses (its means against triceratops.csv)."""
    import json
    have = set(os.listdir(os.path.join(root, base)))
    tri = {(r["TIC"], r["P_d"]): r for r in _rows(triceratops_csv) if r["table"] == table}
    problems = []
    for r in _rows(catalog_csv):
        d = os.path.join(root, base, r["candidate_id"])
        if r["candidate_id"] not in have:
            if folder_tiers is None or r["tier"] in folder_tiers:
                problems.append(f"{r['candidate_id']} (tier {r['tier']}): no folder")
            continue
        for f in required:
            if not os.path.exists(os.path.join(d, f)):
                problems.append(f"{r['candidate_id']}: no {f}")
        t = tri.get((r["TIC"], r["P_d"]))
        g = os.path.join(d, "triceratops_gaia.json")
        if t and t["degenerate"] != "yes":
            if not os.path.exists(g):
                problems.append(f"{r['candidate_id']}: no triceratops_gaia.json")
                continue
            j = json.load(open(g))
            pairs = (("FPP_mean", "FPP_mean"), ("NFPP_mean", "NFPP_mean"), ("FPP_m_mean", "FPP_g_mean"),
                     ("NFPP_m_mean", "NFPP_g_mean"))
            if any(j.get(a) != float(t[b]) for a, b in pairs if t[b]):
                problems.append(f"{r['candidate_id']}: triceratops_gaia.json is not the result the catalog uses")
        elif os.path.exists(g):
            problems.append(f"{r['candidate_id']}: triceratops_gaia.json without a TRICERATOPS result in the catalog")
    return problems
