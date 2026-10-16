"""results_public/numbers.json: every current-state number the documents quote, computed from the tables in one place,
so README.md, results_public/README.md and validation/findability.md (through markers, dag/markers.py) and the website
follow the data. Built by the rule numbers in rules.py. The definitions are the catalog's: counted = tiers A, B, N, L1 (full sky) and A, B (earlier
searches); the TRICERATOPS values a tier uses are FPP_gc/NFPP_gc where they exist, else FPP_c/NFPP_c; validation level =
FPP < 0.015, NFPP < 0.001 and Rp < 8 Earth radii.
"""
import json

import numpy as np
import pandas as pd

SETS = {"SNR>=9": "snr9", "SNR 7.5-9": "low", 'neighbour<15"': "nb"}
FIRST, RESEARCH = "full-sky search", "QLP re-search"
INV = ("inverted, sample 1", "inverted, sample 2")
TIER_ORDER = ["A", "B", "N", "L1", "C", "L", "likely EB", "likely nearby FP", "likely false alarm", "reported"]
C_REASONS = {"grazing": "grazing", "RUWE > 1.4": "ruwe", "MES < 10": "mes", "TRICERATOPS FPP >= 0.5 or NFPP >= 0.1": "triceratops",
             "centroid offset in all sectors": "centroid", "no TRICERATOPS result": "no_result",
             "no TRICERATOPS result (no TIC parallax)": "no_parallax", "no transit fit": "no_fit"}


def slug(t):
    return t.replace(" ", "_").replace(">=", "").replace("<", "").replace('"', "")


def by_tier(d, tiers=TIER_ORDER):
    """'83 `likely nearby FP`, 11 `likely EB`, 6 `C`': the rows of d by tier, largest first."""
    c = d.tier.value_counts()
    parts = [f"{n:,} `{t}`" for t, n in sorted(c.items(), key=lambda x: (-x[1], tiers.index(x[0]) if x[0] in tiers else 99))]
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] if parts else "none"


def tier_values(d):
    g = d.FPP_gc.notna()
    return d.FPP_gc.where(g, d.FPP_c), d.NFPP_gc.where(g, d.NFPP_c)


def compute(allsky_csv, earlier_csv, ephemerides_csv, predictions_csv, funnel_csv, triceratops_csv, P):
    a, e = pd.read_csv(allsky_csv), pd.read_csv(earlier_csv)
    tri_t = pd.read_csv(triceratops_csv)
    eph, pred, fun = pd.read_csv(ephemerides_csv), pd.read_csv(predictions_csv), pd.read_csv(funnel_csv)
    cnt_a, cnt_e = P["catalog.counted_allsky"], P["catalog.counted_earlier"]
    ca, ce = a[a.tier.isin(cnt_a)], e[e.tier.isin(cnt_e)]
    f, n = tier_values(a)
    fe, ne = tier_values(e)
    val_a = ca.index[(f[ca.index] < 0.015) & (n[ca.index] < 0.001) & (ca.Rp_Re < 8)]
    val_e = ce.index[(fe[ce.index] < 0.015) & (ne[ce.index] < 0.001) & (ce.Rp_Re < 8)]
    tiers = {slug(t): int((a.tier == t).sum()) for t in TIER_ORDER}
    other = int((~a.tier.isin(["A", "B", "N", "L1", "C", "L"])).sum())
    nofit = a[a.b.isna()]
    tri = a.FPP.notna()
    lnfp = a[a.tier == "likely nearby FP"]
    lnfp_cs = (lnfp.cs_p_target < P["tiers.centroid_reject_p"]) & (lnfp.cs_p_neighbour >= P["tiers.centroid_neighbour_p"])
    lnfp_tri = (lnfp["set"] == 'neighbour<15"') & lnfp.FPP.notna()
    cs = a.cs_sectors.notna()
    cflag = a.centroid_flag.fillna("")
    strong, weak = a[cflag.str.endswith("p < 0.001")], a[cflag.str.endswith("p < 0.01")]
    fa, de = a[a.fa_flag.notna()], a[a.desert_flag.notna()]
    c_reasons = a[a.tier == "C"].c_reason.value_counts()
    gaia_missing = a[tri & a.FPP_g.isna()]
    out = {
        "catalog": {
            "rows": {"allsky": len(a), "earlier": len(e)},
            "counted": {"total": len(ca) + len(ce), "allsky": len(ca), "earlier": len(ce)},
            "validation": {"total": len(val_a) + len(val_e), "allsky": len(val_a), "earlier": len(val_e)},
            "tier": {**tiers, "other": other},
            "earlier_tier": {t: int((e.tier == t).sum()) for t in ("A", "B", "C")},
            "set": {SETS[s]: int((a["set"] == s).sum()) for s in SETS},
            "c_reason": {C_REASONS[k]: int(c_reasons.get(k, 0)) for k in C_REASONS},
            "c_reason_empty": int((a.tier != "C").sum()),
            "reported_as_empty": int(a.reported_as.isna().sum()),
            "papers_empty": int(a.papers_with_period.isna().sum()),
            "nofit": {"total": len(nofit), "text": by_tier(nofit)},
            "cs": {"filled": int(cs.sum()), "empty": int((~cs).sum()), "p_empty_measured": int((cs & a.cs_p_target.isna()).sum()),
                   "counted_unmeasured": int((a.tier.isin(cnt_a) & ~cs).sum())},
            "fpp": {"empty": int((~tri).sum()),
                    "no_parallax": int(((tri_t.table == "candidates_allsky") & (tri_t.degenerate == "yes")).sum())},
            "fpp_g": {"empty": int(a.FPP_g.isna().sum()), "missing_with_fpp": len(gaia_missing)},
            "bf": {"empty": int(a.BF.isna().sum()), "with_fpp": int((tri & a.BF.isna()).sum())},
            "lnfp": {"total": len(lnfp), "by_triceratops": int(lnfp_tri.sum()), "by_centroids": int(lnfp_cs.sum()),
                     "by_both": int((lnfp_tri & lnfp_cs).sum())},
            "l1_low_fa_score": int(((a.tier == "L1") & (a.fa_score < P["flags.fa_score_min"])).sum()),
            "fpp_not_run": int((~tri).sum()) - int(((tri_t.table == "candidates_allsky") & (tri_t.degenerate == "yes")).sum()),
            "lfa": {"total": int((a.tier == "likely false alarm").sum()),
                    "low_band": int(((a.tier == "likely false alarm") & (a["set"] == "SNR 7.5-9")).sum())},
            "flags": {
                "centroid_strong": {"total": len(strong), "text": by_tier(strong)},
                "centroid_weak": {"total": len(weak), "text": by_tier(weak)},
                "fa": {"total": len(fa), "text": by_tier(fa)},
                "desert": {"total": len(de), "text": by_tier(de)},
                "rv": {slug(k).replace("Gaia_", "").replace("_on_the_target", "").lower(): int(v)
                       for k, v in a.rv_flag.value_counts().items()},
            },
        },
        "earlier": {"binary_empty": int(e.binary_at_target.isna().sum()), "fpp_empty": int(e.FPP.isna().sum()),
                    "rv_empty": int(e.rv_flag.isna().sum()), "c_reason_empty": int((e.tier != "C").sum()),
                    "cs_empty": int(e.cs_p_target.isna().sum()), "cs_neighbour_empty": int(e.cs_neighbour.isna().sum()),
                    "centroid_flag_empty": int(e.centroid_flag.isna().sum())},
        "registry": {"rows": len(eph), "counted_now": int(eph.tier.isin(set(cnt_a) | set(cnt_e)).sum()),
                     "predictions": len(pred), "tess_sector_empty": int(pred.tess_sector.isna().sum()),
                     "planned_empty": int(eph.tess_sectors_planned.isna().sum()),
                     "median_next_sigma_min": float(np.median(eph.next_tc_sigma_min))},
        "funnel": {"rows": len(fun)},
    }
    both = pd.concat([ca, ce])
    fb_, _ = tier_values(both)
    out["catalog"].update({
        "median_fpp": {"default": float(both.FPP_c.median()), "gaia": float(fb_.median())},
        "reported_ctoi": int(((a.tier == "reported") & a.reported_as.fillna("").str.startswith("CTOI")).sum()),
        "centroid_flagged_counted": int(both.centroid_flag.fillna("").str.endswith("p < 0.01").sum()),
        "from_research": int((ca.search == RESEARCH).sum()),
        "hosts": int(ca.TIC.nunique()),
        "median_radius": float(ca.Rp_Re.median()),
        "smaller_than_4": int((ca.Rp_Re < 4).sum()),
        "lower_confidence": int(a.tier.isin(["C", "L"]).sum() + (e.tier == "C").sum()),
    })
    return out


def funnel(funnel_csv):
    """{pass: {band: {stage: count}}} from results_public/funnel_allsky.csv."""
    f = {}
    for r in pd.read_csv(funnel_csv).to_dict("records"):
        f.setdefault(r["pass"], {}).setdefault(r["band"], {})[r["stage"]] = int(r["count"])
    return f


def false_alarms(funnel_csv, tri_inverted_csv, scores_csv, allsky_csv, P):
    """Expected false alarms among the counted full-sky candidates, from the search of inverted light curves (the
    first pass's measurement), and tier L1's selection by the false-alarm classifier at the 0.80 cut, as
    fa_classifier.py computes it. {"false_alarms": ..., "classifier": ...}."""
    f = funnel(funnel_csv)
    stars = f[FIRST]["all"]["stars"]
    inv_stars = sum(f[q]["all"]["stars"] for q in INV)
    scale = stars / inv_stars
    fa = {"stars": stars, "inverted_stars": inv_stars, "scale": scale, "bands": {}, "mes_bins": []}
    for b in ("hi", "low"):
        fa["bands"][b] = {k: {"real": f[FIRST][b][k], "inverted": sum(f[q][b][k] for q in INV),
                              "expected": scale * sum(f[q][b][k] for q in INV)}
                          for k in ("clean", "close_nb", "offset", "no_image")}
    rate = {}
    for key, lo, hi in (("lt10", None, 10), ("10_12", 10, 12), ("ge12", 12, None)):
        real, inv = f[FIRST]["hi"]["clean_mes_" + key], sum(f[q]["hi"]["clean_mes_" + key] for q in INV)
        rate[key] = scale * inv / real
        fa["mes_bins"].append({"bin": key, "lo": lo, "hi": hi, "real": real, "inverted": inv, "fraction": rate[key]})
    a = pd.read_csv(allsky_csv)
    ab = a[a.tier.isin(["A", "B"])]
    exp_ab = float(sum(rate["lt10" if m < 10 else ("10_12" if m < 12 else "ge12")] for m in ab.MES))
    # tier N: TRICERATOPS run on the first sample's inverted close-neighbour false alarms
    tri = pd.read_csv(tri_inverted_csv, dtype=str)
    tri = tri[tri.band == "SNR>=9"]
    tri_pass = int((tri.pass10 == "True").sum())
    fa["triceratops_inverted"] = {"tested": len(tri), "pass": int((tri["pass"] == "True").sum()), "pass_mes10": tri_pass}
    s = pd.read_csv(scores_csv, dtype={"inv_set": str})
    lo = s[s.band == "low"]
    real_c = lo[(lo.label == "real") & (lo.cls == "clean")]
    n_fa = int(((lo.label == "inverted") & (lo.cls == "clean")).sum()) * stars / inv_stars
    i2 = lo[(lo.label == "inverted") & lo.inv_set.isin(["2", "2.0"])]
    cut = 0.8
    sel = int((real_c.score_h >= cut).sum())
    exp_cl = n_fa * int((i2.score_h >= cut).sum()) / len(i2)
    cl = {"cut": cut, "clean_low": len(real_c), "selected": sel, "expected_false_alarms": exp_cl, "purity": 1 - exp_cl / sel,
          "baseline_false_alarms": n_fa}
    fa["expected"] = {"AB": exp_ab, "N": tri_pass * stars / f[INV[0]]["all"]["stars"],
                      "L1": exp_cl / sel * int((a.tier == "L1").sum())}
    return {"false_alarms": fa, "classifier": cl}


def validation(findability_json, recheck_csv):
    """The findability and SPOC 2-minute recheck numbers that validation/findability.md quotes."""
    import findability as fb
    with open(findability_json) as fh:
        return {"findability": json.load(fh), "spoc": fb.recheck_numbers(recheck_csv)}


def write(path, numbers):
    with open(path, "w") as fh:
        json.dump(numbers, fh, indent=1, sort_keys=True)
        fh.write("\n")
