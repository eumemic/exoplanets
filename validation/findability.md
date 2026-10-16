# Why earlier searches missed these signals

When could the counted full-sky candidates have been found, and why did the TESS pipelines not report them? The
numbers cover the <!--n:findability.candidates-->475<!--/n--> full-sky candidates in tiers A, B and N (the SNR ≥ 9 search), <!--n:findability.first-->399<!--/n--> from the first pass and <!--n:findability.research-->76<!--/n-->
from the QLP re-search; the tier L1 candidates are weaker still. (First written on 12 October 2026 for the 438
candidates of that day; updated on 13 October after the QLP re-search and the CTOI correction, on 14 and 15 October for the four and three candidates that
left tiers A, B and N, [details](fpp_combination.md) and [here](catalog_crossmatch.md), and on 15 October for the
TRICERATOPS rerun with single-cadence light curves and its corrections, [details](triceratops_single_cadence.md).) Each candidate's
transits come from the pass that found it. Files:
- [`findability_transits.csv.gz`](findability_transits.csv.gz): the search's per-transit depths, one row per transit,
  with the sector and that sector's light-curve source (SPOC 2-minute, TESS-SPOC or QLP);
- [`findability.csv`](findability.csv): per candidate, the SNR by data date and the best single-sector SNR, and
  [`findability.json`](findability.json), the counts quoted here (`pipeline/findability.py`, from unrounded SNRs);
- [`spoc_2min_recheck.csv`](spoc_2min_recheck.csv): the re-check in SPOC's 2-minute light curves
  (`pipeline/spoc_recheck.py`; the measurements, with the ephemeris each used, are in
  [`../results_public/products/spoc_2min.csv`](../results_public/products/spoc_2min.csv)).

The numbers below are filled in by the build (rules `findability` and `spoc_recheck` in `pipeline/rules.py`).

## The data are not new

For each candidate we combined only the transits observed by the end of a given sector (inverse-variance mean depth
over its error). This ignores how fewer sectors would change the detrending and the period search.

| Data through | Observed by | Candidates at SNR ≥ 9 |
|---|---|---|
| Sector 26, end of the prime mission | July 2020 | <!--n:findability.through.26.n-->54<!--/n--> (<!--n:findability.through.26.frac\|.0%-->11%<!--/n-->) |
| Sector 55, end of the first extended mission | September 2022 | <!--n:findability.through.55.n-->192<!--/n--> (<!--n:findability.through.55.frac\|.0%-->40%<!--/n-->) |
| Sector 69 | September 2023 | <!--n:findability.through.69.n-->284<!--/n--> (<!--n:findability.through.69.frac\|.0%-->60%<!--/n-->) |
| Sector 83 | September 2024 | <!--n:findability.through.83.n-->341<!--/n--> (<!--n:findability.through.83.frac\|.0%-->72%<!--/n-->) |
| Sector 96, end of the second extended mission | September 2025 | <!--n:findability.through.96.n-->414<!--/n--> (<!--n:findability.through.96.frac\|.0%-->87%<!--/n-->) |

<!--n:findability.late.n-->51<!--/n--> needed Sectors 97–104: <!--n:findability.late.research-->29<!--/n--> of the <!--n:findability.research-->76<!--/n--> from the QLP re-search, whose added QLP light curves are mostly from Sectors
94–104, and <!--n:findability.late.first-->22<!--/n--> of the <!--n:findability.first-->399<!--/n--> from the first pass (<!--n:findability.first_by_s96|.0%-->93%<!--/n--> of which reach SNR 9 with the data through Sector 96). Another <!--n:findability.below_9.n-->10<!--/n-->
come out just below SNR 9 (<!--n:findability.below_9.min|.1f-->8.8<!--/n--> to <!--n:findability.below_9.max|.1f-->9.0<!--/n-->) by this measure even with every sector; the search's threshold used the SNR of
its period search, which is slightly higher.

## The signals are weak in any one sector

The median candidate has transits in <!--n:findability.sectors.median|.0f-->5<!--/n--> sectors (10–90%: <!--n:findability.sectors.p10|.0f-->2<!--/n-->–<!--n:findability.sectors.p90|.0f-->17<!--/n-->), and its best sector reaches SNR <!--n:findability.best_sector.median|.1f-->6.6<!--/n-->. <!--n:findability.best_sector.below_7_1.n-->265<!--/n--> candidates
(<!--n:findability.best_sector.below_7_1.frac|.0%-->56%<!--/n-->) never reach 7.1, SPOC's detection threshold, in any single sector, and <!--n:findability.best_sector.below_9.n-->355<!--/n--> (<!--n:findability.best_sector.below_9.frac|.0%-->75%<!--/n-->) never reach 9. <!--n:findability.ffi_only.n-->386<!--/n--> (<!--n:findability.ffi_only.frac|.0%-->81%<!--/n-->) are on
stars observed only in full-frame images in the sectors with transits, which SPOC's multi-sector searches of 2-minute
targets do not include.

## The <!--n:spoc.candidates-->89<!--/n--> candidates with 2-minute data

We downloaded SPOC's 2-minute light curves of their transit sectors up to Sector 96, the range of SPOC's latest
multi-sector search, and re-measured the transits in the PDCSAP flux with three noise estimates:
- **white:** the point-to-point scatter, as our search uses;
- **correlated:** the same, scaled by how much more box-length bins of the out-of-transit flux scatter than white
  noise would;
- **SPOC's CDPP:** the noise SPOC reports for each light curve (the CDPP header values, interpolated to the box
  length).

Each SNR is the highest over box lengths of 0.5–9 h, since SPOC's search tries several durations. <!--n:spoc.few-->13<!--/n--> candidates have
fewer than two 2-minute transits through Sector 96, too few for a periodic search. For the other <!--n:spoc.rest-->76<!--/n-->:

| Estimate | Reach 7.1 | Highest |
|---|---|---|
| Our search's per-transit depths | <!--n:spoc.snr_search.reach-->20<!--/n--> | <!--n:spoc.snr_search.max\|.1f-->11.0<!--/n--> |
| Re-measured, white noise | <!--n:spoc.snr_white.reach-->13<!--/n--> | <!--n:spoc.snr_white.max\|.1f-->10.3<!--/n--> |
| Re-measured, correlated noise | <!--n:spoc.snr_red.reach-->7<!--/n--> | <!--n:spoc.snr_red.max\|.1f-->10.0<!--/n--> |
| Re-measured, SPOC's CDPP | <!--n:spoc.snr_cdpp.reach-->2<!--/n--> | <!--n:spoc.snr_cdpp.max\|.1f-->8.8<!--/n--> |

- The re-measured SNR with correlated noise is a median <!--n:spoc.ratio_red|.2f-->0.87<!--/n--> of our search's for the same transits. The search weights
  each point by the local scatter, and a signal found near a threshold has, on average, had noise add to its depth.
  The false-alarm rates were measured with the search's SNR, so the reliability estimates are unaffected, but our SNRs
  should not be compared one-to-one with SPOC's MES.
- The CDPP header values are root-mean-square averages over the whole light curve, so they overstate the noise for
  transits in quiet stretches.
- Of the <!--n:spoc.tces_on_star-->10<!--/n--> SPOC TCEs on these <!--n:spoc.candidates-->89<!--/n--> stars, <!--n:spoc.tces_on_transit|word-->one<!--/n--> has its epoch inside one of our transits: a Sectors 1–36 TCE at 35.21 d
  on TIC 200744242 (our 12.27 d candidate), whose period is 2.87 times ours, so its other events fall elsewhere
  ([`ctoi_matches.md`](ctoi_matches.md)). Otherwise SPOC did not report these signals at another period either.

For the <!--n:spoc.snr_cdpp.reach-->2<!--/n-->–<!--n:spoc.snr_red.reach-->7<!--/n--> candidates that reach 7.1, SPOC's search may have rejected the signal in its further statistical tests or
given less weight to transits near data gaps; we cannot tell which without running it. The strongest is TIC <!--n:spoc.strongest.TIC-->402339417<!--/n-->
(tier <!--n:spoc.strongest.tier-->B<!--/n-->, <!--n:spoc.strongest.P_d|.2f-->6.35<!--/n--> d, 2-minute data in Sectors <!--n:spoc.strongest.sectors-->2, 29 and 69<!--/n-->): SNR <!--n:spoc.strongest.snr_red|.1f-->10.0<!--/n--> with correlated noise, <!--n:spoc.strongest.snr_cdpp|.1f-->8.8<!--/n--> with SPOC's CDPP.
