import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from astropy.io import fits
import numpy as np

from pipeline.independent_vet import combine, event_measurements, measure_event, phase_distance, read_curve


class LocalMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.signal = SimpleNamespace(tic=1, period_d=3.0, t0_btjd=1.0, duration_h=3.0)
        self.t = np.arange(0, 30, 2 / 1440)
        self.error = np.full(len(self.t), 2e-4)
        noise = np.random.default_rng(8).normal(0, self.error)
        self.flux = 1 + 2e-4 * self.t + noise
        self.flux[np.abs(phase_distance(self.t, 3, 1)) <= 3 / 48] -= 0.001
        self.curves = [(1, "synthetic", self.t, self.flux, self.error)]

    def test_recovers_injected_depth_with_sloping_baseline(self):
        for width in (2.5, 4.0):
            events, _ = event_measurements(self.curves, self.signal, width)
            summary = combine(events)
            self.assertEqual(summary["n_events"], 10)
            self.assertAlmostEqual(summary["depth_ppm"], 1000, delta=40)

    def test_phase_control_does_not_measure_real_transits(self):
        events, _ = event_measurements(self.curves, self.signal, phase_shift=0.5)
        self.assertAlmostEqual(combine(events)["depth_ppm"], 0, delta=40)

    def test_missing_core_is_not_counted_as_non_detection(self):
        keep = np.abs(self.t - 1) > 0.07
        result = measure_event(self.t[keep], self.flux[keep], self.error[keep], 1, 0.125, 0.5)
        self.assertIsNone(result)

    def test_one_sided_baseline_is_rejected(self):
        keep = self.t >= 0.95
        result = measure_event(self.t[keep], self.flux[keep], self.error[keep], 1, 0.125, 0.5)
        self.assertIsNone(result)

    def test_event_scatter_inflates_the_formal_error(self):
        events, _ = event_measurements(self.curves, self.signal)
        events.loc[0, "depth_ppm"] += 1500
        result = combine(events)
        self.assertGreater(result["event_error_ppm"], result["white_error_ppm"])
        self.assertLess(result["snr_event"], result["snr_white"])

    def test_constant_flux_has_zero_depth(self):
        events, _ = event_measurements([(1, "synthetic", self.t, np.ones(len(self.t)), self.error)], self.signal)
        self.assertAlmostEqual(combine(events)["depth_ppm"], 0, places=6)


class QlpReadTests(unittest.TestCase):
    def curve(self, errors, flux=None):
        n = len(errors)
        flux = 1 + np.random.default_rng(5).normal(0, 1e-3, n) if flux is None else flux
        quality = np.zeros(n, dtype=np.int32)
        quality[::5] = 1
        columns = [fits.Column(name=name, format=fmt, array=array) for name, fmt, array in (
            ("TIME", "D", np.arange(n) / 720), ("SYS_RM_FLUX", "D", flux),
            ("DET_FLUX_ERR", "D", errors), ("QUALITY", "J", quality))]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.fits"
            fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(columns)]).writeto(path)
            return read_curve(path, "QLP", return_info=True)

    def test_missing_errors_preserve_quality_accepted_flux(self):
        t, f, e, info = self.curve(np.full(100, np.nan))
        self.assertEqual(len(t), 80)
        self.assertEqual(info["error_source"], "empirical_adjacent_mad")
        self.assertTrue(np.all(np.isfinite(e) & (e > 0)))
        self.assertAlmostEqual(float(np.median(f)), 1)

    def test_supplied_errors_are_preserved(self):
        t, f, e, info = self.curve(np.full(100, 0.002), flux=np.ones(100))
        self.assertEqual(len(t), 80)
        np.testing.assert_array_equal(e, np.full(80, 0.002))
        self.assertEqual(info["error_source"], "provided")

    def test_degenerate_flux_does_not_invent_precision(self):
        t, _, _, info = self.curve(np.full(100, np.nan), flux=np.ones(100))
        self.assertEqual(len(t), 0)
        self.assertEqual(info["error_source"], "unusable")


if __name__ == "__main__":
    unittest.main()
