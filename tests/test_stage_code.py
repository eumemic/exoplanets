"""pipeline/stage_code.py: the code column of a stored result and the stages whose code has changed since, and
tri_plan.py's use of it."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import stage_code as sc  # noqa: E402
import tri_plan as tp  # noqa: E402

REQS = {"fold": dict(code="f1", env="e1"), "tri_setup": dict(code="s1", env="e2"), "tri": dict(code="t1", env="e2")}
NOW = {k: sc.short(r["code"], r["env"]) for k, r in REQS.items()}


class TestStageCode(unittest.TestCase):
    def test_column(self):
        col = sc.of_requests(REQS)
        self.assertEqual(col.split()[0], f"fold={NOW['fold']}")
        self.assertEqual(sc.changed(col, NOW), [])
        self.assertEqual(sc.changed(col, dict(NOW, tri=sc.short("t2", "e2"))), ["tri"])
        self.assertEqual(sc.changed(col, dict(NOW, fold=sc.short("f1", "e9"))), ["fold"])     # packages count too

    def test_legacy(self):
        self.assertEqual(sc.of_requests(dict(REQS, fold=dict(legacy=["code"]))), "")
        self.assertEqual(sc.of_requests(dict(REQS, molusc=None)), "")
        self.assertEqual(sc.changed("", NOW), [])                    # a legacy result is not out of date by code

    def test_current_has_every_kind(self):
        self.assertEqual(sorted(sc.current()), sorted(sc.KINDS))

    def test_tri_plan(self):
        it = dict(tic="1", period="3.5", t0="1.0", duration_h="2.0", depth_ppm="500", drop="", _others=[])
        used = dict(period="3.5", t0_btjd="1.0", duration_h="2.0", depth_ppm="500", masks="", drop="", legacy="",
                    code=sc.of_requests(REQS))
        tol = dict(period_d=2e-6, phase_min=0.5, duration_h=0.005, depth_ppm=0.5)
        self.assertEqual(tp.status(it, used, tol, 0.002, code_now=NOW), ("current", ""))
        st, why = tp.status(it, used, tol, 0.002, code_now=dict(NOW, tri_setup="x"))
        self.assertEqual(st, "pending")
        self.assertIn("tri_setup", why)


if __name__ == "__main__":
    unittest.main()
