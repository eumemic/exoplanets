# Inputs of the catalog build

`pipeline/catalog.py` (rule `catalog` in `pipeline/rules.py`) builds `../candidates_allsky.csv` and
`../tiers_earlier_candidates.csv` from the files here and `../overrides.csv`. It derives the TRICERATOPS columns
(`FPP` … `NFPP_gc`), `tier`, `c_reason`, `reported_as` and the flags; every other column is copied from these files as
written. The rules are listed at the top of `pipeline/catalog.py`, and their thresholds are in `pipeline/params.toml`.

| File | Contents | Made by |
|---|---|---|
| `measurements_allsky.csv`, `measurements_earlier.csv` | The measured columns of the two tables: transit fit, vetting, stellar parameters, pixel and per-sector centroid tests, binary and literature checks, the centroid Bayes factor `BF`, classifier scores, `rv_flag`, `set`, `search`, `candidate_id`. For the earlier searches also `base_tier` and `base_c_reason`: the label each signal was given when it was first listed (8 October 2026, or 12 October for the two added then), which it keeps unless a reason for tier C applies. | Copied from the published tables of commit b2a7d1f (15 October 2026). Some of the checks behind them cannot be rerun from what was kept (see below), so they are carried forward as published until the build recomputes them, one group of columns at a time. |
| `triceratops.csv` | For each catalog row with a TRICERATOPS result: the result it uses (`key`, `batch`), the inputs the result ran with (`period`, `t0_btjd`, `duration_h`, `depth_ppm`, `masks` of the star's other signals, scenario `drop`), the fold (`exptime_min`, `n_points`, `sectors`), and the means and largest values of the ten default-prior runs and of the ten Gaia-limited runs. `degenerate` = yes where TRICERATOPS did not evaluate the target (every scenario equally likely; the target has no TIC parallax). | `pipeline/triceratops_table.py` (rule `triceratops_table`) from the store of TRICERATOPS results (`pipeline/store.py`, `pipeline/tri_store.py`; not in the repository), each result under the hash of what determines it (`store`). The batches run before the store are imported as legacy results (`legacy` = yes): they did not keep their light-curve list, code version, and for all but the last batch their field-star population and MOLUSC file. A result is used only if it passes the checks of `pipeline/fpp_check.py`. |
| `triceratops_batches.csv` | The TRICERATOPS batches run before the store, in the order in which a later batch's result for a signal replaces an earlier one; `pipeline/tri_store.py import` imported them. | By hand (complete). |
| `triceratops_plan.csv` | Every row whose tier can depend on TRICERATOPS (`needed` = yes, `catalog.needs_triceratops`) or that shows a TRICERATOPS result: the inputs a current result must have run with (ephemeris, depth, masks of the star's other signals and TOIs, scenario drops) and its status: `current`, `legacy` (current, from a legacy result), `pending` (needed, and missing or out of date) or `stale` (shown but out of date), with the reason. | `pipeline/tri_plan.py` (rule `triceratops_plan`). |
| `centroids.csv` | Per-sector centroid results measured after the copy of the measured columns: for each catalog row they cover, the measurement (`key`, `batch`), the ephemeris it used and the centroid columns, which replace the row's published ones. | `pipeline/centroid_table.py` (rule `centroid_table`) from the store (`pipeline/centroid_store.py`, entries of kind centroid; `store` is the entry), with centroid_test.py's test; each entry keeps the TIC dispositions of the stars near the target, so TIC artifacts and duplicates are never taken for neighbours. The batch in `centroid_batches.csv` was imported as legacy entries. |
| `centroid_batches.csv` | The centroid batches measured before the store, in order; `pipeline/centroid_store.py import` imported them. | By hand (complete). |
| `spoc_2min.csv` | The re-measurement of each full-sky candidate's transits in SPOC's 2-minute light curves through Sector 96 (three noise estimates, transit and edge counts, SPOC TCEs on the star and on our transits), with the ephemeris (`P_d`, `T0_BJD`, `T14_h`) and sectors it used and the date (`measured`). The build keeps the rows of the current candidates with 2-minute data in `../../validation/spoc_2min_recheck.csv`. | `pipeline/spoc_recheck.py`, for the candidates the check `spoc_measured` lists (no measurement, or one made on another ephemeris or other sectors). The rows before 16 October 2026 are those of the published recheck tables of 12, 13 and 15 October, with the catalog's epoch of that day. |

`../overrides.csv` holds the decisions made by hand, one per row: the table, the signal (`TIC`, `P_d`), the column,
its value, the reason and where it is described. An override of `tier` or `c_reason` replaces the rules' outcome; an
override of any other column replaces an input before the rules run (for example `reported_as` for a community TOI
reported under another period).

Four checks in `pipeline/rules.py` run on these inputs:
- `triceratops_current`: no row of `triceratops_plan.csv` is pending or stale;
- `centroid_inputs_current`: each centroid measurement in `centroids.csv` used the signal's current ephemeris;
- `counted_measured_centroids`: each counted candidate has per-sector centroid measurements;
- `spoc_measured`: each candidate with 2-minute data has a current re-measurement in `spoc_2min.csv`.

Inputs that no longer exist: the outputs of the literature, binary and RUWE checks behind the 726 rows of the first
full-sky release, the script that first wrote the earlier-search table, and some network answers that were not saved
(MAST dispositions, CDS cross-matches). The MOLUSC files and field-star populations of the TRICERATOPS runs were not
kept either.
