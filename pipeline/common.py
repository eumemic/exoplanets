"""Shared paths, product selection and light-curve loading."""
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
                cx=zeros, cy=zeros, bkg=np.asarray(d["background"], float)[good].astype(np.float32),
                camera=int(h[0].header.get("CAMERA", -1) or -1), ccd=int(h[0].header.get("CCD", -1) or -1),
                exptime=float(np.nanmedian(np.diff(t[good]))) * 86400.0 if good.sum() > 2 else np.nan)


def read_lc_fits(path, provenance):
    """Return dict of clean arrays from a SPOC/TESS-SPOC/QLP/TGLC light-curve FITS."""
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
            bad = (q & SPOC_BAD_BITS) != 0
            cx = np.asarray(d["MOM_CENTR1"], float)
            cy = np.asarray(d["MOM_CENTR2"], float)
            bkg = np.asarray(d["SAP_BKG"], float)
        else:
            fcol = "SYS_RM_FLUX" if "SYS_RM_FLUX" in cols else "SAP_FLUX"
            ecol = "DET_FLUX_ERR" if "DET_FLUX_ERR" in cols else "KSPSAP_FLUX_ERR"
            f = np.asarray(d[fcol], float)
            e = np.asarray(d[ecol], float)
            bad = (q & QLP_BAD_BITS) != 0
            cx = np.asarray(d["SAP_X"], float)
            cy = np.asarray(d["SAP_Y"], float)
            bkg = np.asarray(d["SAP_BKG"], float)
        good = ~bad & np.isfinite(t) & np.isfinite(f) & np.isfinite(e) & (e > 0)
        med = np.nanmedian(f[good]) if good.any() else np.nan
        out = dict(
            time=t[good],
            flux=(f[good] / med).astype(np.float32),
            flux_err=(e[good] / med).astype(np.float32),
            cx=cx[good].astype(np.float32),
            cy=cy[good].astype(np.float32),
            bkg=bkg[good].astype(np.float32),
            camera=int(hdr0.get("CAMERA", -1) or -1),
            ccd=int(hdr0.get("CCD", -1) or -1),
            exptime=float(h[1].header.get("TIMEDEL", np.nan)) * 86400.0,
        )
    return out


def load_star(tic: int):
    """Load the per-star npz written by download.py -> list of sector dicts."""
    p = tic_path(tic)
    z = np.load(p, allow_pickle=False)
    sectors = [int(s) for s in z["sectors"]]
    out = []
    for s in sectors:
        k = f"s{s}_"
        out.append(dict(sector=s,
                        provenance=str(z[k + "prov"]),
                        time=z[k + "time"], flux=z[k + "flux"].astype(float),
                        flux_err=z[k + "flux_err"].astype(float),
                        cx=z[k + "cx"], cy=z[k + "cy"], bkg=z[k + "bkg"],
                        exptime=float(z[k + "exptime"])))
    return out


# Cadence (minutes) of the means the biweight trend is fitted to; 0 fits every cadence.
# EXO_TREND_BIN overrides it for tests.
import os as _os
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
