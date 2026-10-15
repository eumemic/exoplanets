"""TRICERATOPS target setup and single runs, shared by fpp.py (one signal) and fpp_pool.py (many, in a process pool).
Runs in .venv-trice.

setup_target() builds the target once: the TIC and Gaia field around the star, the FFI cutouts (served from local files
cut from the S3 cubes), TIC artifacts and duplicates dropped, a 3x3-pixel aperture on the target in each sector, the
depth each star would need, and (optionally) no nearby-star scenarios beyond a separation. The result can be pickled
(save_state / load_state) so that later runs on the same star skip all of this. run_once() is one calc_probs call.
"""
import contextlib
import glob
import math
import os
import pickle
import re
import types

import numpy as np

_CUT_DIR = [None]


def use_local_cutouts():
    """TRICERATOPS reads each sector's FFI cutout through lightkurve.search_tesscut(...).download_all(); serve the
    pre-cut file from _CUT_DIR instead (TESScut serves ~0.2 MB/s)."""
    import lightkurve
    from astropy.io import fits

    def _local_tesscut(target=None, sector=None):
        f = sorted(glob.glob(os.path.join(_CUT_DIR[0], f"tess-s{int(sector):04d}-*.fits")))
        return types.SimpleNamespace(download_all=lambda cutout_size=None: [types.SimpleNamespace(hdu=fits.open(f[0]))])
    lightkurve.search_tesscut = _local_tesscut


def use_vizier_gaia():
    """Stands in for astroquery.gaia.Gaia in TRICERATOPS's field-star query: the same Gaia DR3 cone search, served by
    VizieR (CDS), which answers concurrent queries in seconds (the ESA archive queued them at ~4 per minute)."""
    import astropy.units as u
    import astroquery.gaia
    from astropy.coordinates import SkyCoord
    from astroquery.vizier import Vizier

    class _VizierGaia:
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


def use_molusc_reader():
    """What TRICERATOPS reads the MOLUSC file into: it indexes columns, filters rows with a boolean mask and writes into
    the mass-ratio array, which pandas 3 (copy-on-write) returns read-only; these copies are writable."""
    import pandas as pd
    import triceratops.marginal_likelihoods as ml

    class _Columns:
        def __init__(self, cols):
            self.cols = cols

        def __getitem__(self, key):
            if isinstance(key, str):
                return types.SimpleNamespace(values=self.cols[key].copy())
            return _Columns({k: v[np.asarray(key)] for k, v in self.cols.items()})

    def _read_molusc(f, *args, **kw):
        df = pd.read_csv(f, *args, **kw)
        return _Columns({c: df[c].to_numpy(copy=True) for c in df.columns})
    ml.read_csv = _read_molusc            # its only runtime use is the MOLUSC file


def setup_target(tic, sectors, cache_dir, depth_ppm, cutouts=None, nearby_max_arcsec=None, verbose=True):
    """Build the TRICERATOPS target. The Gaia field-star query result is cached in cache_dir and reused."""
    import triceratops.triceratops as tr
    if cutouts:
        _CUT_DIR[0] = os.path.abspath(cutouts)
    sectors = np.array(sorted(int(s) for s in sectors))
    cache_dir = os.path.abspath(cache_dir)
    gaia_csv = os.path.join(cache_dir, f"{tic}_gaia_background.csv")
    target = None
    for attempt in range(4):
        try:
            # TRICERATOPS writes the Gaia query result to the working directory
            with contextlib.chdir(cache_dir):
                target = tr.target(ID=tic, sectors=sectors, trilegal_fname=gaia_csv if os.path.exists(gaia_csv) else None)
            if len(target.pix_coords) == len(sectors):
                break
        except Exception as ex:
            print("retrying target setup:", ex)
    assert target is not None and len(target.pix_coords) == len(sectors), "TESScut downloads incomplete"
    if isinstance(target.trilegal_fname, str):
        target.trilegal_fname = os.path.join(cache_dir, target.trilegal_fname)
    # TIC entries flagged ARTIFACT (spurious 2MASS sources) or DUPLICATE are not stars and should be ignored (Paegert et al.
    # 2021); SPLIT entries are real. Drop them, with their pixel positions (TRICERATOPS's remove_star keeps the positions,
    # which misaligns them), before the aperture fluxes are computed.
    phantom = np.array(target.stars["disposition"].isin(["ARTIFACT", "DUPLICATE"]), dtype=bool)   # writable copy
    phantom[0] = False
    if phantom.any():
        if verbose:
            print("dropped TIC artifacts/duplicates:", ", ".join(target.stars["ID"][phantom].astype(str)))
        target.stars = target.stars[~phantom].reset_index(drop=True)
        target.pix_coords = [pc[~phantom] for pc in target.pix_coords]
    aps = []
    for i, s in enumerate(sectors):
        c = np.round(target.pix_coords[i][0]).astype(int)
        aps.append(np.array([[c[0] + dx, c[1] + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)]))
    target.calc_depths(tdepth=depth_ppm * 1e-6, all_ap_pixels=aps)
    if nearby_max_arcsec:
        # Sources this far out are ruled out by the difference-image centroid (signals from TOIs 21-63"
        # from our targets gave offsets > 15" in 98-100% of cases); TRICERATOPS evaluates three scenarios
        # for every neighbour that could produce the depth, which dominates its run time in crowded fields.
        far = target.stars["sep (arcsec)"] > nearby_max_arcsec
        if verbose:
            print(f"{int((far & (target.stars['tdepth'] > 0)).sum())} capable neighbours beyond {nearby_max_arcsec}\" dropped")
        target.stars.loc[far, "tdepth"] = 0.0
    if verbose:
        print(target.stars[["ID", "Tmag", "sep (arcsec)", "fluxratio", "tdepth"]].head(8).to_string())
    return target


# The state files are written by setup_target() on the same machine that reads them back; they are a cache of our
# own objects, never data from elsewhere, which is what makes pickle acceptable here.
def save_state(target, path):
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        pickle.dump(target, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)


def load_state(path):
    with open(path, "rb") as fh:
        return pickle.load(fh)


def fold_exptime(d):
    """Model exposure of a fold [days]: written by export_fold.py --single-cadence; folds of every sector binned to
    5 minutes (the earlier method) carry none and were modelled with 10 minutes."""
    return float(d["exptime"]) if "exptime" in d.files else 10 / 1440


def auto_nsamples(exptime):
    """Sub-exposures per point: one per 2 minutes of exposure (1 for 2-minute data, 2 for 200 s, 5 for 10 minutes,
    15 for 30 minutes). TRICERATOPS's default is 20 for any exposure."""
    return max(1, math.ceil(exptime * 1440 / 2 - 1e-9))


def n_scenarios(target):
    """Scenarios calc_probs evaluates: 12 for the target and its companions, 3 per neighbour that could cause the dip."""
    return 12 + 3 * int((target.stars["tdepth"].values[1:] > 0).sum())


def run_once(target, d, N=200000, exptime=None, nsamples=None, molusc_file=None, drop=(), cc=None, cc_filt="TESS"):
    """One calc_probs on the fold d (an npz with time [days from mid-transit], flux, flux_err, P). parallel=True
    evaluates all draws in one vectorised PyTransit call; it needs a scalar flux_err_0."""
    exptime = fold_exptime(d) if exptime is None else exptime
    nsamples = auto_nsamples(exptime) if nsamples is None else nsamples
    target.calc_probs(time=d["time"], flux_0=d["flux"], flux_err_0=float(np.median(d["flux_err"])), P_orb=float(d["P"]),
                      N=N, parallel=True, verbose=0, exptime=exptime, nsamples=nsamples, contrast_curve_file=cc,
                      filt=cc_filt, molusc_file=molusc_file, drop_scenario=list(drop))
    return float(target.FPP), float(target.NFPP)
