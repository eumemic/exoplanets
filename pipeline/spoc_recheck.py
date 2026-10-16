"""Why did SPOC's 2-minute searches not report the full-sky candidates that have 2-minute data? For every candidate in
validation/findability_transits.csv.gz with transits in SPOC 2-minute light curves, the light curves up to Sector 96
(the range of SPOC's latest multi-sector search) are downloaded from the STScI open-data bucket and the transits are
re-measured in the PDCSAP flux (quality flag 0, biweight detrending as in search.py) with three noise estimates:
- white: each transit's box depth over the point-to-point scatter / sqrt(points), as search.py computes it;
- red: that error times the red-noise factor beta, the scatter of box-length bins of the out-of-transit residuals
  over its white-noise expectation (time-averaging method);
- cdpp: each transit's error is the CDPP in the light-curve header (0.5, 1 and 2 h values, interpolated in log-log)
  at the box length, i.e. the noise SPOC reports for the light curve.
Each SNR is maximized over box lengths of 0.5-9 h centred on the transit, since SPOC's search tries several durations.
Also counts transits within 0.5 d of a gap longer than 0.5 d or of a sector's ends, and checks every SPOC TCE on the
star (data/known/tce_all.parquet from fetch_known.py; any run, any period) for an epoch inside one of our transits.

Usage: python spoc_recheck.py --lc-dir ../data/spoc_2min [--last-sector 96] [--all]
Measures the candidates whose measurement is missing or no longer current (findability.recheck_problems; with --all,
every candidate) and writes them into results_public/products/spoc_2min.csv, with the ephemeris used and the date. The
build (rule spoc_recheck) makes validation/spoc_2min_recheck.csv from it.
"""
import argparse
from pathlib import Path

import boto3
import numpy as np
import pandas as pd
from astropy.io import fits
from botocore import UNSIGNED
from botocore.config import Config
from wotan import flatten

ROOT = Path(__file__).resolve().parent.parent
DURS = np.array([0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.5, 9.0])   # box lengths (h)
_s3 = None


def fetch(tic, sector, lc_dir):
    """One star's SPOC 2-minute light curve for one sector from the open-data bucket (cached in lc_dir)."""
    global _s3
    out = Path(lc_dir) / f"{tic}_s{sector}.fits"
    if out.exists():
        return out
    if _s3 is None:
        _s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED))
    t16 = f"{tic:016d}"
    prefix = f"tess/public/tid/s{sector:04d}/{t16[:4]}/{t16[4:8]}/{t16[8:12]}/{t16[12:]}/"
    keys = [o["Key"] for o in _s3.list_objects_v2(Bucket="stpubdata", Prefix=prefix).get("Contents", [])]
    keys = [k for k in keys if k.endswith("_lc.fits") and "fast" not in k]
    if not keys:
        return None
    _s3.download_file("stpubdata", keys[0], str(out))
    return out


def rstd(x):
    x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x)))


def cdpp_at(h, dur_h):
    """Header CDPP (ppm) at a box length: log-log between 0.5, 1 and 2 h, scaled as 1/sqrt(length) outside."""
    if dur_h <= 0.5:
        return h["CDPP0_5"] * np.sqrt(0.5 / dur_h)
    if dur_h >= 2.0:
        return h["CDPP2_0"] * np.sqrt(2.0 / dur_h)
    return float(np.exp(np.interp(np.log(dur_h), np.log([0.5, 1.0, 2.0]),
                                  np.log([h["CDPP0_5"], h["CDPP1_0"], h["CDPP2_0"]]))))


def snr(d, e):
    w = 1 / e ** 2
    return float(np.sum(w * d) / np.sqrt(np.sum(w))) if len(d) else 0.0


def remeasure(tic, P, t0, T14, sectors, lc_dir):
    """Transit and edge counts, and per noise estimate the SNR at the best box length."""
    tr = {dh: [] for dh in DURS}            # per box length: (depth, white error, red error, CDPP error)
    n_tr, edge, betas = 0, 0, []
    for s in sectors:
        f = fetch(tic, s, lc_dir)
        if f is None:
            continue
        with fits.open(f) as h:
            hd, d = h[1].header, h[1].data
            t, fl, q = np.array(d["TIME"], float), np.array(d["PDCSAP_FLUX"], float), np.array(d["QUALITY"])
        ok = np.isfinite(t) & np.isfinite(fl) & (q == 0)
        t, fl = t[ok], fl[ok] / np.nanmedian(fl[ok])
        trend = flatten(t, fl, method="biweight", window_length=float(np.clip(3 * T14, 0.5, 1.0)), return_trend=True)[1]
        res = fl / trend - 1
        good = np.isfinite(res)
        t, res = t[good], res[good]
        ph = ((t - t0 + 0.5 * P) % P) - 0.5 * P
        near = np.abs(ph) < T14
        sig = rstd(res[~near])
        cad = np.median(np.diff(t))
        ep = np.round((t - t0) / P).astype(int)
        gaps = np.where(np.diff(t) > 0.5)[0]
        bounds = np.concatenate([[t[0]], t[gaps], t[gaps + 1], [t[-1]]])
        seen = set()
        for dh in DURS:
            dd = dh / 24
            if dd > 1.5 * T14:
                continue
            n_exp = dd / cad
            idx = np.digitize(t[~near], np.arange(t[0], t[-1] + dd, dd))
            bm = pd.Series(res[~near]).groupby(idx).agg(["mean", "size"])
            bm = bm[bm["size"] >= 0.8 * n_exp]
            beta = max(rstd(bm["mean"].values) / (sig / np.sqrt(n_exp)), 1.0) if len(bm) > 10 else 1.0
            if dh == DURS[np.argmin(np.abs(DURS - 24 * T14))]:
                betas.append(beta)
            box = np.abs(ph) < 0.5 * dd
            for k in np.unique(ep[box]):
                sel = box & (ep == k)
                if sel.sum() < 0.5 * n_exp:
                    continue
                e_w = sig / np.sqrt(sel.sum())
                tr[dh].append((-np.mean(res[sel]), e_w, beta * e_w, cdpp_at(hd, dh) * 1e-6))
                seen.add(k)
        n_tr += len(seen)
        edge += sum(np.min(np.abs(bounds - (t0 + k * P))) < 0.5 for k in seen)
    out = dict(n_2min_transits=n_tr, edge_transits=int(edge), beta_T14=float(np.median(betas)) if betas else np.nan)
    for j, lab in ((1, "white"), (2, "red"), (3, "cdpp")):
        vals = {dh: snr(np.array([x[0] for x in v]), np.array([x[j] for x in v])) for dh, v in tr.items() if v}
        best = max(vals, key=vals.get) if vals else None
        out[f"snr_{lab}"], out[f"box_h_{lab}"] = (vals[best], best) if vals else (0.0, np.nan)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lc-dir", required=True, help="where the 2-minute light curves are downloaded")
    ap.add_argument("--last-sector", type=int, default=96)
    ap.add_argument("--all", action="store_true", help="re-measure every candidate, not only those the build lists")
    a = ap.parse_args()
    import datetime
    import tomllib
    import findability
    Path(a.lc_dir).mkdir(parents=True, exist_ok=True)
    prod = ROOT / "results_public" / "products" / "spoc_2min.csv"
    trp, fap = ROOT / "validation" / "findability_transits.csv.gz", ROOT / "validation" / "findability.csv"
    catp = ROOT / "results_public" / "candidates_allsky.csv"
    tol = tomllib.loads((ROOT / "pipeline" / "params.toml").read_text())["freshness"]
    todo = findability.recheck_problems(prod, fap, trp, catp, tol, a.last_sector)
    tr = pd.read_csv(trp)
    cat = pd.read_csv(catp)[["TIC", "P_d", "T0_BJD", "T14_h"]]
    tce = pd.read_parquet(ROOT / "data" / "known" / "tce_all.parquet")
    rows = []
    for (tic, P), g in tr[tr.prov == "SPOC"].groupby(["TIC", "P_d"]):
        if not a.all and (tic, P) not in todo:
            continue
        c = cat[(cat.TIC == tic) & (cat.P_d == P)].iloc[0]
        t0, T14 = c.T0_BJD - 2457000, c.T14_h / 24
        sectors = sorted(int(s) for s in g.sector.unique() if s <= a.last_sector)
        tc = tce[tce.ticid == tic]
        off = ((tc.tce_time0bt - t0 + 0.5 * P) % P) - 0.5 * P
        rows.append(dict(TIC=tic, P_d=P, T0_BJD=c.T0_BJD, T14_h=c.T14_h, sectors_2min=",".join(map(str, sectors)),
                         **remeasure(tic, P, t0, T14, sectors, a.lc_dir), tces_on_star=len(tc),
                         tces_on_transit=int((np.abs(off) < 0.5 * T14).sum()), measured=datetime.date.today().isoformat()))
    new = pd.DataFrame(rows).round({k: 2 for k in ("snr_white", "snr_red", "snr_cdpp", "beta_T14")})
    old = pd.read_csv(prod, dtype={"sectors_2min": str})
    if len(new):
        keep = ~old.set_index(["TIC", "P_d"]).index.isin(new.set_index(["TIC", "P_d"]).index)
        old = pd.concat([old[keep], new[old.columns]], ignore_index=True)
    old.sort_values(["TIC", "P_d"]).to_csv(prod, index=False, lineterminator="\n")
    print(f"{len(new)} candidates measured -> {prod.relative_to(ROOT)}; the build makes validation/spoc_2min_recheck.csv")


if __name__ == "__main__":
    main()
