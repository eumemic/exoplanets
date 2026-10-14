"""Fetch public TESS light curves for a bounded independent vetting sample.

Query provenance and sector metadata, select SPOC (>=100 s), then TESS-SPOC,
then QLP per sector, and retain original FITS with download URLs and SHA256.
Usage: python pipeline/independent_products.py SIGNALS.csv --out data/independent_vetting
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from pathlib import Path
import time

import pandas as pd
import requests


def archive_url(uri):
    if uri.startswith("mast:HLSP/"):
        return "https://archive.stsci.edu/hlsps/" + uri[len("mast:HLSP/"):]
    if uri.startswith("mast:TESS/product/"):
        name = uri.rsplit("/", 1)[-1]
        sector, tic = name.split("-")[1:3]
        return (f"https://archive.stsci.edu/missions/tess/tid/{sector}/"
                f"{tic[:4]}/{tic[4:8]}/{tic[8:12]}/{tic[12:]}/{name}")
    if uri.startswith("https://"):
        return uri
    raise ValueError(f"Unsupported archive URI: {uri}")


def fetch(row, out):
    url = archive_url(row["uri"])
    path = out / "fits" / url.rsplit("/", 1)[-1]
    result = dict(row, url=url, path=str(path), status="error")
    for attempt in range(3):
        try:
            if path.exists():
                blob = path.read_bytes()
            else:
                response = requests.get(url, timeout=(15, 60))
                response.raise_for_status()
                blob = response.content
            if not blob.startswith(b"SIMPLE"):
                raise ValueError("Response is not a FITS file")
            digest = hashlib.sha256(blob).hexdigest()
            expected = row.get("sha256")
            if isinstance(expected, str) and expected and digest != expected:
                raise ValueError(f"SHA256 mismatch: expected {expected}, received {digest}")
            if not path.exists():
                path.write_bytes(blob)
            result.update(status="ok", bytes=len(blob), sha256=digest)
            return result
        except (OSError, ValueError, requests.RequestException) as exc:
            result["error"] = str(exc)
            if attempt < 2:
                time.sleep(attempt + 1)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("signals")
    ap.add_argument("--out", type=Path, default=Path("data/independent_vetting"))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--manifest", type=Path, help="Replay exact products; verify sha256 when included")
    args = ap.parse_args()
    out = args.out
    (out / "fits").mkdir(parents=True, exist_ok=True)
    manifest = args.manifest or out / "manifest.csv"
    if not manifest.exists():
        if args.manifest:
            raise FileNotFoundError(manifest)
        from astroquery.mast import Observations
        ids = pd.read_csv(args.signals).tic.astype(str).tolist()
        Observations.TIMEOUT = 45
        obs = Observations.query_criteria(
            target_name=ids, obs_collection=["TESS", "HLSP"], dataproduct_type="timeseries",
            provenance_name=["SPOC", "TESS-SPOC", "QLP"])
        df = obs[["target_name", "provenance_name", "sequence_number", "t_exptime",
                  "dataURL", "s_ra", "s_dec", "t_min", "t_max"]].to_pandas()
        df = df.rename(columns={"target_name": "tic", "provenance_name": "provenance",
                                "sequence_number": "sector", "t_exptime": "exptime", "dataURL": "uri"})
        df["tic"] = df.tic.astype(int)
        df = df[df.uri.str.endswith(("lc.fits", "llc.fits"), na=False)]
        df = df[~((df.provenance == "SPOC") & (df.exptime < 100))]
        df["priority"] = df.provenance.map({"SPOC": 0, "TESS-SPOC": 1, "QLP": 2})
        df = df.sort_values(["tic", "sector", "priority", "uri"])
        df.to_csv(out / "available_products.csv", index=False)
        df = df.drop_duplicates(["tic", "sector"])
        df["sector"] = df.sector.astype(int)
        df.to_csv(manifest, index=False)
    rows = pd.read_csv(manifest).to_dict("records")
    requested = set(pd.read_csv(args.signals).tic.astype(int))
    if set(int(row["tic"]) for row in rows) != requested:
        raise ValueError("Manifest TICs must match the requested signal sample")
    results = []
    with ThreadPoolExecutor(args.workers) as pool:
        jobs = [pool.submit(fetch, row, out) for row in rows]
        for future in as_completed(jobs):
            results.append(future.result())
            if len(results) % 20 == 0 or len(results) == len(rows):
                print(f"Downloaded {len(results)}/{len(rows)}: "
                      f"{sum(r['status'] == 'ok' for r in results)} valid FITS", flush=True)
    pd.DataFrame(results).sort_values(["tic", "sector"]).to_csv(out / "downloads.csv", index=False)
    errors = sum(r["status"] != "ok" for r in results)
    if errors:
        raise SystemExit(f"{errors} products failed; see {out / 'downloads.csv'}")


if __name__ == "__main__":
    main()
