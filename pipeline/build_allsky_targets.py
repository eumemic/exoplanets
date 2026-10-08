"""All-sky target list from the TIC on the STScI open-data bucket (TIC 8.2 as HATS parquet, 1,579
files, read anonymously and in parallel; run inside AWS us-east-1): FGKM dwarfs brighter than
T = 13.5 that the earlier searches did not cover.

Usage: python build_allsky_targets.py [--tmax 13.5] [--teff-max 6500] [--out allsky]
Writes data/catalogs/<out>.parquet and <out>.txt.
"""
import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd
import pyarrow.fs as pafs
import pyarrow.parquet as pq

from common import CAT

TIC_HATS = "stpubdata/tess/public/hats/tic/tic/dataset"
COLS = ["ID", "GAIA", "ra", "dec", "plx", "eclat", "Tmag", "Teff", "logg", "MH", "rad", "e_rad",
        "mass", "e_mass", "rho", "d", "lumclass", "contratio", "numcont", "disposition", "objType"]
EARLIER = ("targets.parquet", "toi_hosts.parquet", "faint_targets.parquet")


def read_part(args):
    path, tmax, teff_max, rmax = args
    fs = pafs.S3FileSystem(anonymous=True, region="us-east-1")
    t = pq.read_table(path, columns=COLS, filesystem=fs,
                      filters=[("Tmag", "<=", tmax), ("Teff", "<=", teff_max), ("rad", "<=", rmax),
                               ("lumclass", "==", "DWARF"), ("objType", "==", "STAR")])
    return t.to_pandas()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmax", type=float, default=13.5)
    ap.add_argument("--teff-max", type=float, default=6500)
    ap.add_argument("--rmax", type=float, default=1.5)
    ap.add_argument("--out", default="allsky")
    a = ap.parse_args()
    fs = pafs.S3FileSystem(anonymous=True, region="us-east-1")
    files = sorted(f.path for f in fs.get_file_info(pafs.FileSelector(TIC_HATS, recursive=True))
                   if f.path.endswith(".parquet"))
    t0 = time.time()
    with ProcessPoolExecutor(2 * (os.cpu_count() or 8)) as ex:
        parts = list(ex.map(read_part, [(f, a.tmax, a.teff_max, a.rmax) for f in files]))
    t = pd.concat(parts, ignore_index=True)
    print(f"{len(t):,} dwarfs with T <= {a.tmax} read from {len(files)} files in {time.time() - t0:.0f} s",
          flush=True)
    t = t[~t["disposition"].isin(["SPLIT", "DUPLICATE", "ARTIFACT"])]
    t["ID"] = t["ID"].astype("int64")
    done = set()
    for f in EARLIER:
        if (CAT / f).exists():
            done |= set(pd.read_parquet(CAT / f, columns=["ID"])["ID"].astype("int64"))
    t = t[~t["ID"].isin(done)].drop_duplicates("ID").sort_values("Tmag")
    t.to_parquet(CAT / f"{a.out}.parquet")
    (CAT / f"{a.out}.txt").write_text("\n".join(str(i) for i in t["ID"]) + "\n")
    print(f"{len(t):,} targets after removing {len(done):,} already searched -> {a.out}.parquet")
    print(pd.cut(t["Teff"], [0, 3900, 5300, 6000, 6500]).value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
