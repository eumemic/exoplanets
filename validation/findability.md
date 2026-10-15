# Why earlier searches missed these signals

When could the counted full-sky candidates have been found, and why did the TESS pipelines not report them? The
numbers cover the 490 full-sky candidates in tiers A, B and N (the SNR ≥ 9 search), 413 from the first pass and 77
from the QLP re-search; the tier L1 candidates are weaker still. (First written on 12 October 2026 for the 438
candidates of that day; updated on 13 October after the QLP re-search and the CTOI correction, and on 14 October for the four candidates that
left tiers A, B and N, [details](fpp_combination.md).) Each candidate's
transits come from the pass that found it. Files:
- [`findability_transits.csv.gz`](findability_transits.csv.gz): the search's per-transit depths, one row per transit,
  with the sector and that sector's light-curve source (SPOC 2-minute, TESS-SPOC or QLP);
- [`findability.csv`](findability.csv): per candidate, the SNR by data date and the best single-sector SNR
  (`pipeline/findability.py`);
- [`spoc_2min_recheck.csv`](spoc_2min_recheck.csv): the re-check in SPOC's 2-minute light curves
  (`pipeline/spoc_recheck.py`).

## The data are not new

For each candidate we combined only the transits observed by the end of a given sector (inverse-variance mean depth
over its error). This ignores how fewer sectors would change the detrending and the period search.

| Data through | Observed by | Candidates at SNR ≥ 9 |
|---|---|---|
| Sector 26, end of the prime mission | July 2020 | 59 (12%) |
| Sector 55, end of the first extended mission | September 2022 | 206 (42%) |
| Sector 69 | September 2023 | 296 (60%) |
| Sector 83 | September 2024 | 354 (72%) |
| Sector 96, end of the second extended mission | September 2025 | 428 (87%) |

52 needed Sectors 97–104: 30 of the 77 from the QLP re-search, whose added QLP light curves are mostly from Sectors
94–104, and 22 of the 413 from the first pass (93% of which reach SNR 9 with the data through Sector 96). Another 10
come out just below SNR 9 (8.8 to 9.0) by this measure even with every sector; the search's threshold used the SNR of
its period search, which is slightly higher.

## The signals are weak in any one sector

The median candidate has transits in 5 sectors (10–90%: 2–17), and its best sector reaches SNR 6.7. 270 candidates
(55%) never reach 7.1, SPOC's detection threshold, in any single sector, and 362 (74%) never reach 9. 400 (82%) are on
stars observed only in full-frame images in the sectors with transits, which SPOC's multi-sector searches of 2-minute
targets do not include.

## The 90 candidates with 2-minute data

We downloaded SPOC's 2-minute light curves of their transit sectors up to Sector 96, the range of SPOC's latest
multi-sector search, and re-measured the transits in the PDCSAP flux with three noise estimates:
- **white:** the point-to-point scatter, as our search uses;
- **correlated:** the same, scaled by how much more box-length bins of the out-of-transit flux scatter than white
  noise would;
- **SPOC's CDPP:** the noise SPOC reports for each light curve (the CDPP header values, interpolated to the box
  length).

Each SNR is the highest over box lengths of 0.5–9 h, since SPOC's search tries several durations. 13 candidates have
fewer than two 2-minute transits through Sector 96, too few for a periodic search. For the other 77:

| Estimate | Reach 7.1 | Highest |
|---|---|---|
| Our search's per-transit depths | 21 | 11.0 |
| Re-measured, white noise | 14 | 10.3 |
| Re-measured, correlated noise | 7 | 10.0 |
| Re-measured, SPOC's CDPP | 2 | 8.8 |

- The re-measured SNR with correlated noise is a median 0.87 of our search's for the same transits. The search weights
  each point by the local scatter, and a signal found near a threshold has, on average, had noise add to its depth.
  The false-alarm rates were measured with the search's SNR, so the reliability estimates are unaffected, but our SNRs
  should not be compared one-to-one with SPOC's MES.
- The CDPP header values are root-mean-square averages over the whole light curve, so they overstate the noise for
  transits in quiet stretches.
- Of the 10 SPOC TCEs on these 90 stars, one has its epoch inside one of our transits: a Sectors 1–36 TCE at 35.21 d
  on TIC 200744242 (our 12.27 d candidate), whose period is 2.87 times ours, so its other events fall elsewhere
  ([`ctoi_matches.md`](ctoi_matches.md)). Otherwise SPOC did not report these signals at another period either.

For the 2–7 candidates that reach 7.1, SPOC's search may have rejected the signal in its further statistical tests or
given less weight to transits near data gaps; we cannot tell which without running it. The strongest is TIC 402339417
(tier B, 6.35 d, 2-minute data in Sectors 2, 29 and 69): SNR 10.0 with correlated noise, 8.8 with SPOC's CDPP.
