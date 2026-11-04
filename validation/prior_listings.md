# Candidates listed by another search before we posted them (3 November 2026)

Before archiving the catalog for the AJ paper we listed the 505 Zenodo records created between 1 October and
3 November 2026 that mention TESS, TIC IDs, exoplanets or transiting planets. A listing can predate ours only in the 145
records created before 14 October 00:48 UTC, when we first committed the last of the counted candidates. We searched
every file of those records up to 50 MB, and five larger archives about TESS, for the TIC IDs of the counted candidates
(255 files, 1.4 GB), reading archives without unpacking them and converting PDFs to text. The other 86 files, 26 GB of
NetCDF, HDF5 per-star outputs and split archives from other fields, are not named for any of our stars. For each match
we compared the periods in the surrounding text with ours (within 0.3%) and the record's creation time with the first
commit of this repository that lists the candidate. We also searched 637 files of 119 of the 360 later records, for
[`later_reports.md`](later_reports.md). Two records list counted candidates of ours at our periods before we posted
them.

## Murray (2026)

B. Murray's record [10.5281/zenodo.23230562](https://doi.org/10.5281/zenodo.23230562), created on 8 October 2026 at
06:06 UTC, pre-registers a test of a candidate on L 198-93 (TIC 264151965). The code that builds its report
(`L198-93_prereg/pipeline/make_report.py` in `L198-93_prereg_files.zip`, file dated 7 October 22:51, without a time
zone) holds candidate tables: thirteen candidates besides L 198-93 with periods, depths and notes, and sixteen named
without periods. Five with periods are counted candidates of ours that we posted later:

| TIC | Our period (d) | Murray's period (d) | Our tier before | Our first commit listing it (UTC) |
|---|---|---|---|---|
| 402710280 | 3.783712 | 3.783705 | N | 9 October 14:56 |
| 333735955 | 11.226152 | 11.226155 | S | 9 October 03:34 |
| 402047931 | 27.497623 | 27.497640 | S | 14 October 00:48 |
| 231694211 | 8.55228 | 8.552293 | S | 14 October 00:48 |
| 11650366 | 7.092644 | 7.09264 | S | 14 October 00:48 |

They are now in tier `reported`, with the record in `reported_as` (`results_public/overrides.csv`). Three more of our
signals in the tables we posted first: TIC 135425484 (8.0335 d) and TIC 32636748 (0.7323 d), both tier C, on 7 and
8 October (03:14 UTC), and TIC 458191673 (2.5707 d, tier S, named without a period) on 7 October. TIC 207090140, our
tier L1 signal at 10.453 d (first commit 9 October 14:56 UTC), is named without a period, so we cannot tell whether it
is the same signal; it stays counted. TIC 264151965, the record's subject, was in our first release on 7 October and
is not one of our counted candidates. The record's description and PDF mention only L 198-93, so our earlier searches
of Zenodo, which read descriptions, missed the tables. We found them through the prior-detection notes of another
search ([fergmolina/tess-transit-candidates](https://github.com/fergmolina/tess-transit-candidates)).

## Chopra (2026)

P. Chopra's record [10.5281/zenodo.23257784](https://doi.org/10.5281/zenodo.23257784), created on 9 October 2026 at
08:02 UTC, gives predicted transit times for two candidates and includes a draft CTOI (`CTOI_DRAFT.md`) for
TIC 252721481.01 (HIP 114417) at P = 4.933533 ± 0.000019 d. Our tier L1 signal on the star, at 4.933538 d, was first
committed at 14:56 UTC the same day. It is now in tier `reported`.

Records that posted our counted candidates after we did are in [`later_reports.md`](later_reports.md).
