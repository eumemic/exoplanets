# Novelty check (2026-10-07, 21:21 UTC)

Sources checked for the 11 candidate host stars and their candidate periods (including 1/3, 1/2,
2/3, 3/2, 2 and 3 period harmonics, and TIC neighbours within 2.5′ for the catalog tables):

| Source | Result |
|---|---|
| ExoFOP target pages (JSON), all 11 stars | Only TOI-4342.01/.02 and TOI-6284.01 exist; no CTOIs |
| ExoFOP TOI list (8,148 rows, through TOI-7927.01) | No entry at any candidate period |
| ExoFOP CTOI list (5,137 rows) | No entry on these stars |
| NASA Exoplanet Archive `toi`, `pscomppars` | TOI-4342 b, c and TOI-6284.01 only |
| SPOC TCE tables on MAST (132 files incl. s0001–s0096) | No TCE at any candidate period on these stars or neighbours. TOI-6284 has an unpromoted s0001–s0096 TCE at 7.349 d |
| T16 Planet Hunt (Roth et al. 2026, ApJS 284, 19; Dataverse doi:10.7910/DVN/CWEUGW) | Only TOI-4342 b (5.538 d) |
| RAVEN (Lafarga et al. 2026, MNRAS; Zenodo 19661443) | `nsfp09_table`: TIC 231725883 at 9.0985 d (and its 3.0329 d alias). Not in `vet_table`, `val_table` or `val_rp8_table` |
| Tschudi 2026 (arXiv:2607.23781v3, LaTeX source) | TOI-6284 5.2445 d and 7.3494 d listed as "TOI-6284.02/.03"; none of the other stars |
| TOI-4342 papers (Tey et al. 2023; ESPRESSO 2026, arXiv:2601.22115) | Two transiting planets; RV candidate at 47.5 d; no 18.9 d transit reported |
| Web search on every TIC ID and on "TOI-4342 18.9 d" | No mentions |

Not checked: QLP's internal detections (not public), SPOC FFI-only searches (no public bulk TCE
table), and papers whose tables search engines do not index.
