"""Inspect archived flux and both local baselines at a fixed published ephemeris."""
import argparse
import hashlib
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from .independent_vet import read_curve, measure_event
except ImportError:
    from independent_vet import read_curve, measure_event


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("signals")
    ap.add_argument("--downloads", required=True)
    ap.add_argument("--tic", type=int, required=True)
    ap.add_argument("--sector", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--qlp-flux-column", choices=("SYS_RM_FLUX", "SAP_FLUX", "DET_FLUX"))
    args = ap.parse_args()
    signals = pd.read_csv(args.signals)
    selected = signals[signals.tic == args.tic]
    if len(selected) != 1:
        raise ValueError("Expected one selected ephemeris on this TIC")
    signal = selected.iloc[0]
    products = pd.read_csv(args.downloads)
    selected = products[(products.tic == args.tic) & (products.sector == args.sector)]
    if len(selected) != 1 or selected.iloc[0].status != "ok":
        raise ValueError("Expected one successful download for this star and sector")
    product = selected.iloc[0]
    if hashlib.sha256(Path(product.path).read_bytes()).hexdigest() != product.sha256:
        raise ValueError("Product SHA256 mismatch")
    t, f, e, info = read_curve(product.path, product.provenance, return_info=True,
                              qlp_flux_column=args.qlp_flux_column)
    if len(t) < 10:
        raise ValueError("Insufficient usable flux")
    duration = signal.duration_h / 24
    cadence = np.median(np.diff(t))
    first = int(np.ceil((t.min() - signal.t0_btjd) / signal.period_d))
    last = int(np.floor((t.max() - signal.t0_btjd) / signal.period_d))
    cycles = list(range(first, last + 1))
    fig, axes = plt.subplots(int(np.ceil(len(cycles) / 2)), 2,
                             figsize=(12, 3.3 * int(np.ceil(len(cycles) / 2))), squeeze=False)
    for ax, cycle in zip(axes.flat, cycles):
        centre = signal.t0_btjd + cycle * signal.period_d
        half = min(4 * duration, .4 * signal.period_d)
        lo, hi = np.searchsorted(t, [centre - half, centre + half])
        offset = np.median(f[lo:hi])
        ax.plot((t[lo:hi] - centre) * 24, (f[lo:hi] - offset) * 1e6,
                ".", ms=2, color="0.65", label="Quality-accepted flux")
        for width, color in ((2.5, "#245b8e"), (4., "#be753a")):
            half = min(width * duration, .4 * signal.period_d)
            event = measure_event(t, f, e, centre, duration, half, cadence=cadence)
            if event is None:
                continue
            l, h = np.searchsorted(t, [centre - half, centre + half])
            baseline = (f[l:h] - offset) * 1e6 - event["profile_flux_ppm"]
            ax.plot(event["profile_x_h"], baseline, color=color, lw=1.5,
                    label=f"{width:g}D wings: depth {event['depth_ppm']:.0f} ± {event['error_ppm']:.0f} ppm")
        ax.axvspan(-signal.duration_h / 2, signal.duration_h / 2, color="#245b8e", alpha=.10)
        ax.set_title(f"Cycle {cycle} ({'odd' if cycle % 2 else 'even'}) · BTJD {centre:.5f}")
        ax.set_xlabel("Hours from published transit centre")
        ax.set_ylabel("Flux relative to local median (ppm)")
        ax.legend(fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    for ax in list(axes.flat)[len(cycles):]:
        ax.axis("off")
    fig.suptitle(f"TIC {args.tic} · Sector {args.sector} {product.provenance} {info['flux_column']} · P = {signal.period_d:g} d\n"
                 "Archived flux with local fitted baselines; shaded region is the fixed transit window", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .93))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
