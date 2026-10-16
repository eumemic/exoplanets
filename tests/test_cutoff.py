"""Early cutoff of TRICERATOPS results: fpp_core.setup_digest (the hash of what the runs read from a target setup), and
ticfield.py (the galaxies and galaxy cores near a star that host no scenario)."""
import math
import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import fpp_core as fc  # noqa: E402
import ticfield as tf  # noqa: E402


def target(pop_path, tdepth=(0.0, 0.002), plx=(2.5, math.nan)):
    stars = pd.DataFrame(dict(ID=[5, 9], Tmag=[10.0, 14.0], plx=list(plx), disposition=[None, "DUPLICATE"],
                              fluxratio=[0.99, 0.01], tdepth=list(tdepth)))
    return types.SimpleNamespace(mission="TESS", stars=stars, trilegal_fname=pop_path, pix_coords=[np.zeros((2, 2))])


class TestDigest(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        (d / "a").mkdir()
        (d / "b").mkdir()
        for x in ("a", "b"):
            (d / x / "pop.csv").write_text("Gmag,Teff\n15.0,5000\n")
        self.a, self.b = str(d / "a" / "pop.csv"), str(d / "b" / "pop.csv")

    def test_same_setup_anywhere(self):
        self.assertEqual(fc.setup_digest(target(self.a)), fc.setup_digest(target(self.b)))

    def test_what_the_runs_read_counts(self):
        base = fc.setup_digest(target(self.a))
        self.assertNotEqual(base, fc.setup_digest(target(self.a, tdepth=(0.0, 0.0))))      # a neighbour's depth
        t = target(self.a)
        t.stars = t.stars.iloc[::-1].reset_index(drop=True)                               # the order (the target first)
        self.assertNotEqual(base, fc.setup_digest(t))
        Path(self.b).write_text("Gmag,Teff\n15.0,5001\n")                                  # the population
        self.assertNotEqual(base, fc.setup_digest(target(self.b)))
        t = target(self.a)
        t.pix_coords = [np.ones((2, 2))]                                                  # not read by the runs
        self.assertEqual(base, fc.setup_digest(t))


class TestNoScenarios(unittest.TestCase):
    def test_light_stays_scenarios_go(self):
        with pd.option_context("mode.copy_on_write", True):           # as in .venv-trice (pandas 3)
            t = target("unused", tdepth=(0.001, 0.002))
            t.stars = pd.concat([t.stars, t.stars.iloc[[1]].assign(ID=7, tdepth=0.003)], ignore_index=True)
            rows = fc.no_scenarios(t.stars, [5, 7])                   # the target itself is never dropped
            self.assertEqual(list(rows), [False, False, True])
            self.assertEqual(list(t.stars.tdepth), [0.001, 0.002, 0.0])
            self.assertEqual(list(t.stars.fluxratio), [0.99, 0.01, 0.01])


class TestTicField(unittest.TestCase):
    def field(self):
        return pd.DataFrame([
            dict(ID=5, ra=10.0, dec=0.0, Tmag=10.0, objType="STAR", plx=2.0, sep_arcsec=0.0),
            dict(ID=7, ra=10.003, dec=0.0, Tmag=15.0, objType="EXTENDED", plx=np.nan, sep_arcsec=10.8),
            dict(ID=8, ra=10.0031, dec=0.0, Tmag=16.0, objType="STAR", plx=np.nan, sep_arcsec=11.2),     # its core
            dict(ID=11, ra=10.0029, dec=0.0001, Tmag=15.5, objType="STAR", plx=1.0, sep_arcsec=10.5),    # a star in front
            dict(ID=12, ra=10.02, dec=0.0, Tmag=16.0, objType="EXTENDED", plx=np.nan, sep_arcsec=72.0),
        ])

    def test_galaxies_and_cores(self):
        rows = tf.classify(self.field(), 5)
        self.assertEqual(sorted((r["id"], r["kind"]) for r in rows), [(7, "galaxy"), (8, "core"), (12, "galaxy")])

    def test_files(self):
        d = Path(tempfile.mkdtemp())
        fields, non = tf.build({5: self.field()}, "2026-10-16")
        f, n = d / "f.csv", d / "n.csv"
        tf.write(fields, non, f, n)
        self.assertEqual(tf.not_hosts(n, 5), [7, 8])                                      # within 31": no scenarios
        self.assertEqual(tf.by_star(n), {5: [7, 8, 12]})                                  # within 2': not a source
        cat, earlier = d / "allsky.csv", d / "earlier.csv"
        cat.write_text("TIC,P_d,tier,cs_neighbour\n5,3.0,B,12\n6,2.0,B,\n")
        earlier.write_text("TIC,P_d,tier,cs_neighbour\n")
        self.assertEqual(tf.galaxy_neighbours(n, [cat]), ["TIC 5 P 3.0 (B): TIC 12"])
        self.assertEqual(tf.problems(f, cat, earlier), [6])                               # star 6 not checked


if __name__ == "__main__":
    unittest.main()
