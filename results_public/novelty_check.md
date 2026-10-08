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

# Novelty check for the 2026-10-08 update

The update candidates were checked automatically and by web search.

| Source | Result |
|---|---|
| ExoFOP TOI list (8,148 rows) and CTOI list (5,137 rows), downloaded 2026-10-07 | No entry at any candidate period (harmonics 1/3–3) on these stars or TIC neighbours within 2.5′ |
| NASA Exoplanet Archive `pscomppars` | Only the known planets listed in the table (TOI-5489 b, c; TOI-3896 b; TOI-7333 b) |
| SPOC TCE tables on MAST (132 files incl. s0001–s0096) | No TCE at any candidate period |
| RAVEN (Lafarga et al. 2026; 4 tables) and T16 (Roth et al. 2026) | Only TIC 231725883's 9.10 d signal (RAVEN), already noted in the first release |
| arXiv: 2,037 astro-ph.EP papers whose abstracts mention TESS, TOIs or TICs, read from their HTML versions (`literature.py`) | No TIC/TOI mention with a number within 0.3% of a candidate period (or half/double) |
| Web searches on every candidate TIC ID and host TOI (2026-10-08) | No reports. TOI-3494 has a companion star 0.59″ away (Δ*I* = 2.9; Matson et al. 2025, AJ 169, 76); TOI-5489 b and c were validated by Gomez Barrientos et al. ([arXiv:2512.11971](https://arxiv.org/abs/2512.11971)), which reports no third signal |

Not checked: papers not on arXiv, arXiv papers without an HTML version (54 of those scanned), periods
quoted with fewer than four significant digits, QLP's internal detections, and NASA ADS full text
(which needs an API token).
