"""Pixel-level localisation with FFI difference images (transit-diffImage PRF centroids via LEO-Vetter).

Usage: python pixel_vet.py TIC PERIOD T0_BTJD DURATION_H SECTOR[,SECTOR...] [--rank N]
Prints per-sector PRF-fit offsets of the difference-image source from the TIC position.
"""
import argparse
import json
import os
import warnings

import pandas as pd

from common import CAT, RESULTS

warnings.filterwarnings("ignore")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tic", type=int)
    ap.add_argument("period", type=float)
    ap.add_argument("t0", type=float)
    ap.add_argument("duration_h", type=float)
    ap.add_argument("sectors")
    ap.add_argument("--rank", type=int, default=1)
    ap.add_argument("--n-bad", type=int, default=2)
    a = ap.parse_args()
    from leo_vetter.pixel import multisector_images, planet_dict, star_dict

    row = pd.read_parquet(CAT / "targets.parquet").set_index("ID").loc[a.tic]
    out = RESULTS / "pixels"
    star = star_dict(a.tic, float(row["ra"]), float(row["dec"]))
    star["planetData"] = [planet_dict(a.tic, a.rank, a.period, a.t0, a.duration_h / 24)]
    sectors = [int(s) for s in a.sectors.split(",")]
    _, good, _, cents = multisector_images(star, sectors, save_dir=str(out), n_bad=a.n_bad)
    res = [{k: (float(v) if k != "sector" else int(v)) for k, v in c.items()} for c in cents]
    for c in res:
        print(f"S{c['sector']}: offset {c['offset_arc']:.1f}\" ({c['offset_pix']:.2f} px), quality {c['quality']:.2f}")
    with open(out / f"tic{a.tic}_{a.rank}_centroids.json", "w") as fh:
        json.dump(res, fh)


if __name__ == "__main__":
    main()
