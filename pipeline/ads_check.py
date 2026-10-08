"""Literature check through NASA ADS full-text search: which papers mention a candidate's star
(TIC ID, or TOI number for TOI hosts), and which of those also contain its period. Covers journals
as well as arXiv, one or two queries per candidate.

Needs an ADS API token (https://ui.adsabs.harvard.edu/user/settings/token) in the environment
variable ADS_API_TOKEN or in ~/.ads/dev_key.

Usage: python ads_check.py CANDIDATES.csv OUT.csv
CANDIDATES.csv needs columns TIC and P_d (the candidate tables in results_public/ have both).
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://api.adsabs.harvard.edu/v1/search/query"


def token():
    t = os.environ.get("ADS_API_TOKEN")
    if t:
        return t.strip()
    f = Path.home() / ".ads" / "dev_key"
    if f.exists():
        return f.read_text().strip()
    sys.exit("No ADS token: set ADS_API_TOKEN or write it to ~/.ads/dev_key")


def query(q, tok, rows=200):
    for attempt in range(4):
        r = requests.get(API, headers={"Authorization": f"Bearer {tok}"},
                         params={"q": q, "fl": "bibcode,title,year", "rows": rows}, timeout=60)
        if r.status_code == 200:
            return r.json()["response"]["docs"]
        if r.status_code == 429:          # rate limit: 5,000 queries a day
            time.sleep(60)
            continue
        r.raise_for_status()
    return []


def period_strings(P):
    """How a period is usually quoted: 2 and 3 decimals, rounded and truncated."""
    out = {f"{P:.2f}", f"{P:.3f}", f"{int(P * 100) / 100:.2f}", f"{int(P * 1000) / 1000:.3f}"}
    return sorted(out)


def main():
    tok = token()
    c = pd.read_csv(sys.argv[1])
    toi = pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "known" / "toi.csv")
    rows = []
    for r in c.itertuples():
        names = [f'"TIC {r.TIC}"', f'"TIC{r.TIC}"']
        hosts = sorted({int(t) for t in toi.loc[toi["TIC ID"] == r.TIC, "TOI"]})
        names += [f'"TOI-{h}"' for h in hosts] + [f'"TOI {h}"' for h in hosts]
        star_q = "full:(" + " OR ".join(names) + ")"
        docs = query(star_q, tok)
        per_q = star_q + " AND full:(" + " OR ".join(f'"{s}"' for s in period_strings(r.P_d)) + ")"
        pdocs = query(per_q, tok) if docs else []
        rows.append(dict(TIC=r.TIC, P_d=r.P_d, n_papers=len(docs), n_with_period=len(pdocs),
                         papers_with_period=";".join(d["bibcode"] for d in pdocs),
                         papers=";".join(d["bibcode"] for d in docs[:20])))
        print(f"TIC {r.TIC} P={r.P_d:.4f}: {len(docs)} papers mention the star, {len(pdocs)} also the period",
              flush=True)
        time.sleep(0.5)
    pd.DataFrame(rows).to_csv(sys.argv[2], index=False)


if __name__ == "__main__":
    main()
