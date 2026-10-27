# Gaia limits on companions

On 11 October 2026 we reran TRICERATOPS with constraints from Gaia DR3 on every counted candidate and on every
signal that had failed only the TRICERATOPS bar (670 signals). Each signal got 10 runs with TRICERATOPS's default
priors and 10 with the Gaia constraints, on the same phase-folded light curve, field and settings as the release
(200,000 draws, a 3×3-pixel aperture, nearby-star scenarios within 30″). The centroid Bayes factor is combined with
both sets as in the release. Per-signal values are in [`gaia_companion_limits.csv`](gaia_companion_limits.csv).

## Constraints

**Bound companions.** MOLUSC (Wood et al. 2021, github.com/woodml/MOLUSC, v.20220321; `pipeline/molusc_batch.py`)
simulates 200,000 companions per host, drawn from the period and mass-ratio distributions of Raghavan et al. (2010).
It rejects those that Gaia would have resolved (its contrast curve for Gaia) and those whose astrometric signal would
raise the host's RUWE above the measured value. TRICERATOPS 1.1.0 then draws the companions in its bound-companion
scenarios (planet or eclipsing binary on the target or on the companion) from the survivors with periastron beyond
10 au, instead of from its default prior. In this mode every simulated host has a companion, which is conservative.
For the median host, 34% of simulated companions are excluded, and 27% of the draws are survivors beyond 10 au.

MOLUSC's own code is unchanged. The wrapper makes these changes:
- It answers MOLUSC's two Gaia queries per star from one bulk query of gaiadr3.gaia_source, made at the ARI Heidelberg
  mirror because the ESA archive stalled.
- It replaces `scipy.interpolate.interp2d`, removed in SciPy 1.14, with an equivalent bilinear interpolator.
- It sets a default that MOLUSC's command line leaves unset.
- For hosts of 1.1–1.4 M☉ it uses the oldest BHAC15 model age that includes them (4, 3 or 2 Gyr). At MOLUSC's default
  of 5 Gyr the models stop at 1.1 M☉, and the Gaia test exits without an error code.

The TIC lists Gaia DR2 identifiers. The 18 that differ in DR3 were mapped with gaiadr3.dr2_neighbourhood. The RUWE
test needs a five-parameter astrometric solution and Gaia colours, so it was applied to 523 of the 542 candidates
counted on 10 October that have MOLUSC results. The Gaia resolution test was applied to all 542.

**Eclipsing binary on the target.** Bright hosts have Gaia DR3 epoch-RV statistics: rv_method_used = 1 and at least 10
transits. For these, the epoch RV scatter σ = ε√(2N/π), where ε is radial_velocity_error, is compared with the
smallest semi-amplitude K_min that a companion in TRICERATOPS's eclipsing-binary prior (q = 0.1) would cause at twice
the period. The 0.11 km/s floor is left in ε, which keeps the test conservative. Where K_min/√2 > 3σ, the EB and
EBx2P scenarios are dropped. This applies to 141 of the 543 candidates counted on 10 October.

**RV variability.** Eleven hosts of candidates counted on 10 October meet Gaia's selection of RV-variable stars
(p ≤ 0.01, renormalised goodness of fit > 4, at least 10 transits; Katz et al. 2023). Two lie far above it:
- TIC 258641782: goodness of fit 32, RV amplitude 57 km/s.
- TIC 94673748: goodness of fit 64, RV amplitude 26 km/s.

A planet would produce well under 1 km/s, so these two are treated as binaries at the target and listed as likely
eclipsing binaries. The other nine are flagged (`rv_flag`). Two neighbour-recovered signals have hosts in the same
strong class and were relabelled from likely nearby false positive to likely eclipsing binary.

## Results

| Signals | With both sets of runs | Median FPP, default | Median FPP, Gaia | Pass the bar with Gaia limits |
|---|---|---|---|---|
| Counted on 10 October | 542 of 543 | 0.045 | 0.016 | 537 |
| Tier C, failed only TRICERATOPS | 58 of 59 | 0.76 | 0.72 | 5 |
| Neighbour-recovered, failed only on FPP, otherwise tier N | 67 of 68 | 0.81 | 0.77 | 7 (2 grazing) |

The bar is FPP < 0.5 and NFPP < 0.1, after the centroid Bayes factor.

For the candidates counted on 10 October, the constrained FPP is a median 0.40 of the default on the same fold
(10–90%: 0.13–0.89). For candidates whose eclipsing-binary scenarios were dropped, the median FPP falls from 0.039 to
0.011. Most of the gain comes from the bound-companion scenarios. In the earlier TRICERATOPS runs, these were the
largest contributor to FPP for 78% of tier M, S and L1 candidates. Gaia excludes bright companions, and the faint
companions that survive cannot produce the transit.

The tier changes of 11 October apply the bar to the constrained values, in both directions:
- Five candidates leave the counted tiers. Three were full-sky candidates near the threshold: TIC 7857354 and
  284852238 on FPP, and TIC 191667098 on NFPP. Two were earlier-search candidates on NFPP: TIC 351339274 and
  394657305. The earlier candidates had never been held to the TRICERATOPS bar, and now get the same centroid
  Bayes factor as the full sky.
- Ten join:
  - Tier S: five former tier C candidates (TIC 32372477, 147696248, 251138100, 305962190, 398516880).
  - Tier N: five neighbour-recovered signals (TIC 95567236, 174947296, 207141752, 219972718, 389581705), each fitted
    on 11 October. Two other recovered signals that pass the bar are grazing (b ≥ 0.9) and go to tier C.
- Two move to likely eclipsing binary: the strong Gaia RV binaries above.

All the signals that cross the bar were within the run-to-run scatter of it before.

Of the 546 candidates counted after these changes, 236 have FPP < 0.015 and NFPP < 0.001 with the Gaia limits
(62 with default priors). These are the validation thresholds of Giacalone et al. (2021), but validation also
requires high-resolution imaging, which most of these stars lack. One counted candidate, TIC 370244729, has no TIC
mass and keeps its default-prior values.

As of 15 October 2026 TIC 370244729 is tier C: with single-cadence input its default-prior `FPP_c` is 0.504, which
fails the bar. No counted candidate now lacks the Gaia-constrained values.
