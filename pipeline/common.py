"""Shared paths, product selection and light-curve loading."""
import os as _os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CAT = DATA / "catalogs"
LC_DIR = DATA / "lc"          # one compressed npz per star, all sectors
RESULTS = ROOT / "results"

# Last sector included in SPOC's latest multi-sector search (s0001-s0096).
SPOC_MULTISECTOR_LAST = 96

# Per-sector product preference: lower is better.
PROV_RANK = {"SPOC": 0, "TESS-SPOC": 1, "QLP": 2, "TGLC": 3}

# SPOC / TESS-SPOC quality bits treated as bad: lightkurve's default bitmask
# (17087) plus SPOC's scattered-light exclude (8192).
SPOC_BAD_BITS = 17087 | 8192
# QLP: drop pointing/desat/stray-light/low-precision bits. Bit 29 in the
# TGLC-based releases marks cadences whose scatter is within ~10% of clean
# ones (checked on TIC 4206066, S98), so it is not treated as bad.
QLP_BAD_BITS = (1 | 4 | 8 | 16 | 32 | 128 | 1024 | 2048 | 4096 | (1 << 30))

# First cadence of each TESS orbit in QLP Sectors 94-104 (BTJD), from the ORBITID column of three QLP light
# curves per sector (they agree to within 0.006 d). In these sectors QLP's systematics-corrected flux often dips
# (or rises) for several hours at the start and at the end of an orbit's data; quality flags can move the start
# by most of a day. Detrending leaves part of these ramps, which repeat every orbit and mimic transits at ~13 d
# (or single deep events). load_star drops the first QLP_ORBIT_MASK_DAYS and the last QLP_ORBIT_MASK_END_DAYS of
# each orbit's cadences in these sectors (EXO_QLP_ORBIT_MASK, EXO_QLP_ORBIT_MASK_END; 0 keeps them).
QLP_ORBIT_STARTS = (3856.261, 3868.942, 3882.327, 3894.876, 3907.771, 3920.694, 3933.656, 3947.077, 3960.753,
                    3974.966, 3988.494, 4003.005, 4017.091, 4031.797, 4046.107, 4063.011, 4073.991, 4087.487,
                    4100.675, 4113.747, 4127.018, 4139.728, 4152.027, 4165.434, 4178.582, 4191.985)
QLP_ORBIT_MASK_SECTORS = range(94, 105)
QLP_ORBIT_MASK_DAYS = float(_os.environ.get("EXO_QLP_ORBIT_MASK", "1.0"))
QLP_ORBIT_MASK_END_DAYS = float(_os.environ.get("EXO_QLP_ORBIT_MASK_END", "0.5"))


def tic_path(tic: int) -> Path:
    s = f"{int(tic):016d}"
    return LC_DIR / s[-4:-2] / f"tic{int(tic)}.npz"


S3 = "https://stpubdata.s3.amazonaws.com/"


def s3_url(uri: str):
    """Same product on the STScI AWS open-data mirror (stpubdata), or None. The mirror lags MAST
    for HLSPs (in Oct 2026: QLP to Sector 98, TESS-SPOC to 81, SPOC 2-min to 107)."""
    url = mast_url(uri)
    if url.startswith("https://archive.stsci.edu/missions/tess/tid/"):
        return S3 + "tess/public/tid/" + url[len("https://archive.stsci.edu/missions/tess/tid/"):]
    if url.startswith("https://archive.stsci.edu/hlsps/"):
        return S3 + "mast/hlsp/" + url[len("https://archive.stsci.edu/hlsps/"):]
    return None


def mast_url(uri: str) -> str:
    """Direct archive URL (skips the MAST API redirect) for SPOC and HLSP products."""
    if uri.startswith("mast:HLSP/"):
        return "https://archive.stsci.edu/hlsps/" + uri[len("mast:HLSP/"):]
    if uri.startswith("mast:TESS/product/"):
        fname = uri.rsplit("/", 1)[1]
        sector = fname.split("-")[1]
        tid = fname.split("-")[2]
        return (f"https://archive.stsci.edu/missions/tess/tid/{sector}/"
                f"{tid[:4]}/{tid[4:8]}/{tid[8:12]}/{tid[12:16]}/{fname}")
    return f"https://mast.stsci.edu/api/v0.1/Download/file?uri={uri}"


def read_tglc(h):
    """TGLC light curve (Han & Brandt 2023; Gaia-informed PSF photometry of FFIs, T <= 16). The
    calibrated PSF flux is used, as recommended for faint stars. There are no flux errors, so each
    sector gets a constant error from its point-to-point scatter (the search and vetting estimate
    the noise empirically anyway)."""
    d = h[1].data
    t = np.asarray(d["time"], float)
    f = np.asarray(d["cal_psf_flux"], float)
    q = np.asarray(d["TESS_flags"]).astype(np.int64) | np.asarray(d["TGLC_flags"]).astype(np.int64)
    good = (q == 0) & np.isfinite(t) & np.isfinite(f)
    med = np.nanmedian(f[good]) if good.any() else np.nan
    fn = f[good] / med
    err = 1.4826 * np.nanmedian(np.abs(np.diff(fn) - np.nanmedian(np.diff(fn)))) / np.sqrt(2) if good.sum() > 2 else np.nan
    zeros = np.zeros(good.sum(), np.float32)
    return dict(time=t[good], flux=fn.astype(np.float32), flux_err=np.full(good.sum(), err, np.float32),
                flux_err_source="tglc_point_to_point_mad",
                cx=zeros, cy=zeros, bkg=np.asarray(d["background"], float)[good].astype(np.float32),
                camera=int(h[0].header.get("CAMERA", -1) or -1), ccd=int(h[0].header.get("CCD", -1) or -1),
                exptime=float(np.nanmedian(np.diff(t[good]))) * 86400.0 if good.sum() > 2 else np.nan)


def qlp_point_to_point_error(t, f):
    """Robust raw-flux scatter; require >=3 short-gap differences and positive scatter.

    Sort eligible cadences and exclude separations above three times their median positive
    spacing. This is an empirical white-noise approximation, not a calibrated flux error.
    """
    if len(t) < 4:
        return np.nan
    order = np.argsort(t)
    dt = np.diff(t[order])
    positive = dt[dt > 0]
    if not len(positive):
        return np.nan
    adjacent = (dt > 0) & (dt <= 3 * np.median(positive))
    df = np.diff(f[order])[adjacent]
    if len(df) < 3:
        return np.nan
    err = 1.4826 * np.median(np.abs(df - np.median(df))) / np.sqrt(2)
    return err if np.isfinite(err) and err > 0 else np.nan


def read_lc_fits(path, provenance):
    """Return clean arrays and `flux_err_source` from a light-curve FITS.

    QLP alone may use point-to-point scatter when no eligible cadence has a finite,
    positive selected error. Partially valid uncertainty columns keep the original mask.
    """
    from astropy.io import fits

    with fits.open(path, memmap=False) as h:
        if provenance == "TGLC":
            return read_tglc(h)
        d = h[1].data
        hdr0 = h[0].header
        cols = d.columns.names
        t = np.asarray(d["TIME"], float)
        q = np.asarray(d["QUALITY"]).astype(np.int64)
        if provenance in ("SPOC", "TESS-SPOC"):
            f = np.asarray(d["PDCSAP_FLUX"], float)
            e = np.asarray(d["PDCSAP_FLUX_ERR"], float)
            error_source = "PDCSAP_FLUX_ERR"
            bad = (q & SPOC_BAD_BITS) != 0
            cx = np.asarray(d["MOM_CENTR1"], float)
            cy = np.asarray(d["MOM_CENTR2"], float)
            bkg = np.asarray(d["SAP_BKG"], float)
        else:
            fcol = "SYS_RM_FLUX" if "SYS_RM_FLUX" in cols else "SAP_FLUX"
            ecol = "DET_FLUX_ERR" if "DET_FLUX_ERR" in cols else "KSPSAP_FLUX_ERR"
            f = np.asarray(d[fcol], float)
            e = np.asarray(d[ecol], float)
            error_source = ecol
            bad = (q & QLP_BAD_BITS) != 0
            cx = np.asarray(d["SAP_X"], float)
            cy = np.asarray(d["SAP_Y"], float)
            bkg = np.asarray(d["SAP_BKG"], float)
        eligible = ~bad & np.isfinite(t) & np.isfinite(f)
        valid_error = np.isfinite(e) & (e > 0)
        if provenance == "QLP" and eligible.any() and not (eligible & valid_error).any():
            med = np.median(f[eligible])
            err = qlp_point_to_point_error(t[eligible], f[eligible])
            if np.isfinite(med) and med > 0 and np.isfinite(err):
                e = np.full(len(e), err)
                valid_error = np.isfinite(e) & (e > 0)
                error_source = "qlp_point_to_point_mad"
            else:
                error_source = "qlp_point_to_point_unavailable"
        good = eligible & valid_error
        med = np.nanmedian(f[good]) if good.any() else np.nan
        out = dict(
            time=t[good],
            flux=(f[good] / med).astype(np.float32),
            flux_err=(e[good] / med).astype(np.float32),
            flux_err_source=error_source,
            cx=cx[good].astype(np.float32),
            cy=cy[good].astype(np.float32),
            bkg=bkg[good].astype(np.float32),
            camera=int(hdr0.get("CAMERA", -1) or -1),
            ccd=int(hdr0.get("CCD", -1) or -1),
            exptime=float(h[1].header.get("TIMEDEL", np.nan)) * 86400.0,
        )
    return out


def mask_qlp_orbit_edges(s, days=None, end_days=None):
    """Sector dict without the first `days` and the last `end_days` of each orbit's cadences, for a QLP
    Sector 94-104 light curve."""
    days = QLP_ORBIT_MASK_DAYS if days is None else days
    end_days = QLP_ORBIT_MASK_END_DAYS if end_days is None else end_days
    if s["provenance"] != "QLP" or s["sector"] not in QLP_ORBIT_MASK_SECTORS or (days <= 0 and end_days <= 0):
        return s
    t = s["time"]
    start = np.asarray(QLP_ORBIT_STARTS)
    k = np.searchsorted(start, t + 0.02, side="right") - 1      # orbit of each cadence (0.02 d margin; -1: none)
    first, last = np.full(len(start), np.inf), np.full(len(start), -np.inf)
    np.minimum.at(first, k[k >= 0], t[k >= 0])                   # first and last cadence of each orbit
    np.maximum.at(last, k[k >= 0], t[k >= 0])
    kk = np.maximum(k, 0)
    drop = (k >= 0) & ((t < first[kk] + days) | (t > last[kk] - end_days))
    if not drop.any():
        return s
    return {key: v[~drop] if isinstance(v, np.ndarray) and v.shape == t.shape else v for key, v in s.items()}


def load_star(tic: int, orbit_mask_days=None, orbit_mask_end_days=None):
    """Load the per-star npz written by download.py -> list of sector dicts (QLP orbit edges masked)."""
    p = tic_path(tic)
    z = np.load(p, allow_pickle=False)
    sectors = [int(s) for s in z["sectors"]]
    out = []
    for s in sectors:
        k = f"s{s}_"
        d = dict(sector=s,
                 provenance=str(z[k + "prov"]),
                 time=z[k + "time"], flux=z[k + "flux"].astype(float),
                 flux_err=z[k + "flux_err"].astype(float),
                 flux_err_source=str(z[k + "flux_err_source"]) if k + "flux_err_source" in z else "unknown",
                 cx=z[k + "cx"], cy=z[k + "cy"], bkg=z[k + "bkg"],
                 exptime=float(z[k + "exptime"]))
        out.append(mask_qlp_orbit_edges(d, orbit_mask_days, orbit_mask_end_days))
    return out


# Cadence (minutes) of the means the biweight trend is fitted to; 0 fits every cadence.
# EXO_TREND_BIN overrides it for tests.
TREND_BIN_MIN = float(_os.environ.get("EXO_TREND_BIN", "10"))


def biweight_trend(t, f, window, bin_min=None):
    """wotan biweight trend (window in days, segments split at gaps > 0.5 d) evaluated at t (sorted).
    When the cadence is finer than bin_min minutes, the trend is fitted to bin_min-minute means
    and interpolated within each segment: it varies on the window scale (0.5-1 d), and fitting
    ~5x fewer points with ~5x fewer points per window is much faster than fitting every cadence."""
    from wotan import flatten

    bin_min = TREND_BIN_MIN if bin_min is None else bin_min
    if len(t) < 2 or not bin_min or np.median(np.diff(t)) > 0.5 * bin_min / 1440:
        _, trend = flatten(t, f, method="biweight", window_length=window, break_tolerance=0.5,
                           edge_cutoff=0.0, return_trend=True)
        return trend
    w = bin_min / 1440
    k = np.floor((t - t[0]) / w).astype(np.int64)
    _, idx, cnt = np.unique(k, return_index=True, return_counts=True)
    tb = np.add.reduceat(t, idx) / cnt
    fb = np.add.reduceat(f, idx) / cnt
    _, trb = flatten(tb, fb, method="biweight", window_length=window, break_tolerance=0.5,
                     edge_cutoff=0.0, return_trend=True)
    out = np.full(len(t), np.nan)
    seg_b = np.concatenate([[0], np.cumsum(np.diff(tb) > 0.5)])       # same breaks as wotan
    seg_t = np.repeat(seg_b, cnt)
    for s in np.unique(seg_b):
        ib, it = seg_b == s, seg_t == s
        g = ib & np.isfinite(trb)
        if g.sum() >= 2:
            out[it] = np.interp(t[it], tb[g], trb[g])
    return out
