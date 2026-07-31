from pathlib import Path

import pandas as pd

from pipeline.run_a_root_sensitivity import (
    compare_auditable_units,
    compare_projection_diagnostics,
    load_projection_diagnostics,
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
    assert compare_auditable_units(current_units, baseline_units) == {
        "shared_auditable_unit_count": 1,
        "newly_included_units": 1,
        "excluded_units": 1,
    }
