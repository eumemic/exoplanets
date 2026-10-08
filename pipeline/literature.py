"""Transit signals reported outside ExoFOP: the RAVEN (Lafarga et al. 2026) and T16 (Roth et al.
2026) candidate tables, and TIC/TOI mentions in the text and tables of arXiv astro-ph.EP papers
whose abstracts mention TESS, TOIs or TICs.

Usage: python literature.py [--max-papers N] [--extra 2607.23781,...]
Writes data/known/literature.parquet (tic, period, ra_deg, dec_deg, label), which known.py
checks alongside the ExoFOP and SPOC tables. Each arXiv paper is scanned once and cached as
data/known/arxiv/<id>.json, so reruns only fetch new papers. Papers are read from arXiv's HTML
rendering (arxiv.org/html, or ar5iv for older papers), which is ~20x smaller than the source
tarball; with --source, papers without HTML are read from their LaTeX source instead. arXiv asks
clients to wait 3 s between requests.

A paper "mentions" a star when a TIC ID, a TOI designation (resolved to its host) or a bare
7-10 digit TIC-like number appears in a table row or sentence. Numbers in the same row or
sentence with at least 4 significant digits between 0.2 and 1000 are kept as possible periods.
"""
import argparse
import gzip
import html
import io
import json
import re
import tarfile
import time
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

from common import DATA

K = DATA / "known"
ARXIV = K / "arxiv"
RAVEN = "https://zenodo.org/api/records/19661443/files/{}/content"
RAVEN_TABLES = ("nsfp09_table.csv", "vet_table.csv", "val_table.csv", "val_rp8_table.csv")
T16_FILES = ("https://dataverse.harvard.edu/api/access/datafile/13605255?format=original",
             "https://dataverse.harvard.edu/api/access/datafile/13605256?format=original")
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_QUERY = "cat:astro-ph.EP AND (abs:TESS OR abs:TOI OR abs:TIC)"
EPRINT = "https://export.arxiv.org/e-print/{}"
HTML_URLS = ("https://arxiv.org/html/{}", "https://ar5iv.labs.arxiv.org/html/{}")
DELAY = 3.1
# e-print tarballs download at ~0.2 MB/s, so by default papers without an HTML rendering are
# recorded as "no_html" and fetched from source only with --source (cached results are reused)
SOURCE_FALLBACK = False

TIC_RE = re.compile(r"TIC[\s~\-:]*(?:ID[\s~:]*)?(\d{3,10})")
TOI_RE = re.compile(r"TOI[\s~\-–]*(\d{2,5})(?:\.\d{2})?")
BARE_RE = re.compile(r"(?<![\d.])(\d{7,10})(?![\d.])")
NUM_RE = re.compile(r"(?<![\d.])(\d+\.\d+)(?![\d.])")


def get(url, retries=6, **kw):
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=180, **kw)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(DELAY * 2 ** attempt)
    return None


def raven():
    rows = []
    for name in RAVEN_TABLES:
        d = pd.read_csv(io.BytesIO(get(RAVEN.format(name)).content))
        rows.append(pd.DataFrame(dict(tic=d["ticid"], period=d["bls_per"], ra_deg=d["ra"],
                                      dec_deg=d["dec"], label=f"RAVEN {name.split('_table')[0]}")))
    return pd.concat(rows, ignore_index=True)


def t16():
    rows = []
    for url in T16_FILES:
        d = pd.read_csv(io.BytesIO(get(url).content), sep=None, engine="python")
        if "P_med" in d:
            rows.append(pd.DataFrame(dict(tic=d["TICID"], period=d["P_med"], ra_deg=d["ra"],
                                          dec_deg=d["dec"], label="T16")))
        else:
            rows.append(pd.DataFrame(dict(tic=d["TICID"], period=np.nan, ra_deg=np.nan,
                                          dec_deg=np.nan, label="T16 single transit")))
    return pd.concat(rows, ignore_index=True)


def arxiv_ids(max_papers):
    """IDs of astro-ph.EP papers matching ARXIV_QUERY, newest first."""
    ids, start = [], 0
    while len(ids) < max_papers:
        url = (f"{ARXIV_API}?search_query={quote(ARXIV_QUERY)}&sortBy=submittedDate"
               f"&sortOrder=descending&start={start}&max_results=500")
        r = get(url)
        time.sleep(DELAY)
        if r is None:
            break
        # entry IDs read with a regex rather than an XML parser
        entries = re.findall(r"<id>https?://arxiv\.org/abs/([^<]+?)(?:v\d+)?</id>", r.text)
        if not entries:
            break
        ids += entries
        start += len(entries)
    return ids[:max_papers]


def source_text(blob):
    """Text of the .tex and machine-readable table files in an arXiv e-print, read in memory."""
    try:
        tf = tarfile.open(fileobj=io.BytesIO(blob), mode="r:*")
    except tarfile.ReadError:
        try:
            data = gzip.decompress(blob)
        except OSError:
            data = blob
        return [] if data[:4] == b"%PDF" else [("main.tex", data.decode("latin-1"))]
    out = []
    for m in tf.getmembers():
        if m.isfile() and m.size < 50e6 and m.name.lower().endswith((".tex", ".txt", ".dat", ".csv", ".mrt")):
            out.append((m.name, tf.extractfile(m).read().decode("latin-1")))
    return out


def records(name, text):
    """Table rows and sentences (LaTeX), or lines (machine-readable tables)."""
    if not name.lower().endswith(".tex"):
        return text.splitlines()
    text = re.sub(r"(?<!\\)%.*", "", text)
    out = []
    for para in re.split(r"\n\s*\n", text):
        for row in para.split("\\\\"):
            out += re.split(r"(?<=[.!?])\s+(?=[A-Z\\])", row)
    return out


def _strip(fragment):
    fragment = re.sub(r"(?is)<annotation[^>]*>.*?</annotation>", " ", fragment)
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment))


def html_records(page):
    """Table rows (cells joined by '&') and sentences of an arXiv/ar5iv HTML paper."""
    page = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", page)
    out = [_strip(re.sub(r"(?i)</t[dh]>", " & ", row)) for row in re.findall(r"(?is)<tr\b.*?</tr>", page)]
    body = re.sub(r"(?is)<table\b.*?</table>", " ", page)
    for para in re.findall(r"(?is)<p\b.*?</p>", body):
        out += re.split(r"(?<=[.!?])\s+(?=[A-Z])", _strip(para))
    return out


def mentions(recs):
    """Per record: explicit TIC IDs, TOI numbers, bare TIC-like integers, possible periods."""
    found = []
    for rec in recs:
        tic = [int(x) for x in TIC_RE.findall(rec)]
        toi = [int(x) for x in TOI_RE.findall(rec)]
        bare = [int(x) for x in BARE_RE.findall(rec)]
        if not (tic or toi or bare):
            continue
        nums = []
        for x in NUM_RE.findall(rec):
            v = float(x)
            if 0.2 < v < 1000 and len(x.replace(".", "").lstrip("0")) >= 4:
                nums.append(v)
        found.append(dict(tic=sorted(set(tic)), toi=sorted(set(toi)), bare=sorted(set(bare) - set(tic)),
                          nums=sorted(set(nums))))
    return found


def fetch_paper(aid):
    """Records of one paper: HTML rendering if it exists, else the e-print source."""
    for url in HTML_URLS:
        t0 = time.time()
        r = get(url.format(aid), retries=2, allow_redirects=True)
        time.sleep(max(0.0, DELAY - (time.time() - t0)))
        # arXiv redirects to the abstract page when no HTML rendering exists
        if r is not None and "/abs/" not in r.url and "ltx_" in r.text[:200000]:
            return "html", html_records(r.text)
    if not SOURCE_FALLBACK:
        return "no_html", []
    r = get(EPRINT.format(aid))
    time.sleep(DELAY)
    if r is None:
        return None, []
    return "source", [rec for name, text in source_text(r.content) for rec in records(name, text)]


def scan(aid):
    path = ARXIV / f"{aid.replace('/', '_')}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        if not (SOURCE_FALLBACK and cached.get("kind") == "no_html"):
            return cached
    res = dict(id=aid, ok=False, records=[])
    try:
        kind, recs = fetch_paper(aid)
        res.update(ok=kind is not None, kind=kind, records=mentions(recs))
    except Exception as ex:
        res["error"] = repr(ex)
    path.write_text(json.dumps(res))
    return res


def arxiv_rows(papers, toi_host):
    rows = []
    for p in papers:
        label = f"arXiv:{p['id']}"
        for rec in p["records"]:
            ids = set(rec["tic"]) | set(rec["bare"]) | {toi_host[t] for t in rec["toi"] if t in toi_host}
            for tic in ids:
                rows.append((tic, np.nan, label))
                rows += [(tic, v, label) for v in rec["nums"]]
    d = pd.DataFrame(rows, columns=["tic", "period", "label"]).drop_duplicates()
    d["ra_deg"] = np.nan
    d["dec_deg"] = np.nan
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-papers", type=int, default=5000)
    ap.add_argument("--extra", default="2607.23781", help="comma-separated arXiv IDs to scan as well")
    ap.add_argument("--source", action="store_true", help="read papers without HTML from their source")
    a = ap.parse_args()
    global SOURCE_FALLBACK
    SOURCE_FALLBACK = a.source
    ARXIV.mkdir(parents=True, exist_ok=True)
    toi = pd.read_csv(K / "toi.csv")
    toi_host = dict(zip(toi["TOI"].astype(int), toi["TIC ID"].astype(np.int64)))
    tables = [raven(), t16()]
    print("RAVEN + T16 rows:", sum(len(t) for t in tables), flush=True)
    ids = list(dict.fromkeys(arxiv_ids(a.max_papers) + [x for x in a.extra.split(",") if x]))
    print(len(ids), "arXiv papers", flush=True)
    papers = []
    for i, aid in enumerate(ids, 1):
        papers.append(scan(aid))
        if i % 100 == 0 or i == len(ids):
            # written as it goes, so the known-signal check can use a partial scan
            lit = pd.concat(tables + [arxiv_rows(papers, toi_host)], ignore_index=True)
            lit = lit[np.isfinite(lit["tic"])]
            lit["tic"] = lit["tic"].astype(np.int64)
            lit.to_parquet(K / "literature.parquet")
            n_read = sum(p.get("kind") in ("html", "source") or (p["ok"] and "kind" not in p) for p in papers)
            print(f"{i}/{len(ids)} papers: {len(lit)} rows on {lit.tic.nunique()} stars; "
                  f"{n_read} read, {sum(p.get('kind') == 'no_html' for p in papers)} without HTML",
                  flush=True)


if __name__ == "__main__":
    main()
