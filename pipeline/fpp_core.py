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
import random
import re
import time
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


def setup_target(tic, sectors, cache_dir, depth_ppm, cutouts=None, nearby_max_arcsec=None, not_hosts=(), verbose=True):
    """Build the TRICERATOPS target. The Gaia field-star query result is cached in cache_dir and reused. not_hosts: TIC
    entries near the star that cannot host a signal although their light is real (galaxies and the point sources the TIC
    lists at a galaxy's position without a parallax: ticfield.py); they keep their light but host no scenario."""
    import triceratops.triceratops as tr
    if cutouts:
        _CUT_DIR[0] = os.path.abspath(cutouts)
    sectors = np.array(sorted(int(s) for s in sectors))
    cache_dir = os.path.abspath(cache_dir)
    gaia_csv = os.path.join(cache_dir, f"{tic}_gaia_background.csv")
    target = None
    for attempt in range(7):
        try:
            # TRICERATOPS writes the Gaia query result to the working directory
            with contextlib.chdir(cache_dir):
                target = tr.target(ID=tic, sectors=sectors, trilegal_fname=gaia_csv if os.path.exists(gaia_csv) else None)
            if len(target.pix_coords) == len(sectors):
                break
        except Exception as ex:
            # MAST answers many simultaneous TIC queries with 429 (too many requests): wait longer each time
            print("retrying target setup:", ex)
            time.sleep(min(300, 15 * 2 ** attempt) * (0.5 + random.random()))
    assert target is not None and len(target.pix_coords) == len(sectors), "TESScut downloads incomplete"
    if isinstance(target.trilegal_fname, str):
        target.trilegal_fname = os.path.join(cache_dir, target.trilegal_fname)
    # Without a field-star population calc_probs skips the DTP, DEB, DEBx2P, BTP, BEB and BEBx2P scenarios without a word,
    # which lowers the FPP; on 15 October 2026 the query failed for 353 targets set up together on one machine. Query
    # again, and fail rather than return a target without one.
    from triceratops.funcs import query_gaia_background
    for wait in (0, 30, 90, 180):
        if has_population(target):
            break
        time.sleep(wait)
        with contextlib.chdir(cache_dir):
            fname = query_gaia_background(float(target.stars["ra"].values[0]), float(target.stars["dec"].values[0]), tic,
                                          verbose=0)
        target.trilegal_fname = os.path.join(cache_dir, fname) if isinstance(fname, str) else None
    if not has_population(target):
        raise RuntimeError("no field-star population: the Gaia background query failed")
    # TRICERATOPS takes the first star of its TIC query as the target. Where the TIC has a duplicate entry at the star's
    # position the query can list that first; put the star itself first (at the same position, so the separations,
    # position angles and field-star population TRICERATOPS took from the first star do not change).
    ids = target.stars["ID"].astype(int).to_numpy()
    if ids[0] != int(tic):
        i = np.flatnonzero(ids == int(tic))
        if not len(i) or float(target.stars["sep (arcsec)"].iloc[i[0]]) > 1.0:
            raise RuntimeError(f"TRICERATOPS's first star is TIC {ids[0]}; TIC {tic} is not at its position")
        order = np.r_[i[0], np.delete(np.arange(len(ids)), i[0])]
        target.stars = target.stars.iloc[order].reset_index(drop=True)
        target.pix_coords = [pc[order] for pc in target.pix_coords]
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
    if len(not_hosts):
        nh = no_scenarios(target.stars, not_hosts)
        if verbose and nh.any():
            print("no scenarios on galaxies and their cores:", ", ".join(target.stars["ID"][nh].astype(str)))
    if verbose:
        print(target.stars[["ID", "Tmag", "sep (arcsec)", "fluxratio", "tdepth"]].head(8).to_string())
    return target


def no_scenarios(stars, ids):
    """Give the stars with these TIC IDs, other than the target (the first), no scenario: their transit depth goes to 0,
    their flux ratio (their light in the aperture) stays. Returns which rows."""
    nh = np.array(stars["ID"].astype(int).isin([int(x) for x in ids]), dtype=bool)     # writable copy
    nh[0] = False
    stars.loc[nh, "tdepth"] = 0.0
    return nh


def setup_digest(target):
    """Hash of what calc_probs reads from a target setup: the mission, the stars (in order, every column: the TIC values,
    separations, flux ratios and transit depths) and the content of the field-star population file. File paths and the
    pickle's layout are left out, so a setup made again from the same inputs, on any machine, has the same digest; a
    stored result is reused for a new setup with its setup's digest (cloud_worker.py, tri_store.py)."""
    import hashlib
    import json
    st = target.stars.reset_index(drop=True)
    cols = sorted(map(str, st.columns))

    def val(v):
        if hasattr(v, "item"):
            v = v.item()
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        if isinstance(v, float) and math.isinf(v):
            return repr(v)
        return v if isinstance(v, (int, float, str, bool)) else str(v)
    stars = [[val(v) for v in st[c].tolist()] for c in cols]
    f = getattr(target, "trilegal_fname", None)
    pop = None
    if isinstance(f, str) and os.path.isfile(f):
        with open(f, "rb") as fh:
            pop = hashlib.sha256(fh.read()).hexdigest()
    blob = json.dumps(dict(mission=str(getattr(target, "mission", "")), cols=cols, stars=stars, population=pop),
                      sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode()).hexdigest()


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


def has_population(target):
    """Whether the target has a complete field-star population file, which calc_probs's blended-star scenarios need.
    A write cut off (e.g. by a full disk) leaves a short last row, with empty trailing columns."""
    f = getattr(target, "trilegal_fname", None)
    if not (isinstance(f, str) and os.path.isfile(f) and os.path.getsize(f) > 0):
        return False
    import pandas as pd
    try:
        d = pd.read_csv(f)
    except Exception:
        return False
    return len(d) > 0 and not d.isna().any().any()


def n_scenarios(target):
    """Scenarios calc_probs evaluates: 12 for the target and its companions, 3 per neighbour that could cause the dip."""
    return 12 + 3 * int((target.stars["tdepth"].values[1:] > 0).sum())


def run_once(target, d, N=200000, exptime=None, nsamples=None, molusc_file=None, drop=(), cc=None, cc_filt="TESS"):
    """One calc_probs on the fold d (an npz with time [days from mid-transit], flux, flux_err, P). parallel=True
    evaluates all draws in one vectorised PyTransit call; it needs a scalar flux_err_0."""
    if not has_population(target):
        raise RuntimeError("the target has no field-star population, so calc_probs would skip six scenarios")
    # Without the target's mass, radius, Teff or parallax calc_probs prints a warning, stops before computing anything and
    # leaves every scenario equally likely (FPP 5/6 with one neighbour), which looks like a result.
    s = target.stars.iloc[0]
    missing = [c for c in ("mass", "rad", "Teff", "plx") if not np.isfinite(float(s[c]))]
    if missing:
        raise RuntimeError(f"TRICERATOPS cannot evaluate the target without its {', '.join(missing)}")
    exptime = fold_exptime(d) if exptime is None else exptime
    nsamples = auto_nsamples(exptime) if nsamples is None else nsamples
    target.calc_probs(time=d["time"], flux_0=d["flux"], flux_err_0=float(np.median(d["flux_err"])), P_orb=float(d["P"]),
                      N=N, parallel=True, verbose=0, exptime=exptime, nsamples=nsamples, contrast_curve_file=cc,
                      filt=cc_filt, molusc_file=molusc_file, drop_scenario=list(drop))
    return float(target.FPP), float(target.NFPP)
