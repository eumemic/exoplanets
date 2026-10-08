#!/bin/bash
# Extra-planet search of TOI hosts: TOIs masked, stack-slide search, repeated while the
# downloader is still adding stars, then a final pass.
cd "$(dirname "$0")"
args=(../data/catalogs/toi_hosts.txt --stars ../data/catalogs/toi_hosts.parquet --out ../results/search_toi
      --method stack --mask-tois --max-signals 4 --procs "${1:-8}")
while pgrep -f "download.py ../data/catalogs/toi_hosts.txt" > /dev/null; do
  ../.venv/bin/python search.py "${args[@]}" 2>&1 | grep -v Warn
  sleep 60
done
../.venv/bin/python search.py "${args[@]}" 2>&1 | grep -v Warn
echo TOI_SEARCH_DONE
