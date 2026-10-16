"""The website's data file (_site/data/summary.json): results_public/numbers.json, the numbers the build computes from
the tables (pipeline/doc_numbers.py, rule numbers; the documents quote the same file, so a number has one definition),
with the search funnel as results_public/funnel_allsky.csv gives it and the dated release notes at the top of
README.md. Standard library only, so the site build needs no packages.

Usage: python site_data.py [OUT]     (default: _site/data/summary.json; site/build.sh calls it)
"""
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def funnel():
    f = {}
    with open(ROOT / "results_public" / "funnel_allsky.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            f.setdefault(r["pass"], {}).setdefault(r["band"], {})[r["stage"]] = int(r["count"])
    return f


def releases():
    """The dated release notes at the top of the README: title, date, count and the first linked note."""
    text = re.sub(r"<!--.*?-->", "", (ROOT / "README.md").read_text())   # generated-number markers (pipeline/dag/markers.py)
    out, months = [], {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July",
                                                    "August", "September", "October", "November", "December"), 1)}
    for m in re.finditer(r"^- \*\*(.+?)\*\*(.*?)(?=^- \*\*|^\S|\Z)", text, re.M | re.S):
        head, body = m.group(1), m.group(2)
        d = re.search(r"\((\d{1,2}) (\w+) (\d{4})\)", head)
        if not d:
            continue
        title = head[:d.start()].strip().rstrip(",")
        n = re.search(r"([\d,]+) candidates", head)
        added = re.match(r"\s*(\d+) (?:more|transit-candidate)", body)
        link = re.search(r"\]\(((?:validation|results_public)/[^)#]+(?:#[^)]*)?)\)", body)
        out.append({"date": f"{d.group(3)}-{months[d.group(2)]:02d}-{int(d.group(1)):02d}", "title": title,
                    "count": int(n.group(1).replace(",", "")) if n else None,
                    "added": int(added.group(1)) if added and not n else None,
                    "note": link.group(1) if link else None})
    return sorted(out, key=lambda r: r["date"], reverse=True)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site" / "data" / "summary.json"
    numbers = json.loads((ROOT / "results_public" / "numbers.json").read_text())
    s = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "funnel": funnel(), "numbers": numbers,
         "releases": releases()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(s, indent=1))
    print(f"{out}: {numbers['catalog']['counted']['total']} counted, {len(s['releases'])} releases")


if __name__ == "__main__":
    main()
