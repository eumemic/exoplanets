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
  NFPP < 0.001), against 305 before. Since 15 October these counts leave out candidates larger than 8 R⊕, to which the
  thresholds do not apply (Giacalone et al. 2021): 288.

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

As of 15 October 2026 both are done. The transit fit gives b = 0.11 and 3.06 R⊕. The per-sector centroids (9 sectors,
mean offset 10.9″) reject the target (p = 1.7 × 10⁻⁵) and fit TIC 46806773, 10.8″ away (p = 0.99), so under the
centroid rule it stays a likely nearby false positive, with `centroid_flag` p < 0.001. Its values after the
single-cadence TRICERATOPS rerun are `FPP_gc` 0.005 and `NFPP_gc` 0.0064.

## The neighbour likelihood at low SNR (18 October 2026)

The neighbour hypothesis of BF uses the offsets of TOI planets in the same MES range, shifted to the neighbour's
separation in a random direction. On issue #2 the per-sector centroids of signals from neighbours turned out to be
pulled toward the target at low SNR ([`centroid_sectors.md`](centroid_sectors.md)); if BF's offset were pulled the same
way, BF would favour the target and `NFPP_c` would be too low. On the 202 signals caused by TOIs on neighbouring stars
(calibration set of [`centroid_sectors.md`](centroid_sectors.md)), the model predicts the measured offsets: in each MES
range the median measured offset is 0.99–1.01 times the model's, and the model puts on average 0.47 ± 0.02 of its
probability below the measured offset for MES < 20 (0.52 for MES 7.1–12; 0.5 if calibrated). Fitted as a pull of the
neighbour's position toward the target by a fraction f, the offsets give f ≈ 0.02, with 95% upper limits of 0.06 for
neighbours within 15″ and 0.16 at 15–30″ for MES < 20. BF uses the offset in the best-quality sector, where the pull
seen in the per-sector test, which comes from sectors with little signal, does not appear.

Recomputing BF for the 406 counted rows whose inputs are available (29 others lack them) with f = 0.02 moves one
candidate across NFPP 0.1 (TIC 288979445, 0.099 to 0.103) and takes two at NFPP 0.0010 off the validation level. With
the upper limits, 6 counted candidates, all at NFPP 0.07–0.099, cross NFPP 0.1 (TIC 253576811, 288979445, 289089130,
343262577, 397216278 and 410449566) and 7 leave the validation level. The catalog keeps BF as calibrated; the tiers of
these candidates depend on the neighbour model at that level.
