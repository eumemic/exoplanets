"""TRICERATOPS false-positive probability (run with .venv-trice).

Usage: python fpp.py TIC FOLD.npz DEPTH_PPM [--runs N] [--draws N]
Uses SPOC apertures where available (TRICERATOPS get_spoc_apertures), else a 3x3 box.
"""
import argparse
import json

import numpy as np
import triceratops.triceratops as tr

ap = argparse.ArgumentParser()
ap.add_argument("tic", type=int)
ap.add_argument("fold")
ap.add_argument("depth_ppm", type=float)
ap.add_argument("--runs", type=int, default=5)
ap.add_argument("--draws", type=int, default=200000)
ap.add_argument("--sectors", help="comma-separated subset used for the field geometry")
ap.add_argument("--cc", help="contrast curve CSV (sep_arcsec,dmag) for unresolved-companion limits")
ap.add_argument("--cc-filt", default="TESS")
ap.add_argument("--tag", default="")
a = ap.parse_args()
d = np.load(a.fold)
sectors = np.array(sorted(set(int(s) for s in d["sectors"])))
if a.sectors:
    sectors = np.array([int(s) for s in a.sectors.split(",")])
target = None
for attempt in range(4):
    try:
        target = tr.target(ID=a.tic, sectors=sectors)
        if len(target.pix_coords) == len(sectors):
            break
    except Exception as ex:
        print("retrying target setup:", ex)
assert target is not None and len(target.pix_coords) == len(sectors), "TESScut downloads incomplete"
aps = []
for i, s in enumerate(sectors):
    c = np.round(target.pix_coords[i][0]).astype(int)
    aps.append(np.array([[c[0] + dx, c[1] + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)]))
target.calc_depths(tdepth=a.depth_ppm * 1e-6, all_ap_pixels=aps)
print(target.stars[["ID", "Tmag", "sep (arcsec)", "fluxratio", "tdepth"]].head(8).to_string())
fpps, nfpps = [], []
for r in range(a.runs):
    # parallel=True breaks on array shapes in triceratops 1.1.0; serial is reliable
    target.calc_probs(time=d["time"], flux_0=d["flux"], flux_err_0=float(np.median(d["flux_err"])), P_orb=float(d["P"]),
                      N=a.draws, parallel=False, verbose=0, exptime=10 / 1440,
                      contrast_curve_file=a.cc, filt=a.cc_filt)
    fpps.append(target.FPP); nfpps.append(target.NFPP)
    print(f"run {r}: FPP={target.FPP:.4f} NFPP={target.NFPP:.2e}", flush=True)
print(target.probs.sort_values("prob", ascending=False).head(6).to_string())
res = dict(tic=a.tic, FPP_mean=float(np.mean(fpps)), FPP_sd=float(np.std(fpps)), FPP=fpps,
           NFPP_max=float(np.max(nfpps)))
print(json.dumps(res))
with open(a.fold.replace(".npz", f"_fpp{a.tag}.json"), "w") as fh:
    json.dump(res, fh)
