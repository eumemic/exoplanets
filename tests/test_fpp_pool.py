"""The TRICERATOPS batch helpers: model sub-exposures per fold (pipeline/fpp_core.py) and the adaptive run count
(pipeline/fpp_pool.py)."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import fpp_core as fc  # noqa: E402
from fpp_pool import needs_more, state_path  # noqa: E402


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
