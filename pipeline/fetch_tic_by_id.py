"""Fetch TIC 8.2 rows for a list of TIC IDs (by-ID queries are complete, unlike criteria queries)."""
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from astroquery.mast import Catalogs

KEEP = ["ID", "GAIA", "ra", "dec", "pmRA", "pmDEC", "plx", "eclat", "Tmag", "Vmag", "Kmag",
        "GAIAmag", "gaiabp", "gaiarp", "Teff", "e_Teff", "logg", "MH", "rad", "e_rad", "mass",
        "e_mass", "rho", "d", "lumclass", "contratio", "numcont", "disposition", "objType"]


def fetch(ids):
    for attempt in range(5):
        try:
            r = Catalogs.query_criteria(catalog="Tic", ID=[int(i) for i in ids]).to_pandas()
            return r[[c for c in KEEP if c in r.columns]]
        except Exception as e:
            print("retry", attempt, e, file=sys.stderr)
    raise RuntimeError("TIC query failed")


def fetch_tic(ids, batch=500, workers=6):
    ids = list(ids)
    chunks = [ids[i:i + batch] for i in range(0, len(ids), batch)]
    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(fetch, chunks))
    df = pd.concat(parts, ignore_index=True)
    df["ID"] = df["ID"].astype(int)
    return df.drop_duplicates("ID")


if __name__ == "__main__":
    ids = [int(x) for x in open(sys.argv[1]).read().split()]
    df = fetch_tic(ids)
    df.to_parquet(sys.argv[2])
    print(len(df), "rows ->", sys.argv[2])
