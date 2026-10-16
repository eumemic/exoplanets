"""pipeline/vet_store.py (vetting and pixel follow-up in the store, vetting.csv, what is out of date) and the catalog's
neighbour-set rule for galaxies (catalog.neighbour_set_into)."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import catalog as cat  # noqa: E402
import lcindex as lc  # noqa: E402
import store  # noqa: E402
import vet_store as vs  # noqa: E402


class TestVetStore(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        s = store.Store(self.d / "store")
        row = dict(TIC="5", P_d="3.0")
        (self.d / "vetting.json").write_text(json.dumps(dict(tic=5, rank=1, period=3.0000001, t0=1500.0, duration_h=2.0,
                                                             depth_ppm=500.0, snr=12.3, sector_chi2_dof=1.1,
                                                             leo_fails=["x"], per_sector=[])))
        (self.d / "followup.json").write_text(json.dumps(dict(tic=5, rank=1, offset_qual=3.2,
                                                              capable_within_15arcsec=[[7, 10.8, 5.0], [11, 10.5, 5.5]])))
        vs._put_legacy(s, "vet", "candidates_allsky", row, {"vetting.json": str(self.d / "vetting.json")}, str(self.d))
        vs._put_legacy(s, "pixel", "candidates_allsky", row, {"followup.json": str(self.d / "followup.json")}, str(self.d))
        self.out = self.d / "vetting.csv"
        vs.table(self.d / "store", [("candidates_allsky", "5", "3.0", "TIC5_P3.000")], {5: [7]}, self.out)

    def rows(self):
        with open(self.out, newline="") as fh:
            return list(csv.DictReader(fh))

    def test_table(self):
        r = self.rows()[0]
        self.assertEqual((r["vet_legacy"], r["search_rank"], r["snr"], r["leo_fails"]), ("yes", "1", "12.3", "1"))
        self.assertEqual((r["image"], r["close_capable"], r["close_stellar"]), ("yes", "7 11", "11"))   # 7 is a galaxy

    def test_stale(self):
        for name, uri in (("searched.csv", "a_v01_llc.fits"), ("lists.csv", "a_v01_llc.fits")):
            pd.DataFrame([dict(tic=5, sector=1, prov="QLP", exptime=1800.0, uri=uri)]).to_csv(self.d / name, index=False)
        (self.d / "code.json").write_text(json.dumps({"vet": "x", "pixel": "y"}))
        args = (self.out, self.d / "searched.csv", self.d / "lists.csv", self.d / "code.json")
        self.assertEqual(vs.stale(*args, {"TIC5_P3.000"}), [])                          # legacy, light curves as searched
        pd.DataFrame([dict(tic=5, sector=1, prov="QLP", exptime=1800.0, uri="a_v02_llc.fits")]).to_csv(
            self.d / "lists.csv", index=False)                                            # redelivered
        self.assertIn("light curves", vs.stale(*args, {"TIC5_P3.000"})[0][3])
        self.assertEqual(vs.stale(*args, set()), [])                                      # no folder: not checked


class TestNeighbourSet(unittest.TestCase):
    def test_galaxies_only(self):
        nb = cat.NB
        rows = [dict(TIC="5", P_d="3.0", set=nb), dict(TIC="6", P_d="2.0", set=nb), dict(TIC="7", P_d="1.0", set=nb),
                dict(TIC="8", P_d="4.0", set=nb)]
        vet = {("t", "5", "3.0"): dict(image="yes", close_capable="70", close_stellar=""),        # only a galaxy
               ("t", "6", "2.0"): dict(image="yes", close_capable="70 71", close_stellar="71"),   # a star too
               ("t", "7", "1.0"): dict(image="", close_capable="70", close_stellar="")}           # no difference image
        cat.neighbour_set_into(rows, "t", vet)
        self.assertEqual([r["set"] for r in rows], ["SNR>=9", nb, nb, nb])


if __name__ == "__main__":
    unittest.main()
