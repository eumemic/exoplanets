"""Collect per-candidate evidence into candidates/TIC<id>_P<period>/ for publication:
vetting plot + metrics, transit fit, TRICERATOPS FPP (TESS-only), PRF centroids, and
capable neighbours. Also copies the validation outputs into validation/.

Usage: python package_candidates.py              (first-release table, results/candidates.csv)
       python package_candidates.py LIST.csv     (later candidates; see package_list)
"""
import glob
import json
import re
import shutil
import warnings

import pandas as pd

from common import RESULTS, ROOT
from neighbors import capable_neighbours

warnings.filterwarnings("ignore")
OUT = ROOT / "candidates"


def main():
    c = pd.read_csv(RESULTS / "candidates.csv")
    vetted = pd.read_csv(RESULTS / "vetted.csv", usecols=["tic", "rank", "period"])
    for r in c.itertuples():
        d = OUT / f"TIC{r.TIC}_P{r.P_d:.3f}"
        d.mkdir(parents=True, exist_ok=True)
        v = vetted[(vetted.tic == r.TIC) & ((vetted.period / r.P_d - 1).abs() < 1e-3)].iloc[0]
        rank = int(v["rank"])
        shutil.copy(RESULTS / "vet" / f"tic{r.TIC}_{rank}.png", d / "vetting.png")
        shutil.copy(RESULTS / "vet" / f"tic{r.TIC}_{rank}.json", d / "vetting.json")
        for f in glob.glob(str(RESULTS / f"fit_tic{r.TIC}_P*.json")):
            if abs(json.load(open(f))["P"][1] / r.P_d - 1) < 1e-3:
                shutil.copy(f, d / "transit_fit.json")
        for f in glob.glob(str(RESULTS / "fpp" / f"tic{r.TIC}_P*_fpp.json")):
            if f"{r.P_d:.2f}"[:4] in f:
                shutil.copy(f, d / "triceratops_fpp.json")
        log = RESULTS / "pixels" / f"tic{r.TIC}.log"
        lines = [ln for ln in open(log)] if log.exists() else []
        cen = [ln.strip() for ln in lines if re.match(r"^S\d+:", ln)]
        if cen:
            (d / "centroids.txt").write_text(
                "transit-diffImage PRF fit of the FFI difference image, offset from the TIC position\n"
                + "\n".join(cen) + "\n")
        star, nb = capable_neighbours(r.TIC, r.depth_ppm)
        cap = nb[nb["capable"]][["ID", "sep_arcsec", "Tmag", "dT", "max_ecl_needed"]]
        cap.to_csv(d / "capable_neighbours.csv", index=False)
        print(d.name, "files:", sorted(p.name for p in d.iterdir()))
    val = ROOT / "validation"
    val.mkdir(exist_ok=True)
    for tic, rank in ((4206066, 1), (4206066, 2), (150428135, 1), (150428135, 2), (307210830, 1),
                      (307210830, 2), (307210830, 3)):
        for ext in ("png", "json"):
            src = RESULTS / "vet_controls" / f"tic{tic}_{rank}.{ext}"
            if src.exists():
                shutil.copy(src, val / f"control_tic{tic}_{rank}.{ext}")
    shutil.copy(RESULTS / "inject_snr10.csv", val / "injection_recovery_snr10.csv")


def package_list(list_csv):
    """Candidates from a list (tic, rank, vet_dir, followup_dir, ...; paths relative to the repo
    root): vetting plot and metrics, transit fit, TRICERATOPS result and follow-up record."""
    todo = pd.read_csv(list_csv)
    for r in todo.itertuples():
        v = json.load(open(ROOT / r.vet_dir / f"tic{r.tic}_{r.rank}.json"))
        P = v["period"]
        d = OUT / f"TIC{r.tic}_P{P:.3f}"
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / r.vet_dir / f"tic{r.tic}_{r.rank}.png", d / "vetting.png")
        shutil.copy(ROOT / r.vet_dir / f"tic{r.tic}_{r.rank}.json", d / "vetting.json")
        shutil.copy(ROOT / r.followup_dir / f"tic{r.tic}_{r.rank}.json", d / "followup.json")
        fit_dir = ROOT / r.fit_dir if isinstance(getattr(r, "fit_dir", None), str) else RESULTS
        for f in glob.glob(str(fit_dir / f"fit_tic{r.tic}_P*.json")):
            if abs(json.load(open(f))["P"][1] / P - 1) < 1e-3:
                shutil.copy(f, d / "transit_fit.json")
        for f in glob.glob(str(RESULTS / "fpp" / f"tic{r.tic}_P*_fpp.json")):
            if abs(float(f.split("_P")[1].split("_")[0]) - P) < 0.006:  # file names round P to 0.01 d
                shutil.copy(f, d / "triceratops_fpp.json")
        print(d.name, "files:", sorted(p.name for p in d.iterdir()))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        package_list(sys.argv[1])
    else:
        main()
