"""Unpromoted SPOC TCEs worth a second look: planet-sized (Rp <= 6 Re from the TCE depth, depth
>= 50 ppm), model SNR 7.1-1000, 0.5-30 d, on FGKM dwarfs (Teff < 6500 K, R < 1.5 Rsun), and not at the period (or a
1/3...3 harmonic) of any TOI or CTOI on the same star. Duplicates of one signal across SPOC runs
are merged, keeping the highest-SNR entry.

Writes data/catalogs/tce_targets.csv (one row per TCE), tce_hosts.parquet and tce_hosts.txt.
"""
import numpy as np
import pandas as pd

from common import CAT, DATA

K = DATA / "known"
H = (1 / 3, 1 / 2, 2 / 3, 1, 3 / 2, 2, 3)


def main():
    tce = pd.read_parquet(K / "tce_all.parquet").dropna(subset=["tce_period"])
    hosts = pd.read_parquet(K / "tce_tic.parquet").set_index("ID")
    known = {}
    for f in ("toi.csv", "ctoi.csv"):
        d = pd.read_csv(K / f)
        for tic, p in zip(d["TIC ID"], d["Period (days)"]):
            known.setdefault(int(tic), []).append(p)
    tce["pkey"] = np.round(np.log(tce["tce_period"]) / 0.005).astype(int)
    tce = tce.sort_values("tce_model_snr", ascending=False).drop_duplicates(["ticid", "pkey"])
    match = [any(p == p and p > 0 and abs(per / (p * h) - 1) < 0.003 for p in known.get(int(t), []) for h in H)
             for t, per in zip(tce["ticid"], tce["tce_period"])]
    tce = tce[~np.array(match)].join(hosts[["Teff", "rad"]], on="ticid")
    tce["rp_est"] = np.sqrt(tce["tce_depth"].clip(lower=0) * 1e-6) * tce["rad"] * 109.1
    sel = tce[(tce["Teff"] < 6500) & (tce["rad"] < 1.5) & (tce["tce_period"] > 0.5) & (tce["tce_period"] < 30)
              & (tce["tce_model_snr"] >= 7.1) & (tce["rp_est"] <= 6)
              # a few runs (e.g. Sector 52) list sub-ppm depths at SNR in the thousands
              & (tce["tce_depth"] >= 50) & (tce["tce_model_snr"] < 1000)]
    sel.drop(columns="pkey").to_csv(CAT / "tce_targets.csv", index=False)
    h = hosts.loc[sel["ticid"].unique()].reset_index()
    h.to_parquet(CAT / "tce_hosts.parquet")
    (CAT / "tce_hosts.txt").write_text("\n".join(str(i) for i in h["ID"]) + "\n")
    print(f"{len(sel)} TCEs on {len(h)} stars")


if __name__ == "__main__":
    main()
