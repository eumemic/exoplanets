# TRICERATOPS with single-cadence light curves (15 October 2026)

## Why

TRICERATOPS models every light-curve point with one exposure time. Until now each signal's fold combined every sector
(30-minute, 10-minute, 200-second and 2-minute data), binned to 5 minutes and modelled with a 10-minute exposure
(`pipeline/export_fold.py`, `pipeline/fpp.py`). Antoine Rabtsevich ([issue #1](https://github.com/eumemic/exoplanets/issues/1))
found FPP 0.06–0.90 for TIC 160420269 (17 R⊕), where the catalog had FPP below 1e-10. Rerunning that signal three
ways reproduced his values only with consistent input: the catalog's fold gave FPP about 1e-7; its five 200-second
sectors, binned the same way and modelled with a 200-second exposure, 0.54; the same sectors unbinned, 0.37.

A test on 30 counted candidates whose transits come in two or more cadences (`results_cloud/glue/fppcheck/`,
`analyze_fc2.py`), ten runs each with the default priors:

| Comparison | Median FPP ratio | 10–90% of ratios |
|---|---|---|
| short-cadence sectors with their own exposure / catalog input | 1.00 | 0.65–3.4 |
| the same short-cadence data with their own exposure / with a 10-minute exposure | 1.05 | 0.91–1.23 |

So the exposure setting matters little; which data go in matters. One candidate crossed the tier thresholds (TIC
37068395, 1.1% deep, 8.7 R⊕: FPP 0.03 → 0.56 with its one 200-second sector), and the validation thresholds changed
for 5 of the 30 in FPP and 5 in NFPP.

## The new input

`export_fold.py --single-cadence` uses the sectors of one cadence: of 2-minute, 200-second, 10-minute and 30-minute
data, the one whose points within half a duration of mid-transit carry the most information (the largest sum of
inverse variances), after masking other signals and TOIs on the star. 2-minute and 200-second data are binned in phase
to their own cadence (bins with at least one point); 10- and 30-minute data are binned in phase to 2 minutes, far
narrower than their exposure (unbinned, an ultra-short-period signal has thousands of points and one run took 20
minutes). The fold records its
exposure, and TRICERATOPS models each point with one sub-exposure per 2 minutes of it (1 for 2-minute data, 2 for
200 seconds, 5 for 10 minutes, 15 for 30 minutes; TRICERATOPS's default is 20 for any exposure). The field geometry
(apertures, neighbours, flux ratios) uses the three sectors of that cadence with the most in-transit information.
Everything else is as before: ten runs of 2×10⁵ draws with the default priors and ten with the Gaia limits (MOLUSC
companions, EB scenarios dropped where Gaia RVs exclude them), a 3×3-pixel aperture, nearby-star scenarios within 30″.

## How it ran

`pipeline/fpp_fleet.py` (folds, FFI cutouts from the S3 cubes, target setup) and `pipeline/fpp_pool.py` (one process
pool per machine): each star's TRICERATOPS target is set up once and cached (`fpp_core.save_state`), and every run of
every signal is a separate task, longest first, seeded from its signal, mode and run number. On a prebuilt machine image
with both Python environments, an instance is ready about a minute after launch instead of 5–21. The run used four
spot instances (224 vCPUs, the account's spot limit) for the 1,299 signals that have Gaia-limited runs in the catalog.

## Results

1,298 of the 1,299 signals have new values; TIC 442925572 (14.54 d, a likely nearby false positive with FPP_gc 0.96)
failed its setup twice and keeps its earlier values. The cadence used: 200 seconds for 989 signals, 10 minutes for 159,
30 minutes for 84 and 2 minutes for 66. `results_cloud/glue/t2/apply_t2.py` wrote the new values and tiers.

- Relative to the earlier input, `FPP_gc` changes by a median factor of 1.05 (10–90%: 0.45–2.8). The median `FPP_gc` of
  the counted candidates stays 0.013.
- 55 signals change tier:
  - 25 tier N candidates fail NFPP < 0.1 or FPP < 0.5 and become likely nearby false positives. 7 of them had been
    flagged by the per-sector centroid test, and 12 have centroid ratios that favour a neighbour.
  - 13 tier B candidates (9 of them larger than 8 R⊕) and one tier A candidate of the earlier searches (TIC 410449566,
    7.11 d) move to tier C. One tier L1 candidate (TIC 296974573) returns to tier L.
  - 14 tier C signals now pass and are counted, among them both signals of TIC 229511659 (5.27 and 7.08 d), which are
    now tier A.
- Counted candidates: 632 (575 full-sky: 22 A, 292 B, 149 N, 112 L1; 57 from the earlier searches), against 658.
- Meeting the validation thresholds apart from imaging (FPP < 0.015, NFPP < 0.001, smaller than 8 R⊕, from the
  catalog's rounded values): 267 (240 full-sky, 27 earlier), against 288.
- TIC 160420269: `FPP_gc` 0.33, tier B (it was about 1e-7). TIC 37068395, the 1.1% deep candidate of the test above, uses
  a single 10-minute sector here (more in-transit information than its 200-second sector) and stays tier B (0.003).

## Cost and run time

25,960 runs in the final results took 101 CPU-hours (median 7.3 s per run, 90% within 33 s, the longest 163 s); with
runs repeated after the problems below, 153 CPU-hours. Spot instances cost about $5. Four instances (224 vCPUs) ran for
1.5–2 hours because of three problems, all now handled in the code:

- **Disk.** Each FFI cutout holds every cadence of its sector (about 90 MB for 200-second sectors), and the setup kept
  them all until it ran: 80 GB per instance. The volumes were grown in place; a full disk had truncated some cutouts,
  and 20 signals were set up again. `fpp_fleet.py` now keeps only the first 50 cadences of each cutout, since
  TRICERATOPS uses only its WCS and mean image.
- **Memory.** TRICERATOPS evaluates all transiting draws of a scenario at once, about 2×10⁴ draws times the points
  and sub-exposures, up to 8 GB for one run. With the costliest runs first and 63 workers, the kernel killed workers,
  and Python's process pool waits forever for their tasks. `fpp_pool.py` now keeps the estimated memory of the runs in
  flight under 80% of the machine's.
- **Processes.** Forked workers die when the parent has used GNU OpenMP (PyTransit's kernels); the pool spawns them.
  A forced reboot after one instance ran out of memory left its recently written files empty, and that instance's setup
  was repeated.

With these fixed and every run a separate task, the run time is set by the number of cores: about 100 CPU-hours for
all 1,299 signals, under an hour on the account's present spot limit of 256 vCPUs. The one-time work per star (FFI
cutouts, the Gaia field query and MOLUSC's 2×10⁵ simulated companions, about 2 CPU-minutes) can be kept between runs.

## A faster sampler, not used

`pipeline/fast_trice.py` tries to estimate the same integrals with fewer draws: a scrambled Sobol pilot, then importance
sampling in the space of TRICERATOPS's uniform random numbers, from a proposal fitted to the pilot. On 24 signals it
used 6 times less CPU than ten stock runs, but its FPP was biased low (a median 0.58 of stock TRICERATOPS's; 22 of 48
estimates more than 3 standard errors away). When few pilot draws reach the likelihood peak, as for the eclipsing-binary
scenarios, the fitted proposal misses most of it. It is not used.
