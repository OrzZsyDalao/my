"""Focused tests for denominator, topology, and isolated-run guardrails."""

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))


def test_trace_identifier_ignores_transport_filename():
    """The same Atlas observation must not gain a new denominator in another file."""
    pytest.importorskip("maxminddb")
    import main_analysis

    left = main_analysis.build_trace_id("snapshot-a.json", 5009, 123, 1000, "192.0.2.1")
    right = main_analysis.build_trace_id("snapshot-b.json", 5009, 123, 1000, "192.0.2.1")
    assert left == right == "5009:123:1000:192.0.2.1"


def test_unordered_landing_set_does_not_create_direct_topology(tmp_path):
    """Plain landing membership is not silently interpreted as a complete graph."""
    pytest.importorskip("maxminddb")
    import main_analysis

    (tmp_path / "sample.json").write_text(
        json.dumps({"id": "c1", "name": "Cable 1", "landing_points": [{"id": "a"}, {"id": "b"}]}),
        encoding="utf-8",
    )
    cable = main_analysis.load_all_cables(str(tmp_path))[0]
    assert cable["topology_status"] == "unordered_landing_set"
    assert cable["topology_edges"] == []


def test_explicit_ordered_landing_path_creates_adjacent_edges(tmp_path):
    """Only neighboring entries in explicit ordered metadata become physical segments."""
    pytest.importorskip("maxminddb")
    import main_analysis

    (tmp_path / "sample.json").write_text(
        json.dumps({
            "id": "c1", "name": "Cable 1", "landing_points": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            "ordered_landing_points": ["a", "b", "c"],
        }),
        encoding="utf-8",
    )
    cable = main_analysis.load_all_cables(str(tmp_path))[0]
    assert cable["topology_edges"] == [
        ("a", "b", "adjacent_physical_segment"),
        ("b", "c", "adjacent_physical_segment"),
    ]


def test_segment_accounting_rejects_subset_overflow():
    """A candidate-loop count cannot be emitted as an atomic-segment count."""
    pytest.importorskip("maxminddb")
    import main_analysis

    matcher = object.__new__(main_analysis.CableMatcher)
    matcher.candidate_count_per_matched_link = []
    matcher.stats = {
        "atomic_segments_total": 1,
        "atomic_segments_with_valid_rtt_evidence": 2,
        "atomic_segments_with_inconclusive_rtt": 0,
        "atomic_segments_with_network_transition": 0,
        "atomic_segments_with_landing_candidates": 0,
        "atomic_segments_with_feasible_corridor_candidates": 0,
        "atomic_segments_without_feasible_corridor_candidates": 0,
        "candidate_segments_considered": 0,
        "confirmed_active_candidates": 0,
        "candidates_with_unknown_cable_status": 0,
    }
    with pytest.raises(RuntimeError, match="Invalid segment accounting"):
        matcher.finalize_stats()
