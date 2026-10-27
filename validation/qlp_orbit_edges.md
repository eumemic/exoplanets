# QLP Sectors 94–104: orbit-edge ramps, and the missing Sectors 74–79

On 13 October 2026 we prepared a re-search of the full-sky stars whose QLP light curves the search had lost or
never had. Two problems turned up on the way: a systematic at the edges of each orbit in QLP Sectors 94–104, and
QLP Sectors 74–79 missing from our light-curve index ([issue #9](https://github.com/eumemic/exoplanets/issues/9)).
This note records both, the mask that fixes the first, and the pilot that tested it.

## The ramps

After PR #6 restored the QLP products whose uncertainty columns are empty ([`qlp_missing_errors.md`](qlp_missing_errors.md)),
a pilot re-search of 9,112 random affected stars found 399 new signals passing the full-sky pre-filters. 43% of
them had periods of 12–14 days, against 3% of the original search's signals on the same stars, and 73% of their
signal (SNR²) came from transit events within 1.5 days after an orbit's first cadence or 1 day before its last
(19% for the same events shifted at random by up to ±6 days).

The cause is a ramp in QLP's systematics-corrected flux (`SYS_RM_FLUX`) at the start and end of each orbit's data
in these sectors. Detrending removes most of it and leaves a dip (sometimes a bump) a few hours long, and since it
repeats every orbit (~13.7 days) the search folds it into a signal. We measured the detrended residuals of every
QLP light curve of the pilot stars in 2-hour bins from each data edge (`profile` mode of the pilot script). Fraction
of edges whose bin mean is below −5σ:

| Edge | First 2 h | 2–4 h | 4–6 h | 6–8 h | Baseline (24–46 h) |
|---|---|---|---|---|---|
| Orbit start, Sectors 94–104, recovered products | 57% | 52% | 41% | 22% | 0.8% |
| Orbit start, Sectors 94–104, other products | 29% | 28% | 23% | 13% | 2.5% |
| Orbit end, Sectors 94–104, recovered products | 25% | 19% | 14% | 8% | 0.6% |
| Orbit end, Sectors 94–104, other products | 16% | 12% | 10% | 5% | 0.5% |
| Mid-orbit pauses, Sectors 94–104 | 2–3% | 2–3% | 2% | 2% | 0.6–0.8% |
| Data starts after long gaps, Sectors 56–93 | 5% | 3% | 2% | 2% | 0.6% |

Every QLP product from these sectors has the ramps; the products with empty uncertainty columns have them more
strongly, which is why the original search (which dropped those products) mostly escaped them. Quality flags often
remove the first 0.4–0.8 days of an orbit, and the ramp follows the first unflagged cadence, so the mask counts from
the first cadence an orbit has in the light curve rather than from the scheduled orbit start.

## The mask

`load_star` (`pipeline/common.py`) drops, in QLP light curves of Sectors 94–104, the first 1.0 day and the last
0.5 day of each orbit's cadences (`mask_qlp_orbit_edges`; `EXO_QLP_ORBIT_MASK` and `EXO_QLP_ORBIT_MASK_END` set
the lengths). Orbits are identified from the first cadence of each QLP `ORBITID` in these sectors
(`QLP_ORBIT_STARTS`, 26 orbits; the TESS orbit table mislabels Sectors 102–103). The mask removes 11–16% of the
cadences of these light curves (median 14% in 36 of them). Tests: `tests/test_qlp_orbit_mask.py`.

## Pilot

Same 9,112 stars, searched as the full-sky search does (`run_shard.py` / `search.py`, stack-slide, three signals per
star), with mask A (1.0 d / 0.5 d) and a longer mask B (1.5 d / 1.0 d):

| | Original search | Unmasked | Mask A | Mask B |
|---|---|---|---|---|
| Signals passing the pre-filters, SNR ≥ 9 | 1,309 | 1,319 | 1,265 | 1,225 |
| of which new (no original signal at the period or a simple harmonic) | — | 399 | 414 | 390 |
| new ones at 12–14 d | — | 43% | 7% | 9% |
| their SNR² from orbit edges (shifted control ≈ 20%) | — | 73% | 4% | 0% |
| Inverted light curves: false alarms per 1,000 stars, SNR ≥ 9 / 7.5–9 | 142 / 76 (old data) | — | 138 / 67 | 140 / 67 |
| Injected transits detected (SNR ≥ 9, pre-filters) | 17.8% (old data) | 26.4% | 32.1% | 30.3% |
| the same at 12–14 d | 10.5% | 16.6% | 22.4% | 22.4% |
| Original signals that passed vetting, found again | — | 29 of 31 | 29 of 31 | 29 of 31 |

Each star got one injected transit (period log-uniform in 0.5–30 days, target SNR 6–16), searched in four versions
of its light curves: old (without the recovered products), unmasked, A and B. Mask A detects the most in every
period and SNR bin (paired: 770 injections found only with A against 251 only unmasked, and 1,459 against 158 with
the old data), keeping a median 95% of the in-transit cadences. We use mask A.

Two side effects:
- The pre-filter that rejects periods matching a sector's dominant variability period (`rot_alias`) can now fire
  on a strong transit, because with the ramps gone the transit itself dominates that sector's periodogram
  (21 strong signals among the pilot stars). The injections include this effect.
- Re-searching a star can lose a signal the original search found, mask or not (for example TIC 76894546, where the
  search locked on four times the period). So the re-search adds signals; it does not replace the original ones.

The counted candidates with Sector 94–104 transits were searched the same way. One of them, TIC 141937667
(13.36 d, tier S, SNR 9.8), disappears with the mask: 59% of its SNR² came from orbit edges.

## QLP Sectors 74–79

MAST re-delivered QLP Sectors 74–79 as version 2 after correcting their timestamps, and `index_s3.py` matched only
version 1 ([issue #9](https://github.com/eumemic/exoplanets/issues/9), [PR #12](https://github.com/eumemic/exoplanets/pull/12)),
so the full-sky search had no QLP light curves in those sectors. Listing them with PR #12's patterns gives
1,294,436 products for 651,413 of the full-sky stars; 995,781 of them fill a sector for which the star had no
light curve at all, on 498,744 stars. On 3,000 of those stars, the data edges of Sectors 74–79 look like those of
other sectors (no mask needed), the new signals are spread in period like other new signals, and 16 of the 18
original signals that passed vetting are found again.

## The re-search

We re-searched 1,770,906 stars (44% of the full sky): the 1,272,162 with a QLP light curve in Sectors 94–104 and the
498,744 that gain Sectors 74–79. We also re-ran the 351,954 of them that are in the inverted-light-curve calibration.
The search, vetting and pixel checks were those of the original full-sky run (`run_shard.py`, `collect.py` at
SNR ≥ 7.5, `vet.py`, `shortlist.py`, `followup.py`, `finalize_shard.py`), with the mask applied in `load_star`.
Signals that match a row of our published tables are labelled as ours by the vetting and were not processed again.

| | Count |
|---|---|
| Signals passing the pre-filters, SNR ≥ 7.5 | 415,943 |
| New signals passing every LEO-Vetter test (no match to known objects) | 7,640 |
| of those, after the cuts (MES ≥ 7.1, per-sector χ²/dof ≤ 5, Rp ≤ 20 R⊕) and the pixel checks: clean, fitted | 302 (122 at SNR ≥ 9, 180 at SNR 7.5–9) |
| the same, flagged only for a capable neighbour within 15″ (SNR ≥ 9; the tier N route) | 262 |

None of the 564 is mentioned with its period in ADS full text or Zenodo. 165 of the 302 clean signals had been found
by the original search below the bar (SNR below 9 or a failed check); the added data lifted them over it. All 564
went through the same downstream checks as the original candidates: TRICERATOPS (default and with Gaia/MOLUSC limits),
the centroid Bayes factor, per-sector centroids, the binary check and the false-alarm classifier, retrained with the
re-searched real and inverted signals (see [`false_alarm_classifier.md`](false_alarm_classifier.md)). Tiers follow the
same rules as before; the counts are in the README.
