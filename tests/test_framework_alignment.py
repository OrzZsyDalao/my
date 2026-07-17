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


def test_country_geography_catalog_classifies_operational_types():
    """The versioned catalog should classify landlocked, island, and default coastal countries."""
    catalog = post.load_country_geography_catalog(str(REPO_ROOT / "data" / "country_geography_types.json"))

    assert post.classify_country_geography_type("CH", catalog)[0] == "landlocked"
    assert post.classify_country_geography_type("JP", catalog)[0] == "island_or_archipelagic"
    assert post.classify_country_geography_type("US", catalog)[0] == "coastal_mainland_or_mixed"
    assert post.classify_country_geography_type("NA", catalog)[0] == "unknown"
    assert not (
        catalog["landlocked_country_codes"]
        & catalog["island_or_archipelagic_country_codes"]
    )
    assert all(len(code) == 2 and code.isalpha() for code in catalog["landlocked_country_codes"])
    assert all(len(code) == 2 and code.isalpha() for code in catalog["island_or_archipelagic_country_codes"])


def test_country_geography_dependency_recomputes_trace_level_rate():
    """Country dependency proxies must use trace counts rather than averaging service rates."""
    trace_frame = pd.DataFrame(
        [
            {
                "trace_id": "t1",
                "probe_country": "CH",
                "service_id": "svc-a",
                "probe_id": "p1",
                "probe_asn_norm": "AS64500",
                "service_entry_resolved": True,
                "has_at_least_one_mappable_segment": True,
                "has_inter_region_candidate": True,
                "has_domestic_inter_region_candidate": False,
                "has_international_inter_region_candidate": True,
                "has_intra_region_candidate": False,
            },
            {
                "trace_id": "t2",
                "probe_country": "CH",
                "service_id": "svc-b",
                "probe_id": "p2",
                "probe_asn_norm": "AS64501",
                "service_entry_resolved": False,
                "has_at_least_one_mappable_segment": True,
                "has_inter_region_candidate": False,
                "has_domestic_inter_region_candidate": False,
                "has_international_inter_region_candidate": False,
                "has_intra_region_candidate": True,
            },
        ]
    )
    catalog = post.load_country_geography_catalog(str(REPO_ROOT / "data" / "country_geography_types.json"))

    result = post.build_country_geography_candidate_dependency(trace_frame, catalog)
    all_visible = result.loc[result["path_scope_stratum"] == "all_publicly_visible"].iloc[0]
    resolved = result.loc[result["path_scope_stratum"] == "resolved_entry_only"].iloc[0]

    assert all_visible["total_valid_traces"] == 2
    assert all_visible["candidate_dependency_proxy_rate"] == 0.5
    assert all_visible["country_geography_type"] == "landlocked"
    assert resolved["total_valid_traces"] == 1
    assert resolved["candidate_dependency_proxy_rate"] == 1.0


def test_geography_type_summary_uses_trace_weighted_rate():
    """Geography summaries should expose trace-weighted rates alongside country distributions."""
    country = pd.DataFrame(
        [
            {
                "probe_country": "US",
                "country_geography_type": "coastal_mainland_or_mixed",
                "path_scope_stratum": "all_publicly_visible",
                "total_valid_traces": 100,
                "traces_with_inter_region_candidates": 10,
                "candidate_dependency_proxy_rate": 0.10,
                "candidate_dependency_proxy_tier": "moderate_candidate_dependency_proxy",
                "geography_summary_eligible": True,
            },
            {
                "probe_country": "CA",
                "country_geography_type": "coastal_mainland_or_mixed",
                "path_scope_stratum": "all_publicly_visible",
                "total_valid_traces": 10,
                "traces_with_inter_region_candidates": 5,
                "candidate_dependency_proxy_rate": 0.50,
                "candidate_dependency_proxy_tier": "very_high_candidate_dependency_proxy",
                "geography_summary_eligible": True,
            },
            {
                "probe_country": "MX",
                "country_geography_type": "coastal_mainland_or_mixed",
                "path_scope_stratum": "all_publicly_visible",
                "total_valid_traces": 0,
                "traces_with_inter_region_candidates": 0,
                "candidate_dependency_proxy_rate": np.nan,
                "candidate_dependency_proxy_tier": "unknown_candidate_dependency_proxy",
                "geography_summary_eligible": False,
            },
        ]
    )
    service = pd.DataFrame(
        columns=[
            "country_geography_type",
            "path_scope_stratum",
            "auditable_paper_case",
            "corridor_concentration_tier",
            "cross_layer_distribution_class",
        ]
    )

    summary = post.build_geography_type_candidate_dependency_summary(country, service).iloc[0]

    assert math.isclose(summary["trace_weighted_candidate_dependency_proxy_rate"], 15 / 110)
    assert summary["median_country_candidate_dependency_proxy_rate"] == 0.30
    assert summary["num_countries"] == 2


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


def test_corridor_summary_uses_group_probe_union_not_largest_corridor_count():
    """Disjoint probes across corridors must be unioned before paper audit thresholds are applied."""
    rows = []
    for index in range(30):
        corridor_id = "corridor-a" if index < 15 else "corridor-b"
        probe_number = index % 6 if index < 15 else 6 + ((index - 15) % 7)
        probe_asn_number = probe_number % 2 if probe_number < 6 else 2 + (probe_number % 2)
        rows.append(
            {
                "probe_country": "US",
                "service_id": "svc",
                "path_scope_stratum": "all_publicly_visible",
                "corridor_id": corridor_id,
                "corridor_label": corridor_id,
                "msm_id": 5009,
                "file_name": "sample.json",
                "observation_mass": 1.0,
                "raw_segment_count_with_corridor_feasible": 1,
                "atomic_segment_id": f"segment-{index}",
                "traceroute_observation_id": f"trace-{index}",
                "probe_id": f"probe-{probe_number}",
                "probe_asn_norm": f"AS{64500 + probe_asn_number}",
                "domestic_segment_mass": 0.0,
                "international_segment_mass": 1.0,
            }
        )
    mass = pd.DataFrame(rows)
    group_fields = ["probe_country", "service_id", "path_scope_stratum"]

    distribution = post.summarize_corridor_observation_distribution(mass, group_fields)
    summary = post.build_corridor_concentration_summary(distribution, group_fields).iloc[0]

    assert sorted(distribution["unique_probes"].tolist()) == [6, 7]
    assert distribution["group_unique_probes"].unique().tolist() == [13]
    assert distribution["group_unique_probe_asns"].unique().tolist() == [4]
    assert summary["unique_probes"] == 13
    assert summary["unique_probe_asns"] == 4
    assert bool(summary["auditable_paper_case"]) is True


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


def test_intra_region_candidates_are_retained_but_excluded_from_default_corridor_mass():
    """Domestic inter-region candidates remain auditable while intra-region rows stay supplementary."""
    feasible = pd.DataFrame(
        [
            {"link_id": "domestic", "corridor_id": "r1::r2", "landing_region_entry_id": "r1", "landing_region_exit_id": "r2", "candidate_scope": "domestic_inter_region", "corridor_label": "City A -> City B", "src_country": "US", "dst_country": "US", "probe_country": "US", "probe_id": "p1", "probe_asn": 64500, "src_asn": 64500, "dst_asn": 64496, "service_id": "svc"},
            {"link_id": "intra", "corridor_id": "r1::r1", "landing_region_entry_id": "r1", "landing_region_exit_id": "r1", "candidate_scope": "intra_landing_region", "corridor_label": "City A intra-region", "src_country": "US", "dst_country": "US", "probe_country": "US", "probe_id": "p1", "probe_asn": 64500, "src_asn": 64500, "dst_asn": 64496, "service_id": "svc"},
        ]
    )
    prepared = post.prepare_atomic_segment_projection_frame(feasible)
    mass = post.build_segment_corridor_mass_frame(feasible)

    assert set(prepared["candidate_scope"]) == {"domestic_inter_region", "intra_landing_region"}
    assert set(mass["corridor_id"]) == {"r1::r2"}


def test_paper_filter_keeps_only_auditable_rows():
    """Paper-facing tables must not silently retain insufficient-observation rows."""
    frame = pd.DataFrame([
        {"unit_id": "small", "auditable_paper_case": False},
        {"unit_id": "auditable", "auditable_paper_case": True},
    ])
    filtered = post.filter_auditable_paper_rows(frame)
    assert filtered["unit_id"].tolist() == ["auditable"]


def test_framework_report_keeps_atomic_and_candidate_populations_separate():
    """Projection rows may repeat candidates, but projection segment counts must remain unique."""
    prepared = pd.DataFrame(
        [
            {"atomic_segment_id": "s1", "used_country_fallback_transition": False, "corridor_id": "a::b"},
            {"atomic_segment_id": "s1", "used_country_fallback_transition": False, "corridor_id": "a::c"},
            {"atomic_segment_id": "s2", "used_country_fallback_transition": True, "corridor_id": "d::e"},
        ]
    )
    report = post.build_framework_alignment_report(
        pd.DataFrame(),
        prepared,
        pd.DataFrame(),
        {},
        {
            "atomic_segments_total": 10,
            "atomic_segments_with_valid_rtt_evidence": 7,
            "atomic_segments_with_inconclusive_rtt": 3,
            "candidate_rows_total": 20,
            "candidate_rows_lifecycle_filtered": 4,
            "candidate_rows_rtt_infeasible": 5,
            "candidate_rows_rtt_feasible": 11,
            "candidate_rows_rtt_inconclusive": 2,
        },
    )

    assert report["stage1_atomic_segments_total"] == 10
    assert report["projection_atomic_segments_total"] == 2
    assert report["projection_atomic_segments_with_as_transition"] == 1
    assert report["projection_atomic_segments_using_country_fallback"] == 1
    assert report["candidate_rows_rtt_feasible"] == 11


def test_service_scope_summaries_use_the_same_segment_population_rules():
    """All-visible and resolved-entry-only corridor/network summaries must remain separate."""
    feasible = pd.DataFrame(
        [
            {"link_id": "s1", "corridor_id": "a::b", "src_country": "US", "dst_country": "GB", "probe_country": "US", "probe_id": "p1", "probe_asn": 64500, "src_asn": 64500, "dst_asn": 64496, "service_id": "svc", "service_entry_resolved": True},
            {"link_id": "s2", "corridor_id": "c::d", "src_country": "US", "dst_country": "FR", "probe_country": "US", "probe_id": "p2", "probe_asn": 64501, "src_asn": 64501, "dst_asn": 64497, "service_id": "svc", "service_entry_resolved": False},
        ]
    )
    prepared = post.prepare_atomic_segment_projection_frame(feasible)
    scoped = post.build_service_path_scope_projections(prepared)
    network = post.summarize_network_transition_concentration(
        scoped,
        ["probe_country", "service_id", "path_scope_stratum"],
    )

    totals = dict(zip(network["path_scope_stratum"], network["total_mappable_segments"]))
    assert totals == {"all_publicly_visible": 2, "resolved_entry_only": 1}


def test_complete_service_summary_retains_zero_projection_scope():
    """A resolved-entry stratum with no inter-region candidates remains in the complete summary."""
    exposure = pd.DataFrame(
        [
            {"probe_country": "US", "service_id": "svc", "path_scope_stratum": "all_publicly_visible"},
            {"probe_country": "US", "service_id": "svc", "path_scope_stratum": "resolved_entry_only"},
        ]
    )
    corridor = pd.DataFrame(
        [{
            "probe_country": "US",
            "service_id": "svc",
            "path_scope_stratum": "all_publicly_visible",
            "total_mappable_segments": 35,
            "auditable_paper_case": True,
        }]
    )

    complete = post.ensure_service_path_scope_summary_rows(corridor, exposure, "corridor")
    resolved = complete.loc[complete["path_scope_stratum"] == "resolved_entry_only"].iloc[0]

    assert len(complete) == 2
    assert resolved["total_mappable_segments"] == 0
    assert bool(resolved["auditable_paper_case"]) is False
    assert resolved["corridor_concentration_tier"] == "unknown_corridor_observation_concentration"


def test_service_exposure_uses_inter_region_candidates_as_primary():
    """An intra-region-only trace remains supplementary and is not paper-primary exposure."""
    frame = pd.DataFrame(
        [{
            "trace_id": "t1",
            "probe_country": "US",
            "service_id": "svc",
            "service_entry_resolved": True,
            "has_at_least_one_mappable_segment": True,
            "has_at_least_one_feasible_submarine_corridor": True,
            "has_any_candidate": True,
            "has_inter_region_candidate": False,
            "has_domestic_inter_region_candidate": False,
            "has_international_inter_region_candidate": False,
            "has_intra_region_candidate": True,
            "probe_id": "p1",
            "probe_asn_norm": "AS64500",
            "target_ip": "192.0.2.1",
            "target_asn_norm": "AS64496",
        }]
    )
    summary = post.build_service_country_physical_exposure_summary(frame)
    all_visible = summary.loc[summary["path_scope_stratum"] == "all_publicly_visible"].iloc[0]

    assert all_visible["any_candidate_exposure_rate"] == 1.0
    assert all_visible["inter_region_candidate_exposure_rate"] == 0.0
    assert all_visible["submarine_candidate_exposure_rate"] == 0.0


def test_feasible_candidate_dedup_key_is_direction_independent():
    """Reversing a landing pair must not create a second cable candidate."""
    pytest.importorskip("maxminddb")
    import main_analysis

    forward = {"cable_id": "cable-x", "exact_landing_pair_id": "a::b", "segment": "a -> b"}
    reverse = {"cable_id": "cable-x", "exact_landing_pair_id": "a::b", "segment": "b -> a"}
    assert main_analysis.build_feasible_candidate_dedup_key(forward) == main_analysis.build_feasible_candidate_dedup_key(reverse)
