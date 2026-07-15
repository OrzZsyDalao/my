"""Regression tests for strict probe-and-time matched service comparisons."""

import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from pipeline.matched_comparison import build_shared_service_time_snapshots, nearest_time_probe_matches


def test_nearest_time_matching_respects_probe_and_tolerance():
    """Only same-probe observations inside the configured time window may match."""
    left = pd.DataFrame(
        {
            "probe_id": ["p1", "p1", "p2"],
            "timestamp_dt": pd.to_datetime(["2026-07-01T00:00:00Z", "2026-07-01T00:20:00Z", "2026-07-01T00:00:00Z"]),
            "trace_id": ["left-near", "left-far", "left-other-probe"],
            "has_candidate": [True, False, True],
        }
    )
    right = pd.DataFrame(
        {
            "probe_id": ["p1", "p2"],
            "timestamp_dt": pd.to_datetime(["2026-07-01T00:05:00Z", "2026-07-01T01:00:00Z"]),
            "trace_id": ["right-near", "right-other-probe"],
            "has_candidate": [False, False],
        }
    )

    matched = nearest_time_probe_matches(left, right, tolerance_seconds=600)

    assert matched["trace_id"].tolist() == ["left-near"]
    assert matched["matched_trace_id"].tolist() == ["right-near"]
    assert matched["matched_time_delta_seconds"].tolist() == [300.0]


def test_nearest_time_matching_does_not_reuse_right_trace():
    """One right-side trace can participate in at most one matched pair."""
    left = pd.DataFrame(
        {
            "probe_id": ["p1", "p1"],
            "timestamp_dt": pd.to_datetime(["2026-07-01T00:00:00Z", "2026-07-01T00:02:00Z"]),
            "trace_id": ["left-1", "left-2"],
            "has_candidate": [True, False],
        }
    )
    right = pd.DataFrame(
        {
            "probe_id": ["p1"],
            "timestamp_dt": pd.to_datetime(["2026-07-01T00:01:00Z"]),
            "trace_id": ["right-1"],
            "has_candidate": [True],
        }
    )

    matched = nearest_time_probe_matches(left, right, tolerance_seconds=900)

    assert len(matched) == 1
    assert matched["matched_trace_id"].nunique() == 1


def test_shared_snapshot_requires_every_service_within_tolerance():
    """The multi-service cohort should retain only anchor observations matched in every service."""
    frame = pd.DataFrame(
        {
            "service_id": ["a", "b", "c"],
            "probe_id": ["p1", "p1", "p1"],
            "timestamp": ["2026-07-01T00:00:00Z", "2026-07-01T00:04:00Z", "2026-07-01T00:08:00Z"],
            "timestamp_dt": pd.to_datetime(["2026-07-01T00:00:00Z", "2026-07-01T00:04:00Z", "2026-07-01T00:08:00Z"]),
            "trace_id": ["a1", "b1", "c1"],
            "has_candidate": [True, False, True],
        }
    )

    snapshots = build_shared_service_time_snapshots(frame, ["a", "b", "c"], tolerance_seconds=600)

    assert snapshots["snapshot_id"].nunique() == 1
    assert set(snapshots["service_id"]) == {"a", "b", "c"}
    assert snapshots["probe_id"].nunique() == 1
