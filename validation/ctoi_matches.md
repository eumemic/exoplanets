# Community TOIs under another period

On 13 October 2026, while re-measuring the counted candidates' transits in SPOC 2-minute light curves for a write-up,
we found SPOC and community detections whose epochs fall inside our transits. Our known-signal check (`known.py`)
compared periods only: a known object matched if its period was within 0.3% of ours times 1/3, 1/2, 2/3, 1, 3/2, 2 or
3. That misses two kinds of report of the same transits:
- community TOIs (CTOIs) from single-transit searches, which have no period;
- CTOIs and SPOC threshold-crossing events (TCEs) with a long-period alias, built from two or three of our transits.

## The check

`known.epoch_check` lists the TOIs, CTOIs and TCEs on the star or within 2.5′ whose epoch falls inside one of our
transits and whose period is missing or within 0.1% of p/q times ours (q ≤ 7). The window is half our transit duration
plus three times the period error propagated to the known epoch. In `collect.py` such a match counts like a period match:
a TOI or CTOI on the star makes the signal known, and a match on a neighbour makes it a neighbour's signal. A SPOC TCE
matched only by epoch leaves the signal new and is listed in `known_detail`: an unpromoted TCE is not a report (the TCE
re-check in the README treats TCEs the same way), and a TCE with an alias period could not be recovered by
re-measuring it at that period. Tests: `tests/test_known_epoch.py`.

Run on all 2,990 full-sky signals with the ExoFOP lists of 7 October 2026, it finds 10 CTOI matches and one TCE match
(on a star that also has a matching CTOI). We also checked by hand the 21 CTOIs on the stars of tiers M, S, C, N, L1
and L and of the earlier candidates: the other 11 are other signals, with epochs hours to days away from our transits.

## Relabelled

All ten CTOIs were posted before our first release. The ten signals are now labelled `reported`, with the CTOI in the
new catalog column `reported_as`, and their candidate folders are removed (they remain in the repository history).
The seven registered ones keep their rows in the prediction files, with tier `reported`.

| TIC | Our period (d) | Tier before | CTOI | CTOI period | Source |
|---|---|---|---|---|---|
| 275267824 | 16.818 | S (QLP re-search) | 275267824.01 | 739.958 d (44 times ours) | Salinas et al. 2025, MNRAS 538, 2031 |
| 266376971 | 19.826 | B | 266376971.01 | single transit | Salinas et al. 2025 |
| 334575487 | 21.953 | B | 334575487.01 | 9.408 d (3/7 of ours) | RAVEN (Lafarga et al. 2026) |
| 224279805 | 22.984 | S (QLP re-search) | 224279805.01 | single transit (2020); also a SPOC Sectors 1–69 TCE at 1080.26 d (47 times ours) | single-transit search |
| 99919551 | 23.324 | B | 99919551.01 | 163.189 d (7 times ours) | Salinas et al. 2025 |
| 147898114 | 24.567 | B | 147898114.01 | single transit | Salinas et al. 2025 |
| 101824521 | 29.632 | B | 101824521.01 | single transit | Hawthorn et al. 2024 (arXiv:2310.17268) |
| 157119927 | 21.856 | C (grazing) | 157119927.01 | single transit | Hawthorn et al. 2024 |
| 196601989 | 23.831 | C (grazing) | 196601989.01 | single transit | TESS Single Transit Planet Candidate working group, 2025 |
| 409696823 | 24.950 | C (grazing) | 409696823.01 | single transit | TESS Single Transit Planet Candidate working group, 2025 |

Our periods may still be useful for these CTOIs: four of the counted seven had no period and three a different one.

The counted full-sky candidates fall from 613 to 606 (tier S from 303 to 296), and the total from 671 to 664.

## TCE matches that stay counted

- WASP-166 (TIC 408310006), 27.017 d, tier M (earlier searches): SPOC's Sectors 1–96 search listed two of its
  transits as a 729.46 d TCE, 27 times this period. Like TIC 269728501 (50.32 d, a 754.79 d TCE, 15 times; see the
  README), it stays counted.
- TIC 200744242, 12.270 d, tier S (QLP re-search): one event of a SPOC Sectors 1–36 TCE at 35.21 d (ExoMiner++ score
  0.01) falls on one of our transits, but the period ratio (2.87) is not a simple fraction and the TCE's other events
  do not; it stays counted.
