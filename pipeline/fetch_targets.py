"""Fetch TIC 8.2 small dwarfs (R <= 0.75 Rsun, T <= 11.5) from MAST in Tmag slices."""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from astroquery.mast import Catalogs

OUT = Path(__file__).resolve().parent.parent / "data" / "catalogs" / "tic_small_dwarfs.parquet"
KEEP = ["ID", "GAIA", "ra", "dec", "pmRA", "pmDEC", "plx", "eclat", "Tmag", "Vmag", "Kmag",
        "GAIAmag", "gaiabp", "gaiarp", "Teff", "logg", "MH", "rad", "e_rad", "mass", "e_mass",
        "rho", "d", "lumclass", "contratio", "numcont", "disposition", "duplicate_id", "objType"]


def fetch(lo_hi):
    lo, hi = lo_hi
    for attempt in range(4):
        try:
            r = Catalogs.query_criteria(catalog="Tic", Tmag=[lo, hi], rad=[0.08, 0.75],
                                        lumclass="DWARF", objType="STAR").to_pandas()
            return r[[c for c in KEEP if c in r.columns]]
        except Exception as e:  # MAST is flaky under load; retry
            print(f"retry {lo}-{hi}: {e}", file=sys.stderr)
    raise RuntimeError(f"failed {lo}-{hi}")


edges = np.round(np.concatenate([[-2.0, 7.0, 8.0], np.arange(8.5, 11.5001, 0.1)]), 2)
slices = list(zip(edges[:-1], edges[1:]))
with ThreadPoolExecutor(6) as ex:
    parts = list(ex.map(fetch, slices))
df = pd.concat(parts, ignore_index=True)
# Slice boundaries are inclusive on both ends at MAST; drop the overlap.
df = df.drop_duplicates("ID")
df = df[df["disposition"].isna() | (df["disposition"] != "ARTIFACT")]
df = df[df["disposition"].isna() | (df["disposition"] != "DUPLICATE")]
df.to_parquet(OUT)
print(len(df), "stars ->", OUT)
print(df[["Tmag", "Teff", "rad", "d", "contratio"]].describe().round(3))
