"""figures/allsky.png: period against radius for every full-sky signal in tiers A, B, N, L1 and C, with the tier counts in
the legend and the counted total in the title. Built by the rule allsky_figure in rules.py."""
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TIERS = (("C", "0.75", "tier C (grazing, RUWE > 1.4, MES < 10, TRICERATOPS or centroid)"),
         ("L1", "C1", "tier L1 (SNR 7.5-9, false-alarm classifier)"),
         ("N", "C2", "tier N (neighbour within 15\", TRICERATOPS + centroid)"),
         ("B", "C0", "tier B"),
         ("A", "C3", "tier A (multi-candidate systems)"))


def draw(catalog_csv, out_png, counted):
    c = pd.read_csv(catalog_csv)
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for t, col, lab in TIERS:
        s_ = c[c.tier == t]
        ax.scatter(s_.P_d, s_.Rp_Re, s=12, c=col, label=f"{lab}: {len(s_)}", alpha=0.8, edgecolors="none")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("period (days)")
    ax.set_ylabel("radius (Earth radii)")
    ax.set_title(f"Full-sky search: {int(c.tier.isin(counted).sum())} candidates in tiers A, B, N and L1")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
