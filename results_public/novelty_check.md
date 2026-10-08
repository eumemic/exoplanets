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

# Novelty check for update 2 (2026-10-08)

The 8 candidates from the TCE re-check and the 20–100 d search, and TIC 235005571.

| Source | Result |
|---|---|
| ExoFOP TOI list (8,148 rows) and CTOI list (5,137 rows) | No entry at any candidate period (harmonics 1/3–3) on these stars or TIC neighbours within 2.5′ |
| NASA Exoplanet Archive `pscomppars` | Only TOI-669 b (3.945 d) |
| SPOC TCE tables on MAST | By construction the TCE re-check signals are SPOC TCEs that have not become TOIs. TIC 269728501's 50.32 d transits include two that the Sectors 1–96 search listed as a 754.8 d TCE (15 × P) |
| ExoMiner++ (Valizadegan et al. 2025, Zenodo 15466293; 2026, Zenodo 17707413) | None of the 8 is an ExoMiner++ planet candidate. TIC 105506140's TCEs score 0.34 and 0.45 (threshold 0.5); the other seven have no ExoMiner++ entry at their periods |
| RAVEN, T16, LEO-Vetter M dwarfs (Kunimoto et al. 2025), Eschen et al. (2024) | No entry at any candidate period. On the TOI hosts, RAVEN, T16 and ExoMiner++ list only the TOI signals or their harmonics |
| arXiv: 2,037 astro-ph.EP papers (`literature.py`) | No TIC/TOI mention with a number within 0.3% of a candidate period (or half/double). TIC 257484419 is in the target list of the pterodactyls young-planet search (Fernandes et al. 2022) |
| NASA ADS full-text search on every TIC ID and host TOI (`ads_check.py`) | TIC 235005571 is an Algol-type eclipsing binary ([RNAAS 10, 220](https://ui.adsabs.harvard.edu/abs/2026RNAAS..10..220R)): rejected. A TOI-669 paper (2025MNRAS.544L..51B) matched the period string, but its text does not mention a 9.53 d signal. No other matches |
| Web, Zenodo, ExoFOP target pages and SIMBAD for each star and host TOI (2026-10-08) | TIC 300381700's 3.145 d signal was reported by Tovar Contreras ([Zenodo 23134068](https://zenodo.org/records/23134068), 2026-10-04) and TIC 257484419's 4.353 d signal by Ozturk ([Zenodo 23118499](https://zenodo.org/records/23118499), 2026-10-03), which does not mention the 18.06 d signal: both are independent recoveries. For TOI-669, Akana Murphy et al. (2023, AJ 166, 153, §10.4) see a weak radial-velocity signal at 9.61 ± 0.52 d (ΔAIC < 1, not adopted), which our 9.529 d transit signal matches. TIC 351339274 is GJ 774 A; its companion GJ 774 B (TIC 351339273, ΔT = 1.18) is 17.6″ away. TIC 105506140 is HD 85706; SPOC's TCEs on it have the same epoch at 0.70663 d. No other reports |

Not checked automatically: Zenodo, where two of these signals had been posted days earlier (found by a manual search), and SPOC's TOI vetting of the Sectors 1–96 TCEs, which has not been released.

# Novelty check for update 3 (2026-10-08)

The 21 faint M-dwarf signals that pass every check.

| Source | Result |
|---|---|
| ExoFOP TOI and CTOI lists, NASA Exoplanet Archive, SPOC TCEs, ExoMiner++, RAVEN, T16, LEO-Vetter M dwarfs, Eschen et al. (2024), arXiv scan | No entry at any candidate period |
| This project's published candidates | TIC 165827520 (2.0045 d) and TIC 383313006 (4.2518 d) are update 2 candidates found again |
| NASA ADS full text and Zenodo (`ads_check.py`) | No matches (TIC 165827520 matches papers on TOI-3494 by period string only) |
| ExoFOP target pages, SIMBAD, web search, Planet Hunters TESS Talk, TESS and Gaia DR3 eclipsing-binary tables, VizieR position search (2026-10-08) | TIC 417732194 (G 249-11) at 5.307419 d was posted on 5 October by the tess-transit-hunter project (GitHub, Comdex4/tess-transit-hunter); it is now read by `literature.py`. No reports for the other 18. TIC 102034645: the radio galaxy ESO 243-29 is 25″ away and adds ~39% of the flux. TIC 117798466: space motion matches the AB Doradus moving group. TIC 355815567 is GJ 3514 (17.6 pc) |

Not checked automatically: GitHub repositories (code search had not indexed the one above).
