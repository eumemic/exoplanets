"""QLP Sectors 94-104: the first and last part of each orbit's cadences are masked on load."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from pipeline import common

START = common.QLP_ORBIT_STARTS[0]          # Sector 94, orbit 195


def sector(prov='QLP', sec=94, t=None):
    t = START + np.array([0.0, 0.5, 0.999, 1.0, 1.5, 6.0]) if t is None else t
    n = len(t)
    return dict(sector=sec, provenance=prov, time=t, flux=np.linspace(0.99, 1.01, n), flux_err=np.full(n, 1e-3),
                flux_err_source='DET_FLUX_ERR', cx=np.zeros(n), cy=np.ones(n), bkg=np.arange(n, dtype=float),
                exptime=200.0)


class OrbitStartMaskTests(unittest.TestCase):
    def test_drops_first_day_of_each_orbit_in_every_array(self):
        s = sector()
        out = common.mask_qlp_orbit_edges(s, 1.0, 0.0)
        keep = np.array([False, False, False, True, True, True])
        for k in ('time', 'flux', 'flux_err', 'cx', 'cy', 'bkg'):
            np.testing.assert_array_equal(out[k], s[k][keep])
        for k in ('sector', 'provenance', 'flux_err_source', 'exptime'):
            self.assertEqual(out[k], s[k])

    def test_counts_from_the_first_cadence_when_flags_delay_the_data(self):
        out = common.mask_qlp_orbit_edges(sector(t=START + np.array([0.7, 1.2, 1.69, 1.71, 3.0])), 1.0, 0.0)
        np.testing.assert_allclose(out['time'], START + np.array([1.71, 3.0]))
        # a cadence just before the listed start (barycentric offsets) opens the orbit; earlier ones do not
        out = common.mask_qlp_orbit_edges(sector(t=START + np.array([-0.03, -0.01, 0.5, 2.0])), 1.0, 0.0)
        np.testing.assert_allclose(out['time'], START + np.array([-0.03, 2.0]))

    def test_drops_last_part_of_each_orbit(self):
        s1 = common.QLP_ORBIT_STARTS[1]
        t = np.r_[START + np.array([0.0, 2.0, 5.4, 5.6, 6.0]), s1 + np.array([0.0, 3.0, 6.0])]
        out = common.mask_qlp_orbit_edges(sector(t=t), 0.0, 0.5)
        np.testing.assert_allclose(out['time'], np.r_[START + np.array([0.0, 2.0, 5.4]), s1 + np.array([0.0, 3.0])])

    def test_other_products_sectors_and_zero_length_untouched(self):
        for s, days, end_days in ((sector(prov='SPOC'), 1.0, 0.5), (sector(prov='TESS-SPOC'), 1.0, 0.5),
                                  (sector(sec=93), 1.0, 0.5), (sector(sec=105, t=START + 350 + np.arange(5.0)), 1.0, 0.5),
                                  (sector(), 0.0, 0.0)):
            out = common.mask_qlp_orbit_edges(s, days, end_days)
            np.testing.assert_array_equal(out['time'], s['time'])

    def test_every_listed_start_is_masked(self):
        t = np.concatenate([np.array(common.QLP_ORBIT_STARTS) + d for d in (0.0, 0.9, 1.1)])
        out = common.mask_qlp_orbit_edges(sector(sec=100, t=np.sort(t)), 1.0, 0.0)
        np.testing.assert_allclose(np.sort(out['time']), np.array(common.QLP_ORBIT_STARTS) + 1.1)

    def test_load_star_applies_mask_unless_disabled(self):
        s = sector()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'tic1.npz'
            np.savez_compressed(p, sectors=np.array([94]), s94_prov=np.array('QLP'), s94_time=s['time'],
                                s94_flux=s['flux'].astype(np.float32), s94_flux_err=s['flux_err'].astype(np.float32),
                                s94_flux_err_source=np.array('DET_FLUX_ERR'), s94_cx=s['cx'], s94_cy=s['cy'],
                                s94_bkg=s['bkg'], s94_exptime=np.array(200.0))
            with patch.object(common, 'tic_path', return_value=p):
                self.assertEqual(len(common.load_star(1, 1.0, 0.5)[0]['time']), 2)
                self.assertEqual(len(common.load_star(1, 0.0, 0.5)[0]['time']), 5)
                self.assertEqual(len(common.load_star(1, 0.0, 0.0)[0]['time']), 6)


if __name__ == '__main__':
    unittest.main()
