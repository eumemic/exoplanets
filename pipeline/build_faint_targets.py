"""Faint M-dwarf targets (11.5 < T <= 13.5, Teff <= 3900 K, R <= 0.6 Rsun) not already searched
as K/M dwarfs or TOI hosts, split into tiers by brightness.

Writes data/catalogs/faint_targets.parquet and faint_t1/faint_t2 .txt and .parquet
(T <= 12.5 and 12.5-13.5).
"""
import pandas as pd

from common import CAT


def main():
    d = pd.read_parquet(CAT / "tic_faint_mdwarfs.parquet")
    d["ID"] = d["ID"].astype("int64")      # MAST returns TIC IDs as strings
    d = d[(d["Teff"] <= 3900) & (d["rad"] <= 0.6) & (d["Tmag"] > 11.5)]
    done = set(pd.read_parquet(CAT / "targets.parquet")["ID"]) | set(pd.read_parquet(CAT / "toi_hosts.parquet")["ID"])
    d = d[~d["ID"].isin(done)].sort_values("Tmag")
    d.to_parquet(CAT / "faint_targets.parquet")
    for name, sel in (("faint_t1", d["Tmag"] <= 12.5), ("faint_t2", d["Tmag"] > 12.5)):
        (CAT / f"{name}.txt").write_text("\n".join(str(i) for i in d.loc[sel, "ID"]) + "\n")
        d[sel].to_parquet(CAT / f"{name}.parquet")
        print(name, int(sel.sum()), "stars")


if __name__ == "__main__":
    main()
