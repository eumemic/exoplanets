"""Asymmetric Huber 4-harmonic starspot pre-whitener for cool, active dwarfs.

Ported from Foundation-0/exoplanets-frontier despot.py (blob a47f16b1) at commit
ad02fe103ab2d0ead89cae9975aa8fd947a6302d; the Phase 2 code landed in
412043e048048f8c0123de25c548cb0be70ad960. The numerical method is unchanged: only the
pre-whitener is kept (F0's null-control trial and plotting card are left out).

Per continuous segment (gaps > 0.45 d), find up to max_modes coherent rotation frequencies
on a 0.12-5.6 c/d grid, fit each with a line plus n_harm harmonics by iteratively reweighted
least squares that gives points more than 2.2 MAD low (transits) zero weight, divide the model
out, then polish with a ~polish_d day running median. Used by search.py --harmonic-despot.
"""
import math

import numpy as np
from scipy import signal


def _empty(raw_ppm=0.0, clean_ppm=0.0):
    return np.array([]), np.array([]), np.array([]), {"p_rot_d": 0.0, "raw_ppm": raw_ppm,
                                                      "clean_ppm": clean_ppm}


def harmonic_despot(t, f, fe, q=None, max_modes=3, n_harm=4, polish_d=1.15):
    """De-spotted (t, flux, flux_err, info). Flux comes back normalized to ~1; points near
    segment edges, short segments and upward outliers are dropped. Fewer than 90 usable
    points (or no usable segment) gives empty arrays."""
    t, f, fe = np.asarray(t, float), np.asarray(f, float), np.asarray(fe, float)
    m = np.isfinite(t) & np.isfinite(f) & (f > 0)
    if q is not None:
        m &= np.asarray(q, int) == 0
    t, f, fe = t[m], f[m], fe[m]
    if len(t) < 90:
        return _empty()
    o = np.argsort(t)
    t, f, fe = t[o], f[o], fe[o]
    # Drop 0.1 d at the ends and on both sides of every gap > 0.5 d.
    ek = ((t - t[0]) >= 0.10) & ((t[-1] - t) >= 0.10)
    for g in np.where(np.diff(t) > 0.5)[0]:
        ek &= ~(((t <= t[g]) & ((t[g] - t) < 0.10)) | ((t >= t[g + 1]) & ((t - t[g + 1]) < 0.10)))
    if np.sum(ek) >= 90:
        t, f, fe = t[ek], f[ek], fe[ek]
    med0 = float(np.median(f))
    fn = f / med0
    raw_ppm = 1.4826 * float(np.median(np.abs(fn - 1.0))) * 1e6
    sp = max(1.4826 * float(np.median(np.abs(np.diff(fn)))), 5e-5)
    fen = np.where(np.isfinite(fe) & (fe > 0), fe / med0, sp)
    to, fo, feo, prots = [], [], [], []
    fgrid = np.linspace(0.12, 5.6, 850)
    for s in np.split(np.arange(len(t)), np.where(np.diff(t) > 0.45)[0] + 1):
        if len(s) < 55:
            continue
        ts, fs, fes = t[s], fn[s].copy(), fen[s].copy()
        mad0 = max(1.4826 * float(np.median(np.abs(fs - np.median(fs)))), 5e-5)
        kp = (fs - np.median(fs)) < 4.2 * mad0
        ts, fs, fes = ts[kp], fs[kp], fes[kp]
        if len(ts) < 50:
            continue
        tau = ts - float(np.mean(ts))
        for _ in range(max_modes):
            y = fs - float(np.median(fs))
            mad = max(1.4826 * float(np.median(np.abs(y))), 4e-5)
            inl = y > -2.2 * mad
            if np.sum(inl) < 40:
                break
            ang = 2.0 * np.pi * tau[inl, None] * fgrid[None, :]
            yc = y[inl] - float(np.mean(y[inl]))
            amp = 2.0 * np.hypot(np.dot(yc, np.cos(ang)), np.dot(yc, np.sin(ang))) / max(np.sum(inl), 1)
            bi = int(np.argmax(amp))
            if float(amp[bi]) < 5.2 * mad * math.sqrt(2.0 / np.sum(inl)):
                break
            fine = np.linspace(max(0.10, float(fgrid[bi]) - 0.018), float(fgrid[bi]) + 0.018, 41)
            af = 2.0 * np.pi * tau[inl, None] * fine[None, :]
            f0 = float(fine[int(np.argmax(np.hypot(np.dot(yc, np.cos(af)), np.dot(yc, np.sin(af)))))])
            prots.append(1.0 / f0)
            cols = [np.ones(len(tau)), tau]
            for h in range(1, n_harm + 1):
                if h * f0 <= 9.0 or h == 1:
                    cols += [np.cos(2.0 * np.pi * h * f0 * tau), np.sin(2.0 * np.pi * h * f0 * tau)]
            X = np.column_stack(cols)
            w = np.ones(len(tau), bool)
            mod = np.ones_like(fs)
            for _it in range(4):
                if np.sum(w) < X.shape[1] + 10:
                    break
                coef, *_ = np.linalg.lstsq(X[w], fs[w], rcond=None)
                mod = np.clip(X @ coef, 0.35, 1.85)
                res = fs / mod - 1.0
                rm = max(1.4826 * float(np.median(np.abs(res[w] - np.median(res[w])))), 4e-5)
                w = (res > -2.2 * rm) & (res < 3.6 * rm)
            fs /= mod
            fes /= mod
        # Odd running-median kernel of ~polish_d days (at least 21 points, at most the segment).
        wp = max(21, min(int(round(polish_d / max(float(np.median(np.diff(ts))), 1e-4))) | 1,
                         len(ts) - (1 - len(ts) % 2)))
        inl, tr = np.ones(len(fs), bool), np.ones_like(fs)
        for _ in range(2):
            if np.sum(inl) < 20:
                break
            tr = signal.medfilt(np.interp(ts, ts[inl], fs[inl]), kernel_size=wp)
            r = fs / tr - 1.0
            rm = max(1.4826 * float(np.median(np.abs(r[inl] - np.median(r[inl])))), 4e-5)
            inl = (r > -2.3 * rm) & (r < 3.5 * rm)
        to.append(ts)
        fo.append(fs / tr)
        feo.append(fes / tr)
    if not to:
        return _empty(raw_ppm, raw_ppm)
    tc, fc, fec = np.concatenate(to), np.concatenate(fo), np.concatenate(feo)
    cln = 1.4826 * float(np.median(np.abs(fc - np.median(fc)))) * 1e6
    return tc, fc, fec, {"p_rot_d": round(float(np.median(prots)), 5) if prots else 0.0,
                         "raw_ppm": round(raw_ppm, 1), "clean_ppm": round(cln, 1)}
