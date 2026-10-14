import unittest

import pandas as pd

from pipeline.independent_sample import build_sample


class SampleSelectionTests(unittest.TestCase):
    def setUp(self):
        self.table = pd.DataFrame(dict(tic=[1, 2, 3], rank=[1, 1, 1], label=["real"] * 3,
                                       inv_set=[0] * 3, band=["low"] * 3,
                                       cls=["clean", "clean", "crowded"], period=[2., 3., 4.]))
        self.released = self.table.assign(score_h=[.79, .81, .81])
        self.grouped = self.table.assign(score_h=[.81, .79, .79])
        self.catalog = pd.DataFrame(dict(TIC=[1, 2, 3], P_d=[2., 3., 4.], T0_BJD=[2457001.] * 3,
                                         T14_h=[2.] * 3, depth_ppm=[500.] * 3, tier=["L"] * 3))

    def test_selects_both_directions_and_uses_catalog_epoch(self):
        result = build_sample(self.table, self.released, self.grouped, self.catalog)
        self.assertEqual(result.tic.tolist(), [1, 2])
        self.assertEqual(result.direction.tolist(), ["enter", "leave"])
        self.assertEqual(result.t0_btjd.tolist(), [1., 1.])

    def test_refuses_misaligned_scores_and_ambiguous_ephemerides(self):
        with self.assertRaisesRegex(ValueError, "identical signal keys"):
            build_sample(self.table, self.released, self.grouped.iloc[::-1], self.catalog)
        with self.assertRaisesRegex(ValueError, "one catalog ephemeris"):
            build_sample(self.table, self.released, self.grouped, pd.concat([self.catalog] * 2))


if __name__ == "__main__":
    unittest.main()
