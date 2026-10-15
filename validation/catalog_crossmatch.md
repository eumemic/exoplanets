# Cross-match with catalogs of TESS full-frame-image candidates and eclipsing binaries (15 October 2026)

The literature check searches NASA ADS full text, arXiv and Zenodo for each candidate's TIC ID or TOI number, but
catalogs that publish their lists only as machine-readable tables are not always found that way. We therefore matched
the catalog directly against these tables from VizieR, by TIC ID and period (a ratio of 1/3 to 3 within 0.3%):

| Catalog | VizieR | Rows | Matches among the catalog's signals |
|---|---|---|---|
| DIAmante candidates, southern ecliptic (Montalto et al. 2020) | J/MNRAS/498/1726 | 396 | TIC 214301302: a single 9,100 ppm transit at 22.9 d, 14 h from the nearest transit of our 3.93 d, 1,200 ppm candidate; a different signal |
| DTARPS-S candidates (Melton et al. 2024) | J/AJ/167/203 | 462 + 310 | WASP-166 b (TOI-576.01), not our 27.0 d candidate on the star; TIC 178265008 1.41 d (already a likely EB here); TIC 369676035 (already reported, at half our period) |
| Olmschenk et al. (2021) neural-network candidates | J/AJ/161/273 | 185 | none |
| TESS Ten Thousand eclipsing binaries (Kostov et al. 2025) | J/ApJS/279/50 (tables 3, 4) | 10,001 | six signals on four stars, below |

Eclipsing binaries of the TESS Ten Thousand catalog on our targets:

| TIC | Our period (d) | Binary's period (d) | Was | Now |
|---|---|---|---|---|
| 61754177 | 1.878166 | 3.756346 (twice ours) | B | likely EB |
| 269693249 | 2.316528 | 2.316532 | B | likely EB |
| 390928439 | 8.144337 | 8.144416 | B | likely EB |
| 7857354 | 8.674434 | 17.348757 (twice ours) | C | likely EB |
| 396739318 | 1.246673 | 1.246622 | likely EB | likely EB |
| 178148775 | 1.868342 | 3.736736 (twice ours) | likely EB | likely EB |

As for the other binary catalogs, a binary at the target makes the signal a likely EB; `binary_at_target` now records
`t10k P=<period>`. No counted candidate has a TESS Ten Thousand binary within 60″ at a matching period. The counted total
goes from 661 to 658 (600 full-sky, 58 from the earlier searches). The DIAmante northern search of 1.4 million light
curves (Montalto 2023) has no machine-readable candidate table on VizieR and is not included.
