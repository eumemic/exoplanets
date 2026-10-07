"""Semi-coherent box least squares.

TESS coverage is a few sectors spread over years, so a phase-coherent period grid must be
~span/season times finer than the data within one season need. Stage 1 runs BLS per season on
a grid fine enough for the longest season and sums each season's best delta-chi2 (separately
per duration). Stage 2 refines the top peaks coherently on all data.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def _season_scan(t, y, w, freqs, binw, durs, out):
    """For each frequency and duration, add max over phase of delta-chi2 (dips only) to out."""
    wtot = w.sum()
    ytot = (w * y).sum()
    nd = len(durs)
    for j in range(len(freqs)):
        f = freqs[j]
        P = 1.0 / f
        nb = int(P / binw) + 1
        sw = np.zeros(2 * nb)
        swy = np.zeros(2 * nb)
        for i in range(len(t)):
            ph = (t[i] * f) % 1.0
            b = int(ph * nb)
            if b >= nb:
                b = nb - 1
            sw[b] += w[i]
            swy[b] += w[i] * y[i]
        for b in range(nb):
            sw[nb + b] = sw[b]
            swy[nb + b] = swy[b]
        cw = np.zeros(2 * nb + 1)
        cy = np.zeros(2 * nb + 1)
        for b in range(2 * nb):
            cw[b + 1] = cw[b] + sw[b]
            cy[b + 1] = cy[b] + swy[b]
        for k in range(nd):
            q = int(durs[k] / (P * 1.0) * nb + 0.5)
            if q < 1:
                q = 1
            if q >= nb:
                continue
            best = 0.0
            for s in range(nb):
                win = cw[s + q] - cw[s]
                if win <= 0.0 or win >= wtot:
                    continue
                wy = cy[s + q] - cy[s]
                yin = wy / win
                yout = (ytot - wy) / (wtot - win)
                d = yout - yin
                if d <= 0.0:
                    continue
                c = d * d / (1.0 / win + 1.0 / (wtot - win))
                if c > best:
                    best = c
            out[j, k] += best


@njit(cache=True)
def _coherent_best(t, y, w, freqs, binw, durs):
    """Coherent BLS on all data: best delta-chi2, phase start, duration index per frequency."""
    wtot = w.sum()
    ytot = (w * y).sum()
    nf = len(freqs)
    power = np.zeros(nf)
    t0s = np.zeros(nf)
    kbest = np.zeros(nf, np.int64)
    depth = np.zeros(nf)
    for j in range(nf):
        f = freqs[j]
        P = 1.0 / f
        nb = int(P / binw) + 1
        sw = np.zeros(2 * nb)
        swy = np.zeros(2 * nb)
        for i in range(len(t)):
            b = int(((t[i] * f) % 1.0) * nb)
            if b >= nb:
                b = nb - 1
            sw[b] += w[i]
            swy[b] += w[i] * y[i]
        for b in range(nb):
            sw[nb + b] = sw[b]
            swy[nb + b] = swy[b]
        cw = np.zeros(2 * nb + 1)
        cy = np.zeros(2 * nb + 1)
        for b in range(2 * nb):
            cw[b + 1] = cw[b] + sw[b]
            cy[b + 1] = cy[b] + swy[b]
        for k in range(len(durs)):
            q = int(durs[k] / P * nb + 0.5)
            if q < 1:
                q = 1
            if q >= nb:
                continue
            for s in range(nb):
                win = cw[s + q] - cw[s]
                if win <= 0.0 or win >= wtot:
                    continue
                wy = cy[s + q] - cy[s]
                d = (ytot - wy) / (wtot - win) - wy / win
                if d <= 0.0:
                    continue
                c = d * d / (1.0 / win + 1.0 / (wtot - win))
                if c > power[j]:
                    power[j] = c
                    kbest[j] = k
                    t0s[j] = (s + 0.5 * q) / nb * P
                    depth[j] = d
    return power, t0s, kbest, depth


def seasons(t, gap=20.0):
    """Split sorted times into seasons at gaps longer than `gap` days."""
    cuts = np.where(np.diff(t) > gap)[0] + 1
    return np.split(np.arange(len(t)), cuts)


def semicoherent(t, y, dy, freqs, durs, binw):
    """Stage 1: summed per-season delta-chi2, shape (nfreq, ndur)."""
    w = 1.0 / dy**2
    out = np.zeros((len(freqs), len(durs)))
    for idx in seasons(t):
        if len(idx) < 50:
            continue
        ts = t[idx] - t[idx][0]
        _season_scan(ts, y[idx], w[idx], freqs, binw, durs, out)
    return out


def coherent(t, y, dy, freqs, durs, binw):
    """Stage 2: coherent BLS on all data (times referenced to t[0])."""
    w = 1.0 / dy**2
    p, t0, k, d = _coherent_best(t - t[0], y, w, freqs, binw, durs)
    return p, t0 + t[0], k, d
