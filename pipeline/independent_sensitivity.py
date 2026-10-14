"""Two bounded audit sensitivities: QLP flux columns and omission of QLP S99+.

Column comparison is intended for the archived all-missing-error QLP S94 case.
Omitting complete QLP S99+ sectors is conservative relative to the MAST timing
warning (which begins in the second orbit of S99); it does not correct timestamps.
"""
import argparse
import hashlib
from pathlib import Path

import pandas as pd

try:
    from .independent_vet import read_curve, event_measurements, combine
except ImportError:
    from independent_vet import read_curve, event_measurements, combine


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("signals")
    ap.add_argument("--downloads", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--tic", type=int, required=True)
    ap.add_argument("--sector", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    signals = pd.read_csv(args.signals)
    downloads = pd.read_csv(args.downloads)
    selected = downloads[(downloads.tic == args.tic) & (downloads.sector == args.sector)]
    if len(selected) != 1 or selected.iloc[0].provenance != "QLP" or selected.iloc[0].status != "ok":
        raise ValueError("Expected exactly one successful QLP product")
    product = selected.iloc[0]
    if hashlib.sha256(Path(product.path).read_bytes()).hexdigest() != product.sha256:
        raise ValueError("Product SHA256 mismatch")
    selected = signals[signals.tic == args.tic]
    if len(selected) != 1:
        raise ValueError("Expected one ephemeris for the selected TIC")
    signal = next(selected.itertuples())
    rows = []
    for column in ("SYS_RM_FLUX", "SAP_FLUX", "DET_FLUX"):
        t, f, e, info = read_curve(product.path, "QLP", return_info=True, qlp_flux_column=column)
        if info["error_source"] != "empirical_adjacent_mad":
            raise ValueError("Column sensitivity expects empirical errors for each selected flux column")
        for width in (2.5, 4.0):
            events, _ = event_measurements([(args.sector, "QLP", t, f, e)], signal, width)
            events["flux_column"] = column
            rows.append(events)
    args.out.mkdir(parents=True, exist_ok=True)
    pd.concat(rows, ignore_index=True).to_csv(args.out / "qlp_flux_columns.csv", index=False)
    events = pd.read_csv(args.events)
    rows = []
    for (tic, width), group in events.groupby(["tic", "window_factor"]):
        omitted = group.provenance.eq("QLP") & group.sector.ge(99)
        stats = combine(group[~omitted])
        rows.append(dict(tic=tic, window_factor=width,
                         n_events_omitted=int(omitted.sum()), **stats))
    pd.DataFrame(rows).to_csv(args.out / "without_qlp99plus.csv", index=False)


if __name__ == "__main__":
    main()
