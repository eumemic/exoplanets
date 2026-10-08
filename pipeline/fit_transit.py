"""Transit-model fit (batman + emcee) for one signal, masking other known signals on the star.

Usage: python fit_transit.py TIC P T0 DUR_H [--mask P,T0,DUR_H ...] [--steps N]
Fits P, T0, Rp/R*, b, rho* (prior from TIC), quadratic LD fixed (Claret via LEO-Vetter),
with 10-min supersampling for FFI cadences. Prints posteriors and saves a fold plot + JSON.
"""
import argparse
import json
import warnings

import numpy as np
import pandas as pd

from common import CAT, RESULTS, load_star
from search import bin_sector, expected_duration
from vet import detrend_masked, star_dict

warnings.filterwarnings("ignore")
G_CGS = 6.674e-8


def model_flux(theta, t, u, exptime_d):
    import batman

    P, t0, k, b, rho = theta
    a_rs = (G_CGS * rho * 1.41 * (P * 86400) ** 2 / (3 * np.pi)) ** (1 / 3)
    if b >= a_rs or k <= 0:
        return None
    inc = np.degrees(np.arccos(b / a_rs))
    out = np.ones_like(t)
    for exp in np.unique(exptime_d):
        m = exptime_d == exp
        pr = batman.TransitParams()
        pr.t0, pr.per, pr.rp, pr.a, pr.inc, pr.ecc, pr.w = t0, P, k, a_rs, inc, 0.0, 90.0
        pr.u, pr.limb_dark = list(u), "quadratic"
        ss = max(1, int(round(exp / (2 / 1440))))
        bm = batman.TransitModel(pr, t[m], supersample_factor=ss, exp_time=exp)
        out[m] = bm.light_curve(pr)
    return out


def main():
    import emcee

    ap = argparse.ArgumentParser()
    ap.add_argument("tic", type=int)
    ap.add_argument("P", type=float)
    ap.add_argument("t0", type=float)
    ap.add_argument("dur_h", type=float)
    ap.add_argument("--mask", nargs="*", default=[])
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--stars", default=str(CAT / "targets.parquet"))
    a = ap.parse_args()
    row = pd.read_parquet(a.stars).set_index("ID").loc[a.tic].to_dict()
    star = star_dict(row)
    sectors = load_star(a.tic)
    dur = a.dur_h / 24
    prep = detrend_masked(sectors, a.P, a.t0, dur, 0.75)
    others = [tuple(float(x) for x in m.split(",")) for m in a.mask]
    T, R, E, X = [], [], [], []
    for p in prep:
        keep = np.ones(len(p["t"]), bool)
        for (P2, t2, d2) in others:
            ph2 = ((p["t"] - t2 + 0.5 * P2) % P2) - 0.5 * P2
            keep &= np.abs(ph2) > 0.75 * d2 / 24
        t, r, e = p["t"][keep], p["r"][keep], p["e"][keep]
        if p["exptime"] < 300:          # bin 2-min/200-s data to 10 min for speed
            t, r, e = bin_sector(t, r, e, 10 / 1440)
            exp = 10 / 1440
        else:
            exp = p["exptime"] / 86400
        ph = ((t - a.t0 + 0.5 * a.P) % a.P) - 0.5 * a.P
        w = np.abs(ph) < 4 * dur
        T.append(t[w]); R.append(r[w]); E.append(e[w]); X.append(np.full(w.sum(), exp))
    t, y, e, x = (np.concatenate(v) for v in (T, R, E, X))
    y = 1 + y
    u = (star["u1"], star["u2"])
    rho0 = star["rho"]
    rho_err = max(0.15 * rho0, 0.1)

    def lnprob(th):
        P, t0, k, b, rho, lnj = th
        if not (0 < b < 1 + k and 0 < k < 0.3 and rho > 0 and -15 < lnj < -4):
            return -np.inf
        m = model_flux(th[:5], t, u, x)
        if m is None:
            return -np.inf
        s2 = e**2 + np.exp(2 * lnj)
        return (-0.5 * np.sum((y - m) ** 2 / s2 + np.log(s2))
                - 0.5 * ((rho - rho0) / rho_err) ** 2)

    k0 = np.sqrt(max(1e-5, 1 - np.median(y[np.abs(((t - a.t0 + 0.5 * a.P) % a.P) - 0.5 * a.P) < 0.3 * dur])))
    p0 = np.array([a.P, a.t0, k0, 0.3, rho0, np.log(np.median(e) * 0.3)])
    nw = 32
    scale = np.array([2e-5, 2e-3, 0.002, 0.1, 0.05 * rho0, 0.1])
    pos = p0 + scale * np.random.default_rng(1).standard_normal((nw, 6))
    pos[:, 3] = np.abs(pos[:, 3])
    sampler = emcee.EnsembleSampler(nw, 6, lnprob)
    sampler.run_mcmc(pos, a.steps, progress=False)
    ch = sampler.get_chain(discard=a.steps // 2, thin=5, flat=True)
    names = ["P", "t0", "k", "b", "rho", "lnjit"]
    q = {n: np.percentile(ch[:, i], [16, 50, 84]) for i, n in enumerate(names)}
    rp = ch[:, 2] * row["rad"] * 109.2
    a_rs = (G_CGS * ch[:, 4] * 1.41 * (ch[:, 0] * 86400) ** 2 / (3 * np.pi)) ** (1 / 3)
    inc = np.arccos(ch[:, 3] / a_rs)
    t14 = ch[:, 0] / np.pi * np.arcsin(np.sqrt((1 + ch[:, 2]) ** 2 - ch[:, 3] ** 2) / a_rs / np.sin(inc)) * 24
    out = {n: [float(v) for v in q[n]] for n in names}
    out.update(Rp=[float(v) for v in np.percentile(rp, [16, 50, 84])],
               T14_h=[float(v) for v in np.nanpercentile(t14, [16, 50, 84])],
               depth_ppm=float(np.median(ch[:, 2]) ** 2 * 1e6), n_points=int(len(t)),
               acceptance=float(np.mean(sampler.acceptance_fraction)))
    for n in ("P", "t0", "k", "b", "rho", "Rp", "T14_h"):
        lo, mid, hi = out[n]
        print(f"{n:6s} = {mid:.6f} +{hi - mid:.6f} -{mid - lo:.6f}")
    print(f"acceptance {out['acceptance']:.2f}, points {len(t)}")
    with open(RESULTS / f"fit_tic{a.tic}_P{a.P:.3f}.json", "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
