"""Regression tests for strict probe-and-time matched service comparisons."""

import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from pipeline.matched_comparison import nearest_time_probe_matches


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
