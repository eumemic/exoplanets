"""TRICERATOPS false-positive probability (run with .venv-trice).

Usage: python fpp.py TIC FOLD.npz DEPTH_PPM [--runs N] [--draws N]
Uses a 3x3-pixel aperture centred on the target in each sector. The FPP is a Monte Carlo
estimate that scatters by tens of percent between runs (TIC 61816225: 0.012-0.065 over 14
runs), so several runs are averaged and their spread is reported.
The Gaia field-star query is the slow part of the setup (~4 min); its result is cached next to
the fold file and reused.
"""
import argparse
import contextlib
import json
import os

import numpy as np
import triceratops.triceratops as tr

ap = argparse.ArgumentParser()
ap.add_argument("tic", type=int)
ap.add_argument("fold")
ap.add_argument("depth_ppm", type=float)
ap.add_argument("--runs", type=int, default=10)
ap.add_argument("--draws", type=int, default=200000)
ap.add_argument("--sectors", help="comma-separated subset used for the field geometry")
ap.add_argument("--cc", help="contrast curve CSV (sep_arcsec,dmag) for unresolved-companion limits")
ap.add_argument("--cc-filt", default="TESS")
ap.add_argument("--tag", default="")
ap.add_argument("--cutouts", help="directory of FFI cutouts tess-sSSSS-*.fits (from s3cut.py) to use instead of TESScut")
ap.add_argument("--gaia-vizier", action="store_true", help="query the Gaia DR3 field stars at VizieR instead of the ESA archive")
ap.add_argument("--nearby-max-arcsec", type=float,
                help="evaluate nearby-star scenarios only for neighbours within this separation (centroid-excluded beyond)")
a = ap.parse_args()
if a.cutouts:
    import glob
    import types

    import lightkurve
    from astropy.io import fits

    cut_dir = os.path.abspath(a.cutouts)      # target setup runs inside the fold's directory

    def _local_tesscut(target=None, sector=None):
        """TRICERATOPS reads each sector's FFI cutout through lightkurve.search_tesscut(...).download_all();
        serve the pre-cut file instead (TESScut serves ~0.2 MB/s)."""
        f = sorted(glob.glob(os.path.join(cut_dir, f"tess-s{int(sector):04d}-*.fits")))
        return types.SimpleNamespace(download_all=lambda cutout_size=None: [types.SimpleNamespace(hdu=fits.open(f[0]))])
    lightkurve.search_tesscut = _local_tesscut
if a.gaia_vizier:
    import re
    import types

    import astropy.units as u
    import astroquery.gaia
    from astropy.coordinates import SkyCoord
    from astroquery.vizier import Vizier

    class _VizierGaia:
        """Stands in for astroquery.gaia.Gaia in TRICERATOPS's field-star query: the same Gaia DR3 cone
        search, served by VizieR (CDS), which answers concurrent queries in seconds (the ESA archive
        queued them at ~4 per minute)."""
        ROW_LIMIT = -1
        COLS = {"Gmag": "phot_g_mean_mag", "BPmag": "phot_bp_mean_mag", "RPmag": "phot_rp_mean_mag",
                "Plx": "parallax", "RPlx": "parallax_over_error"}

        def launch_job(self, adql, verbose=False):
            ra, dec, r, glim = (float(x) for x in re.search(
                r"CIRCLE\('ICRS', ([^,]+), ([^,]+), ([^)]+)\)\) AND phot_g_mean_mag < (\S+)", adql).groups())
            res = Vizier(columns=list(self.COLS), column_filters={"Gmag": f"<{glim}"}, row_limit=-1).query_region(
                SkyCoord(ra, dec, unit="deg"), radius=r * u.deg, catalog="I/355/gaiadr3")
            t = res[0][list(self.COLS)] if len(res) else None
            if t is not None:
                for c in self.COLS:
                    t[c] = np.ma.filled(np.ma.asarray(t[c], dtype=float), np.nan)
                t.rename_columns(list(self.COLS), list(self.COLS.values()))
            return types.SimpleNamespace(get_results=lambda: t if t is not None else [])

        launch_job_async = launch_job

    astroquery.gaia.Gaia = _VizierGaia()
d = np.load(a.fold)
sectors = np.array(sorted(set(int(s) for s in d["sectors"])))
if a.sectors:
    sectors = np.array([int(s) for s in a.sectors.split(",")])
cache_dir = os.path.dirname(os.path.abspath(a.fold))
gaia_csv = os.path.join(cache_dir, f"{a.tic}_gaia_background.csv")
target = None
for attempt in range(4):
    try:
        # TRICERATOPS writes the Gaia query result to the working directory
        with contextlib.chdir(cache_dir):
            target = tr.target(ID=a.tic, sectors=sectors,
                               trilegal_fname=gaia_csv if os.path.exists(gaia_csv) else None)
        if len(target.pix_coords) == len(sectors):
            break
    except Exception as ex:
        print("retrying target setup:", ex)
assert target is not None and len(target.pix_coords) == len(sectors), "TESScut downloads incomplete"
if isinstance(target.trilegal_fname, str):
    target.trilegal_fname = os.path.join(cache_dir, target.trilegal_fname)
aps = []
for i, s in enumerate(sectors):
    c = np.round(target.pix_coords[i][0]).astype(int)
    aps.append(np.array([[c[0] + dx, c[1] + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)]))
target.calc_depths(tdepth=a.depth_ppm * 1e-6, all_ap_pixels=aps)
if a.nearby_max_arcsec:
    # Sources this far out are ruled out by the difference-image centroid (signals from TOIs 21-63"
    # from our targets gave offsets > 15" in 98-100% of cases); TRICERATOPS evaluates three scenarios
    # for every neighbour that could produce the depth, which dominates its run time in crowded fields.
    far = target.stars["sep (arcsec)"] > a.nearby_max_arcsec
    print(f"{int((far & (target.stars['tdepth'] > 0)).sum())} capable neighbours beyond {a.nearby_max_arcsec}\" dropped")
    target.stars.loc[far, "tdepth"] = 0.0
print(target.stars[["ID", "Tmag", "sep (arcsec)", "fluxratio", "tdepth"]].head(8).to_string())
fpps, nfpps = [], []
for r in range(a.runs):
    # parallel=True evaluates all draws in one vectorised PyTransit call; it needs a scalar
    # flux_err_0 (an array raises a broadcasting error)
    target.calc_probs(time=d["time"], flux_0=d["flux"], flux_err_0=float(np.median(d["flux_err"])),
                      P_orb=float(d["P"]), N=a.draws, parallel=True, verbose=0, exptime=10 / 1440,
                      contrast_curve_file=a.cc, filt=a.cc_filt)
    fpps.append(target.FPP); nfpps.append(target.NFPP)
    print(f"run {r}: FPP={target.FPP:.4f} NFPP={target.NFPP:.2e}", flush=True)
print(target.probs.sort_values("prob", ascending=False).head(6).to_string())
res = dict(tic=a.tic, FPP_mean=float(np.mean(fpps)), FPP_sd=float(np.std(fpps, ddof=1)) if len(fpps) > 1 else None,
           FPP_sem=float(np.std(fpps, ddof=1) / np.sqrt(len(fpps))) if len(fpps) > 1 else None,
           FPP=fpps, NFPP_max=float(np.max(nfpps)), runs=a.runs, draws=a.draws)
print(json.dumps(res))
with open(a.fold.replace(".npz", f"_fpp{a.tag}.json"), "w") as fh:
    json.dump(res, fh)
