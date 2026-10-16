"""The two candidate tables, results_public/candidates_allsky.csv and results_public/tiers_earlier_candidates.csv, built
from their inputs by fixed rules. Built by the rule `catalog` in rules.py.

Inputs:
- results_public/products/measurements_allsky.csv, measurements_earlier.csv: every column that is measured rather than
  decided (fits, vetting, stellar parameters, pixel and centroid tests, binary and literature checks, the centroid Bayes
  factor BF, classifier scores, rv_flag), and for the earlier searches the A/B/C label they were given (base_tier).
- results_public/products/triceratops.csv: the TRICERATOPS result of each signal (triceratops_table.py).
- results_public/products/centroids.csv: per-sector centroid results measured since the copy of the measured columns
  (centroid_table.py); where a row has one, it replaces the row's centroid columns.
- results_public/products/vetting.csv: the pixel follow-up each row uses (vet_store.py). A row is in the neighbour set
  (neighbour<15") for a TIC entry within 15" bright enough to cause the dip; where the follow-up found such entries,
  fitted a difference image, and every entry it found is a galaxy or a galaxy's core (ticfield.py), the row is not.
- results_public/overrides.csv: decisions made by hand, each with its reason.
Outputs: the same rows with the TRICERATOPS columns, tier, c_reason and flags derived. Columns copied from the inputs
are written exactly as they are there.

The rules (pipeline/params.toml [tiers] and [flags] hold the numbers). Full sky, the first that applies:
1. reported: a published paper or Zenodo record gives the period (papers_with_period, zenodo_with_period), or an
   override names where it was reported (reported_as).
2. likely EB: a binary catalog lists the target or a matching eclipsing binary lies nearby (binary_at_target,
   eb_nearby_same_period), or the radius exceeds rp_eb_min.
3. likely nearby FP, where there is evidence that the signal comes from a nearby star: the per-sector centroids reject
   the target (cs_p_target < centroid_reject_p) and a capable neighbour fits them (cs_p_neighbour >=
   centroid_neighbour_p); or the signal is in set neighbour<15" and its TRICERATOPS result fails the bar.
4. SNR 7.5-9: L1 if fa_score_h >= fa_score_h_min, the bar is passed, b < b_max, RUWE <= ruwe_max and there is a
   transit fit; else likely false alarm if MES < lowband_mes_min; else C if grazing or RUWE (or, for a signal that
   would otherwise be L1, no transit fit); else L.
5. SNR >= 9 and neighbour<15": C if grazing (b >= b_max), RUWE > ruwe_max or MES < mes_min, in that order of c_reason;
   then C if there is no TRICERATOPS result (none is not evidence either way) or, for SNR >= 9, the bar is not passed;
   then C if there is no transit fit (b is empty), since grazing cannot be ruled out without one. What remains is N
   (neighbour<15") or counted (SNR >= 9).
6. Per-sector centroids: a counted row (L1, N, SNR >= 9) whose test rejects the target with no capable neighbour that
   fits becomes C ("centroid offset in all sectors").
7. Counted SNR >= 9 rows are A where the star has at least system_min counted rows, else B.
The bar: FPP < fpp_max and NFPP < nfpp_max, using FPP_gc/NFPP_gc (Gaia limits and centroid ratio) where they exist,
else FPP_c/NFPP_c.
Earlier searches: C if grazing, RUWE, the bar not passed (with a result) or the centroids rejecting the target, in that
order of c_reason; otherwise the label the search gave (A, B, or C for a reason it recorded).
Overrides are applied last.
"""
import csv
import io
import math

from fpp_combine import combine

TRI = ["FPP", "NFPP", "FPP_c", "NFPP_c", "FPP_g", "NFPP_g", "FPP_gc", "NFPP_gc"]
ALLSKY = ["TIC", "P_d", "P_err", "T0_BJD", "Rp_Re", "b", "T14_h", "depth_ppm", "MES", "n_transits", "Tmag", "Teff", "Rstar",
          "dist_pc", "ruwe", "centroid_offset_arcsec", "nearest_capable_arcsec", "cs_sectors", "cs_offset_arcsec",
          "cs_pa_deg", "cs_p_target", "cs_neighbour", "cs_neighbour_sep_arcsec", "cs_p_neighbour", "centroid_flag",
          "binary_at_target", "eb_nearby_same_period", "papers_with_period", "zenodo_with_period", "host_tois", "FPP",
          "NFPP", "BF", "FPP_c", "NFPP_c", "FPP_g", "NFPP_g", "FPP_gc", "NFPP_gc", "rv_flag", "fa_score", "fa_score_h",
          "set", "tier", "c_reason", "reported_as", "fa_flag", "desert_flag", "search", "candidate_id"]
EARLIER = ["TIC", "P_d", "Rp_Re", "b", "ruwe", "binary_at_target", "tier", "src", "FPP", "NFPP", "BF", "FPP_c", "NFPP_c",
           "FPP_g", "NFPP_g", "FPP_gc", "NFPP_gc", "rv_flag", "c_reason", "cs_sectors", "cs_offset_arcsec", "cs_pa_deg",
           "cs_p_target", "cs_neighbour", "cs_neighbour_sep_arcsec", "cs_p_neighbour", "centroid_flag", "candidate_id"]
DERIVED_ALLSKY = TRI + ["tier", "c_reason", "reported_as", "centroid_flag", "fa_flag", "desert_flag"]
DERIVED_EARLIER = TRI + ["tier", "c_reason", "centroid_flag"]
TRI_FAIL = "TRICERATOPS FPP >= 0.5 or NFPP >= 0.1"
NO_RESULT = "no TRICERATOPS result"
NO_PARALLAX = "no TRICERATOPS result (no TIC parallax)"
NO_FIT = "no transit fit"
CENTROID = "centroid offset in all sectors"
NB = 'neighbour<15"'


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return math.nan


def fmt(v, nd):
    """As the catalog has written TRICERATOPS values since 15 October: nd decimals, two significant figures below
    10^-nd, 0.0 for zero, empty for no value."""
    if not math.isfinite(v):
        return ""
    v = max(float(v), 0.0)
    return "0.0" if v == 0 else (repr(round(v, nd)) if v >= 10 ** -nd else f"{v:.2g}")


def read_rows(path):
    with open(path, newline="") as fh:
        text = fh.read()
    return list(csv.DictReader(io.StringIO(text)))


def write_rows(path, columns, rows):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(columns)
    for r in rows:
        w.writerow([r.get(c, "") for c in columns])
    with open(path, "w", newline="") as fh:
        fh.write(out.getvalue())


# TRICERATOPS ---------------------------------------------------------------------------------------------------------
def tri_values(res, bf):
    """The eight catalog columns from a result: FPP is the mean of the runs and NFPP the largest; _c and _gc combine
    them with the centroid Bayes factor (fpp_combine.py); _g and _gc use the Gaia-limited runs."""
    if res is None or res["degenerate"]:
        return {k: math.nan for k in TRI} | {"status": "none" if res is None else "degenerate"}
    f, nm, nx = num(res["FPP_mean"]), num(res["NFPP_mean"]), num(res["NFPP_max"])
    bf = bf if math.isfinite(bf) else None
    out = {"FPP": f, "NFPP": nx}
    out["FPP_c"], out["NFPP_c"] = combine(f, nm, nx, bf)
    if res["FPP_g_mean"]:
        g, gm, gx = num(res["FPP_g_mean"]), num(res["NFPP_g_mean"]), num(res["NFPP_g_max"])
        out["FPP_g"], out["NFPP_g"] = g, gx
        out["FPP_gc"], out["NFPP_gc"] = combine(g, gm, gx, bf)
    else:
        out.update(FPP_g=math.nan, NFPP_g=math.nan, FPP_gc=math.nan, NFPP_gc=math.nan)
    out["status"] = "ok"
    return out


def bar(v, P):
    """(has a result, passes): FPP < fpp_max and NFPP < nfpp_max on the Gaia-limited values where they exist."""
    f, n = (v["FPP_gc"], v["NFPP_gc"]) if math.isfinite(v["FPP_gc"]) else (v["FPP_c"], v["NFPP_c"])
    if not math.isfinite(f):
        return False, False
    return True, f < P["tiers.fpp_max"] and n < P["tiers.nfpp_max"]


# tiers ---------------------------------------------------------------------------------------------------------------
def tier_allsky(r, v, P):
    """Rules 1-5 for one full-sky row; returns (tier, c_reason), with "counted" for SNR >= 9 rows that pass."""
    has, passes = bar(v, P)
    b, ruwe, mes = num(r["b"]), num(r["ruwe"]), num(r["MES"])
    grazing, high_ruwe = b >= P["tiers.b_max"], ruwe > P["tiers.ruwe_max"]
    if r["papers_with_period"] or r["zenodo_with_period"] or r.get("reported_as"):
        return "reported", ""
    if r["binary_at_target"] or r["eb_nearby_same_period"] or num(r["Rp_Re"]) > P["tiers.rp_eb_min"]:
        return "likely EB", ""
    s = r["set"]
    if num(r["cs_p_target"]) < P["tiers.centroid_reject_p"] and num(r["cs_p_neighbour"]) >= P["tiers.centroid_neighbour_p"]:
        return "likely nearby FP", ""
    if s == NB and has and not passes:
        return "likely nearby FP", ""
    fitted = math.isfinite(b)
    if s == "SNR 7.5-9":
        selected = num(r["fa_score_h"]) >= P["tiers.fa_score_h_min"] and passes and not grazing and not high_ruwe
        if selected and fitted:
            return "L1", ""
        if mes < P["tiers.lowband_mes_min"]:
            return "likely false alarm", ""
        if grazing or high_ruwe:
            return "C", "grazing" if grazing else "RUWE > 1.4"
        if selected:
            return "C", NO_FIT
        return "L", ""
    if grazing:
        return "C", "grazing"
    if high_ruwe:
        return "C", "RUWE > 1.4"
    if mes < P["tiers.mes_min"]:
        return "C", "MES < 10"
    if not has:
        return "C", NO_PARALLAX if v.get("status") == "degenerate" else NO_RESULT
    if s != NB and not passes:
        return "C", TRI_FAIL
    if not fitted:
        return "C", NO_FIT
    return ("N", "") if s == NB else ("counted", "")


def needs_triceratops(r, P, table):
    """Whether a row's tier can depend on its TRICERATOPS result under the rules: the rows the build must have a current
    result for (tri_plan.py). A row decided before the bar is consulted (reported, binary, centroids that fit a
    neighbour; grazing, high RUWE or low MES outside the neighbour set; a low-band signal the classifier does not
    select) does not need one."""
    grazing, high_ruwe = num(r["b"]) >= P["tiers.b_max"], num(r["ruwe"]) > P["tiers.ruwe_max"]
    if table == "tiers_earlier_candidates":
        return not (grazing or high_ruwe)
    if r["papers_with_period"] or r["zenodo_with_period"] or r.get("reported_as"):
        return False
    if r["binary_at_target"] or r["eb_nearby_same_period"] or num(r["Rp_Re"]) > P["tiers.rp_eb_min"]:
        return False
    if num(r["cs_p_target"]) < P["tiers.centroid_reject_p"] and num(r["cs_p_neighbour"]) >= P["tiers.centroid_neighbour_p"]:
        return False
    if r["set"] == NB:
        return True
    if r["set"] == "SNR 7.5-9":
        return num(r["fa_score_h"]) >= P["tiers.fa_score_h_min"] and not grazing and not high_ruwe
    return not (grazing or high_ruwe or num(r["MES"]) < P["tiers.mes_min"])


def centroid_out(r, P):
    """None if the per-sector centroids do not reject the target, else the tier they send a counted row to (a row
    whose centroids also fit a neighbour is already a likely nearby FP by rule 3)."""
    p = num(r["cs_p_target"])
    if not (p < P["tiers.centroid_reject_p"]):
        return None
    return ("likely nearby FP", "") if num(r["cs_p_neighbour"]) >= P["tiers.centroid_neighbour_p"] else ("C", CENTROID)


def tier_earlier(r, v, P):
    has, passes = bar(v, P)
    if num(r["b"]) >= P["tiers.b_max"]:
        return "C", "grazing"
    if num(r["ruwe"]) > P["tiers.ruwe_max"]:
        return "C", "RUWE > 1.4"
    if has and not passes:
        return "C", TRI_FAIL
    if num(r["cs_p_target"]) < P["tiers.centroid_reject_p"]:
        return "C", CENTROID
    return r["base_tier"], r.get("base_c_reason", "")


def centroid_flag(r, P):
    p = num(r["cs_p_target"])
    if p < P["flags.centroid_p_strong"]:
        return "centroid offset in all sectors, p < 0.001"
    if p < P["flags.centroid_p"]:
        return "centroid offset in all sectors, p < 0.01"
    return ""


# the build -------------------------------------------------------------------------------------------------------------
DECISIONS = ("tier", "c_reason")         # overrides of these replace a rule's outcome; others replace an input
CS = ["cs_sectors", "cs_offset_arcsec", "cs_pa_deg", "cs_p_target", "cs_neighbour", "cs_neighbour_sep_arcsec", "cs_p_neighbour"]


def centroids_into(rows, table, centroids):
    for r in rows:
        c = centroids.get((table, r["TIC"], r["P_d"]))
        if c is not None:
            for k in CS:
                r[k] = c[k]


def overrides_for(over, table, rows, decisions):
    """Apply the overrides of one table: decisions (tier, c_reason) or inputs (any other column). Each must match
    exactly one row (same TIC, period within 1e-4)."""
    for o in over:
        if o["table"] != table or (o["field"] in DECISIONS) != decisions:
            continue
        hit = [r for r in rows if r["TIC"] == o["TIC"] and abs(num(r["P_d"]) / num(o["P_d"]) - 1) < 1e-4]
        if len(hit) != 1:
            raise ValueError(f"override {o['TIC']} {o['P_d']} {o['field']} matches {len(hit)} rows of {table}")
        hit[0][o["field"]] = o["value"]
        if o["field"] == "tier" and o["value"] != "C":
            hit[0]["c_reason"] = ""


FIT_COLUMNS = {"candidates_allsky": ("P_err", "T0_BJD", "T14_h", "Rp_Re", "b"), "tiers_earlier_candidates": ("Rp_Re", "b")}


def neighbour_set_into(rows, table, vetting):
    """A row in the neighbour set because of TIC entries within 15" that are all galaxies or their cores (vetting.csv:
    close_capable without close_stellar), with a fitted difference image, is a SNR >= 9 row."""
    for r in rows:
        v = vetting.get((table, r["TIC"], r["P_d"]))
        if r["set"] == NB and v and v["image"] == "yes" and v["close_capable"] and not v["close_stellar"]:
            r["set"] = "SNR>=9"


def fits_into(rows, table, fits):
    """The fitted columns of each row from the fit it uses (fits.csv); the period after every lookup by (TIC, P_d)."""
    for r in rows:
        f = fits.get((table, r["TIC"], r["P_d"]))
        if f is not None:
            for k in FIT_COLUMNS[table]:
                r[k] = f[k]                         # empty where the fit failed its checks: the row has no usable fit
            if f["P_fit"]:
                r["_P_fit"] = f["P_fit"]


def build(measurements_allsky, measurements_earlier, triceratops_csv, overrides_csv, out_allsky, out_earlier, P,
          centroids_csv=None, fits_csv=None, vetting_csv=None):
    """The TRICERATOPS, centroid and fit tables name, for each catalog row (table, TIC, P_d of the measurement table),
    the result it uses. A row's published period is its fit's; the measurement table's period stays its key."""
    results = {}
    for r in read_rows(triceratops_csv):
        r["degenerate"] = r["degenerate"] == "yes"
        results[(r["table"], r["TIC"], r["P_d"])] = r
    centroids = {(r["table"], r["TIC"], r["P_d"]): r for r in read_rows(centroids_csv)} if centroids_csv else {}
    fits = {(r["table"], r["TIC"], r["P_d"]): r for r in read_rows(fits_csv)} if fits_csv else {}
    vetting = {(r["table"], r["TIC"], r["P_d"]): r for r in read_rows(vetting_csv)} if vetting_csv else {}
    over = read_rows(overrides_csv)

    def result_for(r, table):
        return results.get((table, r["TIC"], r["P_d"]))

    a = read_rows(measurements_allsky)
    centroids_into(a, "candidates_allsky", centroids)
    fits_into(a, "candidates_allsky", fits)
    neighbour_set_into(a, "candidates_allsky", vetting)
    for r in a:
        r["reported_as"] = ""
    overrides_for(over, "candidates_allsky", a, decisions=False)
    for r in a:
        r["_v"] = tri_values(result_for(r, "candidates_allsky"), num(r["BF"]))
        r["tier"], r["c_reason"] = tier_allsky(r, r["_v"], P)
    overrides_for(over, "candidates_allsky", a, decisions=True)
    for r in a:
        if r["tier"] in ("counted", "N", "L1"):
            moved = centroid_out(r, P)
            if moved:
                r["tier"], r["c_reason"] = moved
    counted_on_star = {}
    for r in a:
        if r["tier"] in ("counted", "N", "L1"):
            counted_on_star[r["TIC"]] = counted_on_star.get(r["TIC"], 0) + 1
    for r in a:
        if r["tier"] == "counted":
            r["tier"] = "A" if counted_on_star[r["TIC"]] >= P["tiers.system_min"] else "B"
    for r in a:
        v = r.pop("_v")
        for k in TRI:
            r[k] = fmt(v[k], 3 if k.startswith("FPP") else 4)
        if r["tier"] == "reported" and not r["reported_as"]:
            r["reported_as"] = r["papers_with_period"] or r["zenodo_with_period"]
        r["centroid_flag"] = centroid_flag(r, P)
        cnt = r["tier"] in P["catalog.counted_allsky"]
        r["fa_flag"] = ("low false-alarm-classifier score" if r["tier"] in P["flags.fa_flag_tiers"]
                        and num(r["fa_score"]) < P["flags.fa_score_min"] else "")
        rp = num(r["Rp_Re"])
        r["desert_flag"] = ("Neptunian desert" if cnt and num(r["P_d"]) < P["flags.desert_period_max"]
                            and P["flags.desert_rp_min"] <= rp <= P["flags.desert_rp_max"] else "")

    e = read_rows(measurements_earlier)
    centroids_into(e, "tiers_earlier_candidates", centroids)
    fits_into(e, "tiers_earlier_candidates", fits)
    overrides_for(over, "tiers_earlier_candidates", e, decisions=False)
    for r in e:
        v = tri_values(result_for(r, "tiers_earlier_candidates"), num(r["BF"]))
        r["tier"], r["c_reason"] = tier_earlier(r, v, P)
        for k in TRI:
            r[k] = fmt(v[k], 3 if k.startswith("FPP") else 4)
        r["centroid_flag"] = centroid_flag(r, P)
    overrides_for(over, "tiers_earlier_candidates", e, decisions=True)
    for r in a:
        if "_P_fit" in r:
            r["P_d"] = r.pop("_P_fit")
    for r in e:
        r.pop("_P_fit", None)                       # the earlier tables keep the period they were registered with
    write_rows(out_allsky, ALLSKY, a)
    write_rows(out_earlier, EARLIER, e)
    return a, e
