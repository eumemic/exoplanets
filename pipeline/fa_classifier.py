"""False-alarm classifier: separates signals of the real search (astrophysical signals mixed with false
alarms) from signals found in inverted light curves (false alarms only), using search, vetting, LEO-Vetter
and stellar features. Inverted signals are weighted by the ratio of stars searched, so the weighted classes
estimate the expected counts in the real search. Scores are out of fold (repeated 5-fold cross-validation).

The hold-out mode trains on the real signals and the first inverted sample only, scores the second inverted
sample (independent stars) with every fold's model, and reports how many false alarms pass each score cut:
that is the purity estimate used for tier L1.

Usage: python fa_classifier.py TABLE.csv.gz --stars-real N --stars-inv N1 N2 [--out scored.csv.gz]
TABLE is validation/false_alarm_classifier_table.csv.gz (one row per signal passing LEO-Vetter and the cuts;
label real/inverted, inv_set 1 or 2 for inverted signals, band hi (SNR >= 9) or low (7.5-9), pixel-check
class cls).
"""
import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold

FEATURES = ["bls_snr", "MES", "sde", "coarse_frac", "log_period", "log_depth", "dur_ratio", "n_good_events",
            "max_ses_frac", "frac_neg_events", "odd_even_sigma", "sec_sig", "chi2_sec", "n_sectors", "span", "noise_ppm",
            "rho", "snr_split", "CHI", "DMM", "Fred", "SHP", "maxses_mes", "mean_chases", "newmes_frac", "q", "sig_pri",
            "sig_sec", "sig_ter", "sine_sig", "transit_b", "transit_aRs", "transit_RpRs", "Tmag", "contratio", "rad", "Teff"]
# Not used: centroid_z and sig_pos, whose values could differ between real and inverted light curves for reasons
# other than the signal being noise (the flux-weighted centroids are not inverted; real dips become positive events).


def features(t):
    t = t.copy()
    t["log_period"] = np.log10(t["period"])
    t["log_depth"] = np.log10(t["depth_ppm"].clip(lower=1))
    t["dur_ratio"] = t["duration_h"] / t["exp_duration_h"]
    t["sec_sig"] = t["secondary"] / t["secondary_err"]
    t["coarse_frac"] = t["coarse_snr"] / t["bls_snr"]
    t["maxses_mes"] = t["max_SES"] / t["MES"]
    t["newmes_frac"] = t["new_MES"] / t["MES"]
    t["snr_split"] = (t["snr_new"] - t["snr_old"]) / (t["snr_new"].abs() + t["snr_old"].abs() + 1)
    return t


def oof_scores(t, train, weight_inv, extra=None, repeats=3):
    """Out-of-fold scores for the rows in `train`; rows in `extra` are scored by every fold's model."""
    d = t[train]
    X, y = d[FEATURES].astype(float).values, (d["label"] == "real").astype(int).values
    w = np.where(y == 0, weight_inv, 1.0)
    s = np.zeros(len(d))
    e = np.zeros(int(extra.sum())) if extra is not None else None
    for rep in range(repeats):
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=rep).split(X, y):
            m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40,
                                               l2_regularization=1.0, random_state=rep)
            m.fit(X[tr], y[tr], sample_weight=w[tr])
            s[te] += m.predict_proba(X[te])[:, 1] / repeats
            if e is not None:
                e += m.predict_proba(t.loc[extra, FEATURES].astype(float).values)[:, 1] / (5 * repeats)
    out = pd.Series(np.nan, index=t.index)
    out[d.index] = s
    if e is not None:
        out[t.index[extra]] = e
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("table")
    ap.add_argument("--stars-real", type=int, required=True)
    ap.add_argument("--stars-inv", type=int, nargs=2, required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    n1, n2 = a.stars_inv
    t = features(pd.read_csv(a.table))
    inv1 = (t["label"] == "inverted") & (t["inv_set"] == 1)
    inv2 = (t["label"] == "inverted") & (t["inv_set"] == 2)
    t["score_h"] = oof_scores(t, (t["label"] == "real") | inv1, a.stars_real / n1, extra=inv2)
    lo = t[t["band"] == "low"]
    real_c = lo[(lo["label"] == "real") & (lo["cls"] == "clean")]
    i2 = lo[inv2.loc[lo.index]]
    n_fa = ((lo["label"] == "inverted") & (lo["cls"] == "clean")).sum() * a.stars_real / (n1 + n2)
    print(f"SNR 7.5-9 clean signals: {len(real_c)} real, {n_fa:.0f} expected false alarms")
    print("cut    selected  expected false alarms  purity")
    for cut in (0.7, 0.75, 0.8, 0.85, 0.9):
        n = int((real_c["score_h"] >= cut).sum())
        fa = n_fa * (i2["score_h"] >= cut).mean()
        print(f"{cut:4.2f}  {n:8d}  {fa:21.1f}  {1 - fa / n if n else float('nan'):.2f}")
    t["score"] = oof_scores(t, t.index == t.index, a.stars_real / (n1 + n2))
    if a.out:
        t[["tic", "rank", "label", "inv_set", "band", "cls", "score", "score_h"]].to_csv(a.out, index=False)


if __name__ == "__main__":
    main()
