# TIC artifacts and duplicates

On 12–13 October 2026 we found that our neighbour checks treated TIC entries that are not stars as possible sources
of a dip. The TIC flags spurious 2MASS sources, mostly on the diffraction spikes of bright stars, as ARTIFACT, and
second entries for the same star as DUPLICATE; both should be ignored (Paegert et al. 2021). Entries flagged SPLIT
are real stars (the TIC moved them to the brighter Gaia component) and are kept. Three steps used the flagged entries:
the close-neighbour check (`pipeline/neighbors.py`), TRICERATOPS's star list (`pipeline/fpp.py`) and the per-sector
centroid test (`pipeline/centroid_test.py`). All three now leave them out.

The case that showed it: WASP-166's 27.0 d signal (TIC 408310006) was set aside on 8 October for a capable
neighbour 5.6″ away, TIC 408310005. That entry is a TIC artifact, a 2MASS-only source with no Gaia counterpart.
Gaia DR3 has nothing within 7.8″ of WASP-166, and no star within 35″ is bright enough to cause the dip.

## Scope

Of the 3,454 TIC stars within 15″ that could cause the dips of the 1,318 full-sky signals with a close neighbour,
30 are flagged ARTIFACT and 68 DUPLICATE (116 more are SPLIT, real stars). For 11 of those signals every such
neighbour is an artifact or duplicate (7 in tier N, and 4 in tier C for MES < 10); 78 more have one among real
neighbours. Of the 73 earlier-search signals set aside only for a close neighbour, 2 had only artifacts or duplicates
and 3 had one among real neighbours.

## Rerun

TRICERATOPS (10 runs with default priors and 10 with the Gaia limits of
[`gaia_companion_limits.md`](gaia_companion_limits.md)) without the flagged entries, for 75 signals: the 13 tier N
candidates and the 60 likely nearby false positives with such an entry, and the 2 earlier-search signals. The
per-sector centroid test was run for the 60 and for TIC 286944151. The other affected signals (tier C, likely
binaries) keep their tiers whatever TRICERATOPS gives. Per-signal results are in
[`tic_artifacts_rerun.csv`](tic_artifacts_rerun.csv).

## Changes

- **7 tier N candidates become tier B**, since they have no real neighbour within 15″: TIC 44005127, 67466087,
  296941558, 355151843, 362063952, 410011615 and 414747618 (FPP_gc ≤ 0.013, NFPP_gc ≤ 0.003).
- **2 earlier-search signals are now counted:**
  - **WASP-166 (TIC 408310006), 27.017 d, 3.07 ± 0.09 R⊕:** tier A, since the star has a known planet. FPP_gc
    < 0.001 and NFPP_gc 0 (no star within 30″ could cause the dip). It is flagged because its centroids sit 10″
    northeast in all four usable sectors (p = 0.007 for the target), while WASP-166 b's transits, measured the same
    way, fall within 1–4″ of the star. The binary check matches WASP-166 b itself (TESS eclipsing-binary catalog and
    VSX type EP, 5.4435 d), not a binary. SPOC's Sectors 1–96 search listed two of its transits as a 729.46 d TCE,
    27 times this period, which is not a TOI ([`ctoi_matches.md`](ctoi_matches.md)).
  - **TIC 286944151, 2.276 d, 1.21 ± 0.08 R⊕, around an M dwarf 36 pc away:** tier B, FPP_gc 0.010, NFPP_gc 0. Its
    difference-image fits are poor (quality 0.13–0.46), so the centroid test has little power here (p = 0.35), but
    no star within 88″ is bright enough to cause the dip. MES 9.4 is allowed in the earlier M-dwarf samples.
- **TIC 678621 is relabelled "reported":** its 2.58 d signal is K2 candidate EPIC 212572439 (VSX type EP:, same
  period). The binary check had labelled it a likely eclipsing binary.
- **No change for the rest.** 58 of the 60 likely nearby false positives still fail. TIC 1393293 and 338864147 moved
  from FPP 0.500 and 0.508 to 0.469 and 0.486, within the scatter of their individual runs (0.42–0.52) and not
  because of the fix; they stay uncounted and keep their released values. The rerun of TIC 89171942 was stopped
  after 17 of 20 runs (FPP ≈ 0.98); it keeps its released values.

  As of 15 October 2026 TIC 1393293 and 338864147 are tier N. In the TRICERATOPS corrections of 15 October they pass
  the bar (`FPP_gc` 0.479 and 0.497, `NFPP_gc` 0.014 and 0.029), and their transit fits and per-sector centroids
  allow tier N. TIC 338864147's centroids give p = 0.003 for the target, so it carries `centroid_flag`; TIC 1393293
  has a centroid fit in one sector only, so the test could not be applied to it.

The counted candidates are now 470 from the full sky (11 A, 257 B, 152 N, 50 L1) and 60 from the earlier searches
(25 A, 35 B): 530 in all.

## Binary check

`binary_check.py` flags any catalogued variable at the target's position. A known planet's own transits can appear
there, as VSX type EP or in the TESS eclipsing-binary catalog: this happened for WASP-166 and TIC 678621, the only
two cases among the catalog's signals.
