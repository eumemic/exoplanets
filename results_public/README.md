# Data dictionary for `results_public/` and `candidates/`

This page defines every column of the tables in this directory and of `candidates/ephemerides.csv` and
`candidates/predictions.csv`. Counts are those of the current tables: the build (`pipeline/rules.py`) writes them to
`numbers.json` and fills them in here (<!--n:catalog.counted.total-->645<!--/n--> candidates). The method behind each table is in the
[top-level README](../README.md) and in [`validation/`](../validation/). Where none of these states what a column
means, the entry says "not documented; appears to be" and gives the likeliest reading.

| File | Rows | Covered in |
|---|---|---|
| `candidates_allsky.csv` | <!--n:catalog.rows.allsky\|,-->2,990<!--/n--> | [Full-sky signals](#candidates_allskycsv) |
| `tiers_earlier_candidates.csv` | <!--n:catalog.rows.earlier-->68<!--/n--> | [Earlier searches](#tiers_earlier_candidatescsv) |
| `candidates.csv` | 12 | [Release tables](#release-tables) |
| `candidates_2026-10-08.csv`, `candidates_2026-10-08b.csv`, `candidates_2026-10-08c.csv`, `candidates_2026-10-08d.csv` | 38, 8, 18, 12 | [Release tables](#release-tables) |
| `../candidates/ephemerides.csv`, `../candidates/predictions.csv` | <!--n:registry.rows\|,-->740<!--/n-->, <!--n:registry.predictions\|,-->50,258<!--/n--> | [Ephemerides and predictions](#ephemerides-and-predictions) |
| `all_signals*.csv.gz`, `vetted_signals*.csv.gz` | 7 files each | [Signal tables](#signal-tables) |
| `followup_*.csv` | 7 files | [Follow-up tables](#follow-up-tables) |
| `funnel_allsky.csv` | <!--n:funnel.rows-->154<!--/n--> | [Search stage counts](#funnel_allskycsv) |
| `products/`, `overrides.csv` | | The inputs of the catalog build: measured columns, TRICERATOPS and centroid results, and hand decisions ([`products/README.md`](products/README.md)) |
| `numbers.json` | | Every count quoted here and in the top-level README, computed from the tables by the build |

`novelty_check.md` is prose and is not covered here.

## Conventions

**Empty values.** In every CSV an empty field means the value is missing: not measured, not applicable or not run.
Each entry below says which. A zero is a measured value. Boolean columns hold `True` or `False`. Several values in one
field are separated by `;`, except in the follow-up `flags` column, where they are separated by `,`.

**Time.** Three conventions are used, and the column name tells which.

| Convention | Meaning | Columns |
|---|---|---|
| BJD_TDB | Barycentric Julian Date in the TDB time scale, in days | `T0_BJD` (candidate tables), `T0_BJD_TDB`, `next_tc_BJD_TDB`, `tc_BJD_TDB` (ephemerides and predictions) |
| BTJD | BJD_TDB − 2457000 days, the time stamp of TESS light-curve files | `t0` (signal tables) |
| UTC | Coordinated Universal Time, as `YYYY-MM-DD HH:MM` | `tc_UTC` |

`registered` in `ephemerides.csv` is a UTC calendar date. To convert, add 2457000 to a BTJD value to get BJD_TDB.

**Units.** Periods and spans are in days, durations in hours, depths in ppm unless the column holds a fraction (the
column says so), radii in Earth radii (R⊕) for planets and solar radii for stars, angles on the sky in arcseconds,
timing uncertainties in minutes.

**Names that differ between files.** The same quantity has different names in different files.

| Quantity | Names, with the files that use them |
|---|---|
| Star | `TIC` (candidate tables, ephemerides, predictions); `tic` (signal tables, follow-up tables) |
| Period, days | `P_d` (candidate tables); `period_d` (ephemerides, predictions); `period` (signal and follow-up tables); `P` in the per-candidate `transit_fit.json` |
| Period uncertainty, days | `P_err` (candidate tables); `period_err_d` (ephemerides) |
| Reference transit | `T0_BJD` (candidate tables, BJD_TDB); `T0_BJD_TDB` (ephemerides, BJD_TDB); `t0` (signal tables, BTJD; also in `transit_fit.json`) |
| Duration, hours | `T14_h` (candidate tables); `duration_h` (ephemerides, predictions, signal tables) |
| Depth | `depth_ppm` (candidate tables, ephemerides, vetted and follow-up tables); `bls_depth_ppm` and `depth` (signal tables; `depth` is a fraction) |
| Planet radius, R⊕ | `Rp_Re` (candidate tables, ephemerides); `rp` (vetted signal tables) |

The candidate tables, `ephemerides.csv` and `predictions.csv` share `candidate_id`, the candidate's folder name where it
has one, else `TIC<id>_P<period to 3 decimals>`: join on it. (The TIC ID and a period that agrees within 0.2% also work.) Signal and
follow-up tables are joined on `tic` and `rank` (see [Signal tables](#signal-tables)).

## Tiers, sets and flags

### Tier labels

`tier` in `candidates_allsky.csv`, `tiers_earlier_candidates.csv`, `ephemerides.csv` and `predictions.csv` holds one
of these labels, spelled exactly as shown. The rules that assign them are in `pipeline/catalog.py`.

| `tier` | Definition | Counted as a candidate | Rows in `candidates_allsky.csv` |
|---|---|---|---|
| `M` | Several counted candidates on the star (multi) | yes | <!--n:catalog.tier.M-->22<!--/n--> |
| `S` | A single candidate on the star | yes | <!--n:catalog.tier.S-->294<!--/n--> |
| `N` | A TIC star within 15″ could produce the dip; the TRICERATOPS and centroid probabilities combined give FPP < 0.5 and NFPP < 0.1, with MES ≥ 10, a transit fit and the same binary, grazing and RUWE checks as tier S | yes | <!--n:catalog.tier.N-->159<!--/n--> |
| `L1` | SNR 7.5–9, selected by the false-alarm classifier (`fa_score_h` ≥ 0.80); passes TRICERATOPS and the per-sector centroid test | yes | <!--n:catalog.tier.L1-->112<!--/n--> |
| `C` | Grazing, RUWE > 1.4, MES < 10, TRICERATOPS FPP ≥ 0.5 or NFPP ≥ 0.1, no TRICERATOPS result, no transit fit, or a centroid offset in all sectors; listed but not counted (reason in `c_reason`) | no | <!--n:catalog.tier.C-->551<!--/n--> |
| `L` | SNR 7.5–9, MES ≥ 9, not selected as tier L1 | no | <!--n:catalog.tier.L-->72<!--/n--> |
| `likely EB` | Likely binary: a binary catalog lists the target, a matching eclipsing binary is nearby, or the fitted radius exceeds 20 R⊕; the Gaia RV binaries also carry it | no | <!--n:catalog.tier.likely_EB-->315<!--/n--> |
| `likely nearby FP` | Likely nearby false positive: there is evidence that the signal comes from a nearby star. Either the signal is in set `neighbour<15"` (a capable TIC star within 15″) and its TRICERATOPS result fails the bar (<!--n:catalog.lnfp.by_triceratops\|,-->1,100<!--/n--> rows), or its per-sector centroids reject the target and fit a capable neighbour (<!--n:catalog.lnfp.by_centroids-->86<!--/n--> rows; <!--n:catalog.lnfp.by_both-->77<!--/n--> have both). A neighbour-set signal without a TRICERATOPS result is tier C, not this | no | <!--n:catalog.tier.likely_nearby_FP\|,-->1,109<!--/n--> |
| `likely false alarm` | Set `SNR 7.5-9` with MES below 9 and not selected as tier L1 (<!--n:catalog.lfa.low_band-->342<!--/n--> rows), and TIC 141937667 (13.36 d), whose signal came from the QLP orbit-edge systematic (an override; [details](../validation/qlp_orbit_edges.md)). The false-alarm classifier note uses the label for signals that fall below its score cut | no | <!--n:catalog.lfa.total-->343<!--/n--> |
| `reported` | A matching signal is already reported elsewhere: in the literature check, in a paper found through NASA ADS, or as a community TOI with a single transit or another period ([details](../validation/ctoi_matches.md)); `reported_as` says where | no | <!--n:catalog.tier.reported-->13<!--/n--> |

Tiers M, S, N and L1 together are the <!--n:catalog.counted.allsky-->587<!--/n--> counted full-sky candidates. In `tiers_earlier_candidates.csv` only tiers
`M`, `S` and `C` occur, and tiers `M` and `S` are counted (<!--n:catalog.counted.earlier-->58<!--/n--> rows). The rules that assign
the tiers are listed at the top of `pipeline/catalog.py`, which builds both tables. `ephemerides.csv` and `predictions.csv` keep the
rows of candidates that later left the counted tiers, with their current tier, so every label above can occur there.
Tiers `M` and `S` were called `A` and `B` until 27 October 2026; release notes from before then use the old names.

### The `set` column

`set` in `candidates_allsky.csv` says which group of signals a row came from.

| `set` | Meaning | Rows |
|---|---|---|
| `SNR>=9` | Search SNR ≥ 9, passed LEO-Vetter and the cuts, with no centroid offset or capable TIC neighbour within 15″ | <!--n:catalog.set.snr9-->857<!--/n--> |
| `SNR 7.5-9` | The same for search SNR 7.5 to 9 | <!--n:catalog.set.low-->562<!--/n--> |
| `neighbour<15"` | Signals rejected only by the close-neighbour check, or without a usable difference image, then assessed with TRICERATOPS and the centroid likelihood ratio | <!--n:catalog.set.nb\|,-->1,571<!--/n--> |

Of the 857 rows of `SNR>=9`, 735 come from the first pass: the 726 clean signals counted in the README's table of
pixel-check outcomes, the 7 signals that moved from tier N to tier S on 13 October when TIC artifacts were removed
([details](../validation/tic_artifacts.md)), and 2 that moved from tier N to tier S on 16 October because every TIC entry
within 15″ bright enough to cause their dip is a galaxy or a galaxy's core (`products/vetting.csv`). The QLP re-search
added 122 rows of `SNR>=9`, 180 of `SNR 7.5-9` and 262 of `neighbour<15"` (column `search`).

### Flag columns

`centroid_flag` marks the result of the per-sector centroid test
([details](../validation/centroid_sectors.md)). Empty means no flag: the target was not rejected at p < 0.01, or the
test was not run.

| Value | Rows | Meaning |
|---|---|---|
| `centroid offset in all sectors, p < 0.001` | <!--n:catalog.flags.centroid_strong.total-->100<!--/n--> (<!--n:catalog.flags.centroid_strong.text-->88 `likely nearby FP`, 11 `likely EB` and 1 `C`<!--/n-->) | `cs_p_target` < 0.001. Not counted |
| `centroid offset in all sectors, p < 0.01` | <!--n:catalog.flags.centroid_weak.total-->56<!--/n--> (<!--n:catalog.flags.centroid_weak.text-->35 `likely nearby FP`, 7 `N`, 4 `S`, 4 `L1`, 4 `C` and 2 `likely EB`<!--/n-->) | 0.001 ≤ `cs_p_target` < 0.01. Counted rows stay counted, flagged |

`fa_flag` marks a low false-alarm-classifier score. Empty means no flag.

| Value | Rows | Meaning |
|---|---|---|
| `low false-alarm-classifier score` | <!--n:catalog.flags.fa.total-->47<!--/n--> (<!--n:catalog.flags.fa.text-->22 `S`, 21 `N` and 4 `M`<!--/n-->) | Tier M, S or N with `fa_score` < 0.8, where most false alarms lie. Flagged, not moved |

`desert_flag` marks counted candidates in the core of the Neptunian desert. Empty means no flag.

| Value | Rows | Meaning |
|---|---|---|
| `Neptunian desert` | <!--n:catalog.flags.desert.total-->26<!--/n--> (<!--n:catalog.flags.desert.text-->14 `S`, 10 `N` and 2 `L1`<!--/n-->) | `P_d` < 3.2 d and `Rp_Re` 4–10 R⊕ (Castro-González et al. 2024). Flagged, not moved |

`rv_flag` marks the result of the Gaia DR3 radial-velocity check
([details](../validation/gaia_companion_limits.md)). Empty means the check did not apply or found nothing.

| Value | Rows | Meaning |
|---|---|---|
| `Gaia RVs exclude an EB on the target` | <!--n:catalog.flags.rv.rvs_exclude_an_eb-->176<!--/n--> | The host has Gaia epoch-RV statistics (`rv_method_used` = 1, at least 10 transits) and the RV scatter rules out an eclipsing binary on the target; the EB scenarios were dropped from the Gaia-constrained TRICERATOPS runs |
| `Gaia RV variable` | <!--n:catalog.flags.rv.rv_variable-->24<!--/n--> | The host meets Gaia's selection of RV-variable stars (p ≤ 0.01, renormalised goodness of fit > 4, at least 10 transits). Flagged |
| `Gaia RV binary` | <!--n:catalog.flags.rv.rv_binary-->8<!--/n--> (all `likely EB`) | RV amplitude far above that selection (26 to 184 km/s); treated as a binary at the target |

`c_reason` gives the reason a row is in tier C. It is empty for every other tier. A row carries one value even when it
meets several criteria: the first that applies, in the order below (the order of the rules in `pipeline/catalog.py`).

| Value | Rows | Meaning |
|---|---|---|
| `grazing` | <!--n:catalog.c_reason.grazing-->147<!--/n--> | Impact parameter `b` ≥ 0.9 |
| `RUWE > 1.4` | <!--n:catalog.c_reason.ruwe-->154<!--/n--> | Gaia RUWE of the target above 1.4 |
| `MES < 10` | <!--n:catalog.c_reason.mes-->183<!--/n--> | `MES` below 10 |
| `no TRICERATOPS result (no TIC parallax)` | <!--n:catalog.c_reason.no_parallax-->6<!--/n--> | TRICERATOPS cannot evaluate the target, because the TIC gives no parallax, so the bar cannot be passed |
| `no TRICERATOPS result` | <!--n:catalog.c_reason.no_result-->0<!--/n--> | TRICERATOPS has not been run, or its run failed |
| `TRICERATOPS FPP >= 0.5 or NFPP >= 0.1` | <!--n:catalog.c_reason.triceratops-->58<!--/n--> | Fails the TRICERATOPS bar (FPP < 0.5 and NFPP < 0.1) |
| `no transit fit` | <!--n:catalog.c_reason.no_fit-->2<!--/n--> | The signal passes every other check but has no transit fit, so grazing cannot be ruled out |
| `centroid offset in all sectors` | <!--n:catalog.c_reason.centroid-->1<!--/n--> | The per-sector centroids reject the target at p < 0.001 and no catalogued star fits |

## `candidates_allsky.csv`

All 2,990 signals of the full-sky search (2,426 from the first pass, 564 from the QLP re-search) that passed LEO-Vetter
and the cuts, or were recovered from the close-neighbour group, one row per signal, 50 columns. A star can have several rows. Rows are identified by `TIC` and `P_d`. Tiers M, S,
C, N, L1 and L have a folder in [`candidates/allsky/`](../candidates/allsky/), and signals that have since left those tiers
keep theirs; a folder's `triceratops_gaia.json` is the TRICERATOPS result behind the row's values (ten runs with the
default priors and ten with the Gaia limits), where there is one.

### Signal and transit fit

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `TIC` | TIC ID of the host star | integer | never empty |
| `P_d` | Orbital period: the median of the transit-fit posterior, or the search period when there is no fit | days | never empty |
| `P_err` | 1σ period uncertainty: half the 16th to 84th percentile range of the fit posterior | days | no transit fit (<!--n:catalog.nofit.total\|,-->1,295<!--/n--> rows) |
| `T0_BJD` | Reference transit time of the fit, or of the search when there is no fit. Usually the first transit in the data; it is not the reference epoch of the ephemerides (see [quirks](#known-quirks)) | BJD_TDB, days | never empty |
| `Rp_Re` | Planet radius from the fitted Rp/R*, using the TIC stellar radius. Without a fit: √(`depth_ppm` × 10⁻⁶) × `Rstar`, converted to R⊕ | R⊕ | never empty |
| `b` | Impact parameter, median of the fit posterior | dimensionless | no transit fit (<!--n:catalog.nofit.total\|,-->1,295<!--/n--> rows) |
| `T14_h` | Transit duration, first to fourth contact, median of the fit posterior. Without a fit: the box duration of the search | hours | never empty |
| `depth_ppm` | Transit depth measured in the vetting step: a box over the transit-masked, re-detrended light curve. It is not the depth of the fitted model | ppm | never empty |
| `MES` | LEO-Vetter multiple-event statistic | dimensionless | never empty |
| `n_transits` | Number of transits in the data (LEO-Vetter `N_transit`) | count | never empty |

Rows without a transit fit: <!--n:catalog.nofit.text-->1,037 `likely nearby FP`, 142 `C`, 114 `likely EB`, 1 `likely false alarm` and 1 `reported`<!--/n-->; every counted candidate has a fit.

### Host star

TIC 8.2 values.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `Tmag` | TESS magnitude | mag | never empty |
| `Teff` | Effective temperature | K | never empty |
| `Rstar` | Stellar radius | R☉ | never empty |
| `dist_pc` | Distance | pc | the TIC lists no distance (11 rows) |
| `ruwe` | Gaia DR3 renormalised unit weight error of the target | dimensionless | no Gaia DR3 match at the target or no RUWE listed (16 rows) |

### Pixel and field checks

From the difference-image and neighbour checks made when the signal was vetted.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `centroid_offset_arcsec` | Offset of the difference-image PRF centroid from the target, in the highest-quality image among the sectors with the strongest transits. LEO-Vetter's limit is 15″ | arcsec | no usable difference image (27 rows) |
| `nearest_capable_arcsec` | Separation of the nearest TIC star within 2.5′ that could produce the depth if it were an eclipsing binary (an eclipse of at most 50% of its flux dilutes to the depth). TIC entries flagged ARTIFACT or DUPLICATE are excluded | arcsec | no such star within 2.5′, or the lookup failed (13 rows) |

### Per-sector centroids

The centroid test of 12 October 2026 ([details](../validation/centroid_sectors.md)). The difference-image centroid is
measured in each sector with transits (up to 12 per candidate) as an offset east and north of the target. The test asks
whether the mean offset is consistent with the target and with each TIC star within 2′ that is bright enough to cause
the dip. It needs at least two sectors. The columns are filled for <!--n:catalog.cs.filled|,-->1,128<!--/n--> rows: every counted candidate
(<!--n:catalog.cs.counted_unmeasured-->0<!--/n--> are not measured), the signals the test moved out of the counted tiers, signals
examined for tier L1 and tier N, and all 564 signals of the QLP re-search. Measurements made since 15 October are in
`products/centroids.csv`, with the ephemeris each used.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `cs_sectors` | Number of sectors with a usable centroid fit | count | not measured (<!--n:catalog.cs.empty\|,-->1,862<!--/n--> rows) |
| `cs_offset_arcsec` | Length of the mean offset of the per-sector centroids from the target | arcsec | not measured |
| `cs_pa_deg` | Direction of that mean offset, east of north | degrees | not measured |
| `cs_p_target` | p-value of the test that the target is the source of the offsets. A small value means the offsets are inconsistent with the target | probability, 0–1 | not measured, or only one sector (<!--n:catalog.cs.p_empty_measured-->35<!--/n--> rows) |
| `cs_neighbour` | TIC ID of the star within 2′ bright enough to cause the dip whose position fits the offsets best (largest p-value) | integer | not measured, one sector, or no star bright enough |
| `cs_neighbour_sep_arcsec` | Separation of that star from the target | arcsec | as `cs_neighbour` |
| `cs_p_neighbour` | p-value of the test that that star is the source | probability, 0–1 | as `cs_neighbour` |
| `centroid_flag` | Outcome of the test; values in [Flag columns](#flag-columns) | text | no flag |

### Binary and literature checks

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `binary_at_target` | Catalog entries within 3″ of the target that explain the signal, as `catalog P=period`: `gaia_eb`, `gaia_sb1`, `gaia_sb2`, `gaia_eb_orbit`, `gaia_orbit` (Gaia DR3 binary and orbit tables), `tess_eb` (TESS eclipsing-binary catalog), `t10k` (TESS Ten Thousand eclipsing binaries, Kostov et al. 2025; matched by TIC ID since 15 October 2026), `vsx:type` (VSX eclipsing or ellipsoidal types only), `apogee_binary`. Also `Gaia DR3 RV variable (amplitude N km/s)` for the four `Gaia RV binary` rows of `rv_flag`. The period is omitted when the catalog has none | period in days | no catalog entry (2,935 rows) |
| `eb_nearby_same_period` | Eclipsing binaries within 60″ of the target whose period matches the candidate's at ratios 1/3, 1/2, 2/3, 1, 3/2, 2 or 3 to within 0.5%, as `catalog separation" P=period` (`gaia_eb`, `tess_eb`, `vsx:type`) | separation in arcsec, period in days | no such binary (2,884 rows) |
| `papers_with_period` | NASA ADS bibcodes of papers whose full text mentions the star (TIC ID or host TOI) and also the candidate's period quoted to two or three decimals | bibcodes | none found (<!--n:catalog.papers_empty\|,-->2,988<!--/n--> rows) |
| `zenodo_with_period` | Zenodo records, as `zenodo:id`, whose title or description mention the star and the period | record IDs | no Zenodo record matched (every row) |
| `host_tois` | TOIs on the same star, as `TOI-number (disposition, period d)` | text | no TOI on the star: TOI hosts were searched separately, so every row is empty |

A known planet's own transits can match a catalog entry in `binary_at_target`; see [quirks](#known-quirks).

### TRICERATOPS

Each pair of columns is the false-positive probability (FPP) and the nearby false-positive probability (NFPP) of
TRICERATOPS (Giacalone et al. 2021). All are dimensionless probabilities. The defaults use TESS data alone, with no
follow-up imaging and no multiplicity boost, and ten runs per signal. Since 15 October, every row uses the transits of
one cadence, the one whose in-transit points carry the most information, modelled with that cadence's exposure (10- and
30-minute data binned in phase to 2 minutes), with the field-star population for the blended-star scenarios, and every
result passed the checks of `pipeline/fpp_check.py` ([details](../validation/triceratops_single_cadence.md)). For 39
targets the TIC gives no parallax; TRICERATOPS cannot evaluate them (it returns equal probabilities for every
scenario), and their columns are empty.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `FPP` | Mean FPP over the ten runs, default priors | probability | TRICERATOPS not run (<!--n:catalog.fpp_not_run-->684<!--/n--> rows), or the TIC gives the target no parallax (<!--n:catalog.fpp.no_parallax-->39<!--/n--> rows); none in tiers M, S, N or L1 |
| `NFPP` | Largest NFPP over the ten runs, default priors | probability | as `FPP` |
| `NFPP_mean` | Mean NFPP over the same ten runs, which `FPP_c` uses | probability | as `FPP` |
| `BF` | The centroid Bayes factor: how likely the measured centroid offset is if the transit is on the target, relative to the neighbour that would best explain it: for the first-pass tier N signals, the capable neighbours within 15″; for the others, every star within 30″ to which TRICERATOPS gives a nearby-star scenario ([details](../validation/fpp_combination.md)). In every row with `BF` > 1, `NFPP_c` ≤ `NFPP`; with `BF` < 1, `NFPP_c` ≥ `NFPP` | dimensionless | no ratio applied (<!--n:catalog.bf.empty-->984<!--/n--> rows, <!--n:catalog.bf.with_fpp-->295<!--/n--> of them with TRICERATOPS values, where `FPP_c` = `FPP` and `NFPP_c` = `NFPP`) |
| `FPP_c` | `FPP` combined with the centroid ratio, using `NFPP_mean` ([details](../validation/fpp_combination.md)) | probability | as `FPP` |
| `NFPP_c` | `NFPP` (the largest of the ten runs) combined with the centroid ratio | probability | as `FPP` |
| `FPP_g` | `FPP` rerun with Gaia DR3 limits on companions (MOLUSC) and, for bright stars, Gaia epoch-RV limits on an eclipsing binary at the target | probability | not run (<!--n:catalog.fpp_g.empty-->727<!--/n--> rows: those without `FPP`, and <!--n:catalog.fpp_g.missing_with_fpp-->4<!--/n--> whose star has no Gaia DR3 row or mass for MOLUSC) |
| `NFPP_g` | `NFPP` of the Gaia-constrained runs | probability | as `FPP_g` |
| `NFPP_g_mean` | `NFPP_mean` of the Gaia-constrained runs, which `FPP_gc` uses | probability | as `FPP_g` |
| `FPP_gc` | `FPP_g` combined with the centroid ratio, using `NFPP_g_mean`. The bar for counted candidates is `FPP_gc` < 0.5 and `NFPP_gc` < 0.1 | probability | as `FPP_g` |
| `NFPP_gc` | `NFPP_g` combined with the centroid ratio | probability | as `FPP_g` |
| `rv_flag` | Gaia radial-velocity check; values in [Flag columns](#flag-columns) | text | no flag |

The Gaia-constrained columns were computed for the counted candidates, for signals that had failed only the
TRICERATOPS bar and for the QLP re-search's signals that went through TRICERATOPS ([details](../validation/gaia_companion_limits.md)). Every counted
candidate has them; <!--n:catalog.fpp_g.missing_with_fpp-->4<!--/n--> uncounted rows with TRICERATOPS values do not (see [quirks](#known-quirks)).

### Classifier, tier and flags

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `fa_score` | False-alarm classifier score: the star-grouped out-of-fold score, which ranks signals by how unlike noise they are. It is not a probability ([details](../validation/false_alarm_classifier.md)) | 0–1 | never empty |
| `fa_score_h` | The hold-out score that tier L1 is selected on (cut 0.80), from models trained without the stars of the second inverted sample. Both scores come from the classifier retrained after the QLP re-search where the signal has a row in its table, and from the previous one otherwise | 0–1 | never empty |
| `set` | Group the signal came from; values in [The `set` column](#the-set-column) | text | never empty |
| `tier` | Reliability tier; values in [Tier labels](#tier-labels) | text | never empty |
| `c_reason` | Reason for tier C; values in [Flag columns](#flag-columns) | text | not tier C (<!--n:catalog.c_reason_empty\|,-->2,439<!--/n--> rows) |
| `reported_as` | Where a signal labelled `reported` was reported: a CTOI (with its period, or `single transit`), a K2 candidate, or an ADS bibcode | text | not tier `reported` (<!--n:catalog.reported_as_empty\|,-->2,977<!--/n--> rows) |
| `fa_flag` | Low classifier score; see [Flag columns](#flag-columns) | text | no flag |
| `desert_flag` | Neptunian desert; see [Flag columns](#flag-columns) | text | no flag |
| `search` | `full-sky search` (the first pass) or `QLP re-search` (the second pass of 13 October; [details](../validation/qlp_orbit_edges.md)) | text | never empty |
| `candidate_id` | The candidate's folder name in `candidates/allsky/`, or `TIC<id>_P<period to 3 decimals>` for a row without a folder; shared with `ephemerides.csv` and `predictions.csv` | text | never empty |

## `tiers_earlier_candidates.csv`

The tiers of the <!--n:catalog.rows.earlier-->68<!--/n--> signals from the earlier searches (K/M dwarfs, TOI hosts, TCE re-check, 20–100 d, faint M dwarfs),
with the same checks as the full-sky catalog. Tiers `M` and `S` are counted. Columns that also occur in
`candidates_allsky.csv` have the same meaning, units and timescale; the table gives only what differs.

| Column | Meaning | Empty means |
|---|---|---|
| `TIC` | As in `candidates_allsky.csv` | never empty |
| `P_d` | Period in days | never empty |
| `Rp_Re` | Planet radius in R⊕ | never empty |
| `b` | Impact parameter | never empty |
| `ruwe` | Gaia DR3 RUWE of the target | never empty |
| `binary_at_target` | As in `candidates_allsky.csv` | no catalog entry (<!--n:earlier.binary_empty-->67<!--/n--> rows) |
| `tier` | `M`, `S` or `C` | never empty |
| `src` | The file in `results_public/` the signal was taken from (`candidates.csv`, `candidates_2026-10-08.csv`, `candidates_2026-10-08b.csv`, `candidates_2026-10-08c.csv`, `candidates_2026-10-08d.csv` or `followup_faint_t1.csv`) | never empty |
| `FPP`, `NFPP`, `NFPP_mean`, `BF`, `FPP_c`, `NFPP_c`, `FPP_g`, `NFPP_g`, `NFPP_g_mean`, `FPP_gc`, `NFPP_gc` | As in `candidates_allsky.csv` | All but `BF`: TRICERATOPS not run (<!--n:earlier.fpp_empty-->6<!--/n--> rows). `BF`: no ratio applied (42 rows) |
| `rv_flag` | As in `candidates_allsky.csv` | no flag (<!--n:earlier.rv_empty-->52<!--/n--> rows) |
| `c_reason` | As in `candidates_allsky.csv` | not tier C (<!--n:earlier.c_reason_empty-->58<!--/n--> rows) |
| `cs_sectors`, `cs_offset_arcsec`, `cs_pa_deg`, `cs_p_target` | As in `candidates_allsky.csv` | not measured or one sector (<!--n:earlier.cs_empty-->8<!--/n--> rows) |
| `cs_neighbour`, `cs_neighbour_sep_arcsec`, `cs_p_neighbour` | As in `candidates_allsky.csv` | not measured, one sector, or no star bright enough (<!--n:earlier.cs_neighbour_empty-->10<!--/n--> rows) |
| `centroid_flag` | As in `candidates_allsky.csv`; only `centroid offset in all sectors, p < 0.01` occurs | no flag (<!--n:earlier.centroid_flag_empty-->66<!--/n--> rows) |
| `candidate_id` | The candidate's folder name in `candidates/` | never empty |

## Release tables

### `candidates_2026-10-08.csv`, `candidates_2026-10-08b.csv`, `candidates_2026-10-08c.csv`, `candidates_2026-10-08d.csv`

The signals of the update of 8 October 2026 and of its Updates 2 to 4, one row per signal, 28 columns in each file:

- `candidates_2026-10-08.csv`: the K/M-dwarf and TOI-host searches, including the signals that pass everything except
  the 15″ neighbour check;
- `candidates_2026-10-08b.csv`: the TCE re-check and the 20–100 d search;
- `candidates_2026-10-08c.csv`: the faint M dwarfs, 11.5 < T ≤ 12.5;
- `candidates_2026-10-08d.csv`: the fainter M dwarfs, 12.5 < T ≤ 13.5.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `TIC` | TIC ID of the host star | integer | never empty |
| `P_d` | Period: the transit-fit median, or the search period without a fit | days | never empty |
| `P_err` | 1σ period uncertainty from the fit | days | no fit (16 rows of `candidates_2026-10-08.csv`) |
| `T0_BJD` | Reference transit time of the fit, or of the search without a fit; usually the first transit in the data | BJD_TDB, days | never empty |
| `Rp_Re` | Planet radius, TIC stellar radius | R⊕ | never empty |
| `b` | Impact parameter | dimensionless | no fit |
| `T14_h` | Transit duration of the fit, or the box duration without a fit | hours | never empty |
| `depth_ppm` | Depth measured in the vetting step | ppm | never empty |
| `MES` | LEO-Vetter multiple-event statistic | dimensionless | never empty |
| `n_transits` | Number of transits in the data | count | never empty |
| `Tmag`, `Teff`, `Rstar`, `dist_pc` | TIC 8.2 magnitude (mag), temperature (K), radius (R☉) and distance (pc) | as stated | never empty |
| `ruwe` | Gaia DR3 RUWE of the target | dimensionless | not available (most rows) |
| `centroid_offset_arcsec` | Difference-image centroid offset from the target, as in `candidates_allsky.csv` | arcsec | no usable difference image |
| `nearest_capable_arcsec` | Separation of the nearest TIC star that could produce the depth, as in `candidates_allsky.csv` | arcsec | none within 2.5′, or the lookup failed (2 rows in `candidates_2026-10-08c.csv`) |
| `followup_flags` | Pixel and neighbour flags, joined by `,`: `offset` (centroid more than 15″ from the target), `no_pixel` (no usable difference image), `close_nb` (a TIC star within 15″ could produce the depth) | text | none raised |
| `FPP` | Mean TRICERATOPS FPP over ten runs, TESS data alone | probability | TRICERATOPS not run (16 rows of `candidates_2026-10-08.csv`; all rows of the other three files) |
| `FPP_sem` | Standard error of the mean of the ten `FPP` runs | probability | as `FPP` |
| `NFPP` | Largest TRICERATOPS NFPP over the ten runs | probability | as `FPP` |
| `host_tois` | TOIs on the same star, as `TOI-number (disposition, period d)` | text | no TOI on the star |
| `confirmed_planets` | Confirmed planets on the same star in the NASA Exoplanet Archive | planet names | none |
| `literature` | Entries on the same star in the literature tables (any period), as `literature:source` | text | none |
| `period_match` | Matches at a period ratio of 1/3, 1/2, 2/3, 1, 3/2, 2 or 3 on the same star, as `table:label:xratio`; `table` is `toi`, `ctoi`, `planet`, `tce` or `ours` (this project's candidate tables, which include the file the row is in) | text | no match |
| `notes` | Free-text remarks | text | none (2 rows of `candidates_2026-10-08.csv`) |
| `search` | The search that found the signal: `K/M dwarfs`, `TOI hosts`, `TCE re-check`, `20-100 d` or `faint M dwarfs` | text | never empty |
| `status` | Free-text status: `candidate`, `candidate; TIC star 13" away could produce the depth`, or `close neighbour could produce the depth` in `candidates_2026-10-08.csv`; `candidate` or `previously reported (Zenodo); independent recovery` in `candidates_2026-10-08b.csv`; `candidate` in the other two | text | never empty |

### `candidates.csv`

The 12 signals of the first release (7 October 2026), 20 columns. Parts of this table were written by hand, and its numeric
columns are unrounded. Columns shared with the dated tables above have the same meaning.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `TIC` | TIC ID of the host star | integer | never empty |
| `label` | Free-text name for the system or signal | text | none (8 rows) |
| `P_d`, `P_err`, `T0_BJD`, `Rp_Re`, `b`, `T14_h`, `depth_ppm` | Period (d), its uncertainty (d), reference transit (BJD_TDB), planet radius (R⊕), impact parameter, duration (h) and depth (ppm), from the transit fit | as stated | never empty |
| `Tmag`, `Teff`, `Rstar`, `dist_pc` | TIC magnitude (mag), temperature (K), radius (R☉) and distance (pc) | as stated | never empty |
| `centroid` | Not documented; appears to be the difference-image centroid offsets from the target, one per sector or image examined (`TPF` for a target pixel file, `FFI` for a full-frame image), or `inconclusive` | arcsec | never empty |
| `neighbours` | Not documented; appears to be the nearest TIC star or stars bright enough to mimic the signal, with separation, or `none` within a stated radius | arcsec | never empty |
| `notes` | Free-text remarks | text | never empty |
| `status` | Result of the novelty check, for example `no prior report found` ([`novelty_check.md`](novelty_check.md)) | text | never empty |
| `TRICERATOPS_FPP` | Mean TRICERATOPS FPP, TESS data alone, as in the README's first-release table | probability | TRICERATOPS not run (8 rows) |
| `TRICERATOPS_NFPP` | TRICERATOPS NFPP | probability | as `TRICERATOPS_FPP` |
| `upcoming_tess_sectors` | Not documented; appears to be the TESS sectors planned after the release in which the star falls on a detector, comma-separated | sector numbers | none listed (5 rows) |

## Ephemerides and predictions

Both files are append-only. A candidate registered by an earlier run keeps its rows; only `tier` is updated, so a
candidate that leaves the counted tiers stays listed with its new tier.

### `candidates/ephemerides.csv`

One row per registered candidate: <!--n:registry.rows|,-->740<!--/n--> rows, of which <!--n:registry.counted_now-->645<!--/n--> are counted now.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `TIC` | TIC ID | integer | never empty |
| `tier` | Current tier of the candidate; see [Tier labels](#tier-labels) | text | never empty |
| `ra`, `dec` | TIC position | degrees | never empty |
| `Tmag` | TESS magnitude | mag | never empty |
| `period_d` | Period, median of the transit fit | days | never empty |
| `period_err_d` | 1σ period uncertainty, to two significant figures | days | never empty |
| `T0_BJD_TDB` | Reference transit of the ephemeris: the fitted transit nearest the information-weighted centre of the observed transits, where the errors of epoch and period are uncorrelated | BJD_TDB, days | never empty |
| `T0_err_min` | 1σ uncertainty of `T0_BJD_TDB` | minutes | never empty |
| `duration_h` | Transit duration T14 of the fit | hours | never empty |
| `depth_ppm` | Depth of the fitted model, (Rp/R*)² | ppm | never empty |
| `Rp_Re` | Planet radius of the fit | R⊕ | never empty |
| `next_tc_BJD_TDB` | First predicted transit after the registration run | BJD_TDB, days | never empty |
| `next_tc_sigma_min` | 1σ uncertainty of that transit | minutes | never empty |
| `tess_transits_scheduled` | Number of predicted transits that fall inside a published TESS orbit window while the star is on a detector (rows of `predictions.csv` with a `tess_sector`) | count | never empty |
| `tess_sectors_planned` | Sectors planned for the star, comma-separated, from the first sector that ends after the registration run (tess-point; its special pointings, numbered from 1751, are left out) | sector numbers | no planned sector places the star on a detector (<!--n:registry.planned_empty-->346<!--/n--> rows) |
| `registered` | Date of the run that registered the candidate | UTC date | never empty |
| `candidate_id` | As in the candidate tables | text | never empty |

### `candidates/predictions.csv`

One row per predicted transit from the registration date through June 2027: <!--n:registry.predictions|,-->50,258<!--/n--> rows. The 1σ uncertainty is
propagated from the information-weighted centre of the observed transits and assumes a constant period, so
transit-timing variations would move transits away from these times.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `TIC` | TIC ID | integer | never empty |
| `tier` | Current tier of the candidate | text | never empty |
| `period_d` | Period, to six decimals | days | never empty |
| `epoch` | Number of periods between the ephemeris reference transit (`T0_BJD_TDB`) and this transit | integer | never empty |
| `tc_BJD_TDB` | Predicted mid-transit time at the solar-system barycentre | BJD_TDB, days | never empty |
| `tc_UTC` | The same time as UTC at Earth's centre, to the minute | UTC | never empty |
| `sigma_min` | 1σ uncertainty of the predicted time | minutes | never empty |
| `duration_h` | Transit duration T14 of the fit | hours | never empty |
| `tess_sector` | TESS sector in which the transit falls inside a published orbit window and the star is on a detector | sector number | not inside a published window, or the star is not on a detector (<!--n:registry.tess_sector_empty\|,-->49,426<!--/n--> rows) |
| `candidate_id` | As in the candidate tables | text | never empty |

## Signal tables

`all_signals*.csv.gz` hold every signal a search found, and `vetted_signals*.csv.gz` the subset that passed the
pre-filters described in the README (an SNR cut, at least 3 good transits, duration and shape cuts) and was vetted. The
suffix names the search.

| Files | Search | Rows (`all_signals`, `vetted_signals`) |
|---|---|---|
| `*_signals.csv.gz` | K/M dwarfs, 0.5–30 d | 41,758; 1,549 |
| `*_signals_toi_hosts.csv.gz` | TOI hosts, 0.5–30 d, TOIs masked | 15,222; 660 |
| `*_signals_tce.csv.gz` | Re-measured SPOC TCEs that are not TOIs | 14,112; 4,348 |
| `*_signals_long.csv.gz` | K/M dwarfs, 20–100 d | 9,179; 312 |
| `*_signals_long_toi_hosts.csv.gz` | TOI hosts, 20–100 d | 6,421; 165 |
| `*_signals_faint_t1.csv.gz` | Faint M dwarfs, 11.5 < T ≤ 12.5 | 38,545; 2,281 |
| `*_signals_faint_t2.csv.gz` | Fainter M dwarfs, 12.5 < T ≤ 13.5 | 139,231; 8,521 |

### Columns of `all_signals*.csv.gz`

Up to three signals are searched per star (four for TOI hosts), strongest first, masking each before the next. Columns
marked "some files" are absent from the others.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `rank` | Order in which the signal was found on the star, 1 first. In `all_signals.csv.gz` the K/M dwarfs were searched with two methods, so `tic` and `rank` do not identify a signal without `method`. In `vetted_signals*.csv.gz` and `followup_*.csv` `rank` is increased by 10 for signals with `method` `semi`, so `tic` and `rank` identify it | integer | never empty |
| `period` | Period of the strongest peak after a fine search | days | never empty |
| `t0` | Reference transit time of the search | BTJD (BJD_TDB − 2457000), days | never empty |
| `duration_h` | Duration of the best-fitting box | hours | never empty |
| `bls_depth_ppm` | Depth of that box | ppm | never empty |
| `bls_snr` | Signal-to-noise ratio of the fine search | dimensionless | never empty |
| `coarse_snr` | Signal-to-noise ratio of the peak in the coarse period search. In `*_tce` it equals `bls_snr` | dimensionless | never empty |
| `sde` | Signal detection efficiency of the peak against a running median in log period | dimensionless | not computed (every row of `*_tce`) |
| `exp_duration_h` | Duration of a central transit expected for a circular orbit around a star of density `rho` | hours | never empty |
| `n_events` | Number of individual transits with data in transit | count | never empty |
| `n_good_events` | Number of those with at least half the expected in-transit points | count | never empty |
| `depth` | Mean depth over the individual transits, as a fraction of the flux (not ppm) | fraction | not computed (13 rows: 1 in `faint_t1`, 3 in `faint_t2`, 9 in `toi_hosts`) |
| `depth_err` | 1σ uncertainty of `depth` | fraction | not computed (4 rows, in `faint_t1` and `faint_t2`) |
| `snr` | `depth` / `depth_err` | dimensionless | as `depth` |
| `odd_even_sigma` | Difference between the odd and even transit depths, in units of its uncertainty | σ | odd or even transits missing |
| `secondary` | Depth at phase 0.5, positive for a dip | fraction | three or fewer points in the window |
| `secondary_err` | 1σ uncertainty of `secondary` | fraction | as `secondary` |
| `max_ses_frac` | The strongest single-transit SNR divided by the root-sum-square of the individual SNRs | fraction | as `depth` |
| `frac_neg_events` | Fraction of the individual transits with a negative depth (a brightening) | fraction | as `depth_err` |
| `toi_alias` (some files) | `True` if `period` is within 0.3% of a harmonic (1/3 to 3) of a masked TOI on the star: leakage from an imperfect mask | boolean | not present in `all_signals.csv.gz` |
| `repeat` | `True` if `period` matches an earlier signal on the star (within 0.5%, or at 2:1 within 0.2%): leftover variability rather than a new signal | boolean | never empty |
| `rot_alias` | `True` if `period` is within 2% of one third, one half, one, two or three times a rotation period measured on the star | boolean | never empty |
| `tic` | TIC ID of the host star | integer | never empty |
| `method` | `semi` if the signal came from the semi-coherent search, otherwise `coherent`. The stack-slide searches (TOI hosts, faint M dwarfs, 20–100 d) also carry `coherent` | text | never empty |
| `rho` | Stellar density used for the search: the TIC density, or mass/radius³ when it is missing, clipped to 0.3–30 | solar density | never empty |
| `n_sectors` | Number of sectors with usable data | count | never empty |
| `n_new_sectors` | Number of those that are Sector 97 or later | count | never empty |
| `span` | Time span of the data | days | never empty |
| `noise_ppm` | Robust scatter of the detrended flux | ppm | never empty |
| `tce_period` (`*_tce` only) | Period of the SPOC TCE the signal was re-measured from | days | never empty |
| `tce_snr` (`*_tce` only) | Model signal-to-noise ratio of that TCE | dimensionless | never empty |
| `tce_file` (`*_tce` only) | Name of the SPOC TCE table the TCE came from | text | never empty |

### Additional columns of `vetted_signals*.csv.gz`

Each vetted row also holds all the columns above. Vetting re-detrends the light curve with the transits masked.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `vet_snr` | Signal-to-noise ratio of the box depth measured in vetting | dimensionless | never empty |
| `MES` | LEO-Vetter multiple-event statistic | dimensionless | never empty |
| `rp` | Planet radius: √(`depth_ppm` × 10⁻⁶) × TIC stellar radius | R⊕ | never empty |
| `depth_ppm` | Box depth measured in vetting | ppm | never empty |
| `chi2_sec` | χ² per degree of freedom of the per-sector depths about their combined depth | dimensionless | never empty |
| `snr_old` | Signal-to-noise ratio of the box depth in Sectors 1–96 | dimensionless | never empty |
| `snr_new` | The same in Sectors 97 and later | dimensionless | never empty; 0 when no such sector has data |
| `n_fail` | Number of LEO-Vetter tests failed | count | never empty |
| `fails` | The failed tests, joined by `; `. There are 17 (13 false-alarm and 4 false-positive tests): `unphysical transit orbit`, `events not unique in phased light curve`, `significant secondary`, `inconsistent transit SNRs`, `sinusoidal variations`, `signal too weak`, `bad transit model fit`, `not enough valid transits`, `odd-even transit differences`, `inconsistent transit depths`, `dominated by single event`, `events not unique in local light curve`, `radius too large`, `asymmetric events`, `bad transit shape`, `too many transits near gaps`, `V-shaped events` | text | no test failed |
| `known_status` | Result of matching against known objects: `known` (ExoFOP TOI or CTOI, NASA Exoplanet Archive planet, or SPOC TCE on the same star at a harmonic period), `reported` (a published list outside ExoFOP), `ours` (one of this project's candidates; no row has it in these files), `neighbour` (a known signal on a TIC star within 2.5′), `new` (none of these) | text | never empty |
| `known_detail` | The first match, as `table:label:xratio` with `table` one of `toi`, `ctoi`, `planet`, `tce`, `literature` or `ours`. For `new` it lists up to three known objects on the same star at other periods, as `table:label:P=period` (`literature:label` for literature entries) | text | no match and no known object on the star |

## Follow-up tables

`followup_*.csv` give the neighbour and pixel checks of the signals that were followed up: by default those with
`known_status` `new` and no failed LEO-Vetter test. There is one file per search: `followup_kmdwarfs.csv` (K/M dwarfs),
`followup_toi_hosts.csv`, `followup_tce.csv`, `followup_long.csv`, `followup_long_toi_hosts.csv`,
`followup_faint_t1.csv` and `followup_faint_t2.csv`. All have the same nine columns, and `tic` and `rank` match the
columns of `vetted_signals*.csv.gz`.

| Column | Meaning | Units, timescale | Empty means |
|---|---|---|---|
| `tic` | TIC ID of the host star | integer | never empty |
| `rank` | As in the signal tables, including the offset of 10 for `semi` signals | integer | never empty |
| `period` | Period of the signal | days | never empty |
| `depth_ppm` | Box depth measured in vetting | ppm | never empty |
| `offset_qual` | Offset of the difference-image PRF centroid from the target in the image of highest fit quality among the sectors examined | arcsec | no usable difference image or the fit failed (11 rows: 2 in `followup_faint_t1.csv`, 9 in `followup_tce.csv`) |
| `offset_mean` | Quality-weighted mean of the offsets of the sectors examined | arcsec | as `offset_qual` |
| `n_capable_2.5arcmin` | Number of TIC stars within 2.5′ that could produce the depth if they were eclipsing binaries | count | the neighbour lookup failed (7 rows, all in `followup_faint_t1.csv`; the rows of the other files are filled) |
| `nearest_capable_arcsec` | Separation of the nearest such star | arcsec | the lookup failed (the same 7 rows), or no such star within 2.5′ |
| `flags` | `offset` (`offset_qual` above 15″), `no_pixel` (no usable difference image), `close_nb` (such a star within 15″), joined by `,`. The combinations in the files are `offset`, `close_nb`, `offset,close_nb`, `no_pixel` and `no_pixel,close_nb` | text | none raised |

## `funnel_allsky.csv`

Stage counts of the full-sky search, written by `pipeline/funnel.py` from the search's output tables (signals,
candidates, vetted and follow-up tables), for the website. One row per pass, band and stage.

| Column | Meaning |
|---|---|
| `pass` | `full-sky search` (the first pass), `QLP re-search` (the second), or an inverted-light-curve run: `inverted, sample 1`, `inverted, sample 2` (the two random samples of the first pass) and `inverted, QLP re-search` |
| `band` | `all` (for `stars` and `signals`), `hi` (SNR ≥ 9) or `low` (7.5 ≤ SNR < 9) |
| `stage` | `stars` searched; `signals` found; `prefilter` (pass the pre-filters, one row per star and period); `vetted`; matched as `known`, `reported`, `neighbour` or `ours`; `leo_pass` (not matched, every LEO-Vetter test passed); `cuts` (also MES ≥ 7.1, per-sector χ²/dof ≤ 5, Rp ≤ 20 R⊕); then the pixel checks of those: `offset`, `no_image`, `close_nb` (only a capable TIC star within 15″) and `clean`; and `clean_mes_lt10`, `clean_mes_10_12`, `clean_mes_ge12`, the clean ones by MES |
| `count` | the number of signals (stars for `stars`) |

The inverted runs have no signals table in the outputs kept, so their `stars` come from the lists of stars searched and
they have no `signals` or `prefilter` rows. The first pass's SNR 7.5–9 band was vetted from its signals table without
a candidates table, so its `prefilter` is computed with the pre-filters and its matches come from the vetted table.

## Known quirks

- **`host_tois` and `zenodo_with_period`** are empty in every row of `candidates_allsky.csv`: TOI hosts were searched
  separately, and no Zenodo record matched. The dated release tables fill `host_tois`.
- **`T0_BJD` and `T0_BJD_TDB` are different epochs.** `T0_BJD` in the candidate tables is a full BJD_TDB and is usually
  the first transit in the data. `T0_BJD_TDB` in `ephemerides.csv` is the fitted transit nearest the centre of the
  observed transits, chosen so that the epoch and period errors are uncorrelated. For the same candidate the two
  differ by hundreds of days (for example 763.8 d for TIC 137499615, P = 0.9919 d). Use `T0_BJD_TDB` and `period_d` to
  predict transits.
- **<!--n:catalog.fpp_g.missing_with_fpp|Word-->Four<!--/n--> rows with TRICERATOPS values have empty `FPP_g`, `NFPP_g`, `NFPP_g_mean`, `FPP_gc` and `NFPP_gc`**, because their stars have
  no Gaia DR3 row or no TIC mass for MOLUSC. One of them, TIC 370244729 (3.62 d, no TIC mass), was a counted tier S
  candidate until 15 October; its tier uses the default-prior values, and with `FPP_c` 0.504 it is now tier C
  ([details](../validation/gaia_companion_limits.md)).
- **`fa_score` and tier L1 use different scores.** `fa_score` is the out-of-fold score; tier L1 is selected on the
  hold-out score, published since 13 October as `fa_score_h` (cut 0.80). All <!--n:catalog.tier.L1-->112<!--/n--> tier L1 rows have `fa_score_h` ≥ 0.80,
  and <!--n:catalog.l1_low_fa_score-->31<!--/n--> of them have `fa_score` < 0.80. `fa_flag` applies to tiers M, S and N only, so those are not flagged.
- **Two depths.** `depth_ppm` in the candidate tables is the vetting box depth, whereas `depth_ppm` in `ephemerides.csv`
  is the depth of the fitted model, so the two differ slightly for the same signal (493 and 484 ppm for TIC 137499615
  at 0.9919 d). `duration_h` in `ephemerides.csv` and `predictions.csv` is the fitted T14, as is `T14_h` in the
  candidate tables when there is a fit.
- **TIC 343942488 (0.65 d)** has transits in one sector only (Sector 83), so its period is uncertain by ±0.0004 d
  and its predicted transit times by hours.
- **`binary_at_target` can match a known planet.** A planet's own transits can appear in VSX (type EP) or in the TESS
  eclipsing-binary catalog. This happens for WASP-166 b (`tess_eb P=5.4435;vsx:EP P=5.4435` in
  `tiers_earlier_candidates.csv`) and for TIC 678621, a K2 candidate (`vsx:EP:`), now tier `reported`.
- **`method` does not name the search.** `coherent` is the default label, so the stack-slide results carry it too.
- **`rank` differs between table families.** It is 1 to 3 (4 for TOI hosts) in `all_signals*.csv.gz`. In
  `vetted_signals.csv.gz` and `followup_kmdwarfs.csv`, which hold signals of two search methods, 10 is added for `semi`,
  so a signal with `rank` 1 in `all_signals.csv.gz` has `rank` 11 in the vetted and follow-up tables if its `method` is
  `semi`.
- **`period_match` can list the table it is in.** Entries starting `ours:` match this project's candidate tables,
  including the one that holds the row.
- **`n_new_sectors` always counts Sectors 97 and later**, whichever search the file is from.
