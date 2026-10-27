"""pipeline/lcindex.py: the light-curve lists new work uses after a MAST snapshot (redelivered products replaced,
withdrawn sectors dropped, new sectors left to a search update), their hashes, and the redo list."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import lcindex as lc  # noqa: E402
import tri_plan as tp  # noqa: E402


def qlp(tic, s, v=1):
    return f"mast:HLSP/qlp/s{s:04d}/hlsp_qlp_tess_ffi_s{s:04d}-{tic:016d}_tess_v{v:02d}_llc.fits"


def spoc(tic, s):
    return f"mast:HLSP/tess-spoc/s{s:04d}/hlsp_tess-spoc_tess_phot_{tic:016d}-s{s:04d}_tess_v1_lc.fits"


SEARCHED = pd.DataFrame([
    dict(tic=1, sector=1, prov="QLP", exptime=1800.0, uri=qlp(1, 1)),
    dict(tic=1, sector=2, prov="QLP", exptime=1800.0, uri=qlp(1, 2)),
    dict(tic=1, sector=3, prov="TESS-SPOC", exptime=1800.0, uri=spoc(1, 3)),
    dict(tic=2, sector=5, prov="QLP", exptime=1800.0, uri=qlp(2, 5)),
    dict(tic=3, sector=7, prov="QLP", exptime=1800.0, uri=qlp(3, 7)),
])
CURRENT = pd.DataFrame([
    dict(tic=1, sector=1, prov="QLP", exptime=1800.0, uri=qlp(1, 1, 2)),        # redelivered as v02
    dict(tic=1, sector=2, prov="TESS-SPOC", exptime=1800.0, uri=spoc(1, 2)),    # QLP withdrew sector 2
    dict(tic=1, sector=3, prov="TESS-SPOC", exptime=1800.0, uri=spoc(1, 3)),
    dict(tic=1, sector=3, prov="QLP", exptime=1800.0, uri=qlp(1, 3)),
    dict(tic=1, sector=4, prov="QLP", exptime=200.0, uri=qlp(1, 4)),            # new
    dict(tic=3, sector=7, prov="QLP", exptime=1800.0, uri=qlp(3, 7)),
]).assign(checked="2026-10-16")


class TestLists(unittest.TestCase):
    def test_snapshot_applied(self):
        m = lc.apply_snapshot(SEARCHED, CURRENT)
        one = m[m.tic == 1].set_index("sector")
        self.assertEqual(sorted(one.index), [1, 3])                     # sector 2 dropped, sector 4 not added
        self.assertEqual(one.loc[1, "uri"], qlp(1, 1, 2))
        self.assertEqual(one.loc[3, "uri"], spoc(1, 3))                 # the source the search used is kept
        self.assertEqual(m[m.tic == 2].uri.tolist(), [qlp(2, 5)])        # not in the snapshot: as searched

    def test_no_snapshot(self):
        self.assertIs(lc.apply_snapshot(SEARCHED, None), SEARCHED)

    def test_hash(self):
        rows = SEARCHED[SEARCHED.tic == 1]
        a = lc.list_hash(rows.to_dict("records"))
        b = lc.list_hash([[r.sector, r.prov, r.exptime, r.uri] for r in rows.itertuples()][::-1])
        c = lc.list_hash([dict(sector=r.sector, uri=r.uri.replace("mast:HLSP", "https://archive")) for r in rows.itertuples()])
        self.assertEqual(a, b)
        self.assertEqual(a, c)                                         # by file name, not where it is kept
        self.assertNotEqual(a, lc.list_hash(lc.apply_snapshot(SEARCHED, CURRENT).query("tic == 1").to_dict("records")))


class TestRedo(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        SEARCHED.to_csv(self.d / "searched.csv", index=False)
        CURRENT.to_csv(self.d / "current.csv", index=False)
        lc.current_lists(self.d / "searched.csv", self.d / "current.csv", self.d / "lists.csv")
        for name, rows in (("allsky.csv", [dict(TIC=1, P_d="3.5", tier="S"), dict(TIC=2, P_d="1.25", tier="LNFP"),
                                            dict(TIC=3, P_d="9.0", tier="C")]),
                           ("earlier.csv", [])):
            pd.DataFrame(rows, columns=["TIC", "P_d", "tier"]).to_csv(self.d / name, index=False)
        now = lc.star_hashes(self.d / "lists.csv")
        pd.DataFrame([dict(table="candidates_allsky", TIC=1, P_d="3.5", lightcurves=""),
                      dict(table="candidates_allsky", TIC=3, P_d="9.0", lightcurves="")]).to_csv(self.d / "fits.csv", index=False)
        pd.DataFrame([dict(table="candidates_allsky", TIC=1, P_d="3.5", lightcurves=now[1]),
                      dict(table="candidates_allsky", TIC=3, P_d="9.0", lightcurves="0" * 16)]).to_csv(self.d / "tri.csv", index=False)

    def redo(self):
        lc.redo(self.d / "allsky.csv", self.d / "earlier.csv", self.d / "searched.csv", self.d / "lists.csv",
                self.d / "current.csv", self.d / "fits.csv", self.d / "tri.csv", self.d / "redo.csv", ["M", "S", "C"])
        return {r["TIC"]: r for r in csv.DictReader(open(self.d / "redo.csv", newline=""))}

    def test_rows(self):
        out = self.redo()
        self.assertEqual(sorted(out), ["1", "3"])                     # star 2 is not in the snapshot
        one = out["1"]
        self.assertEqual((one["redelivered"], one["removed"], one["new"]), ("1", "2", "4"))
        # the legacy fit was made from the searched list; the TRICERATOPS fold already from the list now
        self.assertEqual(one["redo"], "fit, search, vetting, pixel follow-up")
        self.assertEqual((one["folder"], one["checked"]), ("yes", "2026-10-16"))
        # star 3's products are unchanged: its legacy fit is current, its TRICERATOPS fold was made from another list
        self.assertEqual(out["3"]["redo"], "TRICERATOPS")
        self.assertEqual([r["TIC"] for r in lc.stale_fits(self.d / "redo.csv")], ["1"])

    def test_tri_plan_status(self):
        was, now = lc.star_hashes(self.d / "searched.csv"), lc.star_hashes(self.d / "lists.csv")
        it = dict(tic="1", period="3.5", t0="1.0", duration_h="2.0", depth_ppm="500", drop="", _others=[])
        used = dict(period="3.5", t0_btjd="1.0", duration_h="2.0", depth_ppm="500", masks="", drop="", legacy="yes",
                    lightcurves="")
        tol = dict(period_d=2e-6, phase_min=0.5, duration_h=0.005, depth_ppm=0.5)
        st, why = tp.status(it, used, tol, 0.002, (was, now))
        self.assertEqual(st, "pending")
        self.assertIn("light curves", why)
        self.assertEqual(tp.status(it, dict(used, lightcurves=now[1]), tol, 0.002, (was, now))[0], "legacy")
        self.assertEqual(tp.status(it, used, tol, 0.002)[0], "legacy")      # without the lists, as before


if __name__ == "__main__":
    unittest.main()
