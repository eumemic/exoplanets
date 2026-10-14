#!/usr/bin/env bash
# Assemble the GitHub Pages artifact: the static site plus the data and images it reads.
# Used by .github/workflows/pages.yml and for local testing:
#   site/build.sh [output-dir]      (default: _site in the repository root)
#   python3 -m http.server -d _site 8000
# The multi-MB .csv.gz files are deliberately not copied; the site links to them on GitHub.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/_site}"
case "$OUT" in
  ""|"/"|"$ROOT"|"$HOME") echo "refusing to use '$OUT' as the output directory" >&2; exit 1 ;;
esac

rm -rf "$OUT"
mkdir -p "$OUT/data" "$OUT/figures"

# Static pages, styles, scripts and the share image (everything in site/ except this script and
# og.html, the page the share image og.png is rendered from; see the comment at the top of og.html).
for f in "$ROOT"/site/*; do
  case "$(basename "$f")" in build.sh|og.html) continue ;; esac
  cp -R "$f" "$OUT/"
done

# Data the pages read at runtime (the CSV files themselves are the source of truth).
cp "$ROOT/results_public/candidates_allsky.csv"        "$OUT/data/"
cp "$ROOT/results_public/tiers_earlier_candidates.csv" "$OUT/data/"
cp "$ROOT/candidates/ephemerides.csv"                  "$OUT/data/"
cp "$ROOT/candidates/predictions.csv"                  "$OUT/data/"
cp "$ROOT/validation/findability.csv"                  "$OUT/data/"

# Images shown on the pages. The per-candidate vetting plots (about 180 MB) are not copied;
# the candidates page loads each one from GitHub when its row is opened.
for f in allsky.png toi4342.png candidates_grid.png; do cp "$ROOT/figures/$f" "$OUT/figures/"; done

# The next few days of predicted transits of the counted candidates, so the landing page does not
# have to download all of predictions.csv (2.5 MB). Rows are copied from predictions.csv as they are,
# with depth and radius from ephemerides.csv. If the site is older than this window, the page falls
# back to predictions.csv itself.
python3 - "$ROOT" "$OUT/data/upcoming.json" <<'PY'
import csv, json, sys, datetime
root, out = sys.argv[1], sys.argv[2]
counted = {"A", "B", "N", "L1"}
eph = {}
with open(root + "/candidates/ephemerides.csv", newline="") as fh:
    for r in csv.DictReader(fh):
        eph.setdefault(r["TIC"], []).append(r)
now = datetime.datetime.now(datetime.timezone.utc)
start = (now - datetime.timedelta(hours=6)).strftime("%Y-%m-%d %H:%M")
end = (now + datetime.timedelta(days=10)).strftime("%Y-%m-%d %H:%M")
rows = []
with open(root + "/candidates/predictions.csv", newline="") as fh:
    for r in csv.DictReader(fh):
        if r["tier"] not in counted or not (start <= r["tc_UTC"] < end):
            continue
        p = float(r["period_d"])
        e = min(eph.get(r["TIC"], []), key=lambda x: abs(float(x["period_d"]) - p), default=None)
        if e is not None and abs(float(e["period_d"]) - p) > 1e-4 * p:
            e = None
        rows.append([r["tc_UTC"], r["TIC"], r["tier"], r["period_d"], r["sigma_min"], r["duration_h"],
                     e["depth_ppm"] if e else "", e["Rp_Re"] if e else "", r["tess_sector"]])
rows.sort(key=lambda x: x[0])
with open(out, "w") as fh:
    json.dump({"source": "candidates/predictions.csv", "from_utc": start, "to_utc": end,
               "columns": ["tc_UTC", "TIC", "tier", "period_d", "sigma_min", "duration_h", "depth_ppm", "Rp_Re", "tess_sector"],
               "rows": rows}, fh, separators=(",", ":"))
PY

# Index of candidate folders, so the table can link to each folder on GitHub when it exists.
list_dirs() {
  find "$1" -mindepth 1 -maxdepth 1 -type d -name 'TIC*' -exec basename {} \; | LC_ALL=C sort |
    awk 'BEGIN { printf "[" } { printf "%s\"%s\"", (NR > 1 ? "," : ""), $0 } END { printf "]" }'
}
printf '{"earlier":%s,"allsky":%s}\n' "$(list_dirs "$ROOT/candidates")" "$(list_dirs "$ROOT/candidates/allsky")" > "$OUT/data/folders.json"

# Build stamp shown in the page footer.
COMMIT="${GITHUB_SHA:-$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)}"
printf '{"commit":"%s","built":"%s"}\n' "$COMMIT" "$(date -u +%Y-%m-%d)" > "$OUT/data/build.json"

touch "$OUT/.nojekyll"
echo "Site assembled in $OUT"
