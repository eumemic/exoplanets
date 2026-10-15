"""pipeline/fpp_check.py: the checks that catch TRICERATOPS results which look like answers but are not."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "pipeline" / "fpp_check.py"
GOOD = [[1, "TP", 0.9], [1, "EB", 0.05], [1, "BEB", 0.01], [2, "NEB", 0.04]]


class FppCheckTests(unittest.TestCase):
    def run_check(self, probs, n_runs=10, time=None):
        d = Path(tempfile.mkdtemp())
        (d / "folds").mkdir()
        with open(d / "runs.jsonl", "w") as fh:
            for k in range(n_runs):
                fh.write(json.dumps(dict(key="tic1_P3.0000", mode="d", k=k, probs=probs)) + "\n")
        (d / "tic1_P3.0000_fpp.json").write_text(json.dumps(dict(FPP_mean=0.1)))
        t = np.arange(-0.05, 0.05, 2 / 1440) + 1e-4 if time is None else time
        np.savez(d / "folds" / "tic1_P3.0000.npz", time=t, flux=np.ones_like(t), flux_err=np.ones_like(t) * 1e-3,
                 cadence_s=np.int64(120))
        (d / "list.csv").write_text("key,duration_h\ntic1_P3.0000,2.0\n")
        return subprocess.run([sys.executable, str(SCRIPT), str(d), "--list", str(d / "list.csv")],
                              capture_output=True, text=True)

    def test_clean_result_passes(self):
        r = self.run_check(GOOD)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_blended_scenarios_fail(self):
        r = self.run_check([p for p in GOOD if p[1] != "BEB"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("tic1_P3.0000", r.stdout.split("no blended-star scenario in any run:")[1].splitlines()[0])

    def test_degenerate_runs_fail(self):
        r = self.run_check([[0, "", 1 / 18]] * 18)
        self.assertEqual(r.returncode, 1)
        self.assertIn("tic1_P3.0000", r.stdout.split("degenerate")[1].splitlines()[0])

    def test_too_few_runs_fail(self):
        self.assertEqual(self.run_check(GOOD, n_runs=9).returncode, 1)

    def test_unbinned_fold_fails(self):
        t = np.sort(np.random.default_rng(0).uniform(-0.05, 0.05, 400))
        self.assertEqual(self.run_check(GOOD, time=t).returncode, 1)


if __name__ == "__main__":
    unittest.main()
