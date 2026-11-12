# Proposed refined ephemerides (Foundation-0)

[`proposed_refined_ephemerides.csv`](proposed_refined_ephemerides.csv) holds refined linear ephemerides for ten
candidates, proposed by Foundation-0/exoplanets-frontier for review alongside
[issue #20](https://github.com/eumemic/exoplanets/issues/20). It is a proposal: the catalog tiers in
`results_public/` and `candidates/` stay as published, and any change to them is the maintainers' call.

The table is F0's `results/ttv_ephemeris_audit.csv`, all 10 rows and 18 columns copied unchanged, from commit
[`412043e0`](https://github.com/Foundation-0/exoplanets-frontier/commit/412043e048048f8c0123de25c548cb0be70ad960)
(file blob `110a31b5`, unchanged at main
[`ad02fe10`](https://github.com/Foundation-0/exoplanets-frontier/commit/ad02fe103ab2d0ead89cae9975aa8fd947a6302d),
where `CLAIMS.md` C-04 documents it). Four columns record that provenance on every row: `source_repo`, `source_sha`,
`source_file` and `method`.

## Method

F0's `ttv_track.py` (blob `55e8c4fc`) measures each transit midpoint in a +-240 min window around the
predicted time across TESS sectors 1-107, where its Phase 1 window was +-60 min and clipped drifted transits. It then
fits the O-C times with four ephemeris models (fixed, linear, quadratic, and linear plus a sinusoidal TTV) and
compares them by dBIC. `P_ref_d` and `T0_ref_BJD` come from the linear fit; `snr_stale` and `snr_refined` are the
stacked transit SNR at the original and refined ephemerides; `class` is F0's label from the dBIC comparison.

## F0 claims

These are Foundation-0's results as stated in `CLAIMS.md` at `ad02fe10`; they were not rerun against MAST for this
change.

- C-04, rescued ephemerides: TIC 166848769 (tier C) at P_ref = 7.6574415 d, dP = +44.11 s per orbit, stacked SNR
  6.29 to 13.49. TIC 332644900 (tier C) at P_ref = 1.3290094 d, SNR 2.67 to 5.39, with residual timing scatter that
  F0 classes as a TTV candidate (dBIC_ttv = +18.7). TIC 321011164, SNR 7.07 to 10.24, and TIC 7780510, SNR 0.84 to
  9.13, both from two sectors, so a cycle-count alias remains possible. TIC 70557792 is mostly linear: dP = -1.45 s
  per orbit, with a sinusoidal TTV adding only dBIC_ttv = +4.4, so the two-sector TTV flag in #20 reads as a period
  refinement.
- C-03, the pre-whitener in `pipeline/harmonic_despot.py`: on TOI-540 (TIC 200322593, P_rot = 0.726 d), a
  running-median BLS locked onto the spot wave, and after `harmonic_despot` the search recovered TOI-540 b at
  P = 1.239126 d (1.9 s from the published 1.239149 d) with MES = 14.33. Ten scrambled-null trials gave 0/10 false
  alarms above MES 9.5.

F0 states the falsifier for C-04 as Sector 108+ or intermediate-cycle FFI transits missing the linear ephemeris by
more than 3 sigma, which is the check this table invites.

## Reproduction

Compare the table with F0's file:

```
curl -sL https://raw.githubusercontent.com/Foundation-0/exoplanets-frontier/ad02fe103ab2d0ead89cae9975aa8fd947a6302d/results/ttv_ephemeris_audit.csv -o /tmp/f0_audit.csv
python -c "import pandas as pd; a = pd.read_csv('/tmp/f0_audit.csv'); b = pd.read_csv('validation/proposed_refined_ephemerides.csv'); print(a.equals(b[a.columns]))"
```

Browse it at
https://github.com/Foundation-0/exoplanets-frontier/blob/ad02fe103ab2d0ead89cae9975aa8fd947a6302d/results/ttv_ephemeris_audit.csv.
`tests/test_proposed_refined_ephemerides.py` pins the highlighted rows and the provenance columns.

To try the pre-whitener on cool dwarfs in a search, run `pipeline/search.py` with `--harmonic-despot`. It applies to
stars with Teff < 4000 K and leaves the default search unchanged without the flag.
