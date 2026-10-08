#!/bin/bash
# Unpromoted-TCE triage: re-measure TCEs (tce_refit.py), then collect -> vet -> shortlist -> follow-up.
# TCE matches are not counted as known; TOIs, CTOIs, planets and the literature still are.
cd "$(dirname "$0")"
../.venv/bin/python tce_refit.py --procs "${1:-8}" 2>&1 | grep -v Warn | tail -1
../.venv/bin/python collect.py --search ../results/search_tce --stars ../data/catalogs/tce_hosts.parquet \
    --out ../results/cands_tce.csv --signals ../results/signals_tce.parquet --ignore-tce 2>&1 | grep -v Warn | head -3
../.venv/bin/python vet.py ../results/cands_tce.csv --out ../results/vet_tce --stars ../data/catalogs/tce_hosts.parquet \
    --procs "${1:-8}" 2>&1 | grep -v Warn | tail -1
../.venv/bin/python shortlist.py --cands ../results/cands_tce.csv --vet ../results/vet_tce --out ../results/vetted_tce.csv \
    --max-fails 0 2>&1 | grep -v Warn | head -1
../.venv/bin/python followup.py --vetted ../results/vetted_tce.csv --vet-dir ../results/vet_tce \
    --stars ../data/catalogs/tce_hosts.parquet --out ../results/followup_tce --procs 6 2>&1 | grep -v Warn | tail -1
