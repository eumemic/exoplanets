"""The TRICERATOPS-centroid combination (pipeline/fpp_combine.py)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from fpp_combine import combine  # noqa: E402

# ten runs of TIC 411099851 (2.87 d), default priors: FPP and NFPP per run
FPP = [0.4062, 0.4740, 0.5515, 0.5213, 0.4705, 0.5496, 0.5061, 0.4531, 0.4996, 0.5607]
NFPP = [0.378, 0.452, 0.532, 0.484, 0.426, 0.522, 0.489, 0.421, 0.464, 0.512]


class CombineTests(unittest.TestCase):
    def test_no_bayes_factor_leaves_values(self):
        self.assertEqual(combine(0.2, 0.05, 0.08, float('nan')), (0.2, 0.08))

    def test_unit_bayes_factor_leaves_fpp(self):
        f, n = combine(0.2, 0.05, 0.08, 1.0)
        self.assertAlmostEqual(f, 0.2)
        self.assertAlmostEqual(n, 0.08)

    def test_runs_whose_max_nfpp_exceeds_mean_fpp(self):
        fm, nm, nx = sum(FPP) / 10, sum(NFPP) / 10, max(NFPP)
        self.assertGreater(nx, fm)                      # the case that went negative before 14 October 2026
        f, n = combine(fm, nm, nx, 390.0)
        self.assertGreaterEqual(f, 0)
        self.assertAlmostEqual(f, 0.061, places=3)      # the share of false positives on the target star remains
        self.assertLess(n, 0.01)

    def test_bounds(self):
        for fm in (0.0, 0.1, 0.5, 0.9, 1.0):
            for share in (0.0, 0.5, 1.0):
                nm = fm * share
                for bf in (0.01, 0.5, 1.0, 5.0, 1000.0):
                    f, n = combine(fm, nm, min(1.0, nm * 1.5), bf)
                    self.assertGreaterEqual(f, -1e-12)
                    self.assertLessEqual(f, 1 + 1e-12)
                    self.assertGreaterEqual(n, 0)
                    self.assertLessEqual(n, 1 + 1e-12)


if __name__ == '__main__':
    unittest.main()
