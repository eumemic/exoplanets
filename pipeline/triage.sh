#!/bin/bash
# collect -> vet new selections -> shortlist
cd "$(dirname "$0")"
../.venv/bin/python collect.py --snr "${1:-9}" --out ../results/cands.csv 2>&1 | grep -v Warn | head -2
../.venv/bin/python vet.py ../results/cands.csv --out ../results/vet --procs "${2:-4}" 2>&1 | grep -v Warn | tail -1
../.venv/bin/python shortlist.py 2>&1 | grep -v Warn
