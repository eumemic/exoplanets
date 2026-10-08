"""Download the selected light curves per star and store compact arrays (one npz per star).

Usage: python download.py [targets.txt] [--workers N] [--threads M]
Resumable: stars whose npz exists are skipped. FITS are parsed in memory, never stored.
Each of N worker processes handles one star at a time and fetches its sectors with M threads.
(Parsing holds Python's GIL, so a single process with many threads used only ~2 cores.)
"""
import argparse
import io
import os
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests

from common import CAT, mast_url, read_lc_fits, s3_url, tic_path

_local = threading.local()
THREADS = 4               # concurrent fetches per star


def session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    return _local.s


def fetch(uri):
    # EXO_DATA_SOURCE=s3: try the AWS mirror first (fast and free inside AWS us-east-1), then MAST
    if os.environ.get("EXO_DATA_SOURCE") == "s3" and s3_url(uri):
        try:
            r = session().get(s3_url(uri), timeout=120)
            if r.status_code == 200 and r.content[:6] == b"SIMPLE":
                return r.content
        except requests.RequestException:
            pass
    for attempt in range(6):
        try:
            r = session().get(mast_url(uri), timeout=120)
            if r.status_code == 200 and r.content[:6] == b"SIMPLE":
                return r.content
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    return None


def do_star(tic, rows):
    out = tic_path(tic)
    if out.exists():
        return tic, "skip"
    arrays, sectors = {}, []
    with ThreadPoolExecutor(min(THREADS, len(rows))) as fx:
        blobs = list(fx.map(fetch, rows.uri))
    for (_, r), blob in zip(rows.iterrows(), blobs):
        if blob is None:
            continue
        try:
            d = read_lc_fits(io.BytesIO(blob), r.prov)
        except Exception as e:
            print(f"parse fail {tic} s{r.sector}: {e}", file=sys.stderr)
            continue
        if len(d["time"]) < 100:
            continue
        k = f"s{int(r.sector)}_"
        for name in ("time", "flux", "flux_err", "cx", "cy", "bkg"):
            arrays[k + name] = d[name]
        arrays[k + "prov"] = np.array(r.prov)
        arrays[k + "exptime"] = np.array(d["exptime"])
        sectors.append(int(r.sector))
    if not sectors:
        return tic, "empty"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, sectors=np.array(sectors), **arrays)
    tmp.rename(out)
    return tic, f"{len(sectors)} sectors"


def _init(threads):
    global THREADS
    THREADS = threads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="?", help="file with one TIC per line (default: all in manifest)")
    ap.add_argument("--workers", type=int, default=16, help="worker processes")
    ap.add_argument("--threads", type=int, default=THREADS, help="concurrent fetches per star")
    ap.add_argument("--manifest", default=str(CAT / "manifest.parquet"))
    a = ap.parse_args()
    m = pd.read_parquet(a.manifest)
    groups = dict(list(m.groupby("tic")))
    order = [int(x) for x in open(a.targets).read().split()] if a.targets else list(groups)
    groups = [(tic, groups[tic]) for tic in order if tic in groups and not tic_path(tic).exists()]
    t0 = time.time()
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.threads,)) as ex:
        futs = [ex.submit(do_star, tic, rows) for tic, rows in groups]
        for i, f in enumerate(as_completed(futs), 1):
            tic, status = f.result()
            if i % 200 == 0 or i == len(futs):
                rate = i / (time.time() - t0)
                print(f"{i}/{len(futs)} stars  {rate:.1f}/s  last: {tic} {status}", flush=True)


if __name__ == "__main__":
    main()
