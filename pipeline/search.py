"""Multi-sector transit search: clean, detrend, bin, BLS on a stellar-density-aware grid.

Usage: python search.py targets.txt [--procs N] [--out results/search]
Writes one JSON per star with up to MAX_SIGNALS signals (iterative masking).
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

from common import CAT, RESULTS, load_star, tic_path

warnings.filterwarnings("ignore")

P_MIN, P_MAX = 0.5, 30.0
BIN_COARSE = 20.0         # cadence (minutes) of the coarse period search
BIN_FINE = 10.0           # cadence (minutes) used to refine each peak
MAX_SIGNALS = 3
SNR_CONTINUE = 7.0        # keep iterating while the last signal is at least this strong
SEMICOHERENT = True       # per-season scan + coherent refinement of the top peaks (fastbls.py)
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
    from wotan import flatten

    out = []
    for s in sectors:
        t, f = s["time"], s["flux"]
        o = np.argsort(t)
        t, f = t[o], f[o]
        prot, var_snr = rotation_period(t, f)
        fast = bool(np.isfinite(prot) and prot < 3.0 and var_snr > 3.0)
        if fast:
            f = prewhiten(t, f, prot)
        flat = flatten(t, f, method="biweight", window_length=window,
                       break_tolerance=0.5, edge_cutoff=0.0)
        r = flat - 1.0
        ok = np.isfinite(r)
        if ok.sum() < 200:
            continue
        sig = robust_std(r[ok])
        ok &= r < 4 * sig            # flares / upward outliers only; dips are kept
        t, r = t[ok], r[ok]
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


def search_star(args):
    tic, star = args
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
    periods = None if SEMICOHERENT else period_grid(span, rho, P_MIN, pmax)
    result = dict(tic=int(tic), rho=rho, window=window, n_points=int(len(tc)), span=float(span),
                  sectors=[p["sector"] for p in prep], provs=[p["prov"] for p in prep],
                  n_periods=0 if periods is None else int(len(periods)),
                  noise_ppm=float(robust_std(ru) * 1e6),
                  prot=[float(p["prot"]) for p in prep], var_snr=[float(p["var_snr"]) for p in prep],
                  n_prewhitened=int(sum(p["prewhitened"] for p in prep)), signals=[])
    masks = [np.ones(len(x), bool) for x in (tc, tf, tu)]
    for k in range(MAX_SIGNALS):
        mc, mf, mu = masks
        if SEMICOHERENT:
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
        sig["repeat"] = any(abs(P / q - 1) < 0.005 or abs(P / q / 2 - 1) < 0.002
                            or abs(P / q * 2 - 1) < 0.002 for q in prev)
        rots = [p["prot"] for p in prep if p["var_snr"] > 3 and np.isfinite(p["prot"])]
        sig["rot_alias"] = any(abs(P / (pr * h) - 1) < 0.02 for pr in rots
                               for h in (1 / 3, 1 / 2, 1, 2, 3))
        result["signals"].append(sig)
        if sig["bls_snr"] < SNR_CONTINUE or sig["repeat"]:
            break
        for arr_t, m in zip((tc, tf, tu), masks):
            ph = ((arr_t - t0 + 0.5 * P) % P) - 0.5 * P
            m &= np.abs(ph) > 1.0 * dur
    result["runtime_s"] = round(time.time() - t_start, 1)
    return tic, result


def _set_method(semi):
    global SEMICOHERENT
    SEMICOHERENT = semi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets")
    ap.add_argument("--procs", type=int, default=12)
    ap.add_argument("--out", default=str(RESULTS / "search"))
    ap.add_argument("--stars", default=str(CAT / "targets.parquet"))
    ap.add_argument("--method", choices=("semi", "coherent"), default="semi")
    a = ap.parse_args()
    global SEMICOHERENT
    SEMICOHERENT = a.method == "semi"
    os.makedirs(a.out, exist_ok=True)
    stars = pd.read_parquet(a.stars).set_index("ID")
    tics = [int(x) for x in open(a.targets).read().split()]
    todo = [(tic, stars.loc[tic].to_dict()) for tic in tics
            if not os.path.exists(f"{a.out}/{tic}.json") and tic in stars.index
            and tic_path(tic).exists()]
    print(f"{len(todo)} stars to search", flush=True)
    t0 = time.time()
    with Pool(a.procs, initializer=_set_method, initargs=(SEMICOHERENT,)) as pool:
        for i, (tic, res) in enumerate(pool.imap_unordered(search_star, todo, chunksize=1), 1):
            with open(f"{a.out}/{tic}.json", "w") as fh:
                json.dump(res, fh, default=float)
            if i % 50 == 0 or i == len(todo):
                print(f"{i}/{len(todo)}  {i / (time.time() - t0):.2f} stars/s", flush=True)


if __name__ == "__main__":
    main()
