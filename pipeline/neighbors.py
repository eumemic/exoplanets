"""TIC neighbours that could produce an observed transit depth if they were eclipsing binaries.

Usage: python neighbors.py TIC DEPTH_PPM [--radius 2.5]
A neighbour is 'capable' if an eclipse of at most 50% of its flux could dilute to the depth:
flux ratio >= 2 * depth.
"""
import argparse
import warnings

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astroquery.mast import Catalogs

warnings.filterwarnings("ignore")


def capable_neighbours(tic, depth_ppm, radius_arcmin=2.5):
    t = Catalogs.query_criteria(catalog="Tic", ID=int(tic)).to_pandas().iloc[0]
    c = SkyCoord(t["ra"] * u.deg, t["dec"] * u.deg)
    nb = Catalogs.query_region(c, radius=radius_arcmin * u.arcmin, catalog="TIC").to_pandas()
    nb["ID"] = nb["ID"].astype(int)
    nb = nb[nb["ID"] != int(tic)].copy()
    nb["sep_arcsec"] = SkyCoord(nb["ra"].values * u.deg, nb["dec"].values * u.deg).separation(c).arcsec
    nb["dT"] = nb["Tmag"] - t["Tmag"]
    nb["flux_ratio"] = 10 ** (-0.4 * nb["dT"])
    nb["max_ecl_needed"] = depth_ppm * 1e-6 / nb["flux_ratio"]
    nb["capable"] = nb["max_ecl_needed"] <= 0.5
    return t, nb.sort_values("sep_arcsec")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tic", type=int)
    ap.add_argument("depth_ppm", type=float)
    ap.add_argument("--radius", type=float, default=2.5)
    a = ap.parse_args()
    t, nb = capable_neighbours(a.tic, a.depth_ppm, a.radius)
    cap = nb[nb["capable"]]
    print(f"TIC {a.tic} T={t['Tmag']:.2f}: {len(nb)} TIC sources within {a.radius}', "
          f"{len(cap)} could mimic {a.depth_ppm:.0f} ppm")
    cols = ["ID", "sep_arcsec", "Tmag", "dT", "max_ecl_needed", "objType", "disposition"]
    print(cap[cols].head(15).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
