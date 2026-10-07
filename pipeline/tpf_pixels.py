"""Per-pixel transit analysis from SPOC 2-min target pixel files.

Usage: python tpf_pixels.py TIC PERIOD T0_BTJD DURATION_H SECTOR[,SECTOR...]
For each sector: difference image (out- minus in-transit, transit-masked biweight per pixel),
its flux-weighted centroid vs the out-of-transit centroid, and a figure with Gaia/TIC
neighbours overlaid. Writes results/pixels/tic<TIC>_tpf_s<sector>.png.
"""
import argparse
import warnings

import numpy as np

from common import DATA, RESULTS
from search import robust_std

warnings.filterwarnings("ignore")


def analyse(tpf, P, t0, dur):
    from wotan import flatten

    q = tpf.quality
    good = (q & 17087) == 0
    t = tpf.time.value[good]
    cube = np.asarray(tpf.flux.value[good], float)
    ok = np.all(np.isfinite(cube.reshape(len(t), -1)), axis=1) & np.isfinite(t)
    t, cube = t[ok], cube[ok]
    ph = ((t - t0 + 0.5 * P) % P) - 0.5 * P
    intr = np.abs(ph) < 0.4 * dur
    oot = (np.abs(ph) > 0.75 * dur) & (np.abs(ph) < 3 * dur)
    ny, nx = cube.shape[1:]
    diff = np.zeros((ny, nx))
    err = np.zeros((ny, nx))
    med = np.median(cube, axis=0)
    mask_out = np.abs(ph) > 0.75 * dur
    for j in range(ny):
        for i in range(nx):
            f = cube[:, j, i]
            if med[j, i] <= 0:
                continue
            tr = flatten(t[mask_out], f[mask_out], method="biweight", window_length=0.75,
                         return_trend=True)[1]
            g = np.isfinite(tr)
            if g.sum() < 50:
                continue
            trend = np.interp(t, t[mask_out][g], tr[g])
            r = f - trend
            diff[j, i] = np.mean(r[oot]) - np.mean(r[intr])
            s = robust_std(r[oot])
            err[j, i] = s * np.sqrt(1 / intr.sum() + 1 / oot.sum())
    return med, diff, err, int(intr.sum())


def centroid(img, weights_mask):
    y, x = np.mgrid[: img.shape[0], : img.shape[1]]
    w = np.where(weights_mask, np.clip(img, 0, None), 0)
    return np.sum(w * x) / np.sum(w), np.sum(w * y) / np.sum(w)


def main():
    import lightkurve as lk
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from astroquery.mast import Catalogs
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    ap = argparse.ArgumentParser()
    ap.add_argument("tic", type=int)
    ap.add_argument("period", type=float)
    ap.add_argument("t0", type=float)
    ap.add_argument("duration_h", type=float)
    ap.add_argument("sectors")
    a = ap.parse_args()
    dur = a.duration_h / 24
    cache = DATA / "followup" / f"tic{a.tic}"
    cache.mkdir(parents=True, exist_ok=True)
    tic_row = Catalogs.query_criteria(catalog="Tic", ID=a.tic).to_pandas().iloc[0]
    c0 = SkyCoord(tic_row["ra"] * u.deg, tic_row["dec"] * u.deg)
    nb = Catalogs.query_region(c0, radius=1.5 * u.arcmin, catalog="TIC").to_pandas()
    nb = nb[nb["Tmag"] < tic_row["Tmag"] + 7.5]
    for s in [int(x) for x in a.sectors.split(",")]:
        local = sorted(cache.glob(f"tess*-s{s:04d}-*_tp.fits"))
        if not local:
            print(f"S{s}: no SPOC 2-min TPF in {cache}")
            continue
        tpf = lk.read(str(local[0]))
        med, diff, err, n_in = analyse(tpf, a.period, a.t0, dur)
        snr = np.where(err > 0, diff / np.where(err > 0, err, 1), 0)
        core = med > np.percentile(med, 70)
        cx_o, cy_o = centroid(med, core)
        cx_d, cy_d = centroid(diff, snr > 2)
        wcs = tpf.wcs
        tx, ty = wcs.world_to_pixel(c0)
        nx_, ny_ = wcs.world_to_pixel(SkyCoord(nb["ra"].values * u.deg, nb["dec"].values * u.deg))
        off = np.hypot(cx_d - tx, cy_d - ty) * 21
        tot = diff[core].sum() / med[core].sum()
        print(f"S{s}: n_in={n_in}  depth(core, from diff)={tot * 1e6:.0f} ppm  "
              f"diff centroid offset from target {off:.1f}\" (oot centroid offset "
              f"{np.hypot(cx_o - tx, cy_o - ty) * 21:.1f}\")  max pixel SNR {snr.max():.1f}")
        fig, axs = plt.subplots(1, 3, figsize=(15, 5))
        for ax, img, title in zip(axs, (med, diff, snr),
                                  ("out-of-transit (median)", "difference (oot - in)", "difference SNR")):
            im = ax.imshow(img, origin="lower", cmap="viridis")
            plt.colorbar(im, ax=ax, fraction=0.046)
            ax.plot(nx_, ny_, "w.", ms=4)
            for xx, yy, tm in zip(nx_, ny_, nb["Tmag"]):
                if 0 <= xx < img.shape[1] and 0 <= yy < img.shape[0]:
                    ax.text(xx, yy, f"{tm:.1f}", color="w", fontsize=6)
            ax.plot(tx, ty, "r+", ms=14, mew=2)
            ax.plot(cx_d, cy_d, "mx", ms=10, mew=2)
            ax.set_title(f"S{s} {title}")
        fig.savefig(RESULTS / "pixels" / f"tic{a.tic}_tpf_s{s}.png", dpi=80)
        plt.close(fig)


if __name__ == "__main__":
    main()
