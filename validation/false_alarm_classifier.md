# False-alarm classifier

`pipeline/fa_classifier.py` separates signals of the real full-sky search from false alarms found in
inverted light curves. It decides tier L1 (SNR 7.5–9 signals counted as candidates) and gives every signal
a score (`fa_score` in `results_public/candidates_allsky.csv`).

## Data

[`false_alarm_classifier_table.csv.gz`](false_alarm_classifier_table.csv.gz) has one row per signal that
passed every LEO-Vetter test, MES ≥ 7.1, per-sector χ²/dof ≤ 5 and Rp ≤ 20 R⊕:

- 13,453 signals from the real search of 4,039,203 stars (both SNR bands, all pixel-check outcomes). These
  are a mixture: astrophysical signals (planets and eclipsing binaries, including blends) and false alarms.
- 1,033 signals from the inverted light curves of 798,769 random full-sky stars, in two inverted-search samples
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
the real search. The default (`--split star`) uses repeated 5-fold `StratifiedGroupKFold` cross-validation,
grouping all signals with the same TIC: no star is scored by a fold model trained on another signal
from that star. The released scores used row-stratified folds, available as `--split signal`; that mode
excludes the scored signal itself, but can train on other signals from its star. Because the real class contains false alarms, the score ranks signals by how unlike
noise they are; it is not itself a probability.

## Released tier L1 purity estimate (legacy signal split)

The released holdout model trained on real signals and the first inverted sample, then scored the
second inverted sample. Three second-sample TICs also occur in the real training rows
(101524187, 192801224, 444842776), so this was not strictly independent at star level. None of those
three inverted rows passes the released 0.80 cut. Row cross-validation also allows signals from the
same star to occur on both sides of a fold (13,975 training signals on 13,886 TICs).

The following table describes the released scores, not a rerun with grouped folds. For the 382
SNR 7.5–9 clean signals, the baseline expected false-alarm count is
62 × 4,039,203 / 798,769 = 313.5207:

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

The released ~92% estimate transfers the retention fraction from **all pixel classes** in the
low-band second sample (5/268 at 0.80) to the clean baseline count: 313.5207 × 5/268 = 5.8493
expected false alarms among 69 selected signals. All five retained inverted signals are non-clean.
The directly clean-conditioned sensitivity is 0/35, whose plug-in estimate is zero; zero observed
events does not establish zero contamination. Pooling is a transport assumption, not automatically
invalid, but the clean-only sample gives little precision to assess it.

At 0.80, descriptive 95% Wilson binomial intervals are 0.80–4.29% for 5/268 and 0–9.89% for 0/35.
Scaling by the baseline count gives approximately 2.5–13.5 and 0–31.0 expected false alarms,
respectively. These intervals assume independent events and are conditional on the baseline rate;
they ignore its uncertainty, repeated signals on a star, model uncertainty and selection of the cut.
The script reports both sensitivities and intervals at each cut. A displayed point purity of 100%
at a zero-event cut should not be read as certainty.

## Star-disjoint validation and reproduction

The default reserves **all rows** whose TIC appears among the published inverted-sample-2 signal
rows, including any real or sample-1 siblings, and excludes those TICs from holdout training. The full
list of 399,361 searched stars is not in this input; disjointness is guaranteed for the scored holdout TICs. The remaining training rows use
TIC-grouped folds. Reserved rows are still scored by every fold model, so output row coverage and
columns are preserved. The full-data `score` also uses grouped folds. Grouped reruns can change
individual scores and cut membership; this is validation sensitivity, not evidence that every changed
candidate is a false alarm. Published scores, catalogs and tiers are unchanged by this code update.

The holdout score still averages 15 models (five folds × three repeats), while ordinary out-of-fold
scores average three. This pre-existing ensemble-size difference and limited clean holdout size remain
limitations of the comparison.

To reproduce the released algorithm explicitly (write exploratory outputs under ignored `results/`):

```bash
mkdir -p results
.venv/bin/python pipeline/fa_classifier.py validation/false_alarm_classifier_table.csv.gz \
    --stars-real 4039203 --stars-inv 399408 399361 --split signal \
    --out results/false_alarm_classifier_legacy.csv.gz
```

Use `--split star` (or omit `--split`) for star-disjoint validation, with a separate output filename.
Dependencies and numerical libraries can affect exact floating-point reproduction; use the versions
in `requirements.txt`. Regression checks require only the classifier dependencies:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m unittest discover -s tests -v
```

## Verification on the published inputs

On the published 14,486-row table, the legacy signal-split run exactly reproduces the archived `score`
and `score_h` columns (maximum absolute difference 0.0). With grouped folds, train/holdout TIC overlap
falls from 3 to 0, and shared TICs across the 15 folds fall from 22–34 per fold to 0. At `score_h` ≥ 0.80,
the clean low-band selection changes from 69 to 70; 15 signals enter and 14 leave relative to the archived
subset. This reflects changed fold assignments and training, not individual false-positive verdicts or
catalog retiering. The pooled inv2 retention changes from 5/268 to 3/268; clean-conditioned retention
remains 0/35. Both runs score all 14,486 rows. These results used numpy 2.5.3, pandas 2.3.3, scipy 1.18.1
and scikit-learn 1.9.1. Six regression tests passed.

## Re-selection of tier L1 (13 October 2026)

Tier L1 now uses the star-grouped hold-out scores
([`false_alarm_classifier_scores_star.csv.gz`](false_alarm_classifier_scores_star.csv.gz), `--split star`); the
released scores stay in [`false_alarm_classifier_scores.csv.gz`](false_alarm_classifier_scores.csv.gz). The catalog's
`fa_score` column is now the star-grouped out-of-fold score, which changes the low-score flag (`fa_flag`) from 34 to
33 counted candidates.

At the 0.80 cut, 70 clean SNR 7.5–9 signals are selected instead of 69. Eight tier L1 candidates fall below it and
leave: TIC 268436976, 458482761, 233948407 and 346744851 go to tier L (MES ≥ 9), and TIC 407505256, 90956394,
307983022 and 270355278 to likely false alarm. Of the 15 signals that now reach the cut, 3 are grazing (b ≥ 0.9) and
keep their tiers. The other 12 got TRICERATOPS runs (default and with the Gaia limits) and per-sector centroids:
11 pass and join tier L1 (TIC 14598932, 33174398, 71214705, 124382169, 170655214, 199572650, 219694586, 236383404,
308026772, 422443793 and 432163050; TIC 71214705 carries the centroid flag, p = 0.009), and TIC 34228880 stays in
tier L with NFPP 0.12. Tier L1 now has 53 candidates.

These signals were measured with the light curves of the release, which lacked many QLP products from Sectors 94–97
and 101–104 (PR #6). An independent analysis submitted as PR #7, not yet reviewed, reports that the eight leaving candidates other than
TIC 90956394 keep consistent dips, and that TIC 90956394's restored Sector 94 data allow a 13.3 d period (twice the
catalog's), which would point to an eclipsing binary.


## Retraining after the QLP re-search (13 October 2026)

The QLP re-search ([`qlp_orbit_edges.md`](qlp_orbit_edges.md)) changed the light curves of 1,770,906 full-sky stars and
of 351,954 stars of the inverted-light-curve sample. We rebuilt the table with the same features and cuts: the real
rows of re-searched stars (5,970) were replaced by their re-search rows (6,033), and the inverted rows of re-searched
calibration stars (439) by theirs (432), each star keeping its inverted sample. Signals already in our tables are kept
as real rows. The table and the star-grouped scores in
[`false_alarm_classifier_table.csv.gz`](false_alarm_classifier_table.csv.gz) and
[`false_alarm_classifier_scores_star.csv.gz`](false_alarm_classifier_scores_star.csv.gz) are now the retrained ones
(13,516 real and 1,026 inverted rows; the previous versions are in the repository history). The star counts used for
the weights are unchanged.

With `--split star`, the 0.80 cut selects 117 of the 395 clean SNR 7.5–9 signals with 9.2 expected false alarms
(purity 0.92, as before). `fa_score` in the catalog is the new out-of-fold score for every signal with a row in the
new table (2,085 of the 2,426 earlier full-sky rows and all new ones); the other 341 keep the previous score.

Tier L1 was re-selected with the new hold-out scores (approved 13 October):
- Six L1 members fall below 0.80 and leave: TIC 184607166 and 332502575 to tier L (MES ≥ 9); TIC 422443793,
  124382169, 236383404 and 26016707 to likely false alarm. TIC 156909067 leaves for tier C: with the proper-motion fix
  in the binary check (PR #13) its Gaia DR3 RUWE is 3.62. The eight L1 members whose signal has no comparable row in
  the new table (the re-search found it at SNR ≥ 9, or not at all) keep tier L1 and their previous score.
- 46 existing SNR 7.5–9 signals not in L1 reach 0.80. Two are likely eclipsing binaries and 14 are grazing (b ≥ 0.9)
  or have RUWE > 1.4; they keep their tiers. The other 30 got TRICERATOPS runs (default and with Gaia limits) and
  per-sector centroids where they had none: 28 pass and join tier L1, and TIC 238446565 (NFPP 0.31) and 279320939
  (FPP 0.88) keep their tiers. Three of the 28 (TIC 458482761, 407505256 and 270355278) had left L1 at the
  star-grouped re-selection earlier the same day.
- 38 signals of the re-search join tier L1 by the same rules.

Tier L1 now has 112 candidates.
