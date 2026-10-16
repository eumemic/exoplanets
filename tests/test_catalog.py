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
import centroid_table as ctab  # noqa: E402
import tri_plan as tp  # noqa: E402
import triceratops_table as tt  # noqa: E402
import centroid_store  # noqa: E402
import fit_store  # noqa: E402
import store  # noqa: E402
import tri_store  # noqa: E402
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
        self.assertEqual(self.t(row(b="")), ("C", cat.NO_FIT))                                   # no fit, not counted
        self.assertEqual(self.t(row(b="", set='neighbour<15"')), ("C", cat.NO_FIT))
        self.assertEqual(self.t(row(b="", set='neighbour<15"'), tri(0.7, 0.3)), ("likely nearby FP", ""))
        self.assertEqual(self.t(row(b="", set="SNR 7.5-9", MES="9.5")), ("C", cat.NO_FIT))

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
        tri_store.import_batches(store.Store(root / "store"), root, root / "batches.csv")
        return tt.build(root / "store", list(rows), root / "out.csv")

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

    def test_import_is_idempotent_and_refuses_a_different_result(self):
        root = Path(tempfile.mkdtemp())
        rows = self.run_build(root, [self.batch(root, "b1")])
        self.assertEqual(rows, self.run_build(root, ["b1"]))          # importing again changes nothing
        s = store.Store(root / "store")
        self.assertEqual(len(s.keys("tri")), 1)
        req, res, _ = s.get("tri", rows[0]["store"])
        self.assertIn("lightcurves", req["legacy"])
        with self.assertRaises(ValueError):
            s.put("tri", req, dict(res, seq=99))

    def cloud_item(self, root, runs=10, env="E2"):
        """An item as cloud_worker.py uploads it, and its plan entry."""
        import gzip
        d = root / "item"
        (d / "cuts").mkdir(parents=True)
        src = root / self.batch(root, "src", runs=runs)
        (d / "fold.npz").write_bytes((src / "folds" / "tic5_P3.0000.npz").read_bytes())
        (d / "fpp.json").write_text((src / "tic5_P3.0000_fpp.json").read_text())
        (d / "runs.jsonl").write_text((src / "runs.jsonl").read_text())
        (d / "state.pkl").write_bytes(b"state")
        (d / "population.csv").write_text("pop")
        (d / "cuts" / "tess-s0001.fits").write_bytes(b"cut")
        (d / "molusc.csv.gz").write_bytes(gzip.compress(b"a,b\n1,2\n"))
        (d / "molusc.json").write_text(json.dumps(dict(survivors=100000)))
        (d / "item.json").write_text(json.dumps(dict(commit="abc", sectors="1,2", check={},
                                                    env={"requirements.txt": "E1", "requirements-triceratops.txt": env})))
        it = dict(key="tic5_P3.0000", tic="5", period="3.000000", t0="1500.0", duration_h="2.0", depth_ppm="500", masks="", drop="")
        gaia = {c: 1.0 for c in ("source_id", "ra", "dec", "parallax", "parallax_error", "phot_g_mean_mag", "bp_rp", "ruwe",
                                 "astrometric_params_solved", "astrometric_n_good_obs_al", "astrometric_chi2_al")}
        plan_item = dict(item=it, fold_request=tri_store.fold_request(it, [[1, "SPOC", 120.0, "u"]], "c", "E1"),
                         molusc_request=tri_store.molusc_request(5, gaia, 0.8, "m", "c", "E1"), commit="abc",
                         code={k: "c" for k in tri_store.STAGE_CODE},
                         env=dict(fold="E1", tri_setup="E2", molusc="E1", tri="E2"))
        return d, plan_item

    def test_an_ingested_result_replaces_the_legacy_one_and_a_failing_one_is_kept_aside(self):
        root = Path(tempfile.mkdtemp())
        self.run_build(root, [self.batch(root, "b1")])
        s = store.Store(root / "store")
        d, plan_item = self.cloud_item(root)
        key, problems = tri_store.ingest_item(s, d, plan_item, "bX", 10 ** 9)
        self.assertEqual(problems, [])
        self.assertEqual(len(s.keys("tri_setup")), 1)
        self.assertEqual(len(s.keys("molusc")), 1)
        rows = tt.build(root / "store", [("candidates_allsky", "5", "3.0")], root / "out.csv")
        self.assertEqual((rows[0]["batch"], rows[0]["store"], rows[0]["legacy"]), ("bX", key, ""))
        root2 = Path(tempfile.mkdtemp())                               # packages that differ from the lock
        self.run_build(root2, [self.batch(root2, "b1")])
        d, plan_item = self.cloud_item(root2, env="E9")
        key, problems = tri_store.ingest_item(store.Store(root2 / "store"), d, plan_item, "bX", 10 ** 9)
        self.assertTrue(problems)
        rows = tt.build(root2 / "store", [("candidates_allsky", "5", "3.0")], root2 / "out.csv")
        self.assertEqual(rows[0]["batch"], "b1")

    def test_contrast_curve_runs_are_stored_as_their_own_kind(self):
        root = Path(tempfile.mkdtemp())
        d, plan_item = self.cloud_item(root)
        (d / "cc" / "ccK-x").mkdir(parents=True)
        for f in ("fpp.json", "runs.jsonl"):
            (d / f).rename(d / "cc" / "ccK-x" / f)
        info = json.loads((d / "item.json").read_text())
        (d / "item.json").write_text(json.dumps(dict(info, base=False, cc=["ccK-x"])))
        plan_item["cc"] = [dict(label="ccK-x", file="x.csv", filt="K", content="c1")]
        s = store.Store(root / "store")
        key, problems = tri_store.ingest_item(s, d, plan_item, "bX", 10 ** 9)
        self.assertEqual(problems, [])
        self.assertEqual((len(s.keys("tri")), len(s.keys("tri_cc"))), (0, 1))
        req = s.get("tri_cc", key)[0]
        self.assertEqual((req["cc_label"], req["cc_filt"], req["cc"]), ("ccK-x", "K", "c1"))

    def test_degenerate_results_are_kept_without_values(self):
        root = Path(tempfile.mkdtemp())
        rows = self.run_build(root, [self.batch(root, "b1", probs=(("", 1 / 18), ("", 1 / 18)))])
        self.assertEqual((rows[0]["degenerate"], rows[0]["FPP_mean"]), ("yes", ""))


class FreshnessTests(unittest.TestCase):
    TOL = dict(period_d=2e-6, phase_min=0.5, duration_h=0.005, depth_ppm=0.5)

    def test_changed_duration_unmasked_sibling_and_drops_are_reported(self):
        others = [(7.0, 1501.0, 3.0, "catalog"), (9.0, 1502.0, 2.0, "toi")]
        it = dict(period="3.0", t0="1500.0", duration_h="2.61", depth_ppm="500", drop="", _others=others)
        used = dict(period="3.0", t0_btjd="1500.0", duration_h="2.49", depth_ppm="500", masks="", drop="", legacy="yes")
        st, why = tp.status(it, used, self.TOL, 0.002)
        self.assertEqual(st, "pending")
        self.assertIn("duration 2.49 -> 2.61 h", why)
        self.assertIn("7.00000 d signal was not masked", why)
        self.assertNotIn("9.00000", why)                         # a TOI's mask is not compared
        used = dict(used, duration_h="2.61", masks="7.0,1501.0,3.0")
        self.assertEqual(tp.status(it, used, self.TOL, 0.002), ("legacy", ""))
        self.assertIn("drop", tp.status(it, dict(used, drop="EB,EBx2P"), self.TOL, 0.002)[1])
        self.assertEqual(tp.status(it, None, self.TOL, 0.002), ("pending", "no result"))

    def test_rows_decided_before_the_bar_need_no_result(self):
        r = {c: "" for c in cat.ALLSKY}
        r.update(b="0.3", ruwe="1.0", MES="12", Rp_Re="2", fa_score_h="0.9")
        need = lambda **kw: cat.needs_triceratops(dict(r, **kw), P, "candidates_allsky")
        self.assertTrue(need(set="SNR>=9"))
        self.assertFalse(need(set="SNR>=9", MES="9.5"))
        self.assertFalse(need(set="SNR>=9", b="0.95"))
        self.assertTrue(need(set=cat.NB, b="0.95"))                 # failing the bar makes it a likely nearby FP
        self.assertFalse(need(set=cat.NB, reported_as="TOI-1.01"))
        self.assertFalse(need(set=cat.NB, cs_p_target="0.0001", cs_p_neighbour="0.5"))
        self.assertTrue(need(set="SNR 7.5-9"))
        self.assertFalse(need(set="SNR 7.5-9", fa_score_h="0.5"))
        self.assertFalse(cat.needs_triceratops(dict(b="0.95", ruwe="1"), P, "tiers_earlier_candidates"))


class FitTests(unittest.TestCase):
    FIT = dict(P=[0.9919072863903634, 0.991910889854862, 0.9919143486034292], t0=[1842.6585, 1842.66166, 1842.665],
               k=[0.02, 0.022, 0.023], b=[0.39, 0.5257, 0.63], T14_h=[1.12, 1.1994, 1.27], Rp=[1.49, 1.5644, 1.65])

    def test_columns_are_written_as_the_catalog_writes_them(self):
        v = fit_store.values(self.FIT)
        self.assertEqual(v, dict(P_fit="0.991911", P_err="4e-06", T0_BJD="2458842.66166", T14_h="1.2", Rp_Re="1.56", b="0.53"))
        self.assertEqual(fit_store.problems(self.FIT), [])

    def test_a_fit_that_did_not_converge_is_refused_and_its_row_has_no_fitted_values(self):
        bad = dict(self.FIT, P=[-1.3e22, 1.1156, 5.0e21], t0=[-2e22, 1385.15, 4.8e22])
        self.assertTrue(any("period interval" in x for x in fit_store.problems(bad)))
        d = Path(tempfile.mkdtemp())
        s = store.Store(d / "store")
        for i, fit in enumerate((self.FIT, bad)):
            f = d / f"f{i}.json"
            f.write_text(json.dumps(fit))
            s.put("fit", dict(kind="fit", signal_key=f"tic{5 + i}_P3.0000", table="candidates_allsky", tic=5 + i),
                  dict(seq=0, batch="b", signal=dict(table="candidates_allsky", TIC=str(5 + i), P_d="3.0"), fit=fit,
                       content=str(i)), files={"transit_fit.json": f})
        rows = fit_store.table(d / "store", [("candidates_allsky", "5", "3.0", "TIC5_P3.000"),
                                             ("candidates_allsky", "6", "3.0", "TIC6_P3.000")], d / "fits.csv")
        self.assertEqual([r["check"][:6] for r in rows], ["passed", "failed"])
        out = [dict(TIC="5", P_d="3.0", b="0.9", T0_BJD="", T14_h="", Rp_Re="", P_err=""),
               dict(TIC="6", P_d="3.0", b="0.4", T0_BJD="x", T14_h="x", Rp_Re="x", P_err="x")]
        cat.fits_into(out, "candidates_allsky", {(r["table"], r["TIC"], r["P_d"]): r for r in rows})
        self.assertEqual((out[0]["b"], out[0]["_P_fit"]), ("0.53", "0.991911"))
        self.assertEqual((out[1]["b"], out[1]["T0_BJD"], "_P_fit" in out[1]), ("", "", False))


class CloudWorkerTests(unittest.TestCase):
    def test_lock_pins_are_read_by_name_and_version(self):
        import cloud_worker
        text = "Foo_Bar==3.9.2\n# a comment\nbaz==1.0 ; python_version < '4'\ntransitDiffImage @ git+https://x\n"
        self.assertEqual(cloud_worker.pins(text), {"foo-bar": "3.9.2", "baz": "1.0"})


class CentroidTableTests(unittest.TestCase):
    def test_measurements_become_catalog_columns_and_artifacts_are_not_neighbours(self):
        root = Path(tempfile.mkdtemp())
        d = root / "b1"
        (d / "cs").mkdir(parents=True)
        (d / "list.csv").write_text("set,tier,tic,P_d,period,t0,duration_h,depth_ppm,sectors,MES,source_tic,ra,dec,key\n"
                                    "t10,B,5,3.0,3.0,1500.0,2.0,2000,\"1,2,3\",15,,10.0,20.0,tic5_P3.0000\n")
        secs = [dict(sector=s, east=e, north=n, quality=0.9, offset_arc=1.0) for s, e, n in ((1, 9.5, 0.3), (2, 10.4, -0.2), (3, 10.1, 0.4))]
        stars = [dict(tic=5, east=0.0, north=0.0, sep=0.0, Tmag=10.0), dict(tic=6, east=10.0, north=0.0, sep=10.0, Tmag=12.0),
                 dict(tic=7, east=10.0, north=0.1, sep=10.0, Tmag=11.0)]
        (d / "cs" / "tic5_P3.0000.json").write_text(json.dumps(dict(key="tic5_P3.0000", sectors=secs, stars=stars)))
        (d / "stars.csv").write_text("key,tic,disposition\ntic5_P3.0000,5,\ntic5_P3.0000,6,\ntic5_P3.0000,7,ARTIFACT\n")
        (root / "batches.csv").write_text("batch,order,finished_utc,purpose\nb1,1,,\n")
        centroid_store.import_batches(store.Store(root / "store"), root, root / "batches.csv")
        rows = ctab.build(root / "store", [("candidates_allsky", "5", "3.0")], root / "out.csv")
        r = rows[0]
        self.assertEqual((r["cs_sectors"], r["cs_neighbour"]), (3, 6))            # TIC 7 is an artifact
        self.assertLess(float(r["cs_p_target"]), 0.001)
        self.assertEqual(r["cs_offset_arcsec"], "10.0")


if __name__ == "__main__":
    unittest.main()
