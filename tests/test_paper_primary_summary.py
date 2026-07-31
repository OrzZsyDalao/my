from pathlib import Path

import pandas as pd
import pytest

from source.build_paper_primary_summary import (
    build_paper_primary_units,
    fixed_paper_filter,
)


def _entropy_row(
    *,
    msm_id: int = 5009,
    country: str = "US",
    path_scope: str = "all_publicly_visible",
    analysis_scope: str = "probe_country_service",
    auditable: bool = True,
) -> dict:
    return {
        "measurement_label": "msm5009_dns-root-a-root",
        "msm_id": msm_id,
        "probe_country": country,
        "service_id": "A-Root",
        "path_scope_stratum": path_scope,
        "analysis_scope": analysis_scope,
        "auditable_paper_case": auditable,
        "auditable_cross_layer_case": auditable,
        "total_mappable_segments": 40,
        "top2_network_transition_share": 0.5,
        "top2_corridor_share": 0.8,
        "network_transition_normalized_entropy": 0.7,
        "corridor_normalized_entropy": 0.4,
        "effective_network_transition_count": 5.0,
        "effective_corridor_count": 2.0,
        "cross_layer_distribution_class": "network_broad_physical_concentrated",
        "country_fallback_share": 0.1,
        "unique_probes": 12,
        "unique_probe_asns": 4,
        "observation_sufficiency_reason": "auditable",
        "failed_thresholds": "",
    }


def test_fixed_filter_excludes_non_primary_scope_and_non_auditable() -> None:
    """The paper generator must not rely on manual filtering."""
    frame = pd.DataFrame(
        [
            _entropy_row(country="US"),
            _entropy_row(country="DE", path_scope="resolved_entry_only"),
            _entropy_row(country="FR", analysis_scope="transition_country_service"),
            _entropy_row(country="JP", auditable=False),
        ]
    )
    filtered = fixed_paper_filter(frame)
    assert filtered["probe_country"].tolist() == ["US"]


def test_build_units_joins_resolution_and_uses_explicit_family() -> None:
    """Paper units preserve valid/candidate-bearing accounting."""
    entropy = pd.DataFrame([_entropy_row()])
    resolution = pd.DataFrame(
        [
            {
                "msm_id": 5009,
                "probe_country": "US",
                "service_id": "A-Root",
                "path_scope_stratum": "all_publicly_visible",
                "total_atomic_segments": 100,
                "uniquely_resolved_segments": 30,
                "bounded_candidate_set_segments": 4,
            }
        ]
    )
    units = build_paper_primary_units(entropy, resolution)
    assert len(units) == 1
    assert units.loc[0, "dataset_family"] == "DNS Roots"
    assert units.loc[0, "valid_atomic_segment_count"] == 100
    assert units.loc[0, "candidate_bearing_segment_count"] == 34
    assert units.loc[0, "top2_corridor_minus_network_shift"] == pytest.approx(0.3)


def test_current_aggregate_reproduces_paper_primary_unit_counts() -> None:
    """The checked-in 30 km July 1 aggregate retains its documented corpus."""
    root = Path(__file__).resolve().parents[1]
    aggregate = root / "results" / "july1_public_atlas_20260701" / "aggregate"
    entropy_path = (
        aggregate / "all_measurements_cross_layer_normalized_entropy_audit_full.csv"
    )
    resolution_path = (
        aggregate / "all_measurements_service_country_physical_mapping_resolution.csv"
    )
    if not entropy_path.exists() or not resolution_path.exists():
        return
    units = build_paper_primary_units(
        pd.read_csv(entropy_path, low_memory=False),
        pd.read_csv(resolution_path, low_memory=False),
    )
    assert len(units) == 370
    assert units["dataset_family"].value_counts().to_dict() == {
        "DNS Roots": 222,
        "Topology references": 95,
        "Applications": 53,
    }
