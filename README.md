# Multi-sector TESS transit searches of nearby K and M dwarfs and of TOI hosts

Independent searches of NASA TESS light curves for small transiting planets. The first combines
the newest TESS sectors (97–105) with every earlier sector of 9,979 nearby K and M dwarfs. The
second, added on 8 October 2026, looks for additional planets around the hosts of 6,430 TESS
Objects of Interest (TOIs) after masking the known TOIs.

- **First release (7 October 2026):** 10 transit-candidate signals on 9 stars for which we found
  no prior report, including a possible third transiting planet in the TOI-4342 system, and two
  signals that others had reported earlier in 2026.
- **Update (8 October 2026):** 20 more candidates for which we found no prior report:
  6 from completing the fully coherent search of the K/M dwarfs and 14 from the TOI-host search,
  plus two further signals on TIC 231725883. Every TOI-host candidate is on a star that already
  has a TOI, which makes it less likely to be a false positive.

**These are planet candidates, not confirmed planets.** Each passes automated and pixel-level
vetting, but TESS alone cannot rule out every false-positive scenario. Ground-based photometry,
high-resolution imaging, or radial velocities are needed to confirm or reject them.

![Candidate transits](figures/candidates_grid.png)

## Candidates

Radii use TIC 8.2 stellar radii. FPP is the TRICERATOPS false-positive probability from TESS
data alone (no follow-up imaging, no multiplicity boost), averaged over 10 runs from the update
onwards; the statistical-validation threshold is FPP < 0.015.

### First release (7 October 2026)

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
| 231725883 | 9.098778 | 2.47 ± 0.07 | 5110 K, 155 pc | – | independent recovery; in the RAVEN first-stage detection list ([Lafarga et al. 2026](https://arxiv.org/abs/2603.22597)), not in their vetted list; the update finds two more signals on this star |

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
produce the dip. Its predicted RV semi-amplitude is about 2 m/s. The TOI-host search, which masks
b and c before searching, finds it again as the strongest remaining signal.

### Added 8 October 2026

These passed every check: no match in the ExoFOP TOI and CTOI lists, the NASA Exoplanet
Archive, the SPOC TCE tables or the literature check (below); all 17 LEO-Vetter tests; MES ≥ 7.1;
per-sector depths consistent (χ²/dof ≤ 5); a difference-image centroid within 15″ of the target;
no TIC star within 15″ bright enough to produce the dip; and no report found by a web search on
each TIC ID and host TOI ([`novelty_check.md`](results_public/novelty_check.md)). "Known on star" lists the TOIs
(with TFOPWG disposition) on the same star.

![Update candidates](figures/candidates_update_grid.png)

| TIC | Period (d) | Radius (R⊕) | Host (Teff, T mag, distance) | Known on star | FPP | Notes |
|---|---|---|---|---|---|---|
| 32636748 | 0.732324 | 1.43 | 4094 K, 10.4, 55 pc | – | unstable | K/M dwarfs; ultra-short period; TRICERATOPS gives 0.00–0.98 over 10 runs for this 0.7 h transit |
| 117799904 | 3.291093 | 1.39 | 4045 K, 10.9, 61 pc | TOI-2457.01 (PC, 14.20 d) | 0.053 | K/M dwarfs; second signal on TOI-2457 (found by both searches) |
| 124094573 | 13.721761 | 2.18 | 4590 K, 11.4, 110 pc | – | 0.068 | K/M dwarfs |
| 242080609 | 16.955247 | 1.89 | 4500 K, 9.7, 54 pc | – | 0.026 | K/M dwarfs; T=9.7, 5 transits |
| 257484419 | 18.056783 | 2.58 | 4184 K, 11.2, 81 pc | – | 0.016 | K/M dwarfs |
| 179985715 | 19.092785 | 2.56 | 4047 K, 11.3, 71 pc | TOI-249.01 (PC, 6.62 d) | 0.132 | K/M dwarfs; second signal on TOI-249; grazing (b=0.9); Gaia RUWE 2.0 |
| 317134140 | 0.571863 | 1.31 | 5563 K, 10.7, 174 pc | TOI-2514.01 (PC, 6.39 d) | 0.066 | TOI hosts; ultra-short period |
| 72668830 | 2.000544 | 1.59 | 4985 K, 10.4, 116 pc | TOI-4296.01 (FA, 19.97 d); TOI-4296.02 (PC, 5.10 d); TOI-4296.03 (PC, 12.49 d) | 0.105 | TOI hosts |
| 165827520 | 2.004481 | 1.15 | 3230 K, 12.3, 34 pc | TOI-3494.01 (PC, 7.75 d) | 0.088 | TOI hosts; a star 0.59″ away (Δ*I* = 2.9) is known from imaging (Matson et al. 2025), so the radius is a lower limit |
| 383313006 | 4.251808 | 2.05 | 3719 K, 11.8, 73 pc | TOI-6758.01 (PC, 12.61 d) | 0.165 | TOI hosts |
| 380671216 | 5.575799 | 2.29 | 5729 K, 10.6, 191 pc | TOI-5495.01 (PC, 9.66 d) | 0.047 | TOI hosts |
| 423445163 | 6.212551 | 2.75 | 4593 K, 12.5, 187 pc | TOI-6489.01 (PC, 2.92 d) | 0.016 | TOI hosts |
| 441590110 | 6.462490 | 4.13 | 6263 K, 11.6, 436 pc | TOI-5187.01 (PC, 17.86 d) | 0.020 | TOI hosts |
| 410449566 | 7.109099 | 2.70 | 5949 K, 11.5, 239 pc | TOI-7546.01 (PC, 9.64 d) | 0.224 | TOI hosts |
| 402992891 | 8.005848 | 2.48 | 5589 K, 11.0, 164 pc | TOI-7356.01 (PC, 17.40 d) | 0.027 | TOI hosts |
| 468983280 | 8.966677 | 1.41 | 3547 K, 11.7, 45 pc | TOI-5489.01 (PC, 3.15 d); TOI-5489.02 (PC, 4.92 d) | 0.121 | TOI hosts; TOI-5489 b and c are confirmed planets, so this would be a third |
| 416739490 | 10.565600 | 2.03 | 5554 K, 10.8, 150 pc | TOI-5697.01 (PC, 6.22 d) | 0.061 | TOI hosts |
| 154437244 | 11.279747 | 2.84 | 6173 K, 11.1, 273 pc | TOI-5989.01 (PC, 6.87 d) | 0.015 | TOI hosts |
| 445837596 | 15.000796 | 2.42 | 5127 K, 11.7, 182 pc | TOI-3896.01 (PC, 4.38 d) | 0.020 | TOI hosts; TOI-3896 b is a confirmed planet |
| 160585062 | 17.392551 | 1.78 | 4568 K, 12.2, 157 pc | TOI-7333.01 (PC, 6.26 d) | 0.040 | TOI hosts; TOI-7333 b is a confirmed planet |

**TIC 231725883: three signals.** The 9.0988 d signal from the first release (also in the RAVEN
first-stage list) is joined by signals at 4.6593 d (1.43 R⊕) and 18.9653 d (1.95 R⊕), each found
by the coherent search after masking the previous one, each passing all LEO-Vetter tests and
each with consistent depths across sectors. The period ratios are 1.95 and 2.08. A TIC star 13″
away could produce the 4.66 d and 18.97 d dips (but not the deeper 9.10 d one) if it were an
eclipsing binary, so these two are listed separately in
[`results_public/candidates_2026-10-08.csv`](results_public/candidates_2026-10-08.csv), together
with the other signals that pass everything except the 15″ neighbour check.

**TIC 143168991 (TOI-7580), 26.56 d: rejected.** The K/M dwarf search found it with 4 transits,
but two of them fall within 0.2 h of TOI-7580.01 transits; with the TOIs masked only two remain.

### Predicted transit times

[`candidates/predictions.csv`](candidates/predictions.csv) lists every predicted transit of the
first-release candidates through June 2027 with 1σ uncertainties (5–15 min). TESS observes TIC
61816225, 458191673 and 451641911 again in Sectors 111–114, and TIC 422351625 and 135425484 in
Sector 114. This file was committed before those data exist.

## Method

The approach follows Pavel Rabtsevich's search that found TIC 4206066
([write-up](https://doi.org/10.5281/zenodo.22967456), [data](https://doi.org/10.5281/zenodo.22999133)):
detect a signal in recent TESS data and confirm it in archival sectors. SPOC's latest
multi-sector search covers Sectors 1–96, and stars observed only in full-frame images never get a
SPOC multi-sector search at all. A shallow transit that is 5–8σ per sector can stay below every
single-sector threshold while reaching 10–20σ when all sectors are combined.

1. **Targets** (`fetch_targets.py`, `build_targets.py`): TIC 8.2 dwarfs with T ≤ 11.5,
   0.1 < R* ≤ 0.75 R☉, Teff ≤ 5300 K, observed by QLP in Sectors 97–105: 9,979 stars.
   TOI hosts (`build_toi_hosts.py`): every host of a TOI dispositioned CP, KP, PC or APC: 6,430
   stars.
2. **Light curves** (`index_products.py`, `download.py`): one product per star and sector,
   preferring SPOC 2-min PDCSAP, then TESS-SPOC FFI PDCSAP, then QLP. 73,226 light curves for the
   K/M dwarfs and 54,189 for the TOI hosts.
3. **Search** (`search.py`, `fastbls.py`): per-sector biweight detrending (wotan), Lomb–Scargle
   prewhitening of fast rotators (P_rot < 3 d), and box least squares over 0.5–30 d on a
   period grid set by each star's density. Three variants:
   - *coherent*: astropy BLS on the full-baseline grid (~17 s per star);
   - *semi-coherent*: per-season BLS statistics summed, then the top peaks refined coherently
     (~4 s per star), which misses ~15% of weak signals (see Validation);
   - *stack-slide* (`--method stack`, added in the update): each season is folded once per
     coarse frequency; for each fine frequency the folded seasons are shifted by the phase they
     accumulate and summed, which is phase-coherent across seasons (~9 s per star).

   The K/M dwarfs were searched with the coherent and semi-coherent variants, the TOI hosts with
   stack-slide. Up to 3 signals per star (4 for TOI hosts) by iterative masking.
4. **Masking known planets** (`search.py --mask-tois`): for the TOI hosts, every TOI is masked
   before the search, using its catalogue ephemeris widened by 3σ of its propagated timing error
   and our own refit where the signal is detected. Vetting removes the same transits.
5. **Known-signal matching** (`known.py`, `fetch_known.py`): ExoFOP TOIs and CTOIs, NASA Exoplanet
   Archive planets, all public SPOC TCE tables, including period harmonics and TIC neighbours
   within 2.5′.
6. **Literature check** (`literature.py`, added in the update): the RAVEN and T16 candidate tables;
   the SPOC TCEs that ExoMiner++ classifies as planet candidates
   ([Valizadegan et al. 2025](https://arxiv.org/abs/2502.09790),
   [2026](https://arxiv.org/abs/2601.14877)); the LEO-Vetter M-dwarf candidates (Kunimoto et al.
   2025, VizieR J/AJ/170/280); the Eschen et al. (2024) M-dwarf candidates; and TIC IDs, TOI
   designations and nearby periods in the tables and text of 2,037
   arXiv astro-ph.EP papers whose abstracts mention TESS, TOIs or TICs (read from arXiv's HTML
   versions, plus the e-print for papers whose candidate tables are machine-readable only). A
   matching signal is tagged `reported`. Run on the first release, it flags exactly
   the two signals that our manual check had found already published.
7. **Vetting** (`vet.py`): transit-masked re-detrending, the 13 false-alarm and 4 false-positive
   tests of [LEO-Vetter](https://github.com/mkunimoto/LEO-vetter) (Kunimoto et al. 2025),
   per-sector depth consistency, and old-vs-new sector detection. LEO-Vetter's per-cadence loop
   is replaced by a compiled equivalent (same results, 2–5× faster vetting).
8. **Pixel and field checks** (`followup.py`, automated in the update): TIC stars within 2.5′
   that could produce the depth as eclipsing binaries (`neighbors.py`), and FFI difference-image
   PRF centroids with [transit-diffImage](https://github.com/stevepur/transit-diffImage) in the
   two sectors with the strongest transits and smallest cutouts, with LEO-Vetter's 15″ limit.
   For the first release these were run by hand (`pixel_vet.py`, `tpf_pixels.py`).
9. **Characterisation**: batman + emcee transit fits with a TIC stellar-density prior
   (`fit_transit.py`) and [TRICERATOPS](https://github.com/stevengiacalone/triceratops) FPP
   (`export_fold.py`, `fpp.py`, now vectorised, with the Gaia query cached and 10 runs averaged).
10. **Novelty**: for the first release, ExoFOP pages, TOI/CTOI lists, NASA Exoplanet Archive, SPOC
    TCEs, the T16 catalogue ([Roth et al. 2026](https://arxiv.org/abs/2604.18579)), the RAVEN
    tables, the [Tschudi 2026](https://arxiv.org/abs/2607.23781) survey source, and web searches on
    every TIC ID, run on 2026-10-07 (see
    [`results_public/novelty_check.md`](results_public/novelty_check.md)); for the update, steps 5
    and 6 plus web searches on every candidate TIC ID and host TOI.

### Funnel

| Stage | K/M dwarfs | TOI hosts |
|---|---|---|
| Stars searched | 9,972 | 6,430 |
| Signals found | 41,758 | 15,222 |
| Pass pre-filters (SNR ≥ 9, ≥ 3 transits, duration and shape cuts; TOI hosts: FGKM dwarfs only) | 1,549 | 660 |
| Match a known planet, TOI, CTOI or TCE | 236 (of which 109 pass every LEO-Vetter test) | 229 (of which 94 pass every LEO-Vetter test) |
| Match a published list outside ExoFOP (literature check) | 14 | 10 |
| Match a neighbour's known signal | 23 | 1 |
| Unmatched | 1,276 | 420 |
| Unmatched and passing every LEO-Vetter test | 38 | 40 |
| … centroid more than 15″ from the target | 11 | 11 |
| … a TIC star within 15″ could produce the dip | 14 | 11 |
| … neither | 13 | 18 |
| … and MES ≥ 7.1, per-sector χ²/dof ≤ 5 | 13 | 16 |

The last row includes six first-release candidates (K/M dwarfs) and TOI-4342's 18.9 d signal (TOI
hosts); TIC 117799904 is counted in both columns; TIC 143168991's 26.56 d signal (above) was
rejected by hand.

## Validation

- **Blind recovery of TIC 4206066.** Both of Rabtsevich's signals were found without prior
  knowledge: 3.18278 d (his 3.182785 d) and 11.13274 d (his 11.13274 d), with Rp = 1.41 R⊕ (his
  1.4) and the nearest depth-capable neighbour at 44.6″ (his ≳ 43″). See
  [`figures/validation_tic4206066.png`](figures/validation_tic4206066.png).
- **Known planets.** TOI-700 b and c, and L 98-59 b, c and d are recovered
  ([`validation/`](validation/)). With the TOIs masked, the TOI-host search recovers TOI-4342's
  18.9 d signal and the community candidate L 98-59 .04 (CTOI, 1.05 d).
- **Injection–recovery.** Transits injected at a nominal SNR of 10 into 300 random targets
  ([`validation/injection_recovery_snr10_n300.csv`](validation/injection_recovery_snr10_n300.csv)):

  | Search | Recovered at the injected period | Detected with SNR ≥ 9 | Median time per star |
  |---|---|---|---|
  | coherent | 60% | 92 (31%) | 17.5 s |
  | stack-slide | 62% | 88 (29%) | 8.9 s |
  | semi-coherent | 52% | 78 (26%) | 4.2 s |

  Of the SNR ≥ 9 detections, 6 were found only by the coherent search and 2 only by stack-slide;
  18 were found only by the coherent search and 4 only by the semi-coherent one.
- **False alarms.** Searching the inverted light curves of 1,500 random K/M dwarfs (`EXO_INVERT=1`),
  where any dip is a false alarm: 157 signals pass the pre-filters, 1 passes all LEO-Vetter tests,
  and none also has consistent per-sector depths. The real light curves of the same stars give
  6 new signals passing all LEO-Vetter tests, 4 of them with consistent depths. Inversion measures
  false alarms from noise and systematics, not astrophysical false positives such as background
  eclipsing binaries, which steps 8 and 9 address.
- **Automated vs manual checks.** On the first-release signals, `followup.py` passes 7 of the 12
  cleanly, flags the close neighbours we had noted by hand for 4 (TIC 166321785, 147226218,
  451641911, 30470520), and puts TOI-6284's 5.24 d centroid at 15.2″, just over the limit (our
  2-min pixel analysis gave 2.8″). It rejects TIC 264151965, which we had set aside, with a 106″
  offset.
- **Compiled LEO-Vetter loop.** On 6 test signals the compiled version gives the same pass/fail
  results and metrics equal to ~10⁻⁹ (`EXO_SLOW_LEO=1` runs the original).

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
../.venv/bin/python literature.py           # RAVEN, T16, arXiv mentions; ~2 h the first time (arXiv allows
                                            # one request per 3 s), then only new papers are fetched
../.venv/bin/python index_products.py       # MAST product list
../.venv/bin/python download.py             # ~130 GB transferred, ~12 GB stored
../.venv/bin/python search.py targets.txt --method semi --out ../results/search_semi
../.venv/bin/python search.py targets.txt --method coherent --out ../results/search
./triage.sh                                 # collect -> vet -> shortlist
../.venv/bin/python followup.py             # neighbours + difference-image centroids

# TOI hosts
../.venv/bin/python build_toi_hosts.py
../.venv/bin/python index_products.py --targets ../data/catalogs/toi_hosts.parquet --out ../data/catalogs/manifest_toi.parquet
../.venv/bin/python download.py ../data/catalogs/toi_hosts.txt --manifest ../data/catalogs/manifest_toi.parquet
../.venv/bin/python search.py ../data/catalogs/toi_hosts.txt --stars ../data/catalogs/toi_hosts.parquet \
    --out ../results/search_toi --method stack --mask-tois --max-signals 4
../.venv/bin/python collect.py --search ../results/search_toi --stars ../data/catalogs/toi_hosts.parquet \
    --out ../results/cands_toi.csv --signals ../results/signals_toi.parquet --dwarfs
../.venv/bin/python vet.py ../results/cands_toi.csv --out ../results/vet_toi --stars ../data/catalogs/toi_hosts.parquet
../.venv/bin/python shortlist.py --cands ../results/cands_toi.csv --vet ../results/vet_toi --out ../results/vetted_toi.csv
../.venv/bin/python followup.py --vetted ../results/vetted_toi.csv --vet-dir ../results/vet_toi \
    --stars ../data/catalogs/toi_hosts.parquet --out ../results/followup_toi

# validation
../.venv/bin/python inject_test.py 300 --methods coherent,semi,stack
EXO_INVERT=1 ../.venv/bin/python search.py sample.txt --method stack --out ../results/search_inv

# extensions in progress (results not yet published)
../.venv/bin/python build_tce_targets.py    # SPOC TCEs on dwarfs that never became TOIs or CTOIs
./triage_tce.sh                             # re-measure them with later sectors, vet, follow up
../.venv/bin/python search.py stars.txt --method stack --pmin 20 --pmax 100 \
    --premask ../results/search --out ../results/search_long      # 20-100 d, earlier signals masked
../.venv/bin/python fetch_targets.py --tmin 11.5 --tmax 13.5 --rmax 0.6 --step 0.02 \
    --out ../data/catalogs/tic_faint_mdwarfs.parquet && ../.venv/bin/python build_faint_targets.py
../.venv/bin/python ads_check.py candidates.csv ads.csv                 # needs an ADS API token
EXO_DATA_SOURCE=s3 ../.venv/bin/python download.py ...                  # read from the AWS mirror
```

`EXO_DATA_SOURCE=s3` reads light curves from the STScI open-data bucket and falls back to MAST.
Inside AWS us-east-1 this is about 20 times faster than downloading from MAST.

`targets.txt` is one TIC ID per line. Per-candidate follow-up: `fit_transit.py`, `export_fold.py`,
`fpp.py` (in `.venv-trice`), `candidate_table.py`, `predict.py`, `make_figures.py`,
`package_candidates.py`. Light curves and catalogs are downloaded into `data/` and are not part
of the repository.

## Layout

```
pipeline/          code
candidates/        one folder per candidate + predictions.csv
figures/           figures used here
results_public/    all signals, vetted signals, candidate tables, novelty check
validation/        control-star vetting outputs and the injection-recovery tables
```

## Credits

This work uses data from the TESS mission, obtained from MAST at STScI: SPOC light curves
(Jenkins et al. 2016), TESS-SPOC FFI light curves (Caldwell et al. 2020), and QLP light curves
(Huang et al. 2020). It uses data from the ESA mission Gaia, processed by the Gaia DPAC, and the
Gaia Catalogue of Nearby Stars (Gaia Collaboration, Smart et al. 2021). This research has made use
of the Exoplanet Follow-up Observation Program (ExoFOP; DOI: 10.26134/ExoFOP5) website, which is
operated by the California Institute of Technology, under contract with the National Aeronautics
and Space Administration under the Exoplanet Exploration Program, and of the NASA Exoplanet
Archive. The literature check uses the RAVEN (Lafarga et al. 2026) and T16 (Roth et al. 2026)
catalogues and arXiv. Software: astropy, numpy, scipy, numba, lightkurve, wotan, batman, emcee,
LEO-Vetter, transit-diffImage, tess-point and TRICERATOPS.

Method inspired by Pavel Rabtsevich's TIC 4206066 study. Built with Claude Code (Anthropic).

## License

Code: MIT (see `LICENSE`). Results, tables and figures: CC BY 4.0.
