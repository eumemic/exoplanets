"""Vet search signals: transit-masked re-detrend, LEO-Vetter flux tests, per-sector depths,
centroid shifts, known-object matching, and a diagnostic figure.

Usage: python vet.py candidates.csv [--procs N] [--out results/vet]
candidates.csv needs columns tic, rank, period, t0, duration_h.
"""
import argparse
import ast
import contextlib
import io
import json
import os
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd
from numba import njit

from common import CAT, RESULTS, load_star
from known import check as known_check
from search import INVERT, bin_sector, expected_duration, robust_std, rolling_std, toi_windows

warnings.filterwarnings("ignore")


def detrend_masked(sectors, P, t0, dur, window, known=()):
    """Biweight trend fitted with in-transit points removed, then evaluated everywhere. Transits
    of `known` planets (TOIs masked by the search) are removed from the light curve first."""
    from wotan import flatten

    out = []
    for s in sectors:
        o = np.argsort(s["time"])
        t, f = s["time"][o], s["flux"][o]
        cx, cy = s["cx"][o].astype(float), s["cy"][o].astype(float)
        if known:
            keep = np.ones(len(t), bool)
            for k in known:
                keep &= ~toi_windows(t, k, k.get("P_fit"), k.get("t0_fit"), k.get("dur_fit"))
            t, f, cx, cy = t[keep], f[keep], cx[keep], cy[keep]
        ph = ((t - t0 + 0.5 * P) % P) - 0.5 * P
        oot = np.abs(ph) > 0.75 * dur
        if oot.sum() < 200:
            continue
        _, trend = flatten(t[oot], f[oot], method="biweight", window_length=window,
                           break_tolerance=0.5, edge_cutoff=0.0, return_trend=True)
        good = np.isfinite(trend)
        if good.sum() < 100:
            continue
        tr = np.interp(t, t[oot][good], trend[good])
        # do not interpolate across gaps longer than the window
        gapfix = np.ones(len(t), bool)
        tg = t[oot][good]
        j = np.clip(np.searchsorted(tg, t), 1, len(tg) - 1)
        gapfix &= (tg[j] - tg[j - 1]) < window
        r = f / tr - 1.0
        ok = np.isfinite(r) & gapfix
        sig = robust_std(r[ok & oot])
        ok &= r < 4 * sig
        t, r, cx, cy, ph = t[ok], r[ok], cx[ok], cy[ok], ph[ok]
        if INVERT:
            r = -r
        e = np.maximum(rolling_std(t, r), 0.5 * sig)
        out.append(dict(sector=s["sector"], prov=s["provenance"], t=t, r=r, e=e, cx=cx, cy=cy,
                        exptime=s["exptime"]))
    return out


def box_depth(t, r, e, P, t0, dur):
    ph = ((t - t0 + 0.5 * P) % P) - 0.5 * P
    intr = np.abs(ph) < 0.5 * dur
    oot = (np.abs(ph) > 0.75 * dur) & (np.abs(ph) < 3 * dur)
    if intr.sum() < 2 or oot.sum() < 5:
        return np.nan, np.nan
    w = 1 / e**2
    d = np.sum(w[oot] * r[oot]) / np.sum(w[oot]) - np.sum(w[intr] * r[intr]) / np.sum(w[intr])
    return d, np.sqrt(1 / np.sum(w[intr]) + 1 / np.sum(w[oot]))


def centroid_shift(p, P, t0, dur):
    """In- minus out-of-transit flux-weighted centroid (pixels) and its significance."""
    ph = ((p["t"] - t0 + 0.5 * P) % P) - 0.5 * P
    intr = np.abs(ph) < 0.5 * dur
    oot = (np.abs(ph) > 0.75 * dur) & (np.abs(ph) < 3 * dur)
    out = []
    for c in (p["cx"], p["cy"]):
        ok = np.isfinite(c)
        a, b = c[intr & ok], c[oot & ok]
        if len(a) < 3 or len(b) < 10:
            return np.nan, np.nan, np.nan
        # local detrend of centroid against time is skipped; use robust scatter for errors
        s = robust_std(b - np.median(b))
        out.append((np.mean(a) - np.median(b), s * np.sqrt(1 / len(a) + 1 / len(b))))
    dx, ex = out[0]
    dy, ey = out[1]
    z = np.hypot(dx / ex, dy / ey) if ex > 0 and ey > 0 else np.nan
    return dx, dy, z


def star_dict(row):
    from leo_vetter.stellar import quadratic_ldc

    teff = row.get("Teff") if np.isfinite(row.get("Teff", np.nan)) else 4000.0
    logg = row.get("logg") if np.isfinite(row.get("logg", np.nan)) else 4.7
    u1, u2 = quadratic_ldc(teff, logg)
    rad = row["rad"]
    mass = row["mass"] if np.isfinite(row.get("mass", np.nan)) else rad
    rho = row["rho"] if np.isfinite(row.get("rho", np.nan)) else mass / rad**3
    return dict(u1=float(u1), u2=float(u2), rad=rad, mass=mass, Teff=teff, logg=logg,
                e_rad=row.get("e_rad", 0.05 * rad) if np.isfinite(row.get("e_rad", np.nan)) else 0.05 * rad,
                e_mass=row.get("e_mass", 0.05 * mass) if np.isfinite(row.get("e_mass", np.nan)) else 0.05 * mass,
                e_Teff=row.get("e_Teff", 150) if np.isfinite(row.get("e_Teff", np.nan)) else 150.0,
                rho=rho)


@njit(cache=True, error_model="numpy")
def _ses_mes_loop(time, flux, flux_err, near_tran, phase, phase_sorted_idxs, phase_sorted, per,
                  dur, qtran, zpt):
    """LEO-Vetter's per-cadence SES/MES loop (TCELightCurve.get_SES_MES), compiled. For each
    cadence: depth and count of points within +-dur/2 in time (SES) and within +-qtran/2 in
    phase (MES), the number of distinct transits in the MES window, and the out-of-transit
    weighted mean and error in the SES window."""
    N = len(time)
    dep_SES = np.zeros(N)
    n_SES = np.zeros(N)
    dep_MES = np.zeros(N)
    n_MES = np.zeros(N)
    N_transit_MES = np.zeros(N)
    bin_flux = np.zeros(N)
    bin_flux_err = np.zeros(N)
    w = 1.0 / flux_err**2
    h = 0.5 * qtran
    e0 = int(np.floor((time[0] - time[-1]) / per)) - 1
    seen = np.zeros(int(np.ceil((time[-1] - time[0]) / per)) * 2 + 4, np.int64)
    left, right = 0, 0
    for i in range(N):
        while left < N and time[left] < time[i] - 0.5 * dur:
            left += 1
        if right < left:
            right = left
        while right < N and time[right] <= time[i] + 0.5 * dur:
            right += 1
        sw = 0.0
        swy = 0.0
        sw_o = 0.0
        swy_o = 0.0
        for j in range(left, right):
            sw += w[j]
            swy += w[j] * flux[j]
            if not near_tran[j]:
                sw_o += w[j]
                swy_o += w[j] * flux[j]
        n_SES[i] = right - left
        dep_SES[i] = zpt - swy / sw
        bin_flux[i] = swy_o / sw_o
        bin_flux_err[i] = 1.0 / np.sqrt(sw_o)
        p = phase[i]
        lo = np.searchsorted(phase_sorted, p - h, side="right")
        hi = np.searchsorted(phase_sorted, p + h, side="left")
        a2, b2 = 0, 0
        if p < h:
            a2 = np.searchsorted(phase_sorted, p - h + 1.0, side="left")
            b2 = N
        elif p > 1.0 - h:
            a2 = 0
            b2 = np.searchsorted(phase_sorted, p + h - 1.0, side="right")
        sw = 0.0
        swy = 0.0
        n = 0
        ntr = 0
        stamp = i + 1
        for lohi in range(2):
            a, b = (lo, hi) if lohi == 0 else (a2, b2)
            for k in range(a, b):
                j = phase_sorted_idxs[k]
                if lohi == 1 and lo <= k < hi:
                    continue  # already counted (np.unique in the original)
                sw += w[j]
                swy += w[j] * flux[j]
                n += 1
                ep = int(np.round((time[j] - time[i]) / per)) - e0
                if seen[ep] != stamp:
                    seen[ep] = stamp
                    ntr += 1
        n_MES[i] = n
        dep_MES[i] = zpt - swy / sw
        N_transit_MES[i] = ntr
    return dep_SES, n_SES, dep_MES, n_MES, N_transit_MES, bin_flux, bin_flux_err


def _get_ses_mes(self, replace=False):
    """Drop-in replacement for TCELightCurve.get_SES_MES using the compiled loop; the noise
    estimates after the loop are LEO-Vetter's own code."""
    from leo_vetter.utils import phasefold, weighted_std

    if hasattr(self, "MES_series") and not replace:
        return
    phase = phasefold(self.time, self.per, self.epo)
    phase[phase < 0] += 1
    order = np.argsort(phase)
    dep_SES, n_SES, dep_MES, n_MES, N_transit_MES, bin_flux, bin_flux_err = _ses_mes_loop(
        np.asarray(self.time, float), np.asarray(self.flux, float), np.asarray(self.flux_err, float),
        np.asarray(self.near_tran, bool), phase, order, phase[order], float(self.per),
        float(self.dur), float(self.qtran), float(self.zpt))
    mask = ~np.isnan(bin_flux) & ~self.near_tran
    std = weighted_std(self.flux[mask], self.flux_err[mask])
    bin_std = weighted_std(bin_flux[mask], bin_flux_err[mask])
    expected_bin_std = (std * np.sqrt(np.nanmean(bin_flux_err[mask] ** 2))
                        / np.sqrt(np.nanmean(self.flux_err[mask] ** 2)))
    self.sig_w = std
    sig_r2 = bin_std**2 - expected_bin_std**2
    self.sig_r = np.sqrt(sig_r2) if sig_r2 > 0 else 0
    self.err = np.sqrt((self.sig_w**2 / self.n_in) + (self.sig_r**2 / self.N_transit))
    err_SES = np.sqrt((self.sig_w**2 / n_SES) + self.sig_r**2)
    err_MES = np.sqrt((self.sig_w**2 / n_MES) + (self.sig_r**2 / N_transit_MES))
    self.SES_series = dep_SES / err_SES
    self.dep_series = dep_MES
    self.err_series = err_MES
    self.MES_series = dep_MES / err_MES
    self.metrics["sig_w"] = self.sig_w
    self.metrics["sig_r"] = self.sig_r
    self.metrics["err"] = self.err
    self.metrics["MES"] = self.dep / self.err
    Fmin = np.nanmin(-self.dep_series)
    Fmax = np.nanmax(-self.dep_series)
    self.metrics["SHP"] = Fmax / (Fmax - Fmin)


FAST_LEO = os.environ.get("EXO_SLOW_LEO") != "1"


def leo(tic, rank, t, r, e, P, t0, dur, star):
    from leo_vetter.main import TCELightCurve
    from leo_vetter.thresholds import check_thresholds

    if FAST_LEO:
        TCELightCurve.get_SES_MES = _get_ses_mes

    tlc = TCELightCurve(tic, t, 1 + r, 1 + r, e, P, t0, dur, planetno=rank)
    with contextlib.redirect_stdout(io.StringIO()):
        tlc.compute_flux_metrics(star, verbose=False)
    m = tlc.metrics
    fails = []
    for case in ("FA", "FP"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            check_thresholds(m, case, verbose=True)
        fails += [line for line in buf.getvalue().splitlines() if line.startswith(("FA:", "FP:"))]
    keep = ["MES", "SHP", "N_transit", "mean_chases", "max_SES", "DMM", "CHI", "sig_pri",
            "sig_sec", "sig_ter", "sig_pos", "Fred", "transit_b", "transit_RpRs", "transit_aRs",
            "Rp", "trap_dep", "sig_dep", "new_MES", "new_N_transit", "sine_sig", "qtran_exp"
            if "qtran_exp" in m else "q"]
    return {k: (float(m[k]) if k in m and np.isscalar(m[k]) else None) for k in keep}, fails


def plot(path, tic, row, sig, prep, P, t0, dur, per_sector, info):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = np.concatenate([p["t"] for p in prep])
    r = np.concatenate([p["r"] for p in prep])
    e = np.concatenate([p["e"] for p in prep])
    ph = ((t - t0 + 0.5 * P) % P) - 0.5 * P
    fig = plt.figure(figsize=(14, 11))
    gs = fig.add_gridspec(4, 3, hspace=0.45, wspace=0.25)
    ax = fig.add_subplot(gs[0, :])
    for p in prep:
        tb, rb, _ = bin_sector(p["t"], p["r"], p["e"], 30 / 1440)
        ax.plot(tb, rb * 1e6, ".", ms=1.5, color="0.4")
    k = np.arange(np.floor((t.min() - t0) / P), np.ceil((t.max() - t0) / P) + 1)
    tt = t0 + k * P
    has = [np.any(np.abs(t - x) < 0.5 * dur) for x in tt]
    ax.vlines(tt[has], *np.percentile(r * 1e6, [0.5, 99.5]), color="r", alpha=0.25, lw=0.6)
    ax.set_ylabel("ppm (30-min bins)")
    ax.set_title(f"TIC {tic}  T={row['Tmag']:.2f}  R*={row['rad']:.2f}  Teff={row.get('Teff', np.nan):.0f}  "
                 f"d={row.get('d', np.nan):.0f} pc   P={P:.5f} d  dur={dur * 24:.2f} h  "
                 f"depth={info['depth_ppm']:.0f}±{info['depth_err_ppm']:.0f} ppm  "
                 f"Rp={info['rp_earth']:.2f} Re  MES={info.get('leo', {}).get('MES') or np.nan:.1f}",
                 fontsize=9)

    def fold(ax, sel, label, color, center=0.0, span=4.0):
        x = (((t - t0 - center * P + 0.5 * P) % P) - 0.5 * P)[sel] * 24
        y = r[sel] * 1e6
        w = 1 / e[sel] ** 2
        m = np.abs(x) < span * dur * 24
        ax.plot(x[m], y[m], ".", ms=1, color="0.75")
        bins = np.linspace(-span * dur * 24, span * dur * 24, 41)
        idx = np.digitize(x[m], bins)
        bx = [(bins[i - 1] + bins[i]) / 2 for i in range(1, len(bins)) if np.any(idx == i)]
        by = [np.sum(w[m][idx == i] * y[m][idx == i]) / np.sum(w[m][idx == i])
              for i in range(1, len(bins)) if np.any(idx == i)]
        be = [1 / np.sqrt(np.sum(w[m][idx == i])) for i in range(1, len(bins)) if np.any(idx == i)]
        ax.errorbar(bx, by, be, fmt="o", ms=3, color=color, label=label)
        lim = max(3 * info["depth_ppm"], 5 * np.median(be) if be else 1000)
        ax.set_ylim(-lim, lim * 0.6)
        ax.axhline(0, color="k", lw=0.5)
        ax.axhline(-info["depth_ppm"], color="r", lw=0.5, ls=":")
        ax.set_xlabel("hours from mid-transit")

    ax = fig.add_subplot(gs[1, 0]); fold(ax, np.ones(len(t), bool), "all", "C0"); ax.set_title("fold (all)")
    ep = np.round((t - t0) / P).astype(int)
    ax = fig.add_subplot(gs[1, 1]); fold(ax, ep % 2 == 1, "odd", "C1"); fold(ax, ep % 2 == 0, "even", "C2")
    ax.legend(fontsize=7); ax.set_title(f"odd/even  LEO fails: {len(info.get('leo_fails', []))}")
    ax = fig.add_subplot(gs[1, 2]); fold(ax, np.ones(len(t), bool), "phase 0.5", "C3", center=0.5)
    ax.set_title("secondary (phase 0.5)")
    old = np.isin(np.concatenate([[p["sector"]] * len(p["t"]) for p in prep]),
                  [p["sector"] for p in prep if p["sector"] <= 96])
    ax = fig.add_subplot(gs[2, 0]); fold(ax, old, "S<=96", "C4"); ax.set_title(f"sectors <= 96  ({info['snr_old']:.1f} sigma)")
    ax = fig.add_subplot(gs[2, 1]); fold(ax, ~old, "S>=97", "C5"); ax.set_title(f"sectors >= 97  ({info['snr_new']:.1f} sigma)")
    ax = fig.add_subplot(gs[2, 2])
    xs = [s["sector"] for s in per_sector]
    ax.errorbar(range(len(xs)), [s["depth_ppm"] for s in per_sector], [s["err_ppm"] for s in per_sector], fmt="o")
    ax.axhline(info["depth_ppm"], color="r", lw=0.5)
    ax.set_xticks(range(len(xs))); ax.set_xticklabels(xs, fontsize=6, rotation=90)
    ax.set_title(f"per-sector depth (chi2/dof={info['sector_chi2_dof']:.2f})")
    ax = fig.add_subplot(gs[3, :2])
    ev = sig.get("events", [])
    if ev:
        ax.errorbar([x[1] for x in ev], [x[2] for x in ev], [x[3] for x in ev], fmt="o", ms=3)
        ax.axhline(info["depth_ppm"], color="r", lw=0.5); ax.axhline(0, color="k", lw=0.5)
    ax.set_title("individual transit depths (ppm) vs time"); ax.set_xlabel("BTJD")
    ax = fig.add_subplot(gs[3, 2]); ax.axis("off")
    txt = "\n".join([f"LEO fails: {', '.join(info.get('leo_fails', [])) or 'none'}"[:120],
                     f"centroid z={info['centroid_z']:.1f}",
                     f"known same star: {'; '.join(info['known']['same_star'])[:100]}",
                     f"period match same star: {info['known']['same_star_period_match']}",
                     f"neighbour period match: {'; '.join(info['known']['neighbour_period_match'])[:100]}",
                     f"contratio={row.get('contratio', np.nan):.3f}  ruwe={row.get('ruwe', np.nan):.2f}"])
    ax.text(0, 1, txt, va="top", fontsize=7, wrap=True)
    fig.savefig(path, dpi=80)
    plt.close(fig)


def vet_one(args):
    sig, row, outdir = args
    if isinstance(sig.get("events"), str):
        sig["events"] = ast.literal_eval(sig["events"])
    tic, rank = int(sig["tic"]), int(sig["rank"])
    P, t0, dur = float(sig["period"]), float(sig["t0"]), float(sig["duration_h"]) / 24
    try:
        sectors = load_star(tic)
        rho = float(sig.get("rho", row.get("rho", 2.0)))
        window = float(np.clip(3.0 * expected_duration(30.0, rho), 0.5, 1.0))
        known_tois = json.loads(sig["masked_tois"]) if isinstance(sig.get("masked_tois"), str) else []
        prep = detrend_masked(sectors, P, t0, dur, window, known_tois)
        tb, rb, eb = [], [], []
        for p in prep:
            if p["exptime"] < 540:
                a, b, c = bin_sector(p["t"], p["r"], p["e"], 10 / 1440)
            else:
                a, b, c = p["t"], p["r"], p["e"]
            tb.append(a); rb.append(b); eb.append(c)
        t = np.concatenate(tb); r = np.concatenate(rb); e = np.concatenate(eb)
        o = np.argsort(t); t, r, e = t[o], r[o], e[o]
        d, de = box_depth(t, r, e, P, t0, dur)
        per_sector, cz = [], []
        for p in prep:
            ds, dse = box_depth(p["t"], p["r"], p["e"], P, t0, dur)
            if np.isfinite(ds):
                per_sector.append(dict(sector=p["sector"], prov=p["prov"], depth_ppm=ds * 1e6, err_ppm=dse * 1e6))
            dx, dy, z = centroid_shift(p, P, t0, dur)
            if np.isfinite(z):
                cz.append(z)
        chi2 = sum(((s["depth_ppm"] - d * 1e6) / s["err_ppm"]) ** 2 for s in per_sector)
        old = [p for p in prep if p["sector"] <= 96]
        new = [p for p in prep if p["sector"] >= 97]

        def snr_of(ps):
            if not ps:
                return 0.0
            dd, ee = box_depth(np.concatenate([p["t"] for p in ps]), np.concatenate([p["r"] for p in ps]),
                               np.concatenate([p["e"] for p in ps]), P, t0, dur)
            return float(dd / ee) if np.isfinite(dd) else 0.0

        info = dict(tic=tic, rank=rank, period=P, t0=t0, duration_h=dur * 24,
                    depth_ppm=d * 1e6, depth_err_ppm=de * 1e6, snr=d / de,
                    rp_earth=float(np.sqrt(max(d, 0)) * row["rad"] * 109.2),
                    sector_chi2_dof=chi2 / max(len(per_sector) - 1, 1), per_sector=per_sector,
                    snr_old=snr_of(old), snr_new=snr_of(new),
                    centroid_z=float(np.sqrt(np.mean(np.square(cz)))) if cz else np.nan,
                    known=known_check(tic, P, float(row["ra"]), float(row["dec"])))
        try:
            info["leo"], info["leo_fails"] = leo(tic, rank, t, r, e, P, t0, dur, star_dict(row))
        except Exception as ex:
            info["leo"], info["leo_fails"] = {}, [f"LEO error: {ex}"]
        plot(f"{outdir}/tic{tic}_{rank}.png", tic, row, sig, prep, P, t0, dur, per_sector, info)
    except Exception as ex:
        info = dict(tic=tic, rank=rank, error=repr(ex))
    with open(f"{outdir}/tic{tic}_{rank}.json", "w") as fh:
        json.dump(info, fh, default=float)
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--procs", type=int, default=12)
    ap.add_argument("--out", default=str(RESULTS / "vet"))
    ap.add_argument("--stars", default=str(CAT / "targets.parquet"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    stars = pd.read_parquet(a.stars).set_index("ID")
    cands = pd.read_csv(a.candidates)
    todo = [(c.to_dict(), stars.loc[int(c.tic)].to_dict(), a.out) for _, c in cands.iterrows()
            if not os.path.exists(f"{a.out}/tic{int(c.tic)}_{int(c['rank'])}.json")]
    print(len(todo), "signals to vet", flush=True)
    with Pool(a.procs) as pool:
        for i, info in enumerate(pool.imap_unordered(vet_one, todo), 1):
            if i % 25 == 0 or i == len(todo):
                print(f"{i}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()
