"""Publication figures: candidate transit grid, the TOI-4342 system, and the TIC 4206066 check.

Usage: python make_figures.py   (reads results/candidates.csv and results/fit_*.json)
"""
import glob
import json
import warnings

import matplotlib
import numpy as np
import pandas as pd

from common import CAT, RESULTS, ROOT, load_star
from fit_transit import model_flux
from vet import detrend_masked, star_dict

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

warnings.filterwarnings("ignore")
FIG = ROOT / "figures"
STARS = pd.read_parquet(CAT / "targets.parquet").set_index("ID")
TOI4342 = [(5.53826, 1660.07587, 3.0, "b (known)"), (10.68869, 1659.34269, 3.2, "c (known)")]  # our ephemerides; the TOI-list period of b has drifted ~40 min by 2026


def folded(tic, P, t0, dur_h, masks=()):
    dur = dur_h / 24
    prep = detrend_masked(load_star(tic), P, t0, dur, 0.75)
    x, y, w = [], [], []
    for p in prep:
        keep = np.ones(len(p["t"]), bool)
        for P2, t2, d2 in masks:
            keep &= np.abs(((p["t"] - t2 + 0.5 * P2) % P2) - 0.5 * P2) > 0.75 * d2 / 24
        ph = ((p["t"] - t0 + 0.5 * P) % P) - 0.5 * P
        m = keep & (np.abs(ph) < 3 * dur)
        x.append(ph[m]); y.append(p["r"][m]); w.append(1 / p["e"][m] ** 2)
    x, y, w = (np.concatenate(v) for v in (x, y, w))
    edges = np.linspace(-3 * dur, 3 * dur, 37)
    i = np.digitize(x, edges)
    bx, by, be = [], [], []
    for k in range(1, len(edges)):
        s = i == k
        if s.sum() > 2:
            bx.append(np.sum(w[s] * x[s]) / np.sum(w[s])); by.append(np.sum(w[s] * y[s]) / np.sum(w[s]))
            be.append(1 / np.sqrt(np.sum(w[s])))
    return np.array(bx) * 24, np.array(by) * 1e6, np.array(be) * 1e6


def fit_for(tic, P):
    for f in glob.glob(str(RESULTS / f"fit_tic{tic}_P*.json")):
        d = json.load(open(f))
        if abs(d["P"][1] / P - 1) < 1e-3:
            return d
    return None


def model_curve(tic, fit, span_h):
    st = star_dict(STARS.loc[tic].to_dict())
    th = [fit[k][1] for k in ("P", "t0", "k", "b", "rho")]
    tt = th[1] + np.linspace(-span_h, span_h, 600) / 24
    return (tt - th[1]) * 24, (model_flux(th, tt, (st["u1"], st["u2"]), np.full(len(tt), 2 / 1440)) - 1) * 1e6


def panel(ax, tic, P, t0, dur_h, title, masks=(), color="C0"):
    bx, by, be = folded(tic, P, t0, dur_h, masks)
    ax.errorbar(bx, by, be, fmt="o", ms=3.5, color=color, ecolor="0.6", lw=0.8)
    fit = fit_for(tic, P)
    if fit:
        mx, my = model_curve(tic, fit, 3 * dur_h)
        ax.plot(mx, my, color="k", lw=1.2)
    ax.axhline(0, color="0.7", lw=0.6)
    ax.set_title(title, fontsize=9)
    ax.set_xlabel("hours from mid-transit", fontsize=8)
    ax.tick_params(labelsize=7)


def candidates_grid():
    c = pd.read_csv(RESULTS / "candidates.csv")
    masks = {286763141: [(3.447591, 1546.4832, 1.69), (7.349303, 1544.5165, 1.94)],
             354944123: [(p, t, d) for p, t, d, _ in TOI4342]}
    n = len(c)
    ncol = 4
    fig, axs = plt.subplots(int(np.ceil(n / ncol)), ncol, figsize=(15, 3.4 * np.ceil(n / ncol)))
    for ax, (_, r) in zip(axs.flat, c.iterrows()):
        P, t0 = r.P_d, r.T0_BJD - 2457000
        m = masks.get(r.TIC, [])
        if r.TIC == 422351625:
            other = c[(c.TIC == r.TIC) & (c.P_d != r.P_d)].iloc[0]
            m = [(other.P_d, other.T0_BJD - 2457000, other.T14_h)]
        tag = ("" if r.status == "no prior report found" else
               "\nindependent recovery (Tschudi 2026)" if "Tschudi" in r.status else
               "\nindependent recovery (RAVEN 2026)")
        panel(ax, r.TIC, P, t0, r.T14_h, f"TIC {r.TIC}  P={P:.3f} d  {r.Rp_Re:.2f} R$_\\oplus${tag}", m,
              color="C3" if r.status == "no prior report found" else "C7")
        ax.set_ylabel("ppm", fontsize=8)
    for ax in list(axs.flat)[n:]:
        ax.axis("off")
    fig.suptitle("Transit candidates from a multi-sector TESS search of 9,979 nearby K/M dwarfs "
                 "(red: no prior report found; grey: independently recovered)", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "candidates_grid.png", dpi=110)
    plt.close(fig)


def toi4342():
    fig, axs = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    new = (18.908202, 1675.532582, 2.46)
    allsig = TOI4342 + [new + ("candidate (this work)",)]
    for ax, (P, t0, d, lab) in zip(axs, allsig):
        masks = [(p, t, dd) for p, t, dd, *_ in allsig if p != P]
        panel(ax, 354944123, P, t0, d, f"TOI-4342 {lab}: P = {P:.3f} d", masks,
              color="C3" if "candidate" in lab else "C0")
    axs[0].set_ylabel("relative flux (ppm)")
    fig.suptitle("TOI-4342 (TIC 354944123): two confirmed sub-Neptunes and an 18.9-day transit candidate", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "toi4342.png", dpi=120)
    plt.close(fig)


def validation():
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, (P, t0, d, lab) in zip(axs, ((3.18278, 1468.4291, 1.70, "3.18 d (his: 3.182785 d)"),
                                         (11.13274, 1473.7334, 1.29, "11.13 d (his: 11.13274 d)"))):
        other = [(3.18278, 1468.4291, 1.70)] if P > 5 else [(11.13274, 1473.7334, 1.29)]
        panel(ax, 4206066, P, t0, d, f"blind recovery: {lab}", other)
    axs[0].set_ylabel("relative flux (ppm)")
    fig.suptitle("Pipeline check: TIC 4206066 (Rabtsevich 2026) recovered without prior knowledge", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "validation_tic4206066.png", dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    FIG.mkdir(exist_ok=True)
    candidates_grid()
    toi4342()
    validation()
    print("figures ->", FIG)
