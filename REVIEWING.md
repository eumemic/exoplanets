# Reviewing the candidates

This page is for astronomers who would like to check this work. We count <!--n:catalog.counted.total-->645<!--/n--> candidate
transiting planets found in public TESS light curves, none of them on the TOI list when we found them. We have no
ground-based follow-up or high-resolution imaging of any of them. The most useful thing you can tell us is where the
vetting or the false-positive analysis below is wrong or incomplete.

## Where things are

| | |
|---|---|
| **Candidate tables** | [`results_public/candidates_allsky.csv`](results_public/candidates_allsky.csv): the full-sky search, <!--n:catalog.counted.allsky-->587<!--/n--> counted (tiers M, S, N and L1). [`results_public/tiers_earlier_candidates.csv`](results_public/tiers_earlier_candidates.csv): the earlier searches of nearby K and M dwarfs and of TOI hosts, <!--n:catalog.counted.earlier-->58<!--/n--> counted (tiers M and S). Every column is in the [data dictionary](results_public/README.md), and the [candidate explorer](https://eumemic.github.io/exoplanets/candidates.html) shows the same tables. |
| **One candidate** | A folder per candidate in [`candidates/allsky/`](candidates/allsky/) (the earlier searches' are in [`candidates/`](candidates/)): the vetting plot and tests (`vetting.png`, `vetting.json`), centroid offsets and nearby stars (`followup.json`) and the TRICERATOPS result (`triceratops_gaia.json`). |
| **Methods** | The [Method](README.md#method) and [Full-sky search](README.md#full-sky-search-8-october-2026) sections of the README, and a note in [`validation/`](validation/) for each check. |
| **Predicted transits** | [`candidates/predictions.csv`](candidates/predictions.csv) and the [transit planner](https://eumemic.github.io/exoplanets/transits.html). |

## How each candidate was vetted

1. **Search**: box least squares on detrended SPOC, TESS-SPOC and QLP light curves (Sectors 1–105), at least three
   transits and SNR ≥ 9 (7.5–9 for tier L1).
2. **Known signals removed**: TOIs, CTOIs, confirmed planets, SPOC TCEs and candidates from the literature.
3. **LEO-Vetter**: its false-alarm and false-positive tests, and depth consistency between sectors.
4. **Pixel and field checks**: difference-image centroids in every sector with transits, and the TIC stars within
   2.5′ that could produce the depth as eclipsing binaries.
5. **Binary checks**: Gaia RUWE (above 1.4 is not counted), Gaia radial velocities where they exist, TESS
   eclipsing-binary catalogues and the transit shape (grazing is not counted).
6. **TRICERATOPS**: ten runs with the default priors and ten with Gaia limits on bound companions (MOLUSC, five samples
   per star), on the light curves of one cadence, combined with a centroid Bayes factor where a capable star lies
   within 30″. A candidate is counted with FPP < 0.5, NFPP < 0.1 and MES ≥ 10 (tier L1: SNR 7.5–9, selected by a
   false-alarm classifier). <!--n:catalog.validation.total-->254<!--/n--> also meet FPP < 0.015, NFPP < 0.001 and Rp < 8 R⊕, the validation
   thresholds apart from imaging.

## Our own estimate of the false positives

- **Noise and systematics.** We ran the whole pipeline on the inverted light curves of 798,769 stars, where every dip
  is noise or a systematic. Scaled to the search, about <!--n:false_alarms.expected_total|.0f-->48<!--/n--> of the 587 full-sky candidates are expected
  to be false alarms (<!--n:false_alarms.expected.MS|.1f-->27.5<!--/n--> in tiers M and S, <!--n:false_alarms.expected.N|.1f-->10.1<!--/n--> in N, <!--n:false_alarms.expected.L1|.1f-->10.6<!--/n--> in L1), mostly at low MES
  ([`validation/false_alarms_inverted_798769_stars.csv`](validation/false_alarms_inverted_798769_stars.csv)).
- **Astrophysical false positives.** The counted candidates' TRICERATOPS false-positive probabilities sum to about
  <!--n:catalog.fpp_sum|.0f-->37<!--/n-->: if they are calibrated, about that many of the 645 are eclipsing binaries or other astrophysical false
  positives.
- **Flags.** Counted candidates we trust less carry flags: a low false-alarm classifier score (`fa_flag`,
  <!--n:catalog.flags.fa.total-->47<!--/n-->), the Neptunian desert (`desert_flag`, <!--n:catalog.flags.desert.total-->26<!--/n-->) and a centroid offset at p < 0.01 (`centroid_flag`, <!--n:catalog.centroid_flagged_counted-->17<!--/n-->).

## Where an expert's view would help most

1. **Tier N** (<!--n:catalog.tier.N-->159<!--/n--> candidates): a TIC star within 15″ could produce the dip. We count them on TRICERATOPS combined
   with the centroid Bayes factor, but our per-sector centroid test catches only 38% of sources within 15″
   ([`validation/centroid_sectors.md`](validation/centroid_sectors.md)). Would you count these?
2. **TRICERATOPS's scenarios and priors**: MOLUSC gives every host a companion, eclipsing-binary scenarios are dropped
   where Gaia radial velocities exclude them, galaxies host no scenarios, and the field geometry uses a 3×3-pixel
   aperture. Is there a scenario or prior you would treat differently?
3. **Tier L1** (<!--n:catalog.tier.L1-->112<!--/n--> candidates at SNR 7.5–9): is a classifier trained on inverted light curves a sound basis for
   listing them ([`validation/false_alarm_classifier.md`](validation/false_alarm_classifier.md))?
4. **Systematics the inversion test misses**: inverted light curves reproduce noise and systematics that are
   symmetric in flux, not those that only ever make dips. What else would you check?
5. **Follow-up**: which candidates would you observe first, and with what?

## How to reply

Please open an [issue](https://github.com/eumemic/exoplanets/issues) in this repository. Issues and pull requests that
lead to a change are credited by name in the release note (see [Credits](README.md#credits)).
