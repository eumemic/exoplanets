"""Planned-sector filter of predict.py and the committed ephemerides, with no network or data downloads."""
from pathlib import Path
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# predict.py is also run directly from pipeline/.
sys.path.insert(0, str(ROOT / 'pipeline'))
import predict

# tess-point numbers its special pointings from 1751 upwards; regular sectors stay far below.
FIRST_SPECIAL_POINTING = 1751


class PlannedSectors(unittest.TestCase):
    def test_special_pointing_is_rejected(self):
        # tess-point appends 1751, the 3I/ATLAS pointing, to the sectors of every star
        self.assertEqual(predict.planned_sectors([119, 125, 1751], 109, 134), [119, 125])
        self.assertEqual(predict.planned_sectors([1751], 109, 134), [])
        self.assertEqual(predict.planned_sectors([1752, 2000], 109, 134), [])

    def test_regular_sectors_are_kept(self):
        self.assertEqual(predict.planned_sectors([134, 109, 120, 120], 109, 134), [109, 120, 134])
        self.assertEqual(predict.planned_sectors([], 109, 134), [])

    def test_sectors_before_the_first_are_dropped(self):
        self.assertEqual(predict.planned_sectors([5, 108, 109], 109, 134), [109])


class CommittedEphemerides(unittest.TestCase):
    def test_no_special_pointing_in_planned_sectors(self):
        eph = pd.read_csv(ROOT / 'candidates' / 'ephemerides.csv', dtype={'tess_sectors_planned': str},
                          keep_default_na=False)
        planned = {int(s) for v in eph['tess_sectors_planned'] for s in v.split(',') if s}
        self.assertTrue(planned)
        self.assertLess(max(planned), FIRST_SPECIAL_POINTING)


if __name__ == '__main__':
    unittest.main()
