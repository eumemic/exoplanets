"""Internal-consistency checks on the published candidate tables (pandas only, no network).

No counts are hardcoded: every check is relative to the tables themselves, so
the tests keep passing as releases add or re-tier candidates.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results_public"
CANDS = ROOT / "candidates"

COUNTED_ALLSKY = ["A", "B", "N", "L1"]
COUNTED_EARLIER = ["A", "B"]
KNOWN_TIERS = {
    "A", "B", "C", "N", "L", "L1",
    "likely EB", "likely false alarm", "likely nearby FP", "reported",
}
REQUIRED_FILES = ["vetting.png", "vetting.json", "transit_fit.json"]
# Folder names are TIC<id>_P<period to 3 decimals>; the period in the name can come
# from a slightly different fit than the table value, so allow a small offset.
FOLDER_PERIOD_TOL = 0.002


@pytest.fixture(scope="module")
def allsky():
    return pd.read_csv(RESULTS / "candidates_allsky.csv")


@pytest.fixture(scope="module")
def earlier():
    return pd.read_csv(RESULTS / "tiers_earlier_candidates.csv")


@pytest.fixture(scope="module")
def candidate_dirs():
    """Map TIC -> [(period, folder)] over candidates/ and candidates/allsky/."""
    out = {}
    for base in (CANDS, CANDS / "allsky"):
        for d in base.glob("TIC*_P*"):
            tic, _, per = d.name[3:].partition("_P")
            out.setdefault(int(tic), []).append((float(per), d))
    return out


def _missing_files(df, tiers, candidate_dirs):
    problems = []
    for tic, period in df.loc[df["tier"].isin(tiers), ["TIC", "P_d"]].itertuples(index=False):
        folders = [d for p, d in candidate_dirs.get(int(tic), []) if abs(p - period) <= FOLDER_PERIOD_TOL]
        if not any(all((d / f).is_file() for f in REQUIRED_FILES) for d in folders):
            problems.append((int(tic), float(period)))
    return problems


def test_allsky_counted_candidates_have_vetting_files(allsky, candidate_dirs):
    assert _missing_files(allsky, COUNTED_ALLSKY, candidate_dirs) == []


def test_earlier_counted_candidates_have_vetting_files(earlier, candidate_dirs):
    assert _missing_files(earlier, COUNTED_EARLIER, candidate_dirs) == []


@pytest.mark.parametrize("name", ["allsky", "earlier"])
def test_tier_labels_are_known(name, request):
    tiers = request.getfixturevalue(name)["tier"]
    assert tiers.notna().all()
    assert set(tiers) <= KNOWN_TIERS


@pytest.mark.parametrize("name", ["allsky", "earlier"])
def test_no_duplicate_tic_period_rows(name, request):
    df = request.getfixturevalue(name)
    assert not df.duplicated(["TIC", "P_d"]).any()


@pytest.fixture(scope="module")
def predictions_with_ephemerides():
    """Each prediction row joined to its ephemeris (same TIC, same period).

    predictions.csv rounds the period to 6 decimals and ephemerides.csv to 7,
    so the period is matched with a tolerance rather than exactly.
    """
    pred = pd.read_csv(CANDS / "predictions.csv").reset_index(names="row")
    eph = pd.read_csv(CANDS / "ephemerides.csv")
    m = pred.merge(eph, on="TIC", suffixes=("", "_eph"))
    m = m[(m["period_d"] - m["period_d_eph"]).abs() < 1e-5]
    assert m["row"].is_unique
    assert len(m) == len(pred), "every prediction needs exactly one ephemeris"
    return m


def test_predicted_midtimes_follow_ephemeris(predictions_with_ephemerides):
    m = predictions_with_ephemerides
    expected = m["T0_BJD_TDB"] + m["epoch"] * m["period_d_eph"]
    err_min = (m["tc_BJD_TDB"] - expected).abs() * 1440
    assert err_min.max() < 0.5


def test_predicted_sigma_follows_error_propagation(predictions_with_ephemerides):
    m = predictions_with_ephemerides
    expected = np.sqrt(m["T0_err_min"] ** 2 + (m["epoch"] * m["period_err_d"] * 1440) ** 2)
    ratio = m["sigma_min"] / expected
    # Observed spread is a few percent (rounding of the stored values); require
    # that nearly all rows agree within 10% and none is grossly off.
    assert (ratio - 1).abs().lt(0.10).mean() >= 0.95
    assert ratio.between(0.5, 2.0).all()
