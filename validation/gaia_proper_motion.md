# Gaia matches for high-proper-motion stars

`pipeline/binary_check.py` matched the TIC position (epoch J2000) against Gaia DR3 (epoch 2016.0) with CDS XMatch
and a 3″ at-target radius (`AT_TARGET`), without correcting for proper motion. A star moving faster than about
190 mas/yr drifts more than 3″ in the 16 years between the two epochs, so it received no Gaia match. Its `ruwe`
came back NaN, the rule RUWE > 1.4 → tier C could not fire, and the at-target Gaia SB1, SB2, eclipsing-orbit and
orbit checks and the at-target `gaia_eb` check were blind for it as well.

## Evidence

For every candidate with a NaN `ruwe` that we checked, the offset between the TIC position and the Gaia DR3
position equals the TIC proper motion × 16 yr to within 0.001″ (3.0–13.8″). The four stars below have a
Gaia DR3 RUWE above 1.4 that the old check could not see. Run on the old and the fixed code, the old check gives
NaN for all four and the fixed check gives these values:

| TIC | Period (d) | Tier in the catalog | Gaia DR3 RUWE | Note |
|---|---:|---|---:|---|
| 156909067 | 6.667 | L1 | 3.62 | Gaia DR3 5577716114256475776, 4.06″ from the J2000 TIC position, 0.001″ from the propagated one |
| 165827520 | 2.004 | M (earlier search) | 3.72 | the README already notes a 0.59″ companion from imaging |
| 32636748 | 0.732 | S (earlier search) | 1.73 | |
| 26432942 | not listed | C (already) | 1.65 | no change in tier |

## Fix

`binary_check.py` now reads `pmRA` and `pmDEC` from the TIC and moves the position to 2016.0 (`propagate`, linear,
with `pmRA` already including cos(dec) so the RA change is divided by cos(dec); a NaN proper motion leaves the
position unchanged) before the Gaia matches. This applies to every Gaia DR3 table queried: `gaia`, `gaia_eb`,
`gaia_sb1`, `gaia_sb2`, `gaia_eb_orbit` and `gaia_orbit`, whose positions are at epoch 2016.0. The TESS
eclipsing-binary catalog, VSX and the APOGEE binary table are still matched at the TIC position: their epochs
are not one known value (they mix sources), so no correction is applied to them. A candidate CSV that already has
`ra` and `dec` columns now also needs `pmRA` and `pmDEC`; if either is missing, all four are looked up in the TIC.

`tests/test_gaia_epoch.py` checks the propagation on a synthetic star (1000 mas/yr at dec 60° over 16 yr moves
16″ on the sky and 32″ in raw RA), the NaN case, that TIC 156909067's propagated position lies within 3″ of its
Gaia DR3 position (0.001″ here, 4.06″ before), and that the Gaia tables receive the 2016.0 position and the other
tables the TIC position. The tests need no network access.

## Consequence for the catalog

Catalogs, tables and tiers are unchanged by this fix; the table of RUWE values above is what the fixed check
returns. The existing rule (RUWE > 1.4 → tier C) applied to these values would move three counted candidates to
tier C: TIC 156909067 (L1), TIC 165827520 (earlier-search A) and TIC 32636748 (earlier-search B). TIC 26432942
is already tier C. Whether to apply the rule, and the counts that follow, is for the authors to decide. The
check has not been rerun on the full candidate list, so other counted candidates with a NaN `ruwe` may also
be affected.

As of 15 October 2026 the rule has been applied (in the QLP re-search release of 13 October):
TIC 156909067, TIC 165827520 and TIC 32636748 are tier C with `c_reason` RUWE > 1.4, and TIC 26432942 is still tier C.
