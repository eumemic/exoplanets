"""Every number the website shows that is not read straight from a candidate table, computed from the files committed
in the repository: the search funnel (results_public/funnel_allsky.csv, written by funnel.py from the run outputs),
the candidate tables, the false-alarm and classifier tables in validation/, findability.csv, the prediction files and
the dated release notes at the top of README.md. Standard library only, so the site build needs no packages.

Usage: python site_data.py [OUT]     (default: _site/data/summary.json; site/build.sh calls it)
"""
import csv
import gzip
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COUNTED = ("A", "B", "N", "L1")
FIRST, RESEARCH = "full-sky search", "QLP re-search"
INV = ("inverted, sample 1", "inverted, sample 2")


def rows(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(ROOT / path, "rt", newline="") as fh:
        return list(csv.DictReader(fh))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def ok(x):
    return x == x


def funnel():
    f = {}
    for r in rows("results_public/funnel_allsky.csv"):
        f.setdefault(r["pass"], {}).setdefault(r["band"], {})[r["stage"]] = int(r["count"])
    return f


def tier_fpp(r):
    """The values the tier bar uses: Gaia-constrained with the centroid ratio, else the default with it."""
    f, n = num(r.get("FPP_gc")), num(r.get("NFPP_gc"))
    if not ok(f):
        f, n = num(r.get("FPP_c")), num(r.get("NFPP_c"))
    return f, n


def catalog():
    a, e = rows("results_public/candidates_allsky.csv"), rows("results_public/tiers_earlier_candidates.csv")
    tiers = lambda t: {k: sum(1 for r in t if r["tier"] == k) for k in sorted({r["tier"] for r in t})}
    ca = [r for r in a if r["tier"] in COUNTED]
    ce = [r for r in e if r["tier"] in ("A", "B")]
    both = ca + ce
    radius = [num(r["Rp_Re"]) for r in ca]
    by = lambda col, val, t=ca: sum(1 for r in t if r[col] == val)
    out = {
        "rows": {"allsky": len(a), "earlier": len(e)},
        "tiers_allsky": tiers(a), "tiers_earlier": tiers(e),
        "counted": {"total": len(both), "full_sky": len(ca), "earlier": len(ce),
                    "from_research": by("search", RESEARCH),
                    **{t: by("tier", t) for t in COUNTED},
                    "earlier_A": by("tier", "A", ce), "earlier_B": by("tier", "B", ce)},
        "lower_confidence": sum(1 for r in a if r["tier"] in ("C", "L")) + sum(1 for r in e if r["tier"] == "C"),
        "hosts": len({r["TIC"] for r in ca}),
        "median_radius": statistics.median(radius),
        "smaller_than_4": sum(1 for x in radius if x < 4),
        "set": {k: by("set", k, a) for k in sorted({r["set"] for r in a})},
        "search_rows": {k: by("search", k, a) for k in (FIRST, RESEARCH)},
    }
    fpp = [tier_fpp(r) for r in both]
    # the TRICERATOPS validation thresholds (Giacalone et al. 2021), which apply only below 8 Earth radii: giant planets,
    # brown dwarfs and low-mass stars cannot be told apart by radius
    out["validation_level"] = sum(1 for (f, n), r in zip(fpp, both) if f < 0.015 and n < 0.001 and num(r["Rp_Re"]) < 8)
    out["median_fpp_default"] = statistics.median(num(r["FPP_c"]) for r in both if ok(num(r["FPP_c"])))
    out["median_fpp_gaia"] = statistics.median(f for f, _ in fpp if ok(f))
    out["checks"] = {
        "likely_eb": by("tier", "likely EB", a),
        "rv_binary": by("rv_flag", "Gaia RV binary", a),
        "likely_nearby_fp": by("tier", "likely nearby FP", a),
        "likely_false_alarm": by("tier", "likely false alarm", a),
        "reported": by("tier", "reported", a),
        "reported_ctoi": sum(1 for r in a if r["tier"] == "reported" and r["reported_as"].startswith("CTOI")),
        "c_reason": {k: by("c_reason", k, a) for k in sorted({r["c_reason"] for r in a if r["c_reason"]})},
        "centroid_rejected": sum(1 for r in a if r["centroid_flag"].endswith("p < 0.001")),
        "centroid_flagged": sum(1 for r in both if r["centroid_flag"].endswith("p < 0.01")),
        "fa_flag": sum(1 for r in ca if r["fa_flag"]),
        "desert_flag": sum(1 for r in ca if r["desert_flag"]),
    }
    return out, ca


def false_alarms(f, ca):
    """Expected false alarms from the inverted light curves (first-pass measurement), as in the README."""
    stars = f[FIRST]["all"]["stars"]
    inv_stars = sum(f[p]["all"]["stars"] for p in INV)
    scale = stars / inv_stars
    out = {"stars": stars, "inverted_stars": inv_stars, "scale": scale, "bands": {}}
    for b in ("hi", "low"):
        out["bands"][b] = {k: {"real": f[FIRST][b][k], "inverted": sum(f[p][b][k] for p in INV),
                               "expected": scale * sum(f[p][b][k] for p in INV)}
                           for k in ("clean", "close_nb", "offset", "no_image")}
    bins = [("lt10", None, 10), ("10_12", 10, 12), ("ge12", 12, None)]
    rate = {}
    out["mes_bins"] = []
    for key, lo, hi in bins:
        real, inv = f[FIRST]["hi"]["clean_mes_" + key], sum(f[p]["hi"]["clean_mes_" + key] for p in INV)
        rate[key] = scale * inv / real
        out["mes_bins"].append({"bin": key, "lo": lo, "hi": hi, "real": real, "inverted": inv, "fraction": rate[key]})

    def mes_bin(m):
        return "lt10" if m < 10 else ("10_12" if m < 12 else "ge12")
    ab = [r for r in ca if r["tier"] in ("A", "B")]
    exp_ab = sum(rate[mes_bin(num(r["MES"]))] for r in ab)
    # tier N: TRICERATOPS run on the first sample's inverted close-neighbour false alarms
    tri = [r for r in rows("validation/triceratops_inverted_close_neighbour.csv") if r["band"] == "SNR>=9"]
    tri_pass = sum(1 for r in tri if r["pass10"] == "True")
    exp_n = tri_pass * stars / f[INV[0]]["all"]["stars"]
    out["triceratops_inverted"] = {"tested": len(tri), "pass": sum(1 for r in tri if r["pass"] == "True"),
                                   "pass_mes10": tri_pass}
    return out, exp_ab, exp_n


def classifier(f):
    """Tier L1's selection and purity at the 0.80 cut, as fa_classifier.py computes them."""
    s = rows("validation/false_alarm_classifier_scores_star.csv.gz")
    lo = [r for r in s if r["band"] == "low"]
    real_c = [r for r in lo if r["label"] == "real" and r["cls"] == "clean"]
    stars = f[FIRST]["all"]["stars"]
    n_inv = sum(f[p]["all"]["stars"] for p in INV)
    n_fa = sum(1 for r in lo if r["label"] == "inverted" and r["cls"] == "clean") * stars / n_inv
    i2 = [r for r in lo if r["label"] == "inverted" and r["inv_set"] in ("2", "2.0")]
    cut = 0.8
    sel = sum(1 for r in real_c if num(r["score_h"]) >= cut)
    fa = n_fa * sum(1 for r in i2 if num(r["score_h"]) >= cut) / len(i2)
    return {"cut": cut, "clean_low": len(real_c), "selected": sel, "expected_false_alarms": fa,
            "purity": 1 - fa / sel, "baseline_false_alarms": n_fa}


def findability():
    x = rows("validation/findability.csv")
    n = len(x)
    # the file rounds SNRs to 0.01; "above 9" there reproduces findability.py's ">= 9" on the unrounded values
    at = lambda k: sum(1 for r in x if num(r[k]) > 9)
    out = {"n": n, "by_search": {k: sum(1 for r in x if r["search"] == k) for k in (FIRST, RESEARCH)},
           "through": {s: at(f"snr_to_s{s}") for s in (26, 55, 69, 83, 96)}, "all": at("snr"),
           "best_sector_median": statistics.median(num(r["best_sector_snr"]) for r in x),
           "best_below_7_1": sum(1 for r in x if num(r["best_sector_snr"]) < 7.1),
           "ffi_only": sum(1 for r in x if r["two_min"] == "False"),
           "sectors_median": statistics.median(int(r["n_sectors"]) for r in x)}
    out["needed_97"] = sum(1 for r in x if num(r["snr"]) > 9 and num(r["snr_to_s96"]) <= 9)
    out["needed_97_research"] = sum(1 for r in x if num(r["snr"]) > 9 and num(r["snr_to_s96"]) <= 9
                                    and r["search"] == RESEARCH)
    return out


def predictions():
    e, p = rows("candidates/ephemerides.csv"), rows("candidates/predictions.csv")
    return {"registered": len(e), "registered_counted": sum(1 for r in e if r["tier"] in COUNTED),
            "transits": len(p), "registered_dates": sorted({r["registered"] for r in e})}


def releases():
    """The dated release notes at the top of the README: title, date, count and the first linked note."""
    text = re.sub(r"<!--.*?-->", "", (ROOT / "README.md").read_text())   # generated-number markers (pipeline/dag/markers.py)
    out, months = [], {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July",
                                                    "August", "September", "October", "November", "December"), 1)}
    for m in re.finditer(r"^- \*\*(.+?)\*\*(.*?)(?=^- \*\*|^\S|\Z)", text, re.M | re.S):
        head, body = m.group(1), m.group(2)
        d = re.search(r"\((\d{1,2}) (\w+) (\d{4})\)", head)
        if not d:
            continue
        title = head[:d.start()].strip().rstrip(",")
        n = re.search(r"([\d,]+) candidates", head)
        added = re.match(r"\s*(\d+) (?:more|transit-candidate)", body)
        link = re.search(r"\]\(((?:validation|results_public)/[^)#]+(?:#[^)]*)?)\)", body)
        out.append({"date": f"{d.group(3)}-{months[d.group(2)]:02d}-{int(d.group(1)):02d}", "title": title,
                    "count": int(n.group(1).replace(",", "")) if n else None,
                    "added": int(added.group(1)) if added and not n else None,
                    "note": link.group(1) if link else None})
    return sorted(out, key=lambda r: r["date"], reverse=True)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site" / "data" / "summary.json"
    f = funnel()
    cat, ca = catalog()
    fa, exp_ab, exp_n = false_alarms(f, ca)
    cl = classifier(f)
    fa["expected"] = {"AB": exp_ab, "N": exp_n, "L1": cl["expected_false_alarms"] / cl["selected"] * cat["counted"]["L1"]}
    s = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "funnel": f, "catalog": cat,
         "false_alarms": fa, "classifier": cl, "findability": findability(), "predictions": predictions(),
         "releases": releases()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(s, indent=1))
    print(f"{out}: {cat['counted']['total']} counted, {len(s['releases'])} releases")


if __name__ == "__main__":
    main()
