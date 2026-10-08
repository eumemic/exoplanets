"""Light-curve index for millions of stars without MAST queries: lists the SPOC 2-min, TESS-SPOC
and QLP products on the STScI open-data bucket, and reads MAST's per-sector bulk-download scripts
for the HLSP sectors the bucket does not have yet. Keeps one product per star and sector
(SPOC 2-min, then TESS-SPOC, then QLP), in the manifest format download.py reads.

Usage: python index_s3.py TARGETS.parquet --out MANIFEST.parquet [--procs N]
Run inside AWS us-east-1 (anonymous S3 access; ~10^8 keys are listed). Listing responses are
parsed in N worker processes, since parsing in threads is serialized by Python's GIL.
"""
import argparse
import re
import time
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import boto3
import numpy as np
import pandas as pd
import requests
from botocore import UNSIGNED
from botocore.config import Config

from common import PROV_RANK

BUCKET = "stpubdata"
SCRIPTS = {"QLP": "https://archive.stsci.edu/hlsps/qlp/download_scripts/",
           "TESS-SPOC": "https://archive.stsci.edu/hlsps/tess-spoc/download_scripts/"}
TIC_RE = {"QLP": re.compile(r"_s(\d{4})-(\d{16})_tess_v01_llc\.fits$"),
          "TESS-SPOC": re.compile(r"_phot_(\d{16})-s(\d{4})_tess_v1_lc\.fits$"),
          "SPOC": re.compile(r"-s(\d{4})-(\d{16})-\d{4}-s_lc\.fits$")}
_s3 = None
_want = np.zeros(0, np.int64)       # sorted target TIC IDs (a Python set of millions costs ~0.4 GB per process)


def _init(targets):
    global _want
    _want = np.unique(pd.read_parquet(targets, columns=["ID"])["ID"].astype("int64").values)


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name="us-east-1",
                           config=Config(signature_version=UNSIGNED, max_pool_connections=256))
    return _s3


def children(prefix):
    """Sub-prefixes one level below prefix."""
    out = []
    for page in s3().get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix, Delimiter="/"):
        out += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
    return out


def keys(prefix):
    for page in s3().get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        for o in page.get("Contents", []):
            yield o["Key"]


def parse(prov, key):
    m = TIC_RE[prov].search(key)
    if not m:
        return None
    a, b = m.groups()
    return (int(b), int(a)) if prov != "TESS-SPOC" else (int(a), int(b))   # (tic, sector)


def uri(prov, key):
    if prov == "SPOC":
        return "mast:TESS/product/" + key.rsplit("/", 1)[1]
    return "mast:HLSP/" + key[len("mast/hlsp/"):]


def scan(job):
    prov, prefix = job
    found = [(p, k) for k in keys(prefix) for p in [parse(prov, k)] if p]
    if not found:
        return []
    keep = np.isin(np.array([p[0] for p, _ in found], np.int64), _want)
    return [(p[0], p[1], prov, uri(prov, k)) for (p, k), ok in zip(found, keep) if ok]


def leaf_prefixes(prov, sectors):
    """Prefixes small enough to list in one task: sector / TIC digits 5-8 (and 9-12 for 2-min)."""
    base = {"QLP": "mast/hlsp/qlp/s{:04d}/0000/", "TESS-SPOC": "mast/hlsp/tess-spoc/s{:04d}/target/0000/",
            "SPOC": "tess/public/tid/s{:04d}/0000/"}[prov]
    with ThreadPoolExecutor(64) as ex:
        lists = ex.map(children, [base.format(s) for s in sectors])
    return [p for ps in lists for p in ps]


def sectors_on_bucket(prov):
    base = {"QLP": "mast/hlsp/qlp/", "TESS-SPOC": "mast/hlsp/tess-spoc/", "SPOC": "tess/public/tid/"}[prov]
    return sorted(int(p.rstrip("/")[-4:]) for p in children(base) if re.search(r"/s\d{4}/$", p))


def script_rows(prov, sectors_have, want):
    """Products in MAST bulk-download scripts for sectors missing from the bucket."""
    html = requests.get(SCRIPTS[prov], timeout=60).text
    pat = r'href="(hlsp_qlp_tess_ffi_s(\d{4})_tess_v01_llc-fits\.sh)"' if prov == "QLP" else \
          r'href="(hlsp_tess-spoc_tess_phot_s(\d{4})_tess_v1_dl-lc\.sh)"'
    rows = []
    for name, s in sorted(set(re.findall(pat, html))):
        if int(s) in sectors_have or int(s) > 200:
            continue
        txt = requests.get(SCRIPTS[prov] + name, timeout=600).text
        n0 = len(rows)
        found = [(p, u) for u in re.findall(r"uri=(mast:HLSP/[^'\s]+)", txt) for p in [parse(prov, u)] if p]
        if found:
            keep = np.isin(np.array([p[0] for p, _ in found], np.int64), want)
            rows += [(p[0], p[1], prov, u) for (p, u), ok in zip(found, keep) if ok]
        print(f"  {prov} s{s} from MAST script: {len(rows) - n0} products", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets")
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=int(1.5 * (os.cpu_count() or 8)))
    a = ap.parse_args()
    _init(a.targets)
    want = _want
    print(f"{len(want):,} target stars", flush=True)
    rows = []
    for prov in ("SPOC", "TESS-SPOC", "QLP"):
        t0 = time.time()
        have = sectors_on_bucket(prov)
        jobs = [(prov, p) for p in leaf_prefixes(prov, have)]
        n0 = len(rows)
        with ProcessPoolExecutor(a.procs, initializer=_init, initargs=(a.targets,)) as ex:
            for r in ex.map(scan, jobs, chunksize=4):
                rows += r
        print(f"{prov}: sectors {have[0]}-{have[-1]} on the bucket, {len(jobs)} prefixes listed, "
              f"{len(rows) - n0:,} products in {time.time() - t0:.0f} s", flush=True)
        if prov in SCRIPTS:
            rows += script_rows(prov, set(have), want)
    m = pd.DataFrame(rows, columns=["tic", "sector", "prov", "uri"])
    m["rank"] = m["prov"].map(PROV_RANK)
    m = m.sort_values(["tic", "sector", "rank"]).drop_duplicates(["tic", "sector"]).drop(columns="rank")
    m["exptime"] = np.where(m["prov"] == "SPOC", 120.0,
                            np.where(m["sector"] <= 26, 1800.0, np.where(m["sector"] <= 55, 600.0, 200.0)))
    m = m[["tic", "prov", "sector", "exptime", "uri"]].reset_index(drop=True)
    m.to_parquet(a.out)
    n = m.groupby("tic").size()
    print(f"{len(m):,} light curves for {len(n):,} of {len(want):,} stars; sectors per star: "
          f"median {n.median():.0f}, mean {n.mean():.1f}; by provenance {m['prov'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
