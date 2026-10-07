"""Download the catalogs used to flag known signals: ExoFOP TOIs and CTOIs, NASA Exoplanet
Archive confirmed planets, every SPOC TCE table on MAST, and TIC positions of TCE hosts
(so neighbouring stars' TCEs can be matched by period).

Writes data/known/{toi.csv, ctoi.csv, pscomppars.csv, tce_all.parquet, tce_tic.parquet}.
"""
import glob
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from common import DATA
from fetch_tic_by_id import fetch_tic

K = DATA / "known"
SOURCES = {
    "toi.csv": "https://exofop.ipac.caltech.edu/tess/download_toi.php?sort=toi&output=csv",
    "ctoi.csv": "https://exofop.ipac.caltech.edu/tess/download_ctoi.php?sort=ctoi&output=csv",
    "pscomppars.csv": ("https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+pl_name,"
                       "hostname,tic_id,gaia_dr3_id,pl_orbper,pl_rade,ra,dec,disc_facility+from+"
                       "pscomppars&format=csv"),
}
TCE_INDEX = "https://archive.stsci.edu/tess/bulk_downloads/bulk_downloads_tce.html"


def get(url, path):
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    path.write_bytes(r.content)


def main():
    (K / "tce").mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        get(url, K / name)
    links = sorted(set(re.findall(r'href="([^"]*dvr-tcestats\.csv)"', requests.get(TCE_INDEX, timeout=120).text)))
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda p: get("https://archive.stsci.edu" + p, K / "tce" / p.rsplit("/", 1)[1]), links))
    rows = []
    for f in sorted(glob.glob(str(K / "tce" / "*.csv"))):
        d = pd.read_csv(f, comment="#", usecols=lambda c: c in (
            "ticid", "tce_period", "tce_time0bt", "tce_duration", "tce_depth", "tce_model_snr", "sectors"))
        d["file"] = f.rsplit("/", 1)[1].split("_")[0]
        rows.append(d)
    tce = pd.concat(rows, ignore_index=True)
    tce.to_parquet(K / "tce_all.parquet")
    fetch_tic(tce["ticid"].unique()).to_parquet(K / "tce_tic.parquet")
    print(f"{len(links)} TCE tables, {len(tce)} TCEs on {tce.ticid.nunique()} stars")


if __name__ == "__main__":
    main()
