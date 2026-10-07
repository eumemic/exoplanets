"""Export a phase-folded, binned light curve (other signals masked) for TRICERATOPS.

Usage: python export_fold.py TIC P T0 DUR_H OUT.npz [--mask P,T0,DUR_H ...]
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
a = ap.parse_args()
dur = a.dur_h / 24
prep = detrend_masked(load_star(a.tic), a.P, a.t0, dur, 0.75)
others = [tuple(float(x) for x in m.split(",")) for m in a.mask]
x, y, w = [], [], []
for p in prep:
    keep = np.ones(len(p["t"]), bool)
    for (P2, t2, d2) in others:
        keep &= np.abs(((p["t"] - t2 + 0.5 * P2) % P2) - 0.5 * P2) > 0.75 * d2 / 24
    ph = ((p["t"] - a.t0 + 0.5 * a.P) % a.P) - 0.5 * a.P
    m = keep & (np.abs(ph) < 3 * dur)
    x.append(ph[m]); y.append(p["r"][m]); w.append(1 / p["e"][m] ** 2)
x, y, w = (np.concatenate(v) for v in (x, y, w))
edges = np.arange(-3 * dur, 3 * dur + 1e-9, 5 / 1440)
idx = np.digitize(x, edges)
bx, by, be = [], [], []
for i in range(1, len(edges)):
    s = idx == i
    if s.sum() < 3:
        continue
    bx.append(np.sum(w[s] * x[s]) / np.sum(w[s]))
    by.append(1 + np.sum(w[s] * y[s]) / np.sum(w[s]))
    be.append(1 / np.sqrt(np.sum(w[s])))
np.savez(a.out, time=np.array(bx), flux=np.array(by), flux_err=np.array(be),
         sectors=np.array([p["sector"] for p in prep]), P=a.P)
print(f"{len(bx)} bins, median err {np.median(be) * 1e6:.0f} ppm -> {a.out}")
