# TRICERATOPS and the centroid ratio: combining run means (14 October 2026)

TRICERATOPS does not use the difference-image centroid, so for signals with a capable neighbour within 30″ we weight
its nearby-star scenarios by the centroid Bayes factor BF and renormalise (README, tier N):

    FPP_c = 1 − (1 − FPP) / Z,   NFPP_c = (NFPP / BF) / Z,   Z = 1 − NFPP + NFPP / BF

`FPP_gc` and `NFPP_gc` are the same with the Gaia-constrained runs. Each value comes from ten TRICERATOPS runs.

## What was wrong

We used the mean FPP of the ten runs together with the largest NFPP of the ten. NFPP is part of FPP within each run,
but when the runs disagree, the largest NFPP can exceed the mean FPP. With BF > 1 the combination then goes negative:
before this correction 22 rows had a negative `FPP_c` or `FPP_gc` (15 of them counted candidates), down to −0.47.
In other rows the same mismatch lowered `FPP_c` without making it negative.

## The correction

`FPP_c` and `FPP_gc` now combine the means of the same runs' FPP and NFPP. `NFPP_c` and `NFPP_gc` still use the
largest NFPP, a conservative value for the limit NFPP_c < 0.1. The per-run values come from the TRICERATOPS logs
(`run k: FPP=… NFPP=…`), matched to each row by its mean FPP and largest NFPP; `pipeline/fpp.py` now also writes the
per-run NFPP to its JSON output, and `pipeline/fpp_combine.py` holds the combination (`tests/test_fpp_combine.py`).

- 2,346 of the 2,367 rows with TRICERATOPS results and all 1,299 with Gaia-constrained runs were recomputed. The other
  21 rows, none of them counted, have no per-run values in their logs and keep the earlier values; none is negative.
- 786 values of `FPP_c` and 351 of `FPP_gc` change by more than 0.0015 (smaller differences come from the rounding of
  `BF` in the catalog and are left as they were). None is negative now.
- The median `FPP_c` of the counted candidates goes from 0.041 to 0.042 and the median `FPP_gc` from 0.012 to 0.013.
  301 counted candidates now meet the TRICERATOPS validation thresholds apart from imaging (FPP < 0.015 and
  NFPP < 0.001), against 305 before.

## Tier changes

Two counted candidates now fail FPP < 0.5, both narrowly and within the run-to-run scatter of the threshold:

| TIC | Period (d) | Was | Now | FPP_gc before → after |
|---|---|---|---|---|
| 238187210 | 26.026892 | B | C (TRICERATOPS) | 0.026 → 0.504 |
| 387221443 | 15.196655 | N | likely nearby FP | 0.470 → 0.502 |

Two signals already outside the counted tiers fail the limit too and, being on the neighbour route, become likely
nearby false positives: TIC 310418454 (0.571 d, was tier C for RUWE) and TIC 241928959 (3.531 d, was tier C as grazing).

A check of every tier against its rules with the new values found two tier N candidates from the QLP re-search that
are grazing, which tier N excludes: TIC 279052784 (1.166 d, b = 0.93) and TIC 188129917 (3.258 d, b = 1.02). They move
to tier C. No tier C row has lost its reason, and no tier L row now qualifies for tier L1.

The counted total goes from 665 to 661: 603 full-sky candidates (20 A, 296 B, 174 N, 113 L1) and 58 from the earlier
searches. The registry keeps the four rows that left the counted tiers, with their new tier.

## Open

TIC 46806792 (1.968 d, 3.1 R⊕, MES 18.4) is listed as a likely nearby false positive although it passes the limits
(FPP_gc 0.019, NFPP_gc 0.019). It has no transit fit, so the grazing check cannot be made, and it has not had the
per-sector centroid test. It stays where it is until both are done.
