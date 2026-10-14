"""Measure fixed-ephemeris transits using independent, event-local linear baselines.

No discovery-pipeline detrending or search code is imported. This is a diagnostic
on selected signals, not a blind recovery, host localization or planet validation.
Formal errors assume white cadence noise; event-scatter inflation and shifted-phase
controls expose some additional variability but are not calibrated false-alarm tests.
"""
import argparse
import hashlib
from pathlib import Path

from astropy.io import fits
import numpy as np
import pandas as pd


def read_curve(path, provenance, return_info=False, qlp_flux_column=None):
    if qlp_flux_column is not None and provenance != "QLP":
        raise ValueError("QLP flux overrides require a QLP product")
    with fits.open(path, memmap=False) as hdul:
        data = hdul[1].data
        if provenance in ("SPOC", "TESS-SPOC"):
            flux_name, error_name = "PDCSAP_FLUX", "PDCSAP_FLUX_ERR"
        else:
            flux_name = qlp_flux_column or ("SYS_RM_FLUX" if "SYS_RM_FLUX" in data.names else "SAP_FLUX")
            error_name = "DET_FLUX_ERR" if "DET_FLUX_ERR" in data.names else "KSPSAP_FLUX_ERR"
        t = np.asarray(data["TIME"], float)
        f = np.asarray(data[flux_name], float)
        e = (np.asarray(data[error_name], float) if error_name in data.names
             else np.full(len(t), np.nan))
        q = np.asarray(data["QUALITY"], np.int64)
        # An explicit conservative choice, distinct from the discovery quality mask.
        eligible = (q == 0) & np.isfinite(t) & np.isfinite(f) & (f > 0)
        source = "provided"
        # Some QLP S94 products have finite flux but entirely missing errors.
        # Estimate white cadence scatter only when no supplied error is usable.
        # This does not model correlated noise or recover partially missing errors.
        if provenance == "QLP" and not np.any(eligible & np.isfinite(e) & (e > 0)):
            order = np.argsort(t[eligible])
            tt, ff = t[eligible][order], f[eligible][order]
            dt = np.diff(tt)
            positive_dt = dt[dt > 0]
            adjacent = ((dt > 0) & (dt <= 1.5 * np.median(positive_dt))
                        if len(positive_dt) else np.zeros(len(dt), dtype=bool))
            differences = np.diff(ff)[adjacent]
            scatter = (1.4826 * np.median(np.abs(differences - np.median(differences))) / np.sqrt(2)
                       if len(differences) >= 10 else np.nan)
            if np.isfinite(scatter) and scatter > 0:
                e = np.full(len(t), scatter)
                source = "empirical_adjacent_mad"
            else:
                source = "unusable"
        good = eligible & np.isfinite(e) & (e > 0)
        info = dict(flux_column=flux_name, error_column=error_name, error_source=source,
                    n_raw=len(t), n_quality_flux=int(eligible.sum()), n_usable=int(good.sum()))
        t, f, e = t[good], f[good], e[good]
    if not len(t):
        return (t, f, e, info) if return_info else (t, f, e)
    order = np.argsort(t)
    t, f, e = t[order], f[order], e[order]
    _, first = np.unique(t, return_index=True)
    t, f, e = t[first], f[first], e[first]
    info["n_usable"] = len(t)
    median = np.median(f)
    result = (t, f / median, e / median)
    return (*result, info) if return_info else result


def phase_distance(t, period, epoch):
    return (t - epoch + period / 2) % period - period / 2


def measure_event(t, flux, error, centre, duration, half_window, exclude=None, cadence=None):
    """Box-mean depth against robust linear wings; duration and times in days."""
    lo, hi = np.searchsorted(t, [centre - half_window, centre + half_window])
    tt, yy, ee = t[lo:hi], flux[lo:hi], error[lo:hi]
    if len(tt) < 10:
        return None
    x = (tt - centre) / duration
    usable = np.ones(len(tt), dtype=bool) if exclude is None else ~exclude[lo:hi]
    inside = (np.abs(x) <= 0.5) & usable
    outside = (np.abs(x) >= 0.75) & usable
    cadence = np.median(np.diff(t)) if cadence is None else cadence
    expected = duration / cadence
    if (inside.sum() < max(2, int(np.ceil(0.5 * expected)))
            or (outside & (x < 0)).sum() < 3 or (outside & (x > 0)).sum() < 3):
        return None
    design = np.column_stack([np.ones(len(x)), x])
    keep = outside.copy()
    for _ in range(3):
        weights = 1 / ee[keep] ** 2
        normal = design[keep].T @ (weights[:, None] * design[keep])
        if np.linalg.cond(normal) > 1e10:
            return None
        covariance = np.linalg.inv(normal)
        beta = covariance @ (design[keep].T @ (weights * yy[keep]))
        residual = yy - design @ beta
        sigma = max(1.4826 * np.median(np.abs(residual[keep] - np.median(residual[keep]))),
                    float(np.median(ee[keep])))
        updated = outside & (np.abs(residual) < 4 * sigma)
        if np.array_equal(updated, keep):
            break
        keep = updated
        if (keep & (x < 0)).sum() < 3 or (keep & (x > 0)).sum() < 3:
            return None
    # Refit after the last clipping update before forming the covariance.
    w_out = 1 / ee[keep] ** 2
    covariance = np.linalg.inv(design[keep].T @ (w_out[:, None] * design[keep]))
    beta = covariance @ (design[keep].T @ (w_out * yy[keep]))
    residual = yy - design @ beta
    noise_scale = max(1.0, float(np.sum((residual[keep] / ee[keep]) ** 2) / (keep.sum() - 2)))
    w_in = 1 / ee[inside] ** 2
    mean_design = np.average(design[inside], weights=w_in, axis=0)
    depth = float(mean_design @ beta - np.average(yy[inside], weights=w_in))
    variance = noise_scale * (1 / w_in.sum() + mean_design @ covariance @ mean_design)
    return dict(depth_ppm=depth * 1e6, error_ppm=np.sqrt(variance) * 1e6,
                n_in=int(inside.sum()), n_out=int(keep.sum()), coverage=float(inside.sum() / expected),
                centre_btjd=centre, profile_x_h=(tt - centre) * 24,
                profile_flux_ppm=residual * 1e6)


def event_measurements(curves, signal, window_factor=2.5, phase_shift=0.0, profiles=False):
    period, epoch = float(signal.period_d), float(signal.t0_btjd)
    duration = float(signal.duration_h) / 24
    half_window = min(window_factor * duration, 0.4 * period)
    rows, folded = [], []
    for sector, provenance, t, f, e in curves:
        if len(t) < 10:
            continue
        cadence = np.median(np.diff(t))
        first = int(np.ceil((t.min() - epoch) / period - phase_shift))
        last = int(np.floor((t.max() - epoch) / period - phase_shift))
        # Real transits must not contaminate either the core or wings of phase controls.
        excluded = np.abs(phase_distance(t, period, epoch)) < 0.75 * duration if phase_shift else None
        for cycle in range(first, last + 1):
            centre = epoch + (cycle + phase_shift) * period
            r = measure_event(t, f, e, centre, duration, half_window, excluded, cadence)
            if r is None:
                continue
            x, y = r.pop("profile_x_h"), r.pop("profile_flux_ppm")
            if profiles:
                folded.append((x, y))
            rows.append(dict(tic=int(signal.tic), sector=int(sector), provenance=provenance,
                             cycle=cycle, window_factor=window_factor, **r))
    return pd.DataFrame(rows), folded


def combine(events):
    if len(events) == 0:
        return dict(n_events=0, n_sectors=0, depth_ppm=np.nan, white_error_ppm=np.nan,
                    event_error_ppm=np.nan, snr_white=np.nan, snr_event=np.nan,
                    event_chi2_dof=np.nan, positive_fraction=np.nan)
    w = 1 / events.error_ppm.to_numpy() ** 2
    d = events.depth_ppm.to_numpy()
    mean = float(np.average(d, weights=w))
    err = float(np.sqrt(1 / w.sum()))
    chi2 = float(np.sum(w * (d - mean) ** 2) / (len(d) - 1)) if len(d) > 1 else np.nan
    inflated = err * np.sqrt(max(1.0, chi2)) if len(d) > 1 else err
    return dict(n_events=len(events), n_sectors=int(events.sector.nunique()), depth_ppm=mean,
                white_error_ppm=err, event_error_ppm=inflated, snr_white=mean / err,
                snr_event=mean / inflated, event_chi2_dof=chi2,
                positive_fraction=float(np.mean(d > 0)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("signals", help="tic, period_d, t0_btjd, duration_h and tier")
    ap.add_argument("--downloads", default="data/independent_vetting/downloads.csv")
    ap.add_argument("--out", type=Path, default=Path("results/independent_vetting"))
    ap.add_argument("--controls", type=int, default=49)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    signals = pd.read_csv(args.signals)
    downloads = pd.read_csv(args.downloads)
    if (downloads.status != "ok").any():
        raise ValueError("All manifest products must download successfully before analysis")
    if downloads.duplicated(["tic", "sector"]).any():
        raise ValueError("Expected one product per star and sector")
    missing = set(signals.tic) - set(downloads.tic)
    if missing:
        raise ValueError(f"No products for TICs: {sorted(missing)}")
    all_events, all_sectors, summaries, controls, product_rows = [], [], [], [], []
    plot_data = []
    for signal in signals.itertuples():
        rows = downloads[(downloads.tic == signal.tic) & (downloads.status == "ok")]
        curves = []
        for r in rows.itertuples():
            if hashlib.sha256(Path(r.path).read_bytes()).hexdigest() != r.sha256:
                raise ValueError(f"SHA256 mismatch for {r.path}")
            t, f, e, info = read_curve(r.path, r.provenance, return_info=True)
            curves.append((int(r.sector), r.provenance, t, f, e))
            product_rows.append(dict(tic=int(signal.tic), sector=int(r.sector),
                                     provenance=r.provenance, uri=r.uri, **info))
        for factor in (2.5, 4.0):
            events, profile = event_measurements(curves, signal, factor, profiles=(factor == 2.5))
            if len(events):
                all_events.append(events)
            stats = combine(events)
            stats.update(tic=int(signal.tic), tier=signal.tier, period_d=signal.period_d,
                         window_factor=factor, n_products=len(rows),
                         n_later_products=int((rows.sector > 104).sum()))
            if len(events):
                omitted = [combine(events[events.sector != sector])["snr_event"] for sector in events.sector.unique()]
                stats["min_leave_sector_out_snr"] = float(np.nanmin(omitted)) if len(omitted) > 1 else np.nan
                stats["max_event_information_fraction"] = float((1 / events.error_ppm ** 2).max() / (1 / events.error_ppm ** 2).sum())
                odd = combine(events[events.cycle % 2 != 0])
                even = combine(events[events.cycle % 2 == 0])
                for label, group in (("odd", odd), ("even", even)):
                    for key in ("n_events", "n_sectors", "depth_ppm", "event_error_ppm"):
                        stats[f"{label}_{key}"] = group[key]
                stats["odd_even_sigma"] = ((odd["depth_ppm"] - even["depth_ppm"]) /
                                           np.hypot(odd["event_error_ppm"], even["event_error_ppm"]))
                for sector, group in events.groupby("sector"):
                    all_sectors.append(dict(tic=int(signal.tic), sector=int(sector), window_factor=factor, **combine(group)))
            if factor == 2.5:
                controls_this = []
                for shift in np.arange(1, args.controls + 1) / (args.controls + 1):
                    if min(shift, 1 - shift) * signal.period_d <= 2 * signal.duration_h / 24:
                        continue
                    shifted, _ = event_measurements(curves, signal, factor, phase_shift=shift)
                    control = dict(tic=int(signal.tic), phase_shift=shift, **combine(shifted))
                    controls.append(control)
                    if np.isfinite(control["snr_event"]):
                        controls_this.append(control["snr_event"])
                values = np.asarray(controls_this)
                stats["n_phase_controls"] = len(values)
                stats["phase_controls_ge_observed"] = int((values >= stats["snr_event"]).sum()) if np.isfinite(stats["snr_event"]) else np.nan
                stats["max_phase_control_snr"] = float(np.max(values)) if len(values) else np.nan
                if signal.tier == "L1" and profile:
                    plot_data.append((signal, profile, stats.copy()))
            summaries.append(stats)
        print(f"TIC {signal.tic}: {stats['n_events']} events in {stats['n_sectors']} sectors; "
              f"wide-window depth {stats['depth_ppm']:.0f} ppm, diagnostic SNR {stats['snr_event']:.1f}", flush=True)
    pd.DataFrame(summaries).to_csv(args.out / "summary.csv", index=False)
    pd.DataFrame(all_sectors).to_csv(args.out / "sectors.csv", index=False)
    pd.concat(all_events, ignore_index=True).to_csv(args.out / "events.csv", index=False)
    pd.DataFrame(controls).to_csv(args.out / "phase_controls.csv", index=False)
    pd.DataFrame(product_rows).to_csv(args.out / "product_quality.csv", index=False)
    if plot_data:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(int(np.ceil(len(plot_data) / 2)), 2, figsize=(12, 2.8 * int(np.ceil(len(plot_data) / 2))))
        for ax, (signal, profile, stats) in zip(np.ravel(axes), plot_data):
            x = np.concatenate([p[0] for p in profile]); y = np.concatenate([p[1] for p in profile])
            bins = np.linspace(-2.5 * signal.duration_h, 2.5 * signal.duration_h, 46)
            means, errors, centres = [], [], []
            for lo, hi in zip(bins[:-1], bins[1:]):
                vals = y[(x >= lo) & (x < hi)]
                if len(vals) > 1:
                    means.append(np.mean(vals)); errors.append(np.std(vals, ddof=1) / np.sqrt(len(vals)))
                    centres.append((lo + hi) / 2)
            ax.errorbar(centres, means, yerr=errors, fmt="o", ms=3, color="#245b8e", lw=0.8)
            ax.axhline(0, color="0.65", lw=0.7)
            for edge in (-0.5 * signal.duration_h, 0.5 * signal.duration_h):
                ax.axvline(edge, color="#be753a", ls="--", lw=0.7)
            ax.set_title(f"TIC {signal.tic} · {signal.period_d:.4f} d\n"
                         f"{stats['n_events']} events / {stats['n_sectors']} sectors · local depth {stats['depth_ppm']:.0f} ppm", fontsize=10)
            ax.set_xlabel("Hours from published transit centre"); ax.set_ylabel("Local residual (ppm)")
            ax.spines[["top", "right"]].set_visible(False)
        for ax in np.ravel(axes)[len(plot_data):]:
            ax.axis("off")
        fig.suptitle("Independent local-baseline check of eight classifier-sensitive counted candidates\n"
                     "Published ephemerides; existing data; plotted errors assume independent cadences", fontsize=12)
        fig.tight_layout(rect=(0, 0, 1, 0.955))
        fig.savefig(args.out / "counted_candidates.png", dpi=170)
        plt.close(fig)


if __name__ == "__main__":
    main()
