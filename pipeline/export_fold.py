"""Export a phase-folded, binned light curve (other signals masked) for TRICERATOPS.

Usage: python export_fold.py TIC P T0 DUR_H OUT.npz [--mask P,T0,DUR_H ...] [--single-cadence]

By default every sector is folded together and binned to 5 minutes (fpp.py models such folds with a 10-minute
exposure). TRICERATOPS models a single exposure time, so with --single-cadence only the sectors of one cadence are
used: the cadence (2 min, 200 s, 10 min or 30 min) whose in-transit points carry the most information (the largest sum
of inverse variances within half a duration of mid-transit). Cadences shorter than 9 minutes are binned in phase to
their own length, longer ones are kept unbinned, and the fold records the exposure (exptime, days) and the cadence's
sectors ranked by the same information (sectors_ranked), which fpp_pool.py uses to choose the field geometry.
"""
import argparse

import numpy as np

from common import load_star
from vet import detrend_masked

ap = argparse.ArgumentParser()
ap.add_argument("tic", type=int)
ap.add_argument("P", type=float)
ap.add_argument("t0", type=float)
ap.add_argument("dur_h", type=float)
ap.add_argument("out")
ap.add_argument("--mask", nargs="*", default=[])
ap.add_argument("--single-cadence", action="store_true")
ap.add_argument("--phase-bin-min", type=float, help="with --single-cadence, bin 10- and 30-minute data in phase to this many "
                "minutes instead of leaving them unbinned (the model still integrates each point over the full exposure)")
a = ap.parse_args()
dur = a.dur_h / 24
prep = detrend_masked(load_star(a.tic), a.P, a.t0, dur, 0.75)
others = [tuple(float(x) for x in m.split(",")) for m in a.mask]
seg = []
for p in prep:
    keep = np.ones(len(p["t"]), bool)
    for (P2, t2, d2) in others:
        keep &= np.abs(((p["t"] - t2 + 0.5 * P2) % P2) - 0.5 * P2) > 0.75 * d2 / 24
    ph = ((p["t"] - a.t0 + 0.5 * a.P) % a.P) - 0.5 * a.P
    m = keep & (np.abs(ph) < 3 * dur)
    w = 1 / p["e"][m] ** 2
    cad = int(round(p["exptime"] / 10.0)) * 10 if np.isfinite(p["exptime"]) else 0
    seg.append(dict(sector=int(p["sector"]), cad=cad, x=ph[m], y=p["r"][m], w=w, info=float(np.sum(w[np.abs(ph[m]) < 0.5 * dur]))))


def binned(x, y, w, width, min_n):
    edges = np.arange(-3 * dur, 3 * dur + 1e-9, width)
    idx = np.digitize(x, edges)
    bx, by, be = [], [], []
    for i in range(1, len(edges)):
        s = idx == i
        if s.sum() < min_n:
            continue
        bx.append(np.sum(w[s] * x[s]) / np.sum(w[s]))
        by.append(1 + np.sum(w[s] * y[s]) / np.sum(w[s]))
        be.append(1 / np.sqrt(np.sum(w[s])))
    return np.array(bx), np.array(by), np.array(be)


extra = {}
if a.single_cadence:
    info = {}
    for s in seg:
        info[s["cad"]] = info.get(s["cad"], 0.0) + s["info"]
    cad = max(info, key=info.get)
    use = sorted((s for s in seg if s["cad"] == cad), key=lambda s: -s["info"])
    x, y, w = (np.concatenate([s[k] for s in use]) for k in ("x", "y", "w"))
    if cad < 540:
        bx, by, be = binned(x, y, w, cad / 86400, 1)
    elif a.phase_bin_min:
        bx, by, be = binned(x, y, w, a.phase_bin_min / 1440, 1)
    else:
        o = np.argsort(x)
        bx, by, be = x[o], 1 + y[o], 1 / np.sqrt(w[o])
    extra = dict(exptime=cad / 86400, cadence_s=cad, sectors_ranked=np.array([s["sector"] for s in use if s["info"] > 0]),
                 info_by_cadence=np.array([[c, v] for c, v in sorted(info.items())]))
    sectors = np.array([s["sector"] for s in use])
else:
    x, y, w = (np.concatenate([s[k] for s in seg]) for k in ("x", "y", "w"))
    bx, by, be = binned(x, y, w, 5 / 1440, 3)
    sectors = np.array([p["sector"] for p in prep])
np.savez(a.out, time=bx, flux=by, flux_err=be, sectors=sectors, P=a.P, **extra)
print(f"{len(bx)} points, median err {np.median(be) * 1e6:.0f} ppm"
      + (f", {extra['cadence_s']} s cadence, sectors {','.join(map(str, extra['sectors_ranked']))}" if extra else "") + f" -> {a.out}")
