"""Assemble one table row per candidate from the result files: transit fit, vetting, follow-up
centroids and neighbours, TRICERATOPS, host star, TOIs on the host and literature matches.

Usage: python candidate_table.py LIST.csv OUT.csv
LIST.csv columns: tic, rank, vet_dir, followup_dir, stars (catalogue parquet), notes.
"""
import glob
import json
import sys

import numpy as np
import pandas as pd

from common import DATA, RESULTS
from known import check


def fit_for(tic, P):
    for f in glob.glob(str(RESULTS / f"fit_tic{tic}_P*.json")):
        d = json.load(open(f))
        if abs(d["P"][1] / P - 1) < 1e-3:
            return d
    return None


def fpp_for(tic, P):
    for f in glob.glob(str(RESULTS / "fpp" / f"tic{tic}_P*_fpp.json")):
        p = float(f.split("_P")[1].split("_")[0])
        if abs(p / P - 1) < 2e-3:
            return json.load(open(f))
    return None


def main():
    todo = pd.read_csv(sys.argv[1])
    toi = pd.read_csv(DATA / "known" / "toi.csv")
    rows = []
    for r in todo.itertuples():
        v = json.load(open(f"{r.vet_dir}/tic{r.tic}_{r.rank}.json"))
        fu = json.load(open(f"{r.followup_dir}/tic{r.tic}_{r.rank}.json"))
        star = pd.read_parquet(r.stars).set_index("ID").loc[r.tic]
        P = v["period"]
        fit, fpp = fit_for(r.tic, P), fpp_for(r.tic, P)
        k = check(r.tic, P, float(star["ra"]), float(star["dec"]))
        host = toi[toi["TIC ID"] == r.tic]
        q = lambda key, i=1: round(fit[key][i], 6) if fit else np.nan
        rows.append(dict(
            TIC=r.tic, P_d=q("P") if fit else round(P, 6),
            P_err=round((fit["P"][2] - fit["P"][0]) / 2, 6) if fit else np.nan,
            T0_BJD=round(fit["t0"][1] + 2457000, 5) if fit else round(v["t0"] + 2457000, 5),
            Rp_Re=round(fit["Rp"][1], 2) if fit else round(v["rp_earth"], 2),
            b=round(fit["b"][1], 2) if fit else np.nan,
            T14_h=round(fit["T14_h"][1], 2) if fit else round(v["duration_h"], 2),
            depth_ppm=round(v["depth_ppm"]), MES=round(v["leo"].get("MES") or np.nan, 1),
            n_transits=int(v["leo"].get("N_transit") or 0),
            Tmag=round(star["Tmag"], 2), Teff=round(star["Teff"]), Rstar=round(star["rad"], 2),
            dist_pc=round(star["d"], 1), ruwe=star.get("ruwe", np.nan),
            centroid_offset_arcsec=round(fu["offset_qual"], 1) if fu.get("offset_qual") is not None else np.nan,
            nearest_capable_arcsec=fu.get("nearest_capable_arcsec"),
            followup_flags=",".join(fu.get("flags", [])),
            FPP=round(fpp["FPP_mean"], 3) if fpp else np.nan,
            FPP_sem=round(fpp["FPP_sem"], 3) if fpp and fpp.get("FPP_sem") is not None else np.nan,
            NFPP=float(f"{fpp['NFPP_max']:.2g}") if fpp else np.nan,
            host_tois=";".join(f"TOI-{t:.2f} ({d}, {p:.3f} d)" for t, d, p in zip(
                host["TOI"], host["TFOPWG Disposition"].fillna("PC"), host["Period (days)"])),
            literature=";".join(x for x in k["same_star"] if x.startswith("literature")),
            period_match=";".join(k["same_star_period_match"]),
            notes=r.notes if isinstance(r.notes, str) else ""))
    pd.DataFrame(rows).to_csv(sys.argv[2], index=False)
    print(pd.DataFrame(rows).drop(columns=["notes", "host_tois", "literature"]).to_string(index=False))


if __name__ == "__main__":
    main()
