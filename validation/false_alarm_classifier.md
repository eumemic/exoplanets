# False-alarm classifier

`pipeline/fa_classifier.py` separates signals of the real full-sky search from false alarms found in
inverted light curves. It decides tier L1 (SNR 7.5–9 signals counted as candidates) and gives every signal
a score (`fa_score` in `results_public/candidates_allsky.csv`).

## Data

[`false_alarm_classifier_table.csv.gz`](false_alarm_classifier_table.csv.gz) has one row per signal that
passed every LEO-Vetter test, MES ≥ 7.1, per-sector χ²/dof ≤ 5 and Rp ≤ 20 R⊕:

- 13,453 signals from the real search of 4,039,203 stars (both SNR bands, all pixel-check outcomes). These
  are a mixture: astrophysical signals (planets and eclipsing binaries, including blends) and false alarms.
- 1,033 signals from the inverted light curves of 798,769 random full-sky stars, in two independent samples
  of 399,408 and 399,361 stars (`inv_set` 1 and 2). In an inverted light curve every dip the pipeline finds
  is noise or a systematic.

The features are the search statistics (SNR, MES, SDE, duration against the expected duration, number of
good transits, the largest single-event fraction, odd-even and secondary significance, per-sector depth
consistency, early- against late-sector SNR), LEO-Vetter's continuous metrics (CHI, DMM, Fred, SHP, chases,
the significance of the primary, secondary and tertiary events, the sine fit, trapezoid-fit shape), and the
star's T magnitude, contamination ratio, radius and effective temperature. The flux-weighted centroid shift
and LEO-Vetter's positive-event significance are left out, because their values could differ between real
and inverted light curves for reasons other than the signal being noise.

## Model

A gradient-boosted tree classifier (scikit-learn `HistGradientBoostingClassifier`), with the inverted
signals weighted by the ratio of stars searched, so that the weighted classes estimate expected counts in
the real search. Every score is out of fold (repeated 5-fold cross-validation): no signal is scored by a
model trained on it. Because the real class contains false alarms, the score ranks signals by how unlike
noise they are; it is not itself a probability.

## Purity of tier L1, measured on independent stars

The hold-out model is trained on the real signals and the first inverted sample only. The second inverted
sample, from stars the model never saw, then shows how many false alarms pass each score cut. For the 382
SNR 7.5–9 signals that passed every check, of which 314 are expected false alarms:

| Score cut | Signals selected | Expected false alarms | Purity |
|---|---|---|---|
| 0.70 | 158 | 53 | 67% |
| 0.75 | 109 | 25 | 77% |
| **0.80** | **69** | **6** | **92%** |
| 0.85 | 38 | 2 | 94% |
| 0.90 | 16 | 0 | 100% |

Tier L1 takes the cut at 0.80 (`score_h` in [`false_alarm_classifier_scores.csv.gz`](false_alarm_classifier_scores.csv.gz)),
which matches the purity of tier B (about 91–94%). Selected signals must also pass the grazing, RUWE,
binary and literature checks and TRICERATOPS (FPP < 0.5, NFPP < 0.1), like every other counted candidate.

Caveats: the expected false alarms above the cut rest on a handful of held-out events, so the purity is
uncertain by several percent; and repeated runs give individual scores that differ by up to ~0.05, so a
few signals near the cut can move in or out. To reproduce the scores:

```bash
cd pipeline
../.venv/bin/python fa_classifier.py ../validation/false_alarm_classifier_table.csv.gz \
    --stars-real 4039203 --stars-inv 399408 399361 --out ../validation/false_alarm_classifier_scores.csv.gz
```
