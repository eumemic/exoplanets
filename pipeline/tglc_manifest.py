"""Manifest of TGLC light curves (TESS-Gaia Light Curves, Han & Brandt 2023; PSF photometry of FFIs for
stars to T = 16) for a target list, built without listing the bucket: tess-point gives each star's
sectors, cameras and CCDs, and the path follows from the Gaia DR3 source ID. TIC 8.2 lists Gaia DR2 IDs,
which are the same as DR3 for most stars; products that do not exist are dropped. The STScI bucket has
TGLC for Sectors 1-55.

Usage: python tglc_manifest.py TARGETS.parquet --out MANIFEST.parquet [--max-sector 55] [--threads 256]
Run inside AWS us-east-1 (anonymous S3 HEAD requests). Writes the manifest format download.py reads.
"""
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor

import boto3
import numpy as np
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config
from tess_stars2px import tess_stars2px_function_entry

BUCKET = "stpubdata"
KEY = "mast/hlsp/tglc/s{s:04d}/cam{c}-ccd{d}/{p}/hlsp_tglc_tess_ffi_gaiaid-{g}-s{s:04d}-cam{c}-ccd{d}_tess_v1_llc.fits"
_local = threading.local()


def tglc_key(gaia, sector, cam, ccd):
    """Bucket key of a TGLC light curve. The four directory levels are "00" plus the first 14 digits of
    the Gaia ID, in groups of four (1014525155680624640 -> 0010/1452/5155/6806), as in MAST's download
    scripts."""
    p = ("00" + str(gaia))[:16]
    return KEY.format(s=sector, c=cam, d=ccd, p="/".join(p[i:i + 4] for i in (0, 4, 8, 12)), g=gaia)


def exists(key):
    if not hasattr(_local, "s3"):
        _local.s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED))
    try:
        _local.s3.head_object(Bucket=BUCKET, Key=key)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-sector", type=int, default=55)
    ap.add_argument("--threads", type=int, default=256)
    a = ap.parse_args()
    t = pd.read_parquet(a.targets, columns=["ID", "GAIA", "ra", "dec"]).dropna(subset=["GAIA"])
    t["GAIA"] = t["GAIA"].astype("int64")
    r = tess_stars2px_function_entry(t["ID"].values, t["ra"].values, t["dec"].values)
    pos = pd.DataFrame(dict(tic=r[0], sector=r[3], cam=r[4], ccd=r[5]))
    pos = pos[(pos["sector"] >= 1) & (pos["sector"] <= a.max_sector)].drop_duplicates(["tic", "sector"])
    pos = pos.merge(t[["ID", "GAIA"]].rename(columns={"ID": "tic"}), on="tic")
    pos["key"] = [tglc_key(g, s, c, d) for g, s, c, d in zip(pos.GAIA, pos.sector, pos.cam, pos.ccd)]
    with ThreadPoolExecutor(a.threads) as ex:
        pos["ok"] = list(ex.map(exists, pos["key"]))
    m = pos[pos["ok"]]
    out = pd.DataFrame(dict(tic=m["tic"].astype("int64"), prov="TGLC", sector=m["sector"].astype(int),
                            exptime=np.where(m["sector"] <= 26, 1800.0, 600.0),
                            uri="mast:HLSP/tglc/" + m["key"].str[len("mast/hlsp/tglc/"):]))
    out.to_parquet(a.out)
    print(f"{len(t):,} stars, {len(pos):,} star-sectors on silicon in Sectors 1-{a.max_sector}, "
          f"{len(out):,} TGLC light curves found for {out.tic.nunique():,} stars -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
