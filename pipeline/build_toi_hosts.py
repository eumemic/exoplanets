"""Target list for the extra-planet search: every host of a TOI dispositioned CP, KP, PC or APC.

Writes data/catalogs/toi_hosts.parquet (TIC 8.2 columns) and data/catalogs/toi_hosts.txt.
"""
import numpy as np
import pandas as pd

from common import CAT, DATA
from fetch_tic_by_id import fetch_tic


def main():
    toi = pd.read_csv(DATA / "known" / "toi.csv")
    disp = toi["TFOPWG Disposition"].fillna("PC")
    hosts = np.sort(toi.loc[disp.isin(["CP", "KP", "PC", "APC"]), "TIC ID"].unique().astype(np.int64))
    tic = fetch_tic(hosts)
    missing = sorted(set(hosts) - set(tic["ID"]))
    print(f"{len(hosts)} hosts, {len(tic)} TIC rows, {len(missing)} missing")
    tic.to_parquet(CAT / "toi_hosts.parquet")
    (CAT / "toi_hosts.txt").write_text("\n".join(str(i) for i in tic["ID"]) + "\n")


if __name__ == "__main__":
    main()
