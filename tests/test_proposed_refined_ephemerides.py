"""validation/proposed_refined_ephemerides.csv: the Foundation-0 audit copied with its provenance."""
from pathlib import Path
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
F0_COLS = ['tic', 'upstream_tier', 'P_orig_d', 'P_ref_d', 'T0_ref_BJD', 'dP_sec', 'n_sec_avail', 'n_epochs_fit',
           'rms0_min', 'rms_lin_min', 'dBIC_lin', 'dBIC_quad', 'dBIC_ttv', 'ttv_amp_min', 'ttv_sup_orb',
           'snr_stale', 'snr_refined', 'class']


class ProposedEphemeridesTest(unittest.TestCase):
    def setUp(self):
        self.d = pd.read_csv(ROOT / 'validation' / 'proposed_refined_ephemerides.csv').set_index('tic', drop=False)

    def test_shape_and_columns(self):
        self.assertEqual(len(self.d), 10)
        self.assertEqual(list(self.d.columns), F0_COLS + ['source_repo', 'source_sha', 'source_file', 'method'])
        self.assertTrue(self.d['tic'].is_unique)

    def test_provenance(self):
        self.assertEqual(set(self.d['source_repo']), {'Foundation-0/exoplanets-frontier'})
        self.assertEqual(set(self.d['source_sha']), {'412043e048048f8c0123de25c548cb0be70ad960'})
        self.assertEqual(set(self.d['source_file']), {'results/ttv_ephemeris_audit.csv'})
        self.assertTrue(all('ttv_track.py' in m and '240' in m for m in self.d['method']))

    def test_highlighted_rows(self):
        want = {70557792: (7.0488122, 2458391.802734, -1.45, 9.46, 10.22, 'LINEAR_DRIFT_RESCUED'),
                166848769: (7.6574415, 2458410.96363, 44.109, 6.29, 13.49, 'LINEAR_DRIFT_RESCUED'),
                332644900: (1.3290094, 2458439.630816, -5.239, 2.67, 5.39, 'DYNAMICAL_TTV_CANDIDATE'),
                321011164: (22.5548367, 2458396.483749, -2032.5, 7.07, 10.24, 'LINEAR_DRIFT_RESCUED'),
                7780510: (15.392019, 2458404.936883, 6096.9, 0.84, 9.13, 'LINEAR_DRIFT_RESCUED'),
                115241103: (1.864247, 2458354.61, 0.0, 4.15, 4.15, 'INSUFFICIENT_EPOCHS')}
        for tic, row in want.items():
            r = self.d.loc[tic]
            self.assertEqual((r['P_ref_d'], r['T0_ref_BJD'], r['dP_sec'], r['snr_stale'], r['snr_refined'],
                              r['class']), row, tic)
        self.assertEqual(self.d.loc[70557792, 'dBIC_ttv'], 4.4)
        self.assertEqual(self.d.loc[332644900, 'dBIC_ttv'], 18.7)


if __name__ == '__main__':
    unittest.main()
