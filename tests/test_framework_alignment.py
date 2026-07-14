import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

import postprocess_candidate_output as post


def test_confirmed_active_only_excludes_unknown_lifecycle_by_default():
    """Paper-primary lifecycle filtering should exclude unknown cable metadata."""
    pytest.importorskip("maxminddb")
    import main_analysis

    unknown = main_analysis.is_cable_available_at({}, "2026-07-01T00:00:00Z")
    assert unknown["cable_availability_status"] == "unknown"
    assert unknown["availability_filter_passed"] is False

    robustness = main_analysis.is_cable_available_at(
        {},
        "2026-07-01T00:00:00Z",
        mode="confirmed_active_plus_unknown",
    )
    assert robustness["cable_availability_status"] == "unknown"
    assert robustness["availability_filter_passed"] is True


def test_non_positive_rtt_is_inconclusive_not_hard_filter():
    """Noisy RTT deltas should preserve feasible candidates instead of filtering them."""
    pytest.importorskip("maxminddb")
    import main_analysis

    matcher_stub = SimpleNamespace(rtt_tolerance_ms=5.0)
    result = main_analysis.CableMatcher.compute_rtt_feasibility_score(matcher_stub, -1.0, 20.0)

    assert result["rtt_feasible"] is True
    assert result["rtt_feasibility_status"] == "inconclusive"
    assert result["rtt_filter_applied"] is False
    assert result["rtt_delta_quality"] == "non_positive_or_noisy"
    assert result["rtt_margin_ms"] is None


def test_paper_observation_thresholds_use_shared_constants():
    """Paper case sufficiency should use the configured 30/10/3/0.3 thresholds."""
    result = post.evaluate_paper_observation_sufficiency(
        total_observations=29,
        unique_probes=9,
        unique_probe_asns=2,
        country_fallback_share=0.31,
        require_country_fallback=True,
    )

    assert result["auditable_paper_case"] is False
    assert "minimum_mappable_segments" in result["failed_thresholds"]
    assert "minimum_unique_probes" in result["failed_thresholds"]
    assert "minimum_unique_probe_asns" in result["failed_thresholds"]
    assert "maximum_country_fallback_share" in result["failed_thresholds"]


def test_country_physical_exposure_recomputes_unique_counts_from_traces():
    """Country exposure must not sum service-country unique probe counts."""
    trace_frame = pd.DataFrame(
        [
            {
                "trace_id": "t1",
                "probe_country": "US",
                "service_id": "svc-a",
                "probe_id": "p1",
                "probe_asn_norm": "AS64500",
                "target_ip": "192.0.2.1",
                "target_asn_norm": "AS64496",
                "has_at_least_one_mappable_segment": True,
                "has_at_least_one_feasible_submarine_corridor": True,
            },
            {
                "trace_id": "t2",
                "probe_country": "US",
                "service_id": "svc-b",
                "probe_id": "p1",
                "probe_asn_norm": "AS64500",
                "target_ip": "192.0.2.2",
                "target_asn_norm": "AS64497",
                "has_at_least_one_mappable_segment": True,
                "has_at_least_one_feasible_submarine_corridor": False,
            },
        ]
    )

    summary = post.build_country_physical_exposure_summary(trace_frame)
    us_row = summary.loc[summary["probe_country"] == "US"].iloc[0]

    assert us_row["total_valid_traces"] == 2
    assert us_row["unique_services"] == 2
    assert us_row["unique_probes"] == 1
    assert us_row["unique_probe_asns"] == 1


def test_corridor_label_is_region_pair_not_exact_landing_pair():
    """Corridor labels should be stable landing-region labels, not exact station pairs."""
    feasible = pd.DataFrame(
        [
            {
                "link_id": "link-1",
                "corridor_id": "region-a::region-b",
                "corridor_id_fallback": "station-1::station-2",
                "corridor_label": "",
                "landing_pair": ["station-1", "station-2"],
                "landing_region_entry_label": "Region A",
                "landing_region_exit_label": "Region B",
                "src_country": "US",
                "dst_country": "GB",
                "probe_country": "US",
                "probe_id": "p1",
                "probe_asn": 64500,
                "src_asn": 64500,
                "dst_asn": 64496,
                "service_id": "svc",
            },
            {
                "link_id": "link-2",
                "corridor_id": "region-a::region-b",
                "corridor_id_fallback": "station-3::station-4",
                "corridor_label": "",
                "landing_pair": ["station-3", "station-4"],
                "landing_region_entry_label": "Region A",
                "landing_region_exit_label": "Region B",
                "src_country": "US",
                "dst_country": "GB",
                "probe_country": "US",
                "probe_id": "p2",
                "probe_asn": 64501,
                "src_asn": 64501,
                "dst_asn": 64496,
                "service_id": "svc",
            },
        ]
    )

    prepared = post.prepare_atomic_segment_projection_frame(feasible)

    assert prepared["corridor_label"].nunique() == 1
    assert prepared["corridor_label"].iloc[0] == "Region A -> Region B"
    assert "exact_landing_pair_label" in prepared.columns


def test_peeringdb_join_uses_requested_country_role():
    """PeeringDB descriptors should join on the explicit country role requested by the caller."""
    frame = pd.DataFrame(
        [{"probe_country": "us", "src_country": "GB", "unit_id": "u1"}]
    )
    peeringdb = pd.DataFrame(
        [
            {"country": "US", "pdb_interconnection_footprint_score": 1.0},
            {"country": "GB", "pdb_interconnection_footprint_score": 9.0},
        ]
    )

    merged = post.merge_peeringdb_descriptors(frame, peeringdb, country_column="probe_country")

    assert merged["pdb_interconnection_footprint_score"].iloc[0] == 1.0
    assert merged["peeringdb_join_country_field"].iloc[0] == "probe_country"


def test_observation_mass_deduplicates_corridors_per_atomic_segment():
    """One atomic segment should contribute one unit of mass split across distinct corridors."""
    feasible = pd.DataFrame(
        [
            {
                "link_id": "link-1",
                "corridor_id": "c1",
                "corridor_label": "Corridor 1",
                "src_country": "US",
                "dst_country": "GB",
                "probe_country": "US",
                "probe_id": "p1",
                "probe_asn": 64500,
                "src_asn": 64500,
                "dst_asn": 64496,
                "service_id": "svc",
                "fused_candidate_support": 10.0,
            },
            {
                "link_id": "link-1",
                "corridor_id": "c1",
                "corridor_label": "Corridor 1",
                "src_country": "US",
                "dst_country": "GB",
                "probe_country": "US",
                "probe_id": "p1",
                "probe_asn": 64500,
                "src_asn": 64500,
                "dst_asn": 64496,
                "service_id": "svc",
                "fused_candidate_support": 5.0,
            },
            {
                "link_id": "link-1",
                "corridor_id": "c2",
                "corridor_label": "Corridor 2",
                "src_country": "US",
                "dst_country": "GB",
                "probe_country": "US",
                "probe_id": "p1",
                "probe_asn": 64500,
                "src_asn": 64500,
                "dst_asn": 64496,
                "service_id": "svc",
                "fused_candidate_support": 1.0,
            },
        ]
    )

    mass = post.build_segment_corridor_mass_frame(feasible)

    assert set(mass["corridor_id"]) == {"c1", "c2"}
    assert math.isclose(float(mass["observation_mass"].sum()), 1.0)
    assert sorted(mass["observation_mass"].round(6).tolist()) == [0.5, 0.5]
    assert set(mass["raw_segment_count_with_corridor_feasible"]) == {1}


def test_network_and_corridor_summaries_use_same_atomic_segment_population():
    """Network and corridor concentration summaries should be based on the same atomic segments."""
    feasible = pd.DataFrame(
        [
            {
                "link_id": "link-1",
                "corridor_id": "c1",
                "corridor_label": "Corridor 1",
                "src_country": "US",
                "dst_country": "GB",
                "probe_country": "US",
                "probe_id": "p1",
                "probe_asn": 64500,
                "src_asn": 64500,
                "dst_asn": 64496,
                "service_id": "svc",
            },
            {
                "link_id": "link-2",
                "corridor_id": "c2",
                "corridor_label": "Corridor 2",
                "src_country": "US",
                "dst_country": "FR",
                "probe_country": "US",
                "probe_id": "p2",
                "probe_asn": 64501,
                "src_asn": 64501,
                "dst_asn": 64497,
                "service_id": "svc",
            },
        ]
    )

    prepared = post.prepare_atomic_segment_projection_frame(feasible)
    mass = post.build_segment_corridor_mass_frame(feasible)

    assert set(prepared["atomic_segment_id"]) == set(mass["atomic_segment_id"])
    assert prepared["atomic_segment_id"].nunique() == 2
    assert mass["atomic_segment_id"].nunique() == 2
