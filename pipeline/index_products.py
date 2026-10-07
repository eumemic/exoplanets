"""List SPOC / TESS-SPOC / QLP light-curve products per target and pick one per sector.

Writes data/catalogs/manifest.parquet with one row per (tic, sector).
"""
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from astroquery.mast import Observations

from common import CAT, PROV_RANK

BATCH = 300


def query(ids):
    for attempt in range(5):
        try:
            r = Observations.query_criteria(
                target_name=[str(i) for i in ids], obs_collection=["TESS", "HLSP"],
                dataproduct_type="timeseries", provenance_name=list(PROV_RANK))
            df = r[["target_name", "provenance_name", "sequence_number", "t_exptime",
                    "dataURL"]].to_pandas()
            return df
        except Exception as e:
            print("retry", attempt, e, file=sys.stderr)
    raise RuntimeError("MAST query failed")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default=str(CAT / "targets.parquet"))
    ap.add_argument("--out", default=str(CAT / "manifest.parquet"))
    a = ap.parse_args()
    targets = pd.read_parquet(a.targets)
    ids = targets["ID"].astype(int).tolist()
    batches = [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]
    with ThreadPoolExecutor(6) as ex:
        parts = []
        for i, df in enumerate(ex.map(query, batches)):
            parts.append(df)
            if i % 10 == 0:
                print(f"{i + 1}/{len(batches)} batches", flush=True)
    m = pd.concat(parts, ignore_index=True)
    m = m.rename(columns={"target_name": "tic", "provenance_name": "prov",
                          "sequence_number": "sector", "t_exptime": "exptime", "dataURL": "uri"})
    m["tic"] = m["tic"].astype(int)
    m = m[m["uri"].str.endswith(("lc.fits", "llc.fits"))]
    # SPOC also has 20 s products for some targets; the 120 s file is the planet-search product.
    m = m[~((m["prov"] == "SPOC") & (m["exptime"] < 100))]
    m["rank"] = m["prov"].map(PROV_RANK)
    m = m.sort_values(["tic", "sector", "rank"]).drop_duplicates(["tic", "sector"])
    m.drop(columns="rank").to_parquet(a.out)
    print(len(m), "products for", m["tic"].nunique(), "stars")
    print(m.groupby("prov").size())


if __name__ == "__main__":
    main()
