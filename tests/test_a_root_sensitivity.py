from pathlib import Path

import pandas as pd
import pytest

from pipeline.run_a_root_sensitivity import (
    BASELINE,
    compare_shared_cohort,
    compare_auditable_units,
    compare_projection_diagnostics,
    load_setting_summary,
    load_projection_diagnostics,
    stable_exact_candidate_id,
    validate_sensitivity_summary,
)


def test_projection_diagnostics_distinguish_global_and_observed_structure(
    tmp_path: Path,
) -> None:
    """Sensitivity diagnostics must expose changes hidden by summary medians."""
    pd.DataFrame(
        {"landing_region_id": ["r1", "r2", "r3", "r3"]}
    ).to_csv(tmp_path / "landing_region_catalog.csv", index=False)
    pd.DataFrame({"corridor_id": ["c1", "c2"]}).to_csv(
        tmp_path / "corridor_catalog.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "atomic_segment_id": "s1",
                "link_id": "legacy1",
                "corridor_id": "c1",
                "landing_region_entry_id": "r1",
                "landing_region_exit_id": "r2",
                "candidate_scope": "international_inter_region",
                "is_inter_region_candidate": True,
            },
            {
                "atomic_segment_id": "s1",
                "link_id": "legacy1",
                "corridor_id": "c2",
                "landing_region_entry_id": "r1",
                "landing_region_exit_id": "r3",
                "candidate_scope": "international_inter_region",
                "is_inter_region_candidate": True,
            },
            {
                "atomic_segment_id": "s2",
                "link_id": "legacy2",
                "corridor_id": "intra",
                "landing_region_entry_id": "r1",
                "landing_region_exit_id": "r1",
                "candidate_scope": "intra_landing_region",
                "is_inter_region_candidate": False,
            },
        ]
    ).to_csv(tmp_path / "trace_feasible_candidate_space.csv", index=False)

    diagnostics = load_projection_diagnostics(tmp_path)

    assert diagnostics["global_landing_region_count"] == 3
    assert diagnostics["observed_landing_region_count"] == 3
    assert diagnostics["global_corridor_count"] == 2
    assert diagnostics["observed_corridor_count"] == 2
    assert diagnostics["segment_corridor_sets"] == {
        "s1": frozenset({"c1", "c2"})
    }


def test_projection_and_auditable_unit_comparisons() -> None:
    """Baseline comparisons must report changed candidate sets and cohort churn."""
    baseline = {
        "segment_corridor_incidence": {
            ("s1", "c1"),
            ("s1", "c2"),
            ("s3", "c3"),
        },
        "segment_corridor_sets": {
            "s1": frozenset({"c1", "c2"}),
            "s3": frozenset({"c3"}),
        },
    }
    current = {
        "segment_corridor_incidence": {("s1", "c1"), ("s2", "c4")},
        "segment_corridor_sets": {
            "s1": frozenset({"c1"}),
            "s2": frozenset({"c4"}),
        },
    }
    projection = compare_projection_diagnostics(current, baseline)
    assert projection["segment_corridor_set_jaccard_with_baseline"] == 0.25
    assert projection["segments_with_changed_corridor_set"] == 3

    baseline_units = pd.DataFrame(
        [
            ("US", "A-Root", "all_publicly_visible"),
            ("DE", "A-Root", "all_publicly_visible"),
        ],
        columns=["probe_country", "service_id", "path_scope_stratum"],
    )
    current_units = pd.DataFrame(
        [
            ("US", "A-Root", "all_publicly_visible"),
            ("JP", "A-Root", "all_publicly_visible"),
        ],
        columns=["probe_country", "service_id", "path_scope_stratum"],
    )
    comparison = compare_auditable_units(current_units, baseline_units)
    assert comparison["baseline_auditable_unit_count"] == 2
    assert comparison["current_auditable_unit_count"] == 2
    assert comparison["shared_auditable_unit_count"] == 1
    assert comparison["newly_included_unit_count"] == 1
    assert comparison["excluded_baseline_unit_count"] == 1


def test_stable_exact_candidate_id_is_order_invariant_and_region_free() -> None:
    """Stable physical candidates must not inherit resolution-dependent IDs."""
    left = stable_exact_candidate_id("cable-x", "station-b", "station-a")
    right = stable_exact_candidate_id("cable-x", "station-a", "station-b")
    assert left == right
    assert "landing_region" not in left


def test_stable_candidate_agreement_can_coexist_with_corridor_change() -> None:
    """Regrouping stations may alter corridors without altering exact candidates."""
    shared = {
        "segment_exact_candidate_sets": {
            "s1": frozenset({"stable_exact_candidate_v1|x|a|b"})
        },
        "segment_cable_sets": {"s1": frozenset({"x"})},
        "observed_station_ids": {"a", "b"},
    }
    baseline = {
        **shared,
        "segment_corridor_incidence": {("s1", "r1::r2")},
        "segment_corridor_sets": {"s1": frozenset({"r1::r2"})},
        "station_to_region": {"a": "r1", "b": "r2"},
    }
    current = {
        **shared,
        "segment_corridor_incidence": {("s1", "r3::r3")},
        "segment_corridor_sets": {"s1": frozenset({"r3::r3"})},
        "station_to_region": {"a": "r3", "b": "r3"},
    }
    comparison = compare_projection_diagnostics(
        current,
        baseline,
        same_diameter=False,
    )
    assert comparison["exact_candidate_set_jaccard_mean"] == 1.0
    assert comparison["cable_set_jaccard_mean"] == 1.0
    assert comparison["segment_corridor_set_jaccard_with_baseline"] == 0.0
    assert comparison["landing_partition_comembership_jaccard"] == 0.0
    assert (
        comparison["corridor_id_comparison_semantics"]
        == "resolution_dependent_corridor_id_comparison"
    )


def test_resolution_shares_and_shared_classification_denominator(
    tmp_path: Path,
) -> None:
    """Candidate shares sum to one and unknown labels stay out of agreement."""
    pd.DataFrame(
        [
            ("uniquely_resolved", 8),
            ("bounded_candidate_set", 2),
            ("no_matched_corridor", 20),
            ("insufficiently_resolved", 10),
        ],
        columns=["mapping_resolution_state", "atomic_segment_count"],
    ).to_csv(tmp_path / "physical_mapping_resolution_summary.csv", index=False)
    entropy = pd.DataFrame(
        [
            {
                "probe_country": "US",
                "service_id": "A-Root",
                "path_scope_stratum": "all_publicly_visible",
                "analysis_scope": "probe_country_service",
                "auditable_paper_case": True,
                "top2_network_transition_share": 0.5,
                "top2_corridor_share": 0.8,
                "network_transition_normalized_entropy": 0.7,
                "corridor_normalized_entropy": 0.4,
                "normalized_entropy_reduction": 0.3,
                "cross_layer_distribution_class": "broad",
            },
            {
                "probe_country": "DE",
                "service_id": "A-Root",
                "path_scope_stratum": "all_publicly_visible",
                "analysis_scope": "probe_country_service",
                "auditable_paper_case": True,
                "top2_network_transition_share": 0.6,
                "top2_corridor_share": 0.9,
                "network_transition_normalized_entropy": 0.6,
                "corridor_normalized_entropy": 0.3,
                "normalized_entropy_reduction": 0.3,
                "cross_layer_distribution_class": "unknown_cross_layer",
            },
        ]
    )
    entropy.to_csv(
        tmp_path / "cross_layer_normalized_entropy_audit.csv",
        index=False,
    )
    row, baseline = load_setting_summary(tmp_path, 50, 50, 5)
    assert row["all_atomic_segment_count"] == 40
    assert row["candidate_bearing_segment_count"] == 10
    assert row["single_corridor_share_among_candidate_bearing_segments"] == 0.8
    assert row["bounded_multi_corridor_share_among_candidate_bearing_segments"] == 0.2

    current = baseline.copy()
    current.loc[
        current["probe_country"].eq("US"),
        "cross_layer_distribution_class",
    ] = "broad"
    metrics, _ = compare_shared_cohort(current, baseline, "test")
    assert metrics["classification_agreement_denominator"] == 1
    assert metrics["classification_agreement_numerator"] == 1


def test_current_sensitivity_grid_has_one_baseline_and_valid_ranges() -> None:
    """The regenerated local grid retains all 27 unique configurations."""
    root = Path(__file__).resolve().parents[1]
    path = root / "output" / "sensitivity_a_root" / "a_root_sensitivity_summary.csv"
    if not path.exists():
        return
    frame = pd.read_csv(path)
    validate_sensitivity_summary(frame)
    baseline = frame.loc[
        frame["landing_catchment_radius_km"].eq(BASELINE[0])
        & frame["landing_region_maximum_diameter_km"].eq(BASELINE[1])
        & frame["rtt_tolerance_ms"].eq(BASELINE[2])
    ].iloc[0]
    assert baseline["candidate_bearing_segment_count"] == 2016
    assert baseline["single_corridor_segment_count"] == 1912
    assert baseline[
        "single_corridor_share_among_candidate_bearing_segments"
    ] == pytest.approx(1912 / 2016)
    assert baseline["current_auditable_unit_count"] == 13
