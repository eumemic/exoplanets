#!/bin/bash
# Fast semi-coherent pass over newly downloaded stars until the downloader exits,
# then a full coherent pass over everything.
cd "$(dirname "$0")"
while pgrep -f "download.py" > /dev/null; do
  ../.venv/bin/python search.py "$1" --stars "$2" --out ../results/search_semi --method semi --procs "${3:-10}" 2>&1 | grep -v Warn
  sleep 60
done
../.venv/bin/python search.py "$1" --stars "$2" --out ../results/search_semi --method semi --procs 13 2>&1 | grep -v Warn
echo SEMI_DONE
../.venv/bin/python search.py "$1" --stars "$2" --out ../results/search --method coherent --procs 13 2>&1 | grep -v Warn
echo SEARCH_LOOP_DONE
