"""Automated follow-up of shortlisted signals: TIC neighbours bright enough to mimic the depth,
and FFI difference-image centroids (transit-diffImage PRF fits via LEO-Vetter) in the sectors
where the transit is strongest.

Usage: python followup.py [--vetted results/vetted.csv] [--vet-dir results/vet]
                          [--stars data/catalogs/targets.parquet] [--out results/followup]
                          [--status new] [--max-fails 0] [--sectors 3] [--procs 4]
Writes <out>/tic<TIC>_<rank>.json and <out>/summary.csv.

Flags, using LEO-Vetter's pixel threshold (Kunimoto et al. 2025):
  offset    the PRF centroid of the highest-quality difference image is > 15" from the target
  no_pixel  no usable difference image
  close_nb  a TIC star within 15" (below the centroid resolution) could produce the depth
"""
import argparse
import contextlib
import io
import json
import os
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd

from common import CAT, DATA, RESULTS
from neighbors import capable_neighbours
from s3cut import cut

warnings.filterwarnings("ignore")
PIX = DATA / "followup_pixels"
OFFSET_MAX = 15.0


def _s3_tess_cut(self, fitsNum=0):
    """Replacement for transit-diffImage's get_tess_cut: cuts the pixels from the FFI cubes on the
    STScI bucket (s3cut.py) instead of downloading them from TESScut, which serves ~0.2 MB/s.
    Inside AWS a 200-s-cadence sector takes ~5 s instead of ~8 minutes."""
    d = self.ticData
    return cut(d["id"], d["raDegrees"], d["decDegrees"], self.nPixOnSide,
               os.path.join(self.outputDir, self.ticName), None if d["sector"] is None else {int(d["sector"])})


if os.environ.get("EXO_DATA_SOURCE") == "s3":
    from transitDiffImage import tessDiffImage as _tdi
    _tdi.tessDiffImage.get_tess_cut = _s3_tess_cut


def cutout_mb(sector):
    """Approximate TESScut size of the difference-image cutout: FFI cadence was 30 min in
    Sectors 1-26, 10 min in 27-55 and 200 s from 56, and TESScut serves ~0.2 MB/s."""
    return 11 if sector <= 26 else 34 if sector <= 55 else 110


def best_sectors(vet_dir, tic, rank, n):
    """Sectors with a transit SNR within 60% of the best one, cheapest cutouts first."""
    v = json.load(open(f"{vet_dir}/tic{tic}_{rank}.json"))
    ps = [(int(p["sector"]), p["depth_ppm"] / p["err_ppm"]) for p in v.get("per_sector", [])
          if p["err_ppm"] > 0]
    if not ps:
        return []
    top = max(snr for _, snr in ps)
    ok = [(cutout_mb(s), -snr, s) for s, snr in ps if snr >= 0.6 * top]
    return [s for _, _, s in sorted(ok)[:n]]


def centroids(tic, rank, ra, dec, P, t0, dur_h, sectors):
    from leo_vetter.pixel import multisector_images, planet_dict, star_dict

    star = star_dict(tic, ra, dec)
    star["planetData"] = [planet_dict(tic, rank, P, t0, dur_h / 24)]
    with contextlib.redirect_stdout(io.StringIO()):
        _, good, _, cents = multisector_images(star, sectors, save_dir=str(PIX), n_bad=2)
    return [dict(sector=int(s), offset_arc=float(c["offset_arc"]), quality=float(c["quality"]))
            for s, c in zip(good, cents)]


def one(args):
    sig, star, n_sectors, vet_dir, out = args
    tic, rank = int(sig["tic"]), int(sig["rank"])
    path = f"{out}/tic{tic}_{rank}.json"
    if os.path.exists(path):
        return json.load(open(path))
    res = dict(tic=tic, rank=rank, period=float(sig["period"]), depth_ppm=float(sig["depth_ppm"]))
    try:
        _, nb = capable_neighbours(tic, float(sig["depth_ppm"]))
        cap = nb[nb["capable"]]
        res["n_capable_2.5arcmin"] = int(len(cap))
        res["nearest_capable_arcsec"] = float(cap["sep_arcsec"].min()) if len(cap) else None
        res["capable_within_15arcsec"] = cap[cap["sep_arcsec"] < OFFSET_MAX][["ID", "sep_arcsec", "dT"]].round(2).values.tolist()
    except Exception as ex:
        res["neighbour_error"] = repr(ex)
    try:
        sectors = best_sectors(vet_dir, tic, rank, n_sectors)
        c = centroids(tic, rank, float(star["ra"]), float(star["dec"]), float(sig["period"]),
                      float(sig["t0"]), float(sig["duration_h"]), sectors)
        res["centroids"] = c
        if c:
            q = np.array([x["quality"] for x in c])
            off = np.array([x["offset_arc"] for x in c])
            res["offset_qual"] = float(off[np.argmax(q)])
            res["offset_mean"] = float(np.nansum(off * q) / np.nansum(q))
    except Exception as ex:
        res["pixel_error"] = repr(ex)
    finally:
        # FFI cutouts are ~100 MB per sector at 200-s cadence and transit-diffImage's difference-image
        # pickles ~35 MB; thousands of them filled a 300 GB disk
        for pat in ("*.fits", f"imageData_{tic}.{rank}_*.pickle"):
            for f in (PIX / f"tic{tic}").glob(pat):
                f.unlink(missing_ok=True)
    flags = []
    if res.get("offset_qual") is None:
        flags.append("no_pixel")
    elif res["offset_qual"] > OFFSET_MAX:
        flags.append("offset")
    if res.get("capable_within_15arcsec"):
        flags.append("close_nb")
    res["flags"] = flags
    with open(path, "w") as fh:
        json.dump(res, fh)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vetted", default=str(RESULTS / "vetted.csv"))
    ap.add_argument("--vet-dir", default=str(RESULTS / "vet"))
    ap.add_argument("--out", default=str(RESULTS / "followup"))
    ap.add_argument("--stars", default=str(CAT / "targets.parquet"))
    ap.add_argument("--status", default="new")
    ap.add_argument("--max-fails", type=int, default=0)
    ap.add_argument("--sectors", type=int, default=2)
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    PIX.mkdir(parents=True, exist_ok=True)
    v = pd.read_csv(a.vetted)
    v = v[(v["known_status"] == a.status) & (v["n_fail"] <= a.max_fails)]
    stars = pd.read_parquet(a.stars).set_index("ID")
    jobs = [(r.to_dict(), stars.loc[int(r.tic)].to_dict(), a.sectors, a.vet_dir, a.out)
            for _, r in v.iterrows()]
    print(len(jobs), "signals", flush=True)
    with Pool(a.procs) as pool:
        rows = pool.map(one, jobs, chunksize=1)
    s = pd.DataFrame([{k: r.get(k) for k in ("tic", "rank", "period", "depth_ppm", "offset_qual",
                                             "offset_mean", "n_capable_2.5arcmin",
                                             "nearest_capable_arcsec", "flags")} for r in rows])
    s["flags"] = s["flags"].apply(lambda f: ",".join(f) if f else "")
    s.to_csv(f"{a.out}/summary.csv", index=False)
    print(s.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
