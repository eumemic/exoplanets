# Centroids in every sector

On 12 October 2026 we measured the difference-image centroid of every counted candidate in every sector with transits,
and tested whether the mean offset is consistent with the target star and with each neighbour bright enough to cause
the dip. Until then the
pixel checks used the offset in one sector (`followup.py`: the best-quality difference image among a few cheap
sectors). The TOI-913 case on issue #2 showed the problem: one sector can look on target while the others point to a
neighbour.

## Method

- `pipeline/centroid_sectors.py` fits transit-diffImage's PRF model to the difference image of each sector with
  transits (up to 12 per candidate, highest per-sector SNR first), through LEO-Vetter as `followup.py` does, with
  cutouts from the TESS cubes on the STScI open-data bucket. Each fit is kept as an offset east and north of the target
  (arcsec), measured in the sector's pixel frame from transit-diffImage's position of the target. The TIC stars within
  2′ are kept with their offsets.
- `pipeline/centroid_test.py` treats the per-sector offsets as scattered about the true source with a common, unknown
  spread. With n sectors and RSS the scatter of the offsets about their mean (floored at 1″ per axis, since the PRF
  fits have systematic errors of about that size), F = (n |mean − s|² / 2) / (RSS / (2(n − 1))) follows F(2, 2(n − 1))
  if the source is at s. It needs at least two sectors. The test is made for the target and for every star within 2′
  bright enough to cause the dip: a total eclipse of that star, diluted by the target, must reach the observed depth.
  Offsets beyond 60″ are treated as failed fits.

The same code ran on two calibration sets:
- **on target:** the 601 confirmed and known planets among the 1,000 TOIs of
  [`centroid_calibration_tois.csv`](centroid_calibration_tois.csv), with TOI ephemerides and up to 8 sectors each;
- **off target:** the 203 full-sky signals caused by TOIs on neighbouring stars
  ([`centroid_calibration_neighbour_tois.csv`](centroid_calibration_neighbour_tois.csv)), with that neighbour as the
  known source.

## Calibration

| Signals | With ≥ 2 sectors | Target rejected at p < 0.001 | at p < 0.01 | True source fits (p ≥ 0.01) |
|---|---|---|---|---|
| Known planets | 565 | 0 | 3 (0.5%) | – |
| … with MES < 30 | 160 | 0 | 2 (1.3%) | – |
| Signals from neighbouring stars | 175 | 127 (73%) | 141 (81%) | 164 (94%) |
| … source within 15″ | 50 | 38% | | 90% |
| … source 15–30″ away | 39 | 77% | | 100% |
| … source 30–60″ away | 82 | 91% | | 95% |

## Results

517 of the 546 candidates counted on 11 October have difference images in at least two sectors; 29 have one and are
not tested.

**18 reject their target at p < 0.001** (14 in tier N, 4 in tier B). No known planet does, so we expect fewer than one
of the 18 to be on target by chance. They leave the counted tiers: the 16 that a star bright enough to cause the dip
fits (p ≥ 0.01) become likely nearby false positives, and the 2 that no catalogued star fits go to tier C. Several have
mean offsets of 14–60″; their best single sector had passed the 15″ check.

| TIC | P (d) | Tier before → now | Sectors | Mean offset | p, target | Best-fitting star: TIC (separation, T) | p, that star |
|---|---|---|---|---|---|---|---|
| 61411095 | 0.6139 | N → likely nearby FP | 5 | 10.8″ | 0.0009 | 940451958 (11.6″, 18.5) | 0.86 |
| 247464683 | 0.6594 | N → C | 6 | 8.7″ | < 0.0001 | 247483851 (7.4″, 18.4) | 0.0016 |
| 160983090 | 0.7985 | B → likely nearby FP | 5 | 21.4″ | < 0.0001 | 2004563149 (24.0″, 18.5) | 0.46 |
| 308058319 | 0.9492 | N → likely nearby FP | 5 | 12.4″ | 0.0001 | 308058320 (12.4″, 17.2) | 0.54 |
| 92329533 | 0.9738 | N → likely nearby FP | 7 | 5.4″ | 0.0002 | 1964952499 (4.3″, 18.4) | 0.41 |
| 207141752 | 1.1134 | N → likely nearby FP | 3 | 59.8″ | < 0.0001 | 207141748 (60.0″, 17.0) | 0.74 |
| 235711821 | 1.1277 | B → likely nearby FP | 9 | 14.3″ | < 0.0001 | 1271379812 (19.2″, 18.5) | 0.011 |
| 207398162 | 1.3856 | N → likely nearby FP | 6 | 12.9″ | < 0.0001 | 1201126191 (12.7″, 18.7) | 0.85 |
| 261461983 | 1.4434 | N → likely nearby FP | 5 | 17.3″ | 0.0001 | 261461979 (17.6″, 17.6) | 0.28 |
| 393339333 | 1.9213 | N → likely nearby FP | 7 | 21.5″ | 0.0001 | 815720478 (18.9″, 18.8) | 0.18 |
| 167171288 | 2.8751 | N → likely nearby FP | 3 | 11.8″ | 0.0001 | 167171280 (12.1″, 16.7) | 0.52 |
| 231829497 | 3.2786 | B → likely nearby FP | 6 | 23.2″ | 0.0003 | 231829496 (30.9″, 14.3) | 0.13 |
| 399426297 | 3.7869 | N → likely nearby FP | 6 | 41.6″ | < 0.0001 | 399426324 (41.4″, 14.7) | 0.87 |
| 399202562 | 4.5723 | N → likely nearby FP | 3 | 29.2″ | 0.0001 | 399202578 (27.8″, 13.1) | 0.63 |
| 38943164 | 4.7793 | B → likely nearby FP | 10 | 22.5″ | 0.0001 | 38943169 (29.0″, 14.4) | 0.2 |
| 45996905 | 6.2806 | N → C | 5 | 12.9″ | 0.0002 | 45996903 (6.0″, 16.8) | 0.0071 |
| 451538987 | 10.5492 | N → likely nearby FP | 8 | 9.2″ | 0.0001 | 451538984 (5.5″, 17.8) | 0.064 |
| 463343440 | 19.9477 | N → likely nearby FP | 5 | 11.6″ | < 0.0001 | 861750026 (9.4″, 17.9) | 0.21 |

**13 reject their target at 0.001 ≤ p < 0.01** (10 in tier N, 3 in tier B, one of them from the earlier searches). Known
planets with MES < 30 reach this level 1.3% of the time, so about half of the 13 could be on target. They stay counted,
with `centroid_flag` set: TIC 18441994, 137609439, 166574088, 177021616, 184506615, 185840936, 258827696, 267824267,
293616610, 310097407, 352414078, 407232246 and 409700778.

As of 15 October 2026, 7 of the 13 are still counted: TIC 18441994, 177021616, 293616610 and 407232246 in tier N, and
TIC 137609439, 166574088 and 258827696 in tier B. The other six, TIC 184506615, 185840936, 267824267, 310097407,
352414078 and 409700778, failed the TRICERATOPS bar in the single-cadence rerun of 15 October and are now likely nearby
false positives; they keep the flag.

The counted candidates are now 470 from the full sky (11 A, 250 B, 159 N, 50 L1) and 58 from the earlier searches:
528 in all. The catalog columns `cs_sectors`, `cs_offset_arcsec`, `cs_pa_deg` (east of north), `cs_p_target`,
`cs_neighbour`, `cs_neighbour_sep_arcsec`, `cs_p_neighbour` and `centroid_flag` hold the results.

## Limits

- The test is weak for sources within 15″ (38% caught at p < 0.001), which is where tier N candidates have their
  neighbour, so it removes only the clearest cases there.
- It assumes the same spread in every sector, although the per-sector SNR differs; the calibration measures how often it
  flags real planets.
- At low SNR the centroids of a signal from a neighbour are pulled toward the target. Of the calibration signals from
  neighbours 20–60″ away, the six whose per-sector centroids scatter by 14–22″ per axis land 3–14″ closer to the target
  than the source (mean 9 ± 1.5″, about a quarter of the separation); with less scatter the pull is under 1″. The test
  compares the mean with the neighbours' catalogue positions, so at low SNR it overstates the evidence against a
  neighbour, while it does not make real planets fail the target test.
- Two signals outside the catalog were tested as well. TOI-913's 5.45 d signal (issue #2) has a mean offset of 5.3″ east
  across 8 sectors, with a large scatter: p = 0.49 for TOI-913 and 0.62 for the giant 9.5″ away, so the test cannot
  tell them apart. It gives p = 0.0007 for TIC 407126406, 27″ east, but 0.01–0.03 when that star's expected position
  is pulled in by a quarter to a third as above, so it does not exclude that star either; TIC 407126397, 57″ away, stays
  excluded (p ≤ 10⁻⁵). WASP-166's 27.0 d signal sits 10″ northeast in 4 sectors (p = 0.007 for WASP-166, 0.02 for the
  star 6.7″ east), while WASP-166 b's transits, measured the same way, fall within 1–4″ of the star.

## Files

- [`centroid_sectors_list.csv`](centroid_sectors_list.csv): the signals, ephemerides and sectors measured;
- [`centroid_sectors_per_sector.csv.gz`](centroid_sectors_per_sector.csv.gz): one row per sector (failed fits with
  their error);
- [`centroid_sectors_stars.csv.gz`](centroid_sectors_stars.csv.gz): the TIC stars within 2′ of each target, with their
  offsets and T magnitudes;
- [`centroid_sectors.csv`](centroid_sectors.csv): the test for every signal. `python centroid_test.py` reproduces it
  from the three files above.
