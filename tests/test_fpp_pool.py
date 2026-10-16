"""The TRICERATOPS batch helpers: model sub-exposures per fold (pipeline/fpp_core.py) and the adaptive run count
(pipeline/fpp_pool.py)."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import fpp_core as fc  # noqa: E402
from fpp_pool import needs_more, state_path  # noqa: E402



class SilentFailureTests(unittest.TestCase):
    """Inputs for which TRICERATOPS returns a plausible-looking but wrong result without an error, so runs must refuse
    them: no field-star population (six blended-star scenarios skipped), or a target without mass, radius, Teff or
    parallax (every scenario equally likely)."""

    def test_missing_or_empty_population_is_refused(self):
        import tempfile
        from types import SimpleNamespace
        empty = tempfile.NamedTemporaryFile(suffix=".csv", delete=False).name
        for fname in (None, "/nonexistent/x_gaia_background.csv", empty):
            target = SimpleNamespace(trilegal_fname=fname)
            self.assertFalse(fc.has_population(target))
            with self.assertRaises(RuntimeError):
                fc.run_once(target, {}, N=10)

    def test_population_file_is_accepted(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write("Mact,logg\n1,4.5\n")
        self.assertTrue(fc.has_population(SimpleNamespace(trilegal_fname=fh.name)))

    def test_cut_off_population_file_is_refused(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write("Mact,logg,logTe,[M/H],TESS,J,H,Ks\n0.8,4.6,3.7,0.0,12.1,11.2,10.7,10.6\n0.5,4.8,3.6\n")
        self.assertFalse(fc.has_population(SimpleNamespace(trilegal_fname=fh.name)))

    def test_target_without_parallax_is_refused(self):
        import tempfile
        from types import SimpleNamespace
        import pandas as pd
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write("Mact,logg\n1,4.5\n")
        stars = pd.DataFrame(dict(ID=[1], mass=[0.64], rad=[0.67], Teff=[3783.0], plx=[float("nan")]))
        with self.assertRaisesRegex(RuntimeError, "plx"):
            fc.run_once(SimpleNamespace(trilegal_fname=fh.name, stars=stars), {}, N=10)


class SubExposureTests(unittest.TestCase):
    def test_one_per_two_minutes(self):
        for sec, n in ((120, 1), (200, 2), (600, 5), (1800, 15)):
            self.assertEqual(fc.auto_nsamples(sec / 86400), n, sec)

    def test_old_folds_keep_ten_minutes(self):
        d = np.load(self._npz(exptime=None))
        self.assertAlmostEqual(fc.fold_exptime(d), 10 / 1440)

    def test_single_cadence_folds_carry_their_exposure(self):
        d = np.load(self._npz(exptime=200 / 86400))
        self.assertAlmostEqual(fc.fold_exptime(d), 200 / 86400)

    def _npz(self, exptime):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".npz", delete=False).name
        extra = {} if exptime is None else {"exptime": exptime}
        np.savez(f, time=np.zeros(3), flux=np.ones(3), flux_err=np.ones(3), P=1.0, **extra)
        self.addCleanup(lambda: Path(f).unlink())
        return f


class AdaptiveRunTests(unittest.TestCase):
    def test_one_run_is_never_enough(self):
        self.assertTrue(needs_more([0.2], [0.05], 3))

    def test_far_from_every_threshold_stops(self):
        self.assertFalse(needs_more([0.20, 0.21, 0.19], [0.0300, 0.0310, 0.0290], 3))

    def test_near_fpp_half_continues(self):
        self.assertTrue(needs_more([0.45, 0.55, 0.50], [0.03, 0.03, 0.03], 3))

    def test_near_validation_threshold_continues(self):
        self.assertTrue(needs_more([0.010, 0.020, 0.016], [1e-5, 1e-5, 1e-5], 3))

    def test_state_files_are_named_by_star_and_sectors(self):
        self.assertTrue(state_path("out", 123, "5,6,7").endswith("states/123_5-6-7.pkl"))


if __name__ == "__main__":
    unittest.main()
