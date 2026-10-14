"""Known-signal matching by epoch: single-transit CTOIs and long-period aliases of the same transits."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from pipeline import known

TIC, RA, DEC = 1000, 150.0, 20.0
P, T0, DUR_H = 20.0, 2000.0, 4.0          # our signal: transits at 2000 + 20 n (BTJD), 4 h long


def table(rows):
    d = pd.DataFrame(rows, columns=['tic', 'period', 'ra_deg', 'dec_deg', 't0', 'label'])
    return d.astype({'tic': np.int64})


def run(rows, name='ctoi', **kw):
    with patch.object(known, 'tables', return_value={name: table(rows)}):
        return known.epoch_check(TIC, P, T0, DUR_H, RA, DEC, **kw)


class EpochCheckTests(unittest.TestCase):
    def test_single_transit_on_one_of_our_transits(self):
        res = run([(TIC, np.nan, RA, DEC, T0 + 7 * P + 0.05, '1000.01')])
        self.assertEqual(res['same_star_epoch_match'], ['ctoi:1000.01:P=nan:single transit'])
        self.assertEqual(res['neighbour_epoch_match'], [])

    def test_long_period_alias(self):
        res = run([(TIC, 47 * P, RA, DEC, T0 - 3 * P, 's0001-s0069')], name='tce')
        self.assertEqual(res['same_star_epoch_match'], ['tce:s0001-s0069:P=940.0000:x47'])

    def test_simple_fraction(self):
        res = run([(TIC, P * 3 / 7, RA, DEC, T0 + 2 * P, '1000.01')])
        self.assertEqual(res['same_star_epoch_match'], ['ctoi:1000.01:P=8.5714:x3/7'])

    def test_epoch_outside_our_transits(self):
        self.assertEqual(run([(TIC, np.nan, RA, DEC, T0 + 7 * P + 0.2, '1000.01')])['same_star_epoch_match'], [])

    def test_unrelated_period_on_one_of_our_transits(self):
        # one event coincides, but 4.18 is not p/q with q <= 7, so the other events do not
        self.assertEqual(run([(TIC, 4.18 * P, RA, DEC, T0 + P, '1000.01')])['same_star_epoch_match'], [])

    def test_harmonics_are_left_to_check(self):
        self.assertEqual(run([(TIC, 2 * P, RA, DEC, T0, '1000.01')])['same_star_epoch_match'], [])

    def test_period_error_widens_the_window(self):
        rows = [(TIC, np.nan, RA, DEC, T0 + 50 * P + 0.2, '1000.01')]
        self.assertEqual(run(rows, period_err=0.0)['same_star_epoch_match'], [])
        self.assertEqual(len(run(rows, period_err=0.002)['same_star_epoch_match']), 1)
        # without a period error, the period is known to half a duration over the span
        self.assertEqual(len(run(rows, span=500.0)['same_star_epoch_match']), 1)
        self.assertEqual(run(rows, span=10000.0)['same_star_epoch_match'], [])

    def test_neighbours(self):
        near = (TIC + 1, np.nan, RA, DEC + 60 / 3600, T0 + P, '1001.01')      # 1' away
        far = (TIC + 2, np.nan, RA, DEC + 200 / 3600, T0 + P, '1002.01')      # 3.3' away
        res = run([near, far])
        self.assertEqual(res['same_star_epoch_match'], [])
        self.assertEqual(res['neighbour_epoch_match'], ["ctoi:TIC1001:1001.01:1.00':single transit"])


if __name__ == '__main__':
    unittest.main()
