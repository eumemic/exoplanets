"""Bound-companion limits from Gaia DR3 with MOLUSC (Wood et al. 2021), for TRICERATOPS's molusc_file.

For each host star MOLUSC simulates N companions (Raghavan et al. 2010 period and mass-ratio distributions)
and rejects those that Gaia would have resolved (Gaia contrast curve) or whose astrometric perturbation would
exceed the star's measured RUWE. TRICERATOPS then draws its bound companions from the survivors instead of its
default companion prior. MOLUSC simulates a companion for every draw, so this assumes the star has one.

MOLUSC (github.com/woodml/MOLUSC, v.20220321) is run unchanged except that (1) its two ESA Gaia archive
queries per star are answered from one bulk Gaia DR3 query by source_id (columns as in gaiadr3.gaia_source,
the same astrometry as the EDR3 table it queries), and (2) scipy.interpolate.interp2d, removed in SciPy 1.14,
is replaced by an equivalent bilinear interpolator with nearest-value extrapolation. Its command-line mode also
needs Application.star_jitter, which only the GUI sets (-1 means no stellar-jitter test).

Usage: python molusc_batch.py STARS.parquet --gaia GAIA.csv --molusc DIR --out DIR [--n 200000] [--procs 32]
STARS needs ID, GAIA_DR3 (or GAIA) and mass; GAIA.csv is the bulk query (source_id, ra, dec, parallax, ...);
DIR is MOLUSC's code directory. Writes OUT/tic<TIC>_kept.csv.gz (survivors), OUT/tic<TIC>_molusc.json
(counts: generated, survivors, used = survivors with periastron > 10 au, which TRICERATOPS keeps) and a log.
MOLUSC's stellar models (BHAC15) at its default age of 5 Gyr stop at 1.1 Msun, and its Gaia contrast test then
exits without an error code; stars of 1.1-1.4 Msun use the oldest model age that includes them (4, 3 or 2 Gyr),
and above 1.4 Msun only the RUWE test is applied. If the star fails MOLUSC's RUWE preconditions (G, BP-RP or a
5-parameter solution), only the Gaia contrast test is applied. Each log says which tests ran.
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

ENV = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
# oldest BHAC15 age (Gyr) whose grid reaches each mass (Msun)
AGES = [(1.1, 5.0), (1.2, 4.0), (1.3, 3.0), (1.4, 2.0)]
GAIA_COLS = ["source_id", "ra", "dec", "parallax", "parallax_error", "phot_g_mean_mag", "bp_rp", "ruwe",
             "astrometric_params_solved", "astrometric_n_good_obs_al", "astrometric_chi2_al"]


class _Point(np.ndarray):
    """A 1-element interpolation result that MOLUSC both concatenates and passes to float(), as interp2d's
    results allowed before NumPy 2."""
    def __float__(self):
        return float(np.asarray(self).reshape(-1)[0])


def interp2d(x, y, z, kind="linear"):
    """Stand-in for scipy.interpolate.interp2d(x, y, z) on a rectangular grid (z has shape len(y) x len(x)),
    evaluated at scalar points as MOLUSC does: bilinear inside the grid, nearest grid value outside."""
    from scipy.interpolate import RegularGridInterpolator
    x, y = np.asarray(x, float), np.asarray(y, float)
    z = np.asarray(z, float).reshape(len(y), len(x))
    jx, jy = np.argsort(x), np.argsort(y)
    f = RegularGridInterpolator((y[jy], x[jx]), z[np.ix_(jy, jx)])

    def ev(xq, yq):
        xq = np.clip(np.atleast_1d(np.asarray(xq, float)), x.min(), x.max())
        yq = np.clip(np.atleast_1d(np.asarray(yq, float)), y.min(), y.max())
        return f(np.column_stack([yq, xq])).view(_Point)
    return ev


def one(tic, row, mass, n, out, molusc_dir, ruwe, gaia, age):
    """Runs MOLUSC for one star in this process (called through a subprocess per star)."""
    import types

    import astropy.units as u
    import scipy.interpolate
    from astropy.coordinates import Angle
    from astropy.table import Table

    scipy.interpolate.interp2d = interp2d
    try:
        import tkinter.messagebox  # noqa: F401  (MOLUSC's module defines its GUI class at import)
    except ImportError:                        # headless Python without Tk: the command-line path never uses it
        tk = types.ModuleType("tkinter")
        tk.Frame, tk.messagebox = object, types.ModuleType("tkinter.messagebox")
        sys.modules.update({"tkinter": tk, "tkinter.messagebox": tk.messagebox})
    os.chdir(molusc_dir)                       # MOLUSC reads its model tables from the working directory
    sys.path.insert(0, molusc_dir)
    import BinaryStarGUI as M

    t = Table({c: [row[c]] for c in GAIA_COLS})
    t["dist"] = [0.0]

    class OneStarGaia:
        """Answers MOLUSC's cone searches around the target with the target's own Gaia DR3 row."""
        def launch_job(self, query, *args, **kw):
            return types.SimpleNamespace(get_results=lambda: t.copy())

    M.Gaia = OneStarGaia()
    M.Application.star_jitter = -1             # set only by the GUI; the command-line checks read it
    ra = Angle(row["ra"], u.deg).to_string(unit=u.hourangle, sep="hms", precision=3)
    dec = Angle(row["dec"], u.deg).to_string(unit=u.deg, sep="dms", precision=2, alwayssign=True)
    sys.argv = ["BinaryStarGUI.py", "--age", str(age)] + (["--gaia"] if gaia else []) + (["--ruwe"] if ruwe else []) + \
               [os.path.join(out, f"tic{tic}"), ra, "--", dec, str(n), f"{mass:.3f}"]
    M.Application(sys.argv).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stars")
    ap.add_argument("--gaia", required=True)
    ap.add_argument("--molusc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=200000)
    ap.add_argument("--procs", type=int, default=32)
    ap.add_argument("--one", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--no-ruwe", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-gaia", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--age", type=float, default=5.0, help=argparse.SUPPRESS)
    a = ap.parse_args()
    out, molusc_dir = os.path.abspath(a.out), os.path.abspath(a.molusc)
    os.makedirs(out, exist_ok=True)
    stars = pd.read_parquet(a.stars).drop_duplicates("ID").set_index("ID")
    gaia = pd.read_csv(a.gaia).set_index("source_id", drop=False)
    gcol = "GAIA_DR3" if "GAIA_DR3" in stars else "GAIA"      # the TIC lists Gaia DR2 ids
    if a.one:
        return one(a.one, gaia.loc[int(stars[gcol][a.one])], float(stars["mass"][a.one]), a.n, out, molusc_dir,
                   not a.no_ruwe, not a.no_gaia, a.age)

    def run(tic):
        kept = os.path.join(out, f"tic{tic}_kept.csv")
        if os.path.exists(kept + ".gz"):
            return tic, "done"
        gid = int(stars[gcol][tic])           # column access keeps the 19-digit id exact (a row would upcast it)
        if not (gid in gaia.index and stars["mass"][tic] > 0):
            return tic, "no Gaia row or mass"
        g = gaia.loc[gid]
        ruwe_ok = 3.6 <= g["phot_g_mean_mag"] <= 21 and -1 <= g["bp_rp"] <= 10 and g["astrometric_params_solved"] == 31
        mass = float(stars["mass"][tic])
        age = next((t for m_max, t in AGES if mass <= m_max), None)
        gaia_ok = age is not None
        if not (ruwe_ok or gaia_ok):
            return tic, "no applicable test"
        cmd = [sys.executable, os.path.abspath(__file__), os.path.abspath(a.stars), "--gaia", os.path.abspath(a.gaia),
               "--molusc", molusc_dir, "--out", out, "--n", str(a.n), "--one", str(tic), "--age", str(age or 5.0)] + \
              ([] if ruwe_ok else ["--no-ruwe"]) + ([] if gaia_ok else ["--no-gaia"])
        with open(os.path.join(out, f"tic{tic}.log"), "w") as log:
            print(f"tests: RUWE {'yes' if ruwe_ok else 'no (G, BP-RP or solution type)'}, Gaia contrast "
                  f"{'yes' if gaia_ok else 'no (mass above the BHAC15 grid)'}; age {age or 5.0} Gyr", file=log, flush=True)
            rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=ENV).returncode
        if rc != 0 or not os.path.exists(kept):
            # a run that stopped part way (on 15 October 2026 a full disk cut 49 files to ~6,000 of ~140,000 survivors)
            # leaves a partial file, which must not pass as the survivors
            if os.path.exists(kept):
                os.remove(kept)
            return tic, "failed"
        k = pd.read_csv(kept)
        # what TRICERATOPS uses: survivors with periastron beyond 10 au
        used = int((k["semi-major axis(AU)"] * (1 - k["eccentricity"]) > 10).sum())
        pd.Series(dict(tic=tic, generated=a.n, survivors=len(k), used=used, ruwe_test=bool(ruwe_ok), gaia_test=bool(gaia_ok),
                       age_gyr=age or 5.0, ruwe=float(g["ruwe"]))).to_json(os.path.join(out, f"tic{tic}_molusc.json"))
        # pandas (and so TRICERATOPS) reads it compressed; written under another name and renamed, so that the "done"
        # check above never meets a partial file
        k.to_csv(kept + ".gz.tmp", index=False, compression="gzip")
        os.replace(kept + ".gz.tmp", kept + ".gz")
        os.remove(kept)
        return tic, "ok"

    tics = [t for t in stars.index]
    with ThreadPoolExecutor(a.procs) as ex:
        res = list(ex.map(run, tics))
    status = pd.Series(dict(res)).value_counts()
    print(f"MOLUSC: {len(tics)} stars; " + ", ".join(f"{k} {v}" for k, v in status.items()))


if __name__ == "__main__":
    main()
