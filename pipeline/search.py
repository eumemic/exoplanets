"""Multi-sector transit search: clean, detrend, bin, BLS on a stellar-density-aware grid.

Usage: python search.py targets.txt [--procs N] [--out results/search] [--mask-tois]
                         [--pmin 0.5] [--pmax 30] [--premask results/search]
Writes one JSON per star with up to MAX_SIGNALS signals (iterative masking). With --mask-tois,
every TOI on the star is masked before the search, so it looks for additional planets; with
--premask, so is every signal (SNR >= 7) an earlier search found on the star.
"""
import argparse
import json
import os
import sys
import time
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd

from common import CAT, DATA, RESULTS, biweight_trend, load_star, tic_path

warnings.filterwarnings("ignore")

P_MIN, P_MAX = 0.5, 30.0
BIN_COARSE = 20.0         # cadence (minutes) of the coarse period search
BIN_FINE = 10.0           # cadence (minutes) used to refine each peak
MAX_SIGNALS = 3
SNR_CONTINUE = 7.0        # keep iterating while the last signal is at least this strong
SEMICOHERENT = True       # per-season scan + coherent refinement of the top peaks (fastbls.py)
STACK = False             # phase-coherent stack-slide search (fastbls.stackslide); overrides SEMICOHERENT
# Longest stretch of continuous data folded as one block by stack-slide (days; 0 = whole seasons).
# Shorter blocks mean fewer coarse frequencies to fold all the data at (EXO_SEASON_MAX for tests).
SEASON_MAX = float(os.environ.get("EXO_SEASON_MAX", "0")) or None
# False-alarm calibration: with EXO_INVERT=1 the detrended residuals are negated, so any dip
# the pipeline finds is a false alarm (real transits become bumps and are not searched).
INVERT = os.environ.get("EXO_INVERT") == "1"
G = 2.959122e-4           # AU^3 / (Msun d^2)
RSUN_AU = 0.00465047


def expected_duration(P, rho_sun):
    """Central-transit duration (days) for a circular orbit around a star of density rho (solar)."""
    # a/R* = (G rho P^2 / (3 pi))^(1/3) with rho in solar units -> use Msun/Rsun^3 scaling.
    a_rs = (G * rho_sun * P**2 / (4 * np.pi**2)) ** (1 / 3) / RSUN_AU
    return P / np.pi * np.arcsin(np.minimum(1.0, 1.0 / a_rs))


def robust_std(x):
    x = x[np.isfinite(x)]
    if len(x) < 5:
        return np.nan
    return 1.4826 * np.median(np.abs(x - np.median(x)))


def rolling_std(t, r, half=0.5):
    """Robust local scatter in a +-half day window (evaluated on a 0.1 d grid, interpolated)."""
    grid = np.arange(t.min(), t.max() + 0.1, 0.1)
    vals = np.full(len(grid), np.nan)
    lo = np.searchsorted(t, grid - half)
    hi = np.searchsorted(t, grid + half)
    for i, (a, b) in enumerate(zip(lo, hi)):
        if b - a >= 20:
            vals[i] = robust_std(r[a:b])
    ok = np.isfinite(vals)
    if not ok.any():
        return np.full(len(t), robust_std(r))
    return np.interp(t, grid[ok], vals[ok])


def rotation_period(t, f):
    """Dominant variability period (d) of one sector and its semi-amplitude / 30-min noise."""
    from astropy.timeseries import LombScargle

    tb, fb, _ = bin_sector(t, f - np.nanmedian(f), np.ones(len(t)), 30 / 1440)
    if len(tb) < 50:
        return np.nan, 0.0
    noise = robust_std(np.diff(fb)) / np.sqrt(2)
    freq = np.linspace(1 / 10.0, 1 / 0.1, 20000)
    ls = LombScargle(tb, fb)
    fbest = freq[np.argmax(ls.power(freq))]
    amp = np.sqrt(np.sum(ls.model_parameters(fbest)[1:] ** 2))
    return 1 / fbest, amp / max(noise, 1e-6)


def prewhiten(t, f, pvar, nharm=4):
    """Remove spot modulation: robust Fourier fit at pvar (nharm harmonics + line) in chunks."""
    chunk = max(2.0, 3 * pvar)
    model = np.full(len(f), np.nan)
    for lo in np.arange(t.min(), t.max() + chunk, chunk):
        m = (t >= lo) & (t < lo + chunk)
        if m.sum() < 4 * nharm + 10:
            model[m] = np.median(f[m]) if m.any() else np.nan
            continue
        x = t[m] - lo
        cols = [np.ones(m.sum()), x]
        for k in range(1, nharm + 1):
            w = 2 * np.pi * k * x / pvar
            cols += [np.sin(w), np.cos(w)]
        X = np.vstack(cols).T
        keep = np.ones(m.sum(), bool)
        for _ in range(3):
            coef = np.linalg.lstsq(X[keep], f[m][keep], rcond=None)[0]
            res = f[m] - X @ coef
            keep = np.abs(res) < 3 * robust_std(res[keep])
        model[m] = X @ coef
    return f - model + 1.0


def prepare(sectors, window):
    """Detrend each sector, clip flares, attach empirical errors. Spot modulation faster than
    ~3 d survives a 0.5-1 d biweight, so such sectors are prewhitened first."""
    out = []
    for s in sectors:
        t, f = s["time"], s["flux"]
        o = np.argsort(t)
        t, f = t[o], f[o]
        # Normalized flux outside (0, 5) is not stellar (one QLP sector had a 9e20 point, on which
        # wotan's biweight never converged).
        ok = (f > 0) & (f < 5)
        t, f = t[ok], f[ok]
        if len(t) < 200:
            continue
        prot, var_snr = rotation_period(t, f)
        fast = bool(np.isfinite(prot) and prot < 3.0 and var_snr > 3.0)
        if fast:
            f = prewhiten(t, f, prot)
        r = f / biweight_trend(t, f, window) - 1.0
        ok = np.isfinite(r)
        if ok.sum() < 200:
            continue
        sig = robust_std(r[ok])
        ok &= r < 4 * sig            # flares / upward outliers only; dips are kept
        t, r = t[ok], r[ok]
        if INVERT:
            r = -r
        e = rolling_std(t, r)
        e = np.maximum(e, 0.5 * sig)
        out.append(dict(sector=s["sector"], prov=s["provenance"], t=t, r=r, e=e,
                        exptime=s["exptime"], prot=prot, var_snr=var_snr, prewhitened=fast))
    return out


def bin_sector(t, r, e, width_d):
    """Inverse-variance binning in fixed time bins."""
    idx = np.floor((t - t[0]) / width_d).astype(np.int64)
    w = 1.0 / e**2
    n = idx.max() + 1
    sw = np.bincount(idx, w, n)
    swr = np.bincount(idx, w * r, n)
    swt = np.bincount(idx, w * t, n)
    m = sw > 0
    return swt[m] / sw[m], swr[m] / sw[m], 1.0 / np.sqrt(sw[m])


def period_grid(span, rho, pmin, pmax, oversample=1.0):
    """Frequency spacing set so the timing error accumulated over `span` stays below
    half of the shortest plausible duration divided by `oversample`."""
    freqs = []
    f = 1.0 / pmax
    fmax = 1.0 / pmin
    while f < fmax:
        P = 1.0 / f
        dmin = 0.5 * expected_duration(P, rho)
        df = dmin * f / (span * oversample)
        freqs.append(f)
        f += df
    return 1.0 / np.array(freqs)[::-1]


def run_bls(t, y, dy, periods, rho):
    """Astropy BLS in period chunks, each with a duration set matched to the star."""
    from astropy.timeseries import BoxLeastSquares

    bls = BoxLeastSquares(t, y, dy)
    edges = np.geomspace(periods.min(), periods.max() + 1e-9, 7)
    res = {k: [] for k in ("period", "power", "depth", "depth_err", "duration", "t0")}
    for lo, hi in zip(edges[:-1], edges[1:]):
        p = periods[(periods >= lo) & (periods < hi)]
        if len(p) == 0:
            continue
        d_lo = max(0.4 * expected_duration(lo, rho), 0.5 / 24)
        d_hi = min(1.6 * expected_duration(hi, rho), 0.3 * lo, 8 / 24)
        durs = np.unique(np.clip(np.geomspace(d_lo, max(d_hi, d_lo * 1.01), 6), 0.02, None))
        r = bls.power(p, durs, objective="likelihood", method="fast", oversample=4)
        res["period"].append(np.asarray(r.period))
        res["power"].append(np.asarray(r.power))
        res["depth"].append(np.asarray(r.depth))
        res["depth_err"].append(np.asarray(r.depth_err))
        res["duration"].append(np.asarray(r.duration))
        res["t0"].append(np.asarray(r.transit_time))
    return {k: np.concatenate(v) for k, v in res.items()}


def semicoherent_peak(t, y, dy, rho, pmin, pmax, k_peaks=40):
    """Best period from a semi-coherent scan (per-season BLS summed) refined coherently."""
    from fastbls import coherent, seasons, semicoherent

    seas = [i for i in seasons(t) if len(i) >= 50]
    span_season = max(10.0, max(t[i].max() - t[i].min() for i in seas))
    span_total = t.max() - t.min()
    periods = period_grid(span_season, rho, pmin, pmax, oversample=1.5)
    freqs = 1.0 / periods
    durs = np.geomspace(max(0.4 * expected_duration(pmin, rho), 0.5 / 24),
                        min(1.6 * expected_duration(pmax, rho), 8 / 24), 8)
    binw = durs.min() / 3
    grid = semicoherent(t, y, dy, freqs, durs, binw)
    dexp = expected_duration(periods, rho)
    ok = (durs[None, :] > 0.3 * dexp[:, None]) & (durs[None, :] < 2.0 * dexp[:, None])
    stat = np.where(ok, grid, 0).max(axis=1)
    z = sde(stat, periods)
    # Candidates: highest local maxima by excess over the running median and by raw value.
    excess = stat - running_median(stat, periods)
    loc = np.where((stat[1:-1] >= stat[:-2]) & (stat[1:-1] >= stat[2:]))[0] + 1
    top = np.union1d(loc[np.argsort(excess[loc])[::-1][:k_peaks]],
                     loc[np.argsort(stat[loc])[::-1][:k_peaks // 2]])
    best = (-1.0, None)
    for j in top:
        df = abs(freqs[min(j + 1, len(freqs) - 1)] - freqs[max(j - 1, 0)]) / 2
        step = df * span_season / max(span_total, span_season) / 2
        n = int(np.ceil(2 * df / step)) + 1
        f = np.linspace(freqs[j] - df, freqs[j] + df, n)
        dsel = durs[(durs > 0.3 * dexp[j]) & (durs < 2.0 * dexp[j])]
        if len(dsel) == 0:
            continue
        pw, t0, kk, dep = coherent(t, y, dy, f, dsel, binw)
        i = int(np.argmax(pw))
        if pw[i] > best[0]:
            best = (pw[i], 1.0 / f[i])
    return best[1], float(np.sqrt(max(best[0], 0))), len(periods), z


def stackslide_peak(t, y, dy, rho, pmin, pmax, os_coarse=2.0):
    """Best period from a phase-coherent stack-slide spectrum: seasons folded on a grid set by
    the longest season, then shifted and summed on the full-baseline grid."""
    from fastbls import seasons, stackslide

    if len(t) < 100:
        return None, 0.0, 0, 0.0
    span_season = max(10.0, max(t[i].max() - t[i].min()
                                for i in seasons(t, max_len=SEASON_MAX) if len(i)))
    span_total = t.max() - t.min()
    periods_c = period_grid(span_season, rho, pmin, pmax, oversample=os_coarse)
    fc = 1.0 / periods_c
    dexp = expected_duration(periods_c, rho)
    dfc = 0.5 * dexp * fc / (span_season * os_coarse)
    nfine = max(1, int(np.ceil(span_total / (span_season * os_coarse))))
    durs = np.geomspace(max(0.4 * expected_duration(pmin, rho), 0.5 / 24),
                        min(1.6 * expected_duration(pmax, rho), 8 / 24), 8)
    dlo, dhi = 0.3 * dexp, 2.0 * dexp
    shortest = np.array([durs[(durs >= a) & (durs <= b)].min() if np.any((durs >= a) & (durs <= b))
                         else durs[0] for a, b in zip(dlo, dhi)])
    binw = shortest / 3
    freqs, power, _, _ = stackslide(t, y, dy, fc, dfc, nfine, binw, durs, dlo, dhi, max_len=SEASON_MAX)
    periods = 1.0 / freqs
    ok = (periods >= pmin) & (periods <= pmax)
    periods, power = periods[ok], power[ok]
    z = sde(power, periods)
    i = int(np.argmax(power))
    return float(periods[i]), float(np.sqrt(max(power[i], 0))), len(periods), float(z[i])


def refine(t, y, dy, P, rho, span):
    """Fine BLS around a coarse peak: +-3 coarse steps in frequency, denser durations."""
    from astropy.timeseries import BoxLeastSquares

    step = 0.5 * expected_duration(P, rho) / P / span
    periods = np.sort(1.0 / (1.0 / P + np.linspace(-3, 3, 241) * step))
    D = expected_duration(P, rho)
    durs = np.geomspace(max(0.3 * D, 0.4 / 24), min(2.0 * D, 0.3 * P, 10 / 24), 12)
    r = BoxLeastSquares(t, y, dy).power(periods, durs, objective="likelihood",
                                         method="fast", oversample=10)
    i = int(np.argmax(r.power))
    return (float(r.period[i]), float(r.transit_time[i]), float(r.duration[i]),
            float(r.depth[i]), float(np.sqrt(2 * max(r.power[i], 0))))


def running_median(power, periods, nb=200):
    lp = np.log(periods)
    edges = np.linspace(lp.min(), lp.max() + 1e-9, nb + 1)
    which = np.digitize(lp, edges) - 1
    med = np.array([np.median(power[which == i]) if np.any(which == i) else 0.0 for i in range(nb)])
    return med[which]


def sde(power, periods):
    """Signal detection efficiency against a running median/MAD in log period."""
    lp = np.log(periods)
    nb = 200
    edges = np.linspace(lp.min(), lp.max() + 1e-9, nb + 1)
    which = np.digitize(lp, edges) - 1
    med = np.zeros(nb)
    mad = np.zeros(nb)
    for i in range(nb):
        x = power[which == i]
        if len(x):
            med[i] = np.median(x)
            mad[i] = 1.4826 * np.median(np.abs(x - med[i]))
    mad = np.maximum(mad, 0.05 * np.median(np.abs(power)) + 1e-9)
    return (power - med[which]) / mad[which]


def event_stats(t, r, e, P, t0, dur):
    """Per-transit depths/SNRs, odd/even, secondary, coverage."""
    ph = ((t - t0 + 0.5 * P) % P) - 0.5 * P
    intr = np.abs(ph) < 0.5 * dur
    near = np.abs(ph) < 1.0 * dur
    w = 1 / e**2
    base = np.sum(w[~near] * r[~near]) / np.sum(w[~near])
    ep = np.round((t - t0) / P).astype(np.int64)
    events = []
    for k in np.unique(ep[intr]):
        m = intr & (ep == k)
        n_exp = dur / max(np.median(np.diff(t[ep == k])) if (ep == k).sum() > 2 else dur, 1e-4)
        cov = m.sum() / max(n_exp, 1)
        d = base - np.sum(w[m] * r[m]) / np.sum(w[m])
        de = 1 / np.sqrt(np.sum(w[m]))
        events.append((int(k), float(t0 + k * P), d, de, min(cov, 1.0)))
    ev = np.array([(x[2], x[3], x[4], x[0]) for x in events]) if events else np.zeros((0, 4))
    good = ev[:, 2] >= 0.5 if len(ev) else np.zeros(0, bool)

    def comb(sel):
        if not np.any(sel):
            return np.nan, np.nan
        ww = 1 / ev[sel, 1] ** 2
        return float(np.sum(ww * ev[sel, 0]) / np.sum(ww)), float(1 / np.sqrt(np.sum(ww)))

    dep, dep_e = comb(np.ones(len(ev), bool))
    odd, odd_e = comb((ev[:, 3] % 2 == 1) if len(ev) else np.zeros(0, bool))
    even, even_e = comb((ev[:, 3] % 2 == 0) if len(ev) else np.zeros(0, bool))
    # secondary at phase 0.5
    ph2 = ((t - t0) % P) / P - 0.5
    sec = np.abs(ph2 * P) < 0.5 * dur
    if sec.sum() > 3:
        sdep = base - np.sum(w[sec] * r[sec]) / np.sum(w[sec])
        sdep_e = 1 / np.sqrt(np.sum(w[sec]))
    else:
        sdep, sdep_e = np.nan, np.nan
    snr_ev = ev[:, 0] / ev[:, 1] if len(ev) else np.zeros(0)
    tot = np.sqrt(np.sum(np.clip(snr_ev, 0, None) ** 2)) if len(ev) else 0.0
    return dict(
        n_events=int(len(ev)), n_good_events=int(good.sum()),
        depth=dep, depth_err=dep_e, snr=dep / dep_e if dep_e else np.nan,
        odd_even_sigma=float(abs(odd - even) / np.hypot(odd_e, even_e)) if np.isfinite(odd + even) else np.nan,
        secondary=sdep, secondary_err=sdep_e,
        max_ses_frac=float(np.max(snr_ev) / tot) if tot > 0 else np.nan,
        frac_neg_events=float(np.mean(ev[:, 0] < 0)) if len(ev) else np.nan,
        events=[(x[0], round(x[1], 5), round(x[2] * 1e6, 1), round(x[3] * 1e6, 1), round(x[4], 2))
                for x in events],
    )


def toi_windows(t, toi, P_fit=None, t0_fit=None, dur_fit=None):
    """In-transit mask for one TOI: catalogue ephemeris widened by its propagated timing error,
    plus our own refit ephemeris when the signal is detected in our data."""
    dur = toi["dur_h"] / 24 if np.isfinite(toi["dur_h"]) and toi["dur_h"] > 0 else 0.25
    P, T0 = toi["P"], toi["T0"]
    if not (np.isfinite(P) and P > 0):
        return np.abs(t - T0) < max(1.5 * dur, 0.5)
    eP = toi["eP"] if np.isfinite(toi["eP"]) and toi["eP"] > 0 else 1e-4 * P
    eT = toi["eT0"] if np.isfinite(toi["eT0"]) and toi["eT0"] > 0 else 0.01
    n = np.round((t - T0) / P)
    hw = np.minimum(0.75 * dur + 3 * np.sqrt(eT**2 + (n * eP) ** 2), 0.25 * P)
    m = np.abs(t - (T0 + n * P)) < hw
    if P_fit is not None:
        m |= np.abs(((t - t0_fit + 0.5 * P_fit) % P_fit) - 0.5 * P_fit) < dur_fit
    return m


def search_star(args):
    try:
        return _search_star(args)
    except Exception as ex:
        return args[0], {"tic": int(args[0]), "error": f"search: {ex!r}"}


def _search_star(args):
    tic, star = args[:2]
    tois = args[2] if len(args) > 2 else []
    premask = args[3] if len(args) > 3 else []
    t_start = time.time()
    try:
        sectors = load_star(tic)
    except Exception as ex:
        return tic, {"tic": tic, "error": f"load: {ex}"}
    rho = star.get("rho")
    if not np.isfinite(rho) or rho <= 0:
        rho = star["mass"] / star["rad"] ** 3 if np.isfinite(star["mass"]) else 1.5
    rho = float(np.clip(rho, 0.3, 30))
    pmax_dur = expected_duration(P_MAX, rho)
    window = float(np.clip(3.0 * pmax_dur, 0.5, 1.0))
    prep = prepare(sectors, window)
    if not prep:
        return tic, {"tic": tic, "error": "no usable data"}
    def binned(minutes):
        tb, yb, eb = [], [], []
        for p in prep:
            if p["exptime"] < 0.9 * minutes * 60:
                a, b, c = bin_sector(p["t"], p["r"], p["e"], minutes / 1440)
            else:
                a, b, c = p["t"], p["r"], p["e"]
            tb.append(a); yb.append(b); eb.append(c)
        t, y, e = np.concatenate(tb), np.concatenate(yb), np.concatenate(eb)
        o = np.argsort(t)
        return t[o], y[o], e[o]

    tc, yc, ec = binned(BIN_COARSE)
    tf, yf, ef = binned(BIN_FINE)
    tu = np.concatenate([p["t"] for p in prep]); ru = np.concatenate([p["r"] for p in prep])
    eu = np.concatenate([p["e"] for p in prep])
    o = np.argsort(tu); tu, ru, eu = tu[o], ru[o], eu[o]
    span = tc.max() - tc.min()
    pmax = min(P_MAX, span / 2)
    periods = None if (SEMICOHERENT or STACK) else period_grid(span, rho, P_MIN, pmax)
    result = dict(tic=int(tic), rho=rho, window=window, n_points=int(len(tc)), span=float(span),
                  sectors=[p["sector"] for p in prep], provs=[p["prov"] for p in prep],
                  n_periods=0 if periods is None else int(len(periods)),
                  noise_ppm=float(robust_std(ru) * 1e6),
                  prot=[float(p["prot"]) for p in prep], var_snr=[float(p["var_snr"]) for p in prep],
                  n_prewhitened=int(sum(p["prewhitened"] for p in prep)), signals=[])
    masks = [np.ones(len(x), bool) for x in (tc, tf, tu)]
    result["masked_tois"] = []
    for toi in tois:
        fit = None
        if np.isfinite(toi["P"]) and toi["P"] > 0 and toi["P"] < span / 2:
            P, t0, dur, dep, snr = refine(tf, yf, ef, toi["P"], rho, span)
            if snr >= 7 and abs(P / toi["P"] - 1) < 0.01:
                fit = (P, t0, dur)
        for arr_t, m in zip((tc, tf, tu), masks):
            m &= ~toi_windows(arr_t, toi, *(fit or (None, None, None)))
        result["masked_tois"].append(dict(toi, refit=fit is not None, P_fit=fit[0] if fit else None,
                                          t0_fit=fit[1] if fit else None, dur_fit=fit[2] if fit else None))
    # signals found by an earlier search of the same star (--premask), so a longer-period search
    # does not rediscover them or combine their transits
    for P, t0, dur in premask:
        for arr_t, m in zip((tc, tf, tu), masks):
            m &= np.abs(((arr_t - t0 + 0.5 * P) % P) - 0.5 * P) > dur
    result["premasked"] = [list(x) for x in premask]
    result["frac_masked"] = float(1 - masks[2].mean())
    for k in range(MAX_SIGNALS):
        mc, mf, mu = masks
        if mc.sum() < 100 or mf.sum() < 100:
            break
        if STACK:
            Pc, coarse_snr, nper, sde_val = stackslide_peak(tc[mc], yc[mc], ec[mc], rho, P_MIN, pmax)
            result["n_periods"] = int(nper)
        elif SEMICOHERENT:
            Pc, coarse_snr, nper, z = semicoherent_peak(tc[mc], yc[mc], ec[mc], rho, P_MIN, pmax)
            result["n_periods"] = int(nper)
            sde_val = float(np.max(z))
        else:
            r = run_bls(tc[mc], yc[mc], ec[mc], periods, rho)
            s = sde(r["power"], r["period"])
            i = int(np.argmax(r["power"]))
            Pc, coarse_snr, sde_val = float(r["period"][i]), float(np.sqrt(2 * max(r["power"][i], 0))), float(s[i])
        if Pc is None:
            break
        P, t0, dur, dep, snr = refine(tf[mf], yf[mf], ef[mf], Pc, rho, span)
        st = event_stats(tu[mu], ru[mu], eu[mu], P, t0, dur)
        sig = dict(rank=k + 1, period=P, t0=t0, duration_h=dur * 24, bls_depth_ppm=dep * 1e6,
                   bls_snr=snr, coarse_snr=coarse_snr, sde=sde_val,
                   exp_duration_h=float(expected_duration(P, rho) * 24), **st)
        # Same period again after masking = leftover variability, not a new planet. Real pairs
        # near 2:1 sit >~0.5% from exact commensurability, hence the tighter harmonic tolerance.
        prev = [x["period"] for x in result["signals"]]
        sig["toi_alias"] = any(np.isfinite(x["P"]) and x["P"] > 0 and known_alias(P, x["P"])
                               for x in result["masked_tois"])
        sig["repeat"] = any(abs(P / q - 1) < 0.005 or abs(P / q / 2 - 1) < 0.002
                            or abs(P / q * 2 - 1) < 0.002 for q in prev)
        rots = [p["prot"] for p in prep if p["var_snr"] > 3 and np.isfinite(p["prot"])]
        sig["rot_alias"] = any(abs(P / (pr * h) - 1) < 0.02 for pr in rots
                               for h in (1 / 3, 1 / 2, 1, 2, 3))
        result["signals"].append(sig)
        if sig["bls_snr"] < SNR_CONTINUE or (sig["repeat"] and not sig["toi_alias"]):
            break
        for arr_t, m in zip((tc, tf, tu), masks):
            ph = ((arr_t - t0 + 0.5 * P) % P) - 0.5 * P
            m &= np.abs(ph) > 1.0 * dur
    result["runtime_s"] = round(time.time() - t_start, 1)
    return tic, result


def known_alias(P, Pk, tol=0.003):
    """P within tol of a 1/3...3 harmonic of a known period: leakage from an imperfect mask."""
    return any(abs(P / (Pk * h) - 1) < tol for h in (1 / 3, 1 / 2, 2 / 3, 1, 3 / 2, 2, 3))


def star_tois(tic, toi_table):
    rows = toi_table[toi_table["TIC ID"] == tic]
    return [dict(toi=float(r["TOI"]), P=float(r["Period (days)"]), eP=float(r["Period (days) err"]),
                 T0=float(r["Epoch (BJD)"]) - 2457000, eT0=float(r["Epoch (BJD) err"]),
                 dur_h=float(r["Duration (hours)"])) for _, r in rows.iterrows()]


def _set_method(semi, max_signals=3, stack=False, pmin=0.5, pmax=30.0):
    global SEMICOHERENT, MAX_SIGNALS, STACK, P_MIN, P_MAX
    SEMICOHERENT = semi
    MAX_SIGNALS = max_signals
    STACK = stack
    P_MIN, P_MAX = pmin, pmax


def previous_signals(path, snr_min=7.0):
    """(P, t0, duration) of the signals in an earlier search result for the same star."""
    if not os.path.exists(path):
        return []
    r = json.load(open(path))
    return [(s["period"], s["t0"], s["duration_h"] / 24) for s in r.get("signals", [])
            if s["bls_snr"] >= snr_min]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets")
    ap.add_argument("--procs", type=int, default=12)
    ap.add_argument("--out", default=str(RESULTS / "search"))
    ap.add_argument("--stars", default=str(CAT / "targets.parquet"))
    ap.add_argument("--method", choices=("semi", "coherent", "stack"), default="semi")
    ap.add_argument("--mask-tois", action="store_true", help="mask every TOI on the star first")
    ap.add_argument("--max-signals", type=int, default=MAX_SIGNALS)
    ap.add_argument("--pmin", type=float, default=P_MIN)
    ap.add_argument("--pmax", type=float, default=P_MAX)
    ap.add_argument("--premask", help="directory of an earlier search; its signals are masked first")
    a = ap.parse_args()
    global SEMICOHERENT, STACK
    SEMICOHERENT = a.method == "semi"
    STACK = a.method == "stack"
    os.makedirs(a.out, exist_ok=True)
    stars = pd.read_parquet(a.stars).set_index("ID")
    tics = [int(x) for x in open(a.targets).read().split()]
    toi_table = pd.read_csv(DATA / "known" / "toi.csv") if a.mask_tois else None
    todo = [(tic, stars.loc[tic].to_dict(), star_tois(tic, toi_table) if a.mask_tois else [],
             previous_signals(f"{a.premask}/{tic}.json") if a.premask else [])
            for tic in tics
            if not os.path.exists(f"{a.out}/{tic}.json") and tic in stars.index
            and tic_path(tic).exists()]
    print(f"{len(todo)} stars to search", flush=True)
    t0 = time.time()
    with Pool(a.procs, initializer=_set_method,
              initargs=(SEMICOHERENT, a.max_signals, STACK, a.pmin, a.pmax)) as pool:
        for i, (tic, res) in enumerate(pool.imap_unordered(search_star, todo, chunksize=1), 1):
            with open(f"{a.out}/{tic}.json", "w") as fh:
                json.dump(res, fh, default=float)
            if i % 50 == 0 or i == len(todo):
                print(f"{i}/{len(todo)}  {i / (time.time() - t0):.2f} stars/s", flush=True)


if __name__ == "__main__":
    main()
