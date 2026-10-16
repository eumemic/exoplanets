"""pipeline/catalog.py, triceratops_table.py and catalog_checks.py: the tier rules branch by branch, the TRICERATOPS
columns, overrides, the checks a TRICERATOPS result must pass before the catalog uses it, and the freshness checks."""
import csv
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import catalog as cat  # noqa: E402
import catalog_checks as cc  # noqa: E402
import triceratops_table as tt  # noqa: E402
from dag.params import load  # noqa: E402

P = load(Path(__file__).resolve().parents[1] / "pipeline" / "params.toml")
NAN = math.nan


def row(**kw):
    r = dict(TIC="1", P_d="5.0", b="0.3", ruwe="1.0", MES="15", Rp_Re="2.0", set="SNR>=9", fa_score="0.9",
             fa_score_h="0.9", papers_with_period="", zenodo_with_period="", reported_as="", binary_at_target="",
             eb_nearby_same_period="", cs_p_target="0.5", cs_p_neighbour="", BF="")
    r.update(kw)
    return r


def tri(fpp=0.01, nfpp=0.001, g=True):
    v = {k: NAN for k in cat.TRI}
    if fpp is not None:
        v.update(FPP=fpp, NFPP=nfpp, FPP_c=fpp, NFPP_c=nfpp)
        if g:
            v.update(FPP_g=fpp, NFPP_g=nfpp, FPP_gc=fpp, NFPP_gc=nfpp)
    return v


class TierRuleTests(unittest.TestCase):
    def t(self, r, v=None):
        return cat.tier_allsky(r, tri() if v is None else v, P)

    def test_reported_and_binaries_come_first(self):
        self.assertEqual(self.t(row(papers_with_period="2024AJ....167..203M", binary_at_target="vsx")), ("reported", ""))
        self.assertEqual(self.t(row(reported_as="CTOI 1.01")), ("reported", ""))
        self.assertEqual(self.t(row(binary_at_target="vsx:EA"), tri(0.9, 0.5)), ("likely EB", ""))
        self.assertEqual(self.t(row(Rp_Re="21", b="0.95", set='neighbour<15"')), ("likely EB", ""))

    def test_neighbour_set(self):
        nb = dict(set='neighbour<15"')
        self.assertEqual(self.t(row(**nb), tri(0.6, 0.01)), ("likely nearby FP", ""))
        self.assertEqual(self.t(row(**nb, b="0.95"), tri(0.6, 0.01)), ("likely nearby FP", ""))   # release 3's order
        self.assertEqual(self.t(row(**nb), tri(None)), ("C", cat.NO_RESULT))                    # none is not evidence
        self.assertEqual(self.t(row(**nb), tri(None) | {"status": "degenerate"}), ("C", cat.NO_PARALLAX))
        self.assertEqual(self.t(row(**nb, ruwe="2"), tri(None)), ("C", "RUWE > 1.4"))
        self.assertEqual(self.t(row(**nb, b="0.95")), ("C", "grazing"))
        self.assertEqual(self.t(row(**nb, MES="9.5")), ("C", "MES < 10"))
        self.assertEqual(self.t(row(**nb)), ("N", ""))

    def test_low_band(self):
        low = dict(set="SNR 7.5-9", MES="8.5")
        self.assertEqual(self.t(row(**low)), ("L1", ""))                                         # before MES < 9
        self.assertEqual(self.t(row(**{**low, "fa_score_h": "0.5"})), ("likely false alarm", ""))
        self.assertEqual(self.t(row(**{**low, "fa_score_h": "0.5", "MES": "9.2", "ruwe": "2"})), ("C", "RUWE > 1.4"))
        self.assertEqual(self.t(row(**{**low, "fa_score_h": "0.5", "MES": "9.2"})), ("L", ""))
        self.assertEqual(self.t(row(**{**low, "MES": "9.2"}), tri(0.6, 0.01)), ("L", ""))

    def test_snr9_order_of_reasons(self):
        self.assertEqual(self.t(row(b="0.95", ruwe="2", MES="9")), ("C", "grazing"))
        self.assertEqual(self.t(row(ruwe="2", MES="9"), tri(0.9, 0.5)), ("C", "RUWE > 1.4"))
        self.assertEqual(self.t(row(MES="9"), tri(0.9, 0.5)), ("C", "MES < 10"))
        self.assertEqual(self.t(row(), tri(0.9, 0.05)), ("C", cat.TRI_FAIL))
        self.assertEqual(self.t(row(), tri(0.3, 0.2)), ("C", cat.TRI_FAIL))
        self.assertEqual(self.t(row(), tri(None)), ("C", cat.NO_RESULT))
        # centroids that reject the target and fit a neighbour make any row a likely nearby FP
        self.assertEqual(self.t(row(b="0.95", cs_p_target="0.0001", cs_p_neighbour="0.3")), ("likely nearby FP", ""))
        self.assertEqual(self.t(row(set="SNR 7.5-9", MES="8", cs_p_target="0.0001", cs_p_neighbour="0.3")),
                         ("likely nearby FP", ""))
        self.assertEqual(self.t(row(binary_at_target="vsx", cs_p_target="0.0001", cs_p_neighbour="0.3")), ("likely EB", ""))
        self.assertEqual(self.t(row()), ("counted", ""))

    def test_the_bar_prefers_gaia_limited_values(self):
        v = tri(0.01, 0.001)
        v.update(FPP_c=0.7, NFPP_c=0.3)                      # the default priors fail, the Gaia-limited pass
        self.assertEqual(self.t(row(), v), ("counted", ""))
        v = tri(0.7, 0.3, g=False)
        self.assertEqual(self.t(row(), v), ("C", cat.TRI_FAIL))

    def test_centroids(self):
        self.assertIsNone(cat.centroid_out(row(cs_p_target="0.002"), P))
        self.assertEqual(cat.centroid_out(row(cs_p_target="0.0005", cs_p_neighbour="0.4"), P), ("likely nearby FP", ""))
        self.assertEqual(cat.centroid_out(row(cs_p_target="0.0005", cs_p_neighbour="0.001"), P), ("C", cat.CENTROID))
        self.assertEqual(cat.centroid_flag(row(cs_p_target="0.0005"), P), "centroid offset in all sectors, p < 0.001")
        self.assertEqual(cat.centroid_flag(row(cs_p_target="0.005"), P), "centroid offset in all sectors, p < 0.01")
        self.assertEqual(cat.centroid_flag(row(cs_p_target=""), P), "")

    def test_earlier_searches_keep_their_label_unless_a_reason_applies(self):
        e = dict(base_tier="A", base_c_reason="", cs_p_target="")
        self.assertEqual(cat.tier_earlier(row(**e), tri(), P), ("A", ""))
        self.assertEqual(cat.tier_earlier(row(**e), tri(None), P), ("A", ""))
        self.assertEqual(cat.tier_earlier(row(**e), tri(0.6, 0.01), P), ("C", cat.TRI_FAIL))
        self.assertEqual(cat.tier_earlier(row(**e, b="0.95"), tri(0.6, 0.01), P), ("C", "grazing"))

    def test_formatting(self):
        self.assertEqual([cat.fmt(x, 3) for x in (0.0, 0.12345, 0.0004321, NAN, -1e-9)], ["0.0", "0.123", "0.00043", "", "0.0"])
        self.assertEqual(cat.fmt(0.012345, 4), "0.0123")


def write_csv(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


class BuildTests(unittest.TestCase):
    def test_tiers_overrides_and_columns(self):
        d = Path(tempfile.mkdtemp())
        base = {c: "" for c in cat.ALLSKY if c not in cat.DERIVED_ALLSKY}
        rows = []
        for tic, per, extra in (("1", "2.0", {}), ("1", "5.0", {}), ("2", "3.0", {}), ("3", "4.0", {"papers_with_period": "2021X"}),
                                ("4", "6.0", {})):
            r = dict(base, TIC=tic, P_d=per, b="0.3", ruwe="1.0", MES="15", Rp_Re="2", set="SNR>=9", fa_score="0.7",
                     fa_score_h="0.9", cs_p_target="0.5")
            r.update(extra)
            rows.append(r)
        write_csv(d / "m_allsky.csv", rows)
        erow = {c: "" for c in cat.EARLIER if c not in cat.DERIVED_EARLIER}
        write_csv(d / "m_earlier.csv", [dict(erow, TIC="9", P_d="7.0", b="0.2", ruwe="1.1", base_tier="B", base_c_reason="")])
        res = [dict(table="candidates_allsky", TIC=t, P_d=p, key=f"tic{t}_P{p}", FPP_mean="0.01", NFPP_mean="0.001",
                    NFPP_max="0.002", FPP_g_mean="", NFPP_g_mean="", NFPP_g_max="", degenerate="")
               for t, p in (("1", "2.0"), ("1", "5.0"), ("2", "3.0"), ("4", "6.0"))]
        res.append(dict(table="tiers_earlier_candidates", TIC="9", P_d="7.0", key="tic9_P7.0", FPP_mean="0.7",
                        NFPP_mean="0.01", NFPP_max="0.02", FPP_g_mean="", NFPP_g_mean="", NFPP_g_max="", degenerate=""))
        write_csv(d / "tri.csv", res)
        write_csv(d / "over.csv", [dict(table="candidates_allsky", TIC="4", P_d="6.0", field="tier", value="likely false alarm",
                                        reason="test", source="", date="")])
        a, e = cat.build(d / "m_allsky.csv", d / "m_earlier.csv", d / "tri.csv", d / "over.csv", d / "a.csv", d / "e.csv", P)
        tiers = {(r["TIC"], r["P_d"]): (r["tier"], r["c_reason"]) for r in a}
        self.assertEqual(tiers[("1", "2.0")], ("A", ""))         # two counted on the star
        self.assertEqual(tiers[("2", "3.0")], ("B", ""))
        self.assertEqual(tiers[("3", "4.0")], ("reported", ""))
        self.assertEqual(tiers[("4", "6.0")], ("likely false alarm", ""))
        self.assertEqual([r["reported_as"] for r in a if r["TIC"] == "3"], ["2021X"])
        self.assertEqual([r["fa_flag"] for r in a if r["TIC"] == "2"], ["low false-alarm-classifier score"])
        self.assertEqual((e[0]["tier"], e[0]["c_reason"], e[0]["FPP"]), ("C", cat.TRI_FAIL, "0.7"))
        with open(d / "a.csv") as fh:
            self.assertEqual(next(csv.reader(fh)), cat.ALLSKY)


class TriceratopsTableTests(unittest.TestCase):
    def batch(self, root, name, key="tic5_P3.0000", runs=10, probs=(("TP", 0.9), ("BEB", 0.01)), survivors=100000,
              cadence=120, period="3.000000", spacing_min=2.0):
        d = root / name
        (d / "folds").mkdir(parents=True)
        with open(d / "runs.jsonl", "w") as fh:
            for mode in ("d", "m"):
                for k in range(runs):
                    fh.write(json.dumps(dict(key=key, mode=mode, k=k, probs=[[1, s, v] for s, v in probs])) + "\n")
        (d / f"{key}_fpp.json").write_text(json.dumps(dict(
            tic=5, FPP_mean=0.1, NFPP_mean=0.01, NFPP_max=0.02, runs=runs, exptime_min=2.0, n_points=100, sectors="1,2",
            n_scenarios=15, FPP_m=[0.1] * runs, FPP_m_mean=0.05, NFPP_m_mean=0.01, NFPP_m_max=0.02, molusc_survivors=survivors)))
        t = np.arange(-0.2, 0.2, spacing_min / 1440) + 1e-4
        np.savez(d / "folds" / f"{key}.npz", time=t, flux=np.ones_like(t), cadence_s=np.int64(cadence))
        (d / "list.csv").write_text(f"key,tic,period,t0,duration_h,depth_ppm,masks,drop\n{key},5,{period},1500.0,2.0,500,,\n")
        return name

    def run_build(self, root, batches, rows=(("candidates_allsky", "5", "3.0"),)):
        with open(root / "batches.csv", "w") as fh:
            fh.write("batch,order,finished_utc,purpose\n" + "".join(f"{b},{i},,\n" for i, b in enumerate(batches)))
        return tt.build(root / "batches.csv", root, list(rows), root / "out.csv")

    def test_a_later_batch_replaces_an_earlier_one(self):
        root = Path(tempfile.mkdtemp())
        rows = self.run_build(root, [self.batch(root, "b1"), self.batch(root, "b2")])
        self.assertEqual([r["batch"] for r in rows], ["b2"])

    def test_results_failing_a_check_are_refused(self):
        for kw, msg in ((dict(runs=9), "runs"), (dict(probs=(("TP", 0.9), ("EB", 0.1))), "blended"),
                        (dict(survivors=8000), "MOLUSC"), (dict(cadence=1800, spacing_min=0.5), "phase bin")):
            root = Path(tempfile.mkdtemp())
            with self.assertRaises(ValueError) as cm:
                self.run_build(root, [self.batch(root, "b1", **kw)])
            self.assertIn(msg, str(cm.exception))

    def test_a_superseded_result_failing_a_check_is_not_used_or_checked(self):
        root = Path(tempfile.mkdtemp())
        old = self.batch(root, "b1", key="tic5_P3.0010", survivors=8000, period="3.001000")
        rows = self.run_build(root, [old, self.batch(root, "b2")])
        self.assertEqual([r["key"] for r in rows], ["tic5_P3.0000"])

    def test_degenerate_results_are_kept_without_values(self):
        root = Path(tempfile.mkdtemp())
        rows = self.run_build(root, [self.batch(root, "b1", probs=(("", 1 / 18), ("", 1 / 18)))])
        self.assertEqual((rows[0]["degenerate"], rows[0]["FPP_mean"]), ("yes", ""))


class FreshnessTests(unittest.TestCase):
    def test_changed_duration_and_unmasked_sibling_are_reported(self):
        d = Path(tempfile.mkdtemp())
        m = {c: "" for c in cat.ALLSKY if c not in cat.DERIVED_ALLSKY}
        write_csv(d / "m.csv", [dict(m, TIC="5", P_d="3.0", T0_BJD="2458500.0", T14_h="2.61", depth_ppm="500"),
                                dict(m, TIC="5", P_d="7.0", T0_BJD="2458501.0", T14_h="3.0", depth_ppm="400")])
        write_csv(d / "eph.csv", [dict(TIC="0", period_d="1", T0_BJD_TDB="0", duration_h="1", depth_ppm="1")])
        p = dict(table="candidates_allsky", TIC="5", P_d="3.0", batch="b1", period="3.0", t0_btjd="1500.0",
                 duration_h="2.49", depth_ppm="500", masks="")
        write_csv(d / "p.csv", [p])
        tol = dict(period_d=2e-6, phase_min=0.5, duration_h=0.005, depth_ppm=0.5)
        probs = cc.triceratops_inputs_current(d / "p.csv", d / "m.csv", d / "eph.csv", tol, 0.002)
        self.assertEqual(len(probs), 1)
        self.assertIn("duration 2.49 -> 2.61 h", probs[0])
        self.assertIn("7.00000 d signal was not masked", probs[0])
        write_csv(d / "p.csv", [dict(p, duration_h="2.61", masks="7.0,1501.0,3.0")])
        self.assertEqual(cc.triceratops_inputs_current(d / "p.csv", d / "m.csv", d / "eph.csv", tol, 0.002), [])


if __name__ == "__main__":
    unittest.main()
