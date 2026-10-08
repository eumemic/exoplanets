"""Merge vetting results with candidate tags; print new signals that survive LEO-Vetter.

Usage: python shortlist.py [--max-fails N]
"""
import argparse
import glob
import json

import pandas as pd

from common import RESULTS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-fails", type=int, default=1)
    ap.add_argument("--cands", default=str(RESULTS / "cands.csv"))
    ap.add_argument("--vet", default=str(RESULTS / "vet"))
    ap.add_argument("--out", default=str(RESULTS / "vetted.csv"))
    a = ap.parse_args()
    c = pd.read_csv(a.cands)
    rows = []
    for f in glob.glob(f"{a.vet}/*.json"):
        r = json.load(open(f))
        if "error" in r:
            continue
        l = r["leo"]
        rows.append(dict(tic=r["tic"], rank=r["rank"], vet_snr=r["snr"], MES=l.get("MES"),
                         rp=r["rp_earth"], depth_ppm=r["depth_ppm"], chi2_sec=r["sector_chi2_dof"],
                         snr_old=r["snr_old"], snr_new=r["snr_new"], n_fail=len(r["leo_fails"]),
                         fails="; ".join(x.split(": ", 1)[-1] for x in r["leo_fails"])))
    v = pd.DataFrame(rows).merge(c, on=["tic", "rank"])
    v.to_csv(a.out, index=False)
    s = v[(v["known_status"] == "new") & (v["n_fail"] <= a.max_fails)].sort_values("MES", ascending=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 60)
    print(f"vetted {len(v)}: known {sum(v.known_status == 'known')}, "
          f"known passing all {sum((v.known_status == 'known') & (v.n_fail == 0))}; "
          f"reported elsewhere {sum(v.known_status == 'reported')}; "
          f"ours already {sum(v.known_status == 'ours')}; "
          f"new {sum(v.known_status == 'new')}, new with <= {a.max_fails} fails: {len(s)}")
    cols = ["tic", "rank", "period", "duration_h", "depth_ppm", "rp", "MES", "vet_snr", "sde",
            "n_good_events", "snr_old", "snr_new", "chi2_sec", "n_sectors", "n_fail", "fails"]
    print(s[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
