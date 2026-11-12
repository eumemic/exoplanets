"""harmonic_despot (ported from Foundation-0/exoplanets-frontier) and the search.py --harmonic-despot hook."""
from pathlib import Path
import sys
import unittest

import numpy as np

# search.py imports its siblings directly (it is run from pipeline/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import search
from harmonic_despot import harmonic_despot

P, T0, DUR, DEPTH = 1.24, 0.31, 1.5 / 24, 1500e-6


def spotted_sector(seed=0, amp=0.015, noise=4e-4):
    """One 2-min sector (two 12.5 d orbits) of a 0.7 d spot wave plus a box transit."""
    rng = np.random.default_rng(seed)
    t = np.concatenate([np.arange(0.0, 12.5, 2 / 1440), np.arange(13.5, 26.0, 2 / 1440)])
    spot = amp * np.sin(2 * np.pi * t / 0.7) + 0.3 * amp * np.sin(4 * np.pi * t / 0.7 + 1.0)
    intr = np.abs(((t - T0 + 0.5 * P) % P) - 0.5 * P) < 0.5 * DUR
    f = (1 + spot) * (1 - DEPTH * intr) + noise * rng.standard_normal(len(t))
    return t, f, np.full(len(t), noise), intr


def fold_depth(t, f):
    ph = np.abs(((t - T0 + 0.5 * P) % P) - 0.5 * P)
    return np.median(f[(ph > 2 * DUR) & (ph < 0.3)]) - np.mean(f[ph < 0.35 * DUR])


class HarmonicDespotTest(unittest.TestCase):
    def test_removes_spot_wave_and_keeps_transit(self):
        t, f, fe, intr = spotted_sector()
        tc, fc, fec, info = harmonic_despot(t, f, fe)
        self.assertGreater(len(tc), 0.9 * len(t))
        self.assertEqual(len(tc), len(fc))
        self.assertEqual(len(tc), len(fec))
        self.assertAlmostEqual(info['p_rot_d'], 0.7, delta=0.01)
        oot = ~(np.abs(((tc - T0 + 0.5 * P) % P) - 0.5 * P) < DUR)
        raw_rms, clean_rms = np.std(f[~intr]), np.std(fc[oot])
        self.assertLess(clean_rms, raw_rms / 10)
        self.assertGreater(fold_depth(tc, fc), 0.9 * DEPTH)
        self.assertLess(fold_depth(tc, fc), 1.2 * DEPTH)
        self.assertGreater(info['raw_ppm'], 5 * info['clean_ppm'])

    def test_short_input_returns_empty(self):
        for n in (0, 10, 89):
            tc, fc, fec, info = harmonic_despot(np.arange(n) * 0.01, np.ones(n), np.ones(n))
            self.assertEqual((len(tc), len(fc), len(fec)), (0, 0, 0))
            self.assertEqual(info, {'p_rot_d': 0.0, 'raw_ppm': 0.0, 'clean_ppm': 0.0})

    def test_only_short_segments_returns_empty(self):
        t = np.concatenate([np.arange(40) * 0.01 + 2 * k for k in range(4)])
        tc, fc, fec, info = harmonic_despot(t, np.ones(len(t)), np.full(len(t), np.nan))
        self.assertEqual(len(tc), 0)
        self.assertEqual(info['p_rot_d'], 0.0)


def old_prepare(sectors, window):
    """prepare() as it was before --harmonic-despot (eumemic/exoplanets e2eee928)."""
    out = []
    for s in sectors:
        t, f = s['time'], s['flux']
        o = np.argsort(t)
        t, f = t[o], f[o]
        ok = (f > 0) & (f < 5)
        t, f = t[ok], f[ok]
        prot, var_snr = search.rotation_period(t, f)
        fast = bool(np.isfinite(prot) and prot < 3.0 and var_snr > 3.0)
        if fast:
            f = search.prewhiten(t, f, prot)
        r = f / search.biweight_trend(t, f, window) - 1.0
        ok = np.isfinite(r)
        sig = search.robust_std(r[ok])
        ok &= r < 4 * sig
        t, r = t[ok], r[ok]
        e = np.maximum(search.rolling_std(t, r), 0.5 * sig)
        out.append(dict(t=t, r=r, e=e, prot=prot, prewhitened=fast))
    return out


class SearchHookTest(unittest.TestCase):
    def setUp(self):
        t, f, fe, _ = spotted_sector(seed=1)
        self.sectors = [dict(sector=1, provenance='spoc', exptime=120.0, time=t, flux=f, flux_err=fe)]
        self.addCleanup(setattr, search, 'HARMONIC_DESPOT', search.HARMONIC_DESPOT)

    def test_default_off(self):
        self.assertFalse(search.HARMONIC_DESPOT)
        search._set_method(True)
        self.assertFalse(search.HARMONIC_DESPOT)

    def test_flag_off_matches_previous_path(self):
        search.HARMONIC_DESPOT = False
        ref = old_prepare(self.sectors, 0.75)[0]
        for teff in (None, 3500.0):
            p = search.prepare(self.sectors, 0.75, teff=teff)[0]
            self.assertTrue(p['prewhitened'])
            self.assertEqual(p['prewhitened'], ref['prewhitened'])
            self.assertEqual(p['prewhiten_method'], 'fourier')
            self.assertEqual(p['prot'], ref['prot'])
            for k in ('t', 'r', 'e'):
                np.testing.assert_array_equal(p[k], ref[k])

    def test_flag_on_cool_dwarf_uses_harmonic_despot(self):
        search._set_method(True, despot=True)
        p = search.prepare(self.sectors, 0.75, teff=3500.0)[0]
        self.assertEqual(p['prewhiten_method'], 'harmonic_despot')
        self.assertTrue(p['prewhitened'])
        self.assertGreater(fold_depth(p['t'], p['r']), 0.9 * DEPTH)

    def test_flag_on_warm_or_unknown_star_keeps_previous_path(self):
        search.HARMONIC_DESPOT = True
        ref = search.prepare(self.sectors, 0.75)[0]
        self.assertEqual(ref['prewhiten_method'], 'fourier')
        for teff in (5000.0, 4000.0, np.nan):
            p = search.prepare(self.sectors, 0.75, teff=teff)[0]
            self.assertEqual(p['prewhiten_method'], 'fourier')
            np.testing.assert_array_equal(p['r'], ref['r'])

    def test_flag_on_falls_back_when_despot_keeps_too_little(self):
        search.HARMONIC_DESPOT = True
        t = np.arange(0.0, 26.0, 30 / 1440)[::3][:260]   # 260 points, 1.5 h cadence
        f = 1 + 0.015 * np.sin(2 * np.pi * t / 0.7)
        # Segments under 55 points are dropped, so gaps every 50 points leave harmonic_despot nothing.
        t = t + 0.5 * (np.arange(len(t)) // 50)
        s = [dict(sector=2, provenance='qlp', exptime=1800.0, time=t, flux=f, flux_err=np.full(len(t), 1e-3))]
        self.assertEqual(len(harmonic_despot(t, f, s[0]['flux_err'])[0]), 0)
        p = search.prepare(s, 0.75, teff=3500.0)
        self.assertEqual(len(p), 1)
        self.assertNotEqual(p[0]['prewhiten_method'], 'harmonic_despot')


if __name__ == '__main__':
    unittest.main()
