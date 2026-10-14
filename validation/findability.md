# Why earlier searches missed these signals

On 12 October 2026 we checked when the counted full-sky candidates could have been found, and why the TESS pipelines
did not report them. The numbers cover the 438 full-sky candidates in tiers A, B and N (the SNR ≥ 9 search); the
tier L1 candidates are weaker still. Later the same day, the per-sector centroid test moved 18 of the 438 out of the
counted tiers ([`centroid_sectors.md`](centroid_sectors.md)); the numbers here include them, and for the remaining 420
the percentages are within one point of these. Files:
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
| Sector 26, end of the prime mission | July 2020 | 62 (14%) |
| Sector 55, end of the first extended mission | September 2022 | 204 (47%) |
| Sector 69 | September 2023 | 287 (66%) |
| Sector 83 | September 2024 | 345 (79%) |
| Sector 96, end of the second extended mission | September 2025 | 407 (93%) |

Only 24 needed Sectors 97–104, but this understates what the newest sectors contribute: the light curves used
here lacked many QLP products from Sectors 94–97 and 101–104 (24–82% in the earlier searches), which our reader
dropped because their
uncertainty columns are empty (found on 13 October; PR #6). The other 7 come out at SNR 8.9–9.0 by this measure even with every sector; the search's
threshold used the SNR of its period search, which is slightly higher.

## The signals are weak in any one sector

The median candidate has transits in 5 sectors (10–90%: 2–17), and its best sector reaches SNR 7.0. 223 candidates
(51%) never reach 7.1, SPOC's detection threshold, in any single sector, and 315 (72%) never reach 9. 360 (82%) are on
stars observed only in full-frame images in the sectors with transits, which SPOC's multi-sector searches of 2-minute
targets do not include.

## The 78 candidates with 2-minute data

We downloaded SPOC's 2-minute light curves of their transit sectors up to Sector 96, the range of SPOC's latest
multi-sector search, and re-measured the transits in the PDCSAP flux with three noise estimates:
- **white:** the point-to-point scatter, as our search uses;
- **correlated:** the same, scaled by how much more box-length bins of the out-of-transit flux scatter than white
  noise would;
- **SPOC's CDPP:** the noise SPOC reports for each light curve (the CDPP header values, interpolated to the box
  length).

Each SNR is the highest over box lengths of 0.5–9 h, since SPOC's search tries several durations. 10 candidates have
fewer than two 2-minute transits through Sector 96, too few for a periodic search. One is TIC 266376971 (T = 8.3;
3.3 R⊕, 19.8 d), whose other two 2-minute transits came in Sectors 99 and 100 (relabelled reported on 13 October:
it is the single-transit CTOI 266376971.01; see [`ctoi_matches.md`](ctoi_matches.md)). For the other 68:

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
- None of the 8 SPOC TCEs on these 78 stars has its epoch inside one of our transits, so SPOC did not report these
  signals at another period either.

For the 2–7 candidates that reach 7.1, SPOC's search may have rejected the signal in its further statistical tests or
given less weight to transits near data gaps; we cannot tell which without running it. The strongest is TIC 402339417
(tier B, 6.35 d, 2-minute data in Sectors 2, 29 and 69): SNR 10.0 with correlated noise, 8.8 with SPOC's CDPP.
