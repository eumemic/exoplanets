# Multi-sector TESS transit search of 9,979 nearby K and M dwarfs

An independent search of NASA TESS light curves for small transiting planets around nearby
K and M dwarfs. It combines the newest TESS sectors (97–105) with every earlier sector of the
same stars. **It produced 10 transit-candidate signals on 9 stars for which we found no prior
report**, including a possible third transiting planet in the TOI-4342 system. It also
independently recovered two signals that others reported earlier this year.

**These are planet candidates, not confirmed planets.** Each passes automated and pixel-level
vetting, but TESS alone cannot rule out every false-positive scenario. Ground-based photometry,
high-resolution imaging, or radial velocities are needed to confirm or reject them.

![Candidate transits](figures/candidates_grid.png)

## Candidates

Radii use TIC 8.2 stellar radii. FPP is the TRICERATOPS false-positive probability from TESS
data alone (no follow-up imaging, no multiplicity boost); the statistical-validation threshold is
FPP < 0.015.

| TIC | Period (d) | Radius (R⊕) | Host (Teff, distance) | FPP | Status |
|---|---|---|---|---|---|
| 354944123 (TOI-4342) | 18.90820 | 2.21 ± 0.11 | 3880 K, 62 pc | 0.14 | no prior report found; third transiting signal in a system with two confirmed planets |
| 61816225 | 12.77703 | 1.99 ± 0.06 | 4380 K, 57 pc | 0.03 | no prior report found |
| 458191673 | 2.570687 | 2.31 ± 0.07 | 4470 K, 66 pc | 0.03 | no prior report found |
| 422351625 | 8.14641 | 2.35 ± 0.16 | 4410 K, 93 pc | – | no prior report found; second signal on the same star ↓ |
| 422351625 | 1.969879 | 1.46 ± 0.09 | 4410 K, 93 pc | – | no prior report found |
| 166321785 | 2.480128 | 2.08 ± 0.09 | 4380 K, 96 pc | – | no prior report found; two T≈15–16 stars at 9″ |
| 147226218 | 3.87159 | 1.57 ± 0.08 | 4840 K, 77 pc | – | no prior report found; T=16.6 star at 3.4″ |
| 451641911 | 3.90974 | 1.36 ± 0.05 | 3650 K, 41 pc | – | no prior report found; crowded field |
| 30470520 | 18.75190 | 1.45 ± 0.04 | 5150 K, 208 pc | – | no prior report found; crowded field, depth varies by sector |
| 135425484 | 8.03350 | 3.12 ± 0.15 | 4230 K, 79 pc | – | no prior report found; impact parameter 0.91 (near-grazing) |
| 286763141 (TOI-6284) | 5.244548 | 0.85 ± 0.04 | 3550 K, 21 pc | 0.03 | independent recovery; reported as "TOI-6284.02" by [Tschudi 2026](https://arxiv.org/abs/2607.23781) |
| 231725883 | 9.098778 | 2.47 ± 0.07 | 5110 K, 155 pc | – | independent recovery; in the RAVEN first-stage detection list ([Lafarga et al. 2026](https://arxiv.org/abs/2603.22597)), not in their vetted list |

Each candidate has a folder in [`candidates/`](candidates/) with the vetting plot and metrics,
the transit fit (P, T0, Rp/R*, b, ρ*), PRF centroid offsets, nearby stars bright enough to mimic
the signal, and the TRICERATOPS result where computed. All parameters are in
[`results_public/candidates.csv`](results_public/candidates.csv).

### TOI-4342: a third transiting candidate

![TOI-4342](figures/toi4342.png)

TOI-4342 b and c are confirmed sub-Neptunes at 5.54 and 10.69 d
([Tey et al. 2023](https://arxiv.org/abs/2301.01370); masses from
[ESPRESSO, 2026](https://arxiv.org/abs/2601.22115), which also reports a probably non-transiting
47.5 d RV candidate). We find a third transit signal at 18.9082 d with the same radius as b and c
(2.2 R⊕), with transits in 8 sectors (11σ in Sectors 13–93, 7σ in 101–103). The difference-image centroid
is within 7–16″ of the star in each 2-min sector, and no star within 30″ is bright enough to
produce the dip. Its predicted RV semi-amplitude is about 2 m/s.

### Predicted transit times

[`candidates/predictions.csv`](candidates/predictions.csv) lists every predicted transit through
June 2027 with 1σ uncertainties (5–15 min). TESS observes TIC 61816225, 458191673 and 451641911
again in Sectors 111–114, and TIC 422351625 and 135425484 in Sector 114. This file was committed
before those data exist.

## Method

The approach follows Pavel Rabtsevich's search that found TIC 4206066
([write-up](https://doi.org/10.5281/zenodo.22967456), [data](https://doi.org/10.5281/zenodo.22999133)):
detect a signal in recent TESS data and confirm it in archival sectors. SPOC's latest
multi-sector search covers Sectors 1–96, and stars observed only in full-frame images never get a
SPOC multi-sector search at all. A shallow transit that is 5–8σ per sector can stay below every
single-sector threshold while reaching 10–20σ when all sectors are combined.

1. **Targets** (`fetch_targets.py`, `build_targets.py`): TIC 8.2 dwarfs with T ≤ 11.5,
   0.1 < R* ≤ 0.75 R☉, Teff ≤ 5300 K, observed by QLP in Sectors 97–105: 9,979 stars.
2. **Light curves** (`index_products.py`, `download.py`): one product per star and sector,
   preferring SPOC 2-min PDCSAP, then TESS-SPOC FFI PDCSAP, then QLP. 73,226 light curves.
3. **Search** (`search.py`, `fastbls.py`): per-sector biweight detrending (wotan), Lomb–Scargle
   prewhitening of fast rotators (P_rot < 3 d), and box least squares over 0.5–30 d on a
   period grid set by each star's density. A semi-coherent pass sums per-season BLS statistics
   and refines the top peaks coherently (~5 s/star); a fully coherent pass is also run. Up to 3
   signals per star by iterative masking.
4. **Known-signal matching** (`known.py`, `fetch_known.py`): ExoFOP TOIs and CTOIs, NASA Exoplanet
   Archive planets, all public SPOC TCE tables, including period harmonics and TIC neighbours
   within 2.5′.
5. **Vetting** (`vet.py`): transit-masked re-detrending, the 13 false-alarm and 4 false-positive
   tests of [LEO-Vetter](https://github.com/mkunimoto/LEO-vetter) (Kunimoto et al. 2025),
   per-sector depth consistency, and old-vs-new sector detection.
6. **Pixel and field checks**: FFI difference-image PRF centroids with
   [transit-diffImage](https://github.com/stevepur/transit-diffImage) (`pixel_vet.py`), per-pixel
   2-min TPF difference images (`tpf_pixels.py`), and TIC stars within 2.5′ that could produce the
   depth as eclipsing binaries (`neighbors.py`).
7. **Characterisation**: batman + emcee transit fits with a TIC stellar-density prior
   (`fit_transit.py`) and [TRICERATOPS](https://github.com/stevengiacalone/triceratops) FPP
   (`export_fold.py`, `fpp.py`).
8. **Novelty**: ExoFOP pages, TOI/CTOI lists, NASA Exoplanet Archive, SPOC TCEs, the T16
   catalogue ([Roth et al. 2026](https://arxiv.org/abs/2604.18579)), the RAVEN tables, the
   [Tschudi 2026](https://arxiv.org/abs/2607.23781) survey source, and web searches on every
   TIC ID, run on 2026-10-07. See [`results_public/novelty_check.md`](results_public/novelty_check.md).

### Funnel

| Stage | Count |
|---|---|
| Stars searched | 9,972 |
| Signals found | 21,654 |
| Pass pre-filters (SNR ≥ 9, ≥ 3 transits, duration and shape cuts) | 1,233 |
| Match a known planet, TOI, CTOI or TCE | 226 (108 of them pass every LEO-Vetter test) |
| Match a neighbour's known signal | 22 |
| Unmatched | 985 |
| Unmatched and passing every LEO-Vetter test | 38 |
| Examined in detail and listed above | 12 |

Of the other 26 LEO-passing signals, one is Rabtsevich's TIC 4206066 11.13 d signal (see
Validation), two were examined and set aside — TIC 264151965 (4.82 d; galactic-plane field with a
strongly variable neighbour) and TIC 48439430 (0.55 d; pixel tests disagree between sectors) —
and 23 have not been examined. They are in
[`results_public/vetted_signals.csv.gz`](results_public/vetted_signals.csv.gz)
(`known_status == "new"`, `n_fail == 0`); several are on stars with high Gaia RUWE (likely
binaries) or have only 4–6 transits.

## Validation

- **Blind recovery of TIC 4206066.** Both of Rabtsevich's signals were found without prior
  knowledge: 3.18278 d (his 3.182785 d) and 11.13274 d (his 11.13274 d), with Rp = 1.41 R⊕ (his
  1.4) and the nearest depth-capable neighbour at 44.6″ (his ≳ 43″). See
  [`figures/validation_tic4206066.png`](figures/validation_tic4206066.png).
- **Known planets.** TOI-700 b and c, and L 98-59 b, c and d are recovered
  ([`validation/`](validation/)).
- **Injection–recovery.** Transits injected at a nominal SNR of 10 into 60 random targets are
  recovered at the injected period 57% of the time by the coherent search and 45% by the
  semi-coherent search; 30% and 25% are recovered with measured SNR ≥ 9
  ([`validation/injection_recovery_snr10.csv`](validation/injection_recovery_snr10.csv)).

## Reproducing

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
# transit-diffImage is installed from GitHub (see requirements.txt). Its PRF download URL uses
# http://archive.stsci.edu, which now returns 404; change it to https in tessprfmodel.py.
uv venv --python 3.11 .venv-trice && uv pip install --python .venv-trice/bin/python -r requirements-triceratops.txt

cd pipeline
../.venv/bin/python fetch_targets.py        # TIC criteria query (~10 min)
../.venv/bin/python build_targets.py        # QLP S97-105 lists + Gaia GCNS columns
../.venv/bin/python fetch_known.py          # TOI/CTOI/planets/TCE catalogs
../.venv/bin/python index_products.py       # MAST product list
../.venv/bin/python download.py             # ~130 GB transferred, ~12 GB stored
../.venv/bin/python search.py targets.txt --method semi --out ../results/search_semi
../.venv/bin/python search.py targets.txt --method coherent --out ../results/search
./triage.sh                                 # collect -> vet -> shortlist
```

`targets.txt` is one TIC ID per line. Per-candidate follow-up: `pixel_vet.py`, `tpf_pixels.py`,
`neighbors.py`, `fit_transit.py`, `export_fold.py`, `fpp.py` (in `.venv-trice`), `predict.py`,
`make_figures.py`, `package_candidates.py`. Light curves and catalogs are downloaded into `data/`
and are not part of the repository.

## Layout

```
pipeline/          code
candidates/        one folder per candidate + predictions.csv
figures/           figures used here
results_public/    all signals, vetted signals, candidate table, novelty check
validation/        control-star vetting outputs and the injection-recovery table
```

## Credits

This work uses data from the TESS mission, obtained from MAST at STScI: SPOC light curves
(Jenkins et al. 2016), TESS-SPOC FFI light curves (Caldwell et al. 2020), and QLP light curves
(Huang et al. 2020). It uses data from the ESA mission Gaia, processed by the Gaia DPAC, and the
Gaia Catalogue of Nearby Stars (Gaia Collaboration, Smart et al. 2021). This research has made use
of the Exoplanet Follow-up Observation Program (ExoFOP; DOI: 10.26134/ExoFOP5) website, which is
operated by the California Institute of Technology, under contract with the National Aeronautics
and Space Administration under the Exoplanet Exploration Program, and of the NASA Exoplanet
Archive. Software: astropy, numpy, scipy, lightkurve, wotan, numba, batman, emcee, LEO-Vetter,
transit-diffImage, tess-point and TRICERATOPS.

Method inspired by Pavel Rabtsevich's TIC 4206066 study. Built with Claude Code (Anthropic).

## License

Code: MIT (see `LICENSE`). Results, tables and figures: CC BY 4.0.
