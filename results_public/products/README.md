# Inputs of the catalog build

`pipeline/catalog.py` (rule `catalog` in `pipeline/rules.py`) builds `../candidates_allsky.csv` and
`../tiers_earlier_candidates.csv` from the files here and `../overrides.csv`. It derives the TRICERATOPS columns
(`FPP` … `NFPP_gc`), `tier`, `c_reason`, `reported_as` and the flags; every other column is copied from these files as
written. The rules are listed at the top of `pipeline/catalog.py`, and their thresholds are in `pipeline/params.toml`.

| File | Contents | Made by |
|---|---|---|
| `measurements_allsky.csv`, `measurements_earlier.csv` | The measured columns of the two tables: transit fit, vetting, stellar parameters, pixel and per-sector centroid tests, binary and literature checks, the centroid Bayes factor `BF`, classifier scores, `rv_flag`, `set`, `search`, `candidate_id`. For the earlier searches also `base_tier` and `base_c_reason`: the label each signal was given when it was first listed (8 October 2026, or 12 October for the two added then), which it keeps unless a reason for tier C applies. | Copied from the published tables of commit b2a7d1f (15 October 2026). Some of the checks behind them cannot be rerun from what was kept (see below), so they are carried forward as published until the build recomputes them, one group of columns at a time. |
| `triceratops.csv` | For each catalog row with a TRICERATOPS result: the result it uses (`key`, `batch`), the inputs the result ran with (`period`, `t0_btjd`, `duration_h`, `depth_ppm`, `masks` of the star's other signals, scenario `drop`), the fold (`exptime_min`, `n_points`, `sectors`), and the means and largest values of the ten default-prior runs and of the ten Gaia-limited runs. `degenerate` = yes where TRICERATOPS did not evaluate the target (every scenario equally likely; the target has no TIC parallax). | `pipeline/triceratops_table.py` (rule `triceratops_table`) from the fpp_pool batches listed in `triceratops_batches.csv`, which are not in the repository. A result is used only if it passes the checks of `pipeline/fpp_check.py`. |
| `triceratops_batches.csv` | The TRICERATOPS batches, in the order in which a later batch's result for a signal replaces an earlier one. | By hand, when a batch is added. |
| `centroids.csv` | Per-sector centroid results measured after the copy of the measured columns: for each catalog row they cover, the measurement (`key`, `batch`), the ephemeris it used and the centroid columns, which replace the row's published ones. | `pipeline/centroid_table.py` (rule `centroid_table`) from the centroid_sectors.py batches in `centroid_batches.csv`, with centroid_test.py's test; each batch keeps the TIC dispositions of the stars near each target (`stars.csv`), so TIC artifacts and duplicates are never taken for neighbours. |
| `centroid_batches.csv` | The centroid batches, in order. | By hand, when a batch is added. |

`../overrides.csv` holds the decisions made by hand, one per row: the table, the signal (`TIC`, `P_d`), the column,
its value, the reason and where it is described. An override of `tier` or `c_reason` replaces the rules' outcome; an
override of any other column replaces an input before the rules run (for example `reported_as` for a community TOI
reported under another period).

Three checks in `pipeline/rules.py` run on these inputs:
- `triceratops_inputs_current`: each TRICERATOPS result ran on the signal's current ephemeris, depth and masks;
- `centroid_inputs_current`: each centroid measurement in `centroids.csv` used the signal's current ephemeris;
- `counted_measured_centroids`: each counted candidate has per-sector centroid measurements.

Inputs that no longer exist: the outputs of the literature, binary and RUWE checks behind the 726 rows of the first
full-sky release, the script that first wrote the earlier-search table, and some network answers that were not saved
(MAST dispositions, CDS cross-matches). The MOLUSC files and field-star populations of the TRICERATOPS runs were not
kept either.
