"""Run and summarize the 27-setting A-Root projection sensitivity grid."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from source.result_provenance import (
    file_manifest,
    git_generation_state,
    inherited_commit,
    read_json,
    sha256_file,
    source_hashes,
)


DEFAULT_INPUT_ROOT = (
    REPO_ROOT
    / "data"
    / "traceroute_rundnsroot"
    / "ripe_atlas_public_20260701_0000_0100"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "output" / "sensitivity_a_root"
DEFAULT_AS_PRECOMPUTE = (
    REPO_ROOT / "output" / "preprocessed" / "as_graph_owner_reachability.pkl.gz"
)
BASELINE = (50, 50, 5)
SENSITIVITY_SCHEMA_VERSION = "a_root_sensitivity_v2"
PAPER_SCOPE = {
    "path_scope_stratum": "all_publicly_visible",
    "analysis_scope": "probe_country_service",
    "auditable_paper_case": True,
}
UNIT_KEY_COLUMNS = [
    "probe_country",
    "service_id",
    "path_scope_stratum",
    "analysis_scope",
]
SETTING_INPUT_FILES = [
    "physical_mapping_resolution_summary.csv",
    "service_country_cross_layer_distribution_audit.csv",
    "service_country_corridor_concentration_summary.csv",
    "cross_layer_normalized_entropy_audit.csv",
    "trace_feasible_candidate_space.csv",
    "landing_region_catalog.csv",
    "corridor_catalog.csv",
    "method_manifest.json",
]


def parse_args() -> argparse.Namespace:
    """Parse sensitivity input, output, and execution controls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--as-precompute-file",
        type=Path,
        default=DEFAULT_AS_PRECOMPUTE,
    )
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve_a_root_input(explicit: Path | None) -> Path:
    """Resolve the downloaded A-Root result file."""
    if explicit:
        return explicit.resolve()
    matches = sorted(DEFAULT_INPUT_ROOT.glob("*a-root*msm5009*.json"))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one A-Root msm5009 input under {DEFAULT_INPUT_ROOT}, "
            f"found {len(matches)}."
        )
    return matches[0].resolve()


def setting_name(catchment: int, diameter: int, rtt: int) -> str:
    """Return a stable directory label for one sensitivity setting."""
    return f"catchment{catchment}_diameter{diameter}_rtt{rtt}"


def run_command(command: Iterable[str], dry_run: bool) -> None:
    """Run one subprocess and fail immediately on non-zero exit."""
    printable = " ".join(str(item) for item in command)
    print(f"Running: {printable}")
    if not dry_run:
        subprocess.run(list(command), cwd=REPO_ROOT, check=True)


def median_numeric(frame: pd.DataFrame, column: str) -> float:
    """Return one robust numeric median."""
    if frame.empty or column not in frame:
        return np.nan
    return float(pd.to_numeric(frame[column], errors="coerce").median())


def mean_positive(frame: pd.DataFrame, column: str) -> float:
    """Return the share of finite values strictly above zero."""
    if frame.empty or column not in frame:
        return np.nan
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.gt(0).mean()) if not values.empty else np.nan


def auditable_scope(frame: pd.DataFrame) -> pd.DataFrame:
    """Select the fixed paper-primary A-Root unit population."""
    result = frame.copy()
    if "path_scope_stratum" in result:
        result = result.loc[
            result["path_scope_stratum"].astype(str).eq(
                PAPER_SCOPE["path_scope_stratum"]
            )
        ]
    if "analysis_scope" in result:
        result = result.loc[
            result["analysis_scope"].astype(str).eq(PAPER_SCOPE["analysis_scope"])
        ]
    audit_column = next(
        (
            column
            for column in ["auditable_paper_case", "auditable_cross_layer_case"]
            if column in result
        ),
        None,
    )
    if audit_column:
        result = result.loc[result[audit_column].fillna(False).astype(bool)]
    return result.copy()


def stable_paper_unit_id(row: pd.Series | dict[str, Any]) -> str:
    """Serialize the stable country-service paper unit identity."""
    values = []
    for column in UNIT_KEY_COLUMNS:
        value = row.get(column, "")  # type: ignore[arg-type]
        text = "" if pd.isna(value) else str(value).strip()
        values.append(text)
    return "paper_unit_v1|" + "|".join(values)


def add_stable_unit_id(frame: pd.DataFrame) -> pd.DataFrame:
    """Add a deterministic unit ID without dropping existing identifiers."""
    result = frame.copy()
    for column in UNIT_KEY_COLUMNS:
        if column not in result:
            result[column] = PAPER_SCOPE.get(column, "")
    result["stable_unit_id"] = result.apply(stable_paper_unit_id, axis=1)
    return result


def stable_exact_candidate_id(
    cable_id: Any,
    landing_station_a_id: Any,
    landing_station_b_id: Any,
) -> str:
    """Build a region-independent candidate ID from cable and station pair.

    Endpoint order does not affect the ID, and landing-region identifiers are
    intentionally excluded because region membership changes with diameter.
    """
    cable = str(cable_id).strip()
    endpoints = sorted(
        [str(landing_station_a_id).strip(), str(landing_station_b_id).strip()]
    )
    return f"stable_exact_candidate_v1|{cable}|{endpoints[0]}|{endpoints[1]}"


def split_exact_landing_pair(value: Any) -> tuple[str, str] | None:
    """Parse one unordered exact landing-pair ID."""
    if pd.isna(value):
        return None
    parts = [item.strip() for item in str(value).split("::")]
    if len(parts) != 2 or not all(parts):
        return None
    return tuple(sorted(parts))  # type: ignore[return-value]


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    """Return a finite ratio or NaN for a zero denominator."""
    return float(numerator / denominator) if denominator else np.nan


def load_setting_summary(
    output_dir: Path,
    catchment: int,
    diameter: int,
    rtt: int,
) -> tuple[Dict[str, Any], pd.DataFrame]:
    """Extract unambiguous resolution and paper-unit metrics for one setting."""
    resolution = pd.read_csv(output_dir / "physical_mapping_resolution_summary.csv")
    resolution_counts = {
        str(state): int(count)
        for state, count in zip(
            resolution["mapping_resolution_state"],
            pd.to_numeric(resolution["atomic_segment_count"], errors="coerce").fillna(0),
        )
    }
    all_atomic = int(sum(resolution_counts.values()))
    single = int(resolution_counts.get("uniquely_resolved", 0))
    bounded = int(resolution_counts.get("bounded_candidate_set", 0))
    candidate_bearing = single + bounded
    if single + bounded != candidate_bearing:
        raise AssertionError("Resolution-state accounting is inconsistent.")
    single_among = _safe_ratio(single, candidate_bearing)
    bounded_among = _safe_ratio(bounded, candidate_bearing)
    if candidate_bearing and not math.isclose(
        single_among + bounded_among,
        1.0,
        abs_tol=1e-9,
    ):
        raise AssertionError("Candidate-bearing resolution shares do not sum to one.")

    entropy = pd.read_csv(output_dir / "cross_layer_normalized_entropy_audit.csv")
    units = add_stable_unit_id(auditable_scope(entropy))
    if units["stable_unit_id"].duplicated().any():
        raise AssertionError(f"Duplicate paper unit IDs in {output_dir}.")
    return (
        {
            "setting": setting_name(catchment, diameter, rtt),
            "landing_catchment_radius_km": catchment,
            "landing_region_maximum_diameter_km": diameter,
            "rtt_tolerance_ms": rtt,
            "all_atomic_segment_count": all_atomic,
            "candidate_bearing_segment_count": candidate_bearing,
            "single_corridor_segment_count": single,
            "bounded_multi_corridor_segment_count": bounded,
            "single_corridor_share_of_all_atomic_segments": _safe_ratio(
                single, all_atomic
            ),
            "bounded_multi_corridor_share_of_all_atomic_segments": _safe_ratio(
                bounded, all_atomic
            ),
            "single_corridor_share_among_candidate_bearing_segments": single_among,
            "bounded_multi_corridor_share_among_candidate_bearing_segments": bounded_among,
            # Deprecated compatibility aliases. Their denominator is all atomic segments.
            "inter_region_candidate_bearing_segments": candidate_bearing,
            "uniquely_resolved_segments": single,
            "bounded_candidate_set_segments": bounded,
            "uniquely_resolved_share": _safe_ratio(single, all_atomic),
            "bounded_candidate_set_share": _safe_ratio(bounded, all_atomic),
            "auditable_country_service_units": int(len(units)),
            "median_corridor_top2_share": median_numeric(
                units, "top2_corridor_share"
            ),
            "median_corridor_normalized_entropy": median_numeric(
                units, "corridor_normalized_entropy"
            ),
            "median_normalized_entropy_reduction": median_numeric(
                units, "normalized_entropy_reduction"
            ),
        },
        units,
    )


def _boolean_mask(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a tolerant Boolean mask for one optional column."""
    if column not in frame:
        return pd.Series(False, index=frame.index, dtype=bool)
    values = frame[column]
    if values.dtype == bool:
        return values.fillna(False)
    return values.astype(str).str.strip().str.lower().eq("true")


def _candidate_sets(
    frame: pd.DataFrame,
    segment_column: str,
    value_column: str,
) -> dict[str, frozenset[str]]:
    """Group distinct candidate identifiers by canonical atomic segment."""
    valid = frame.dropna(subset=[segment_column, value_column]).copy()
    return {
        str(segment_id): frozenset(group[value_column].astype(str).unique())
        for segment_id, group in valid.groupby(segment_column, sort=False)
    }


def _comember_pairs(
    station_to_region: dict[str, str],
    observed_stations: set[str],
) -> set[tuple[str, str]]:
    """Build co-membership pairs only for observed A-Root landing stations."""
    members_by_region: dict[str, list[str]] = {}
    for station_id in sorted(observed_stations):
        region_id = station_to_region.get(station_id)
        if region_id:
            members_by_region.setdefault(region_id, []).append(station_id)
    return {
        pair
        for members in members_by_region.values()
        for pair in itertools.combinations(sorted(members), 2)
    }


def load_projection_diagnostics(output_dir: Path) -> Dict[str, Any]:
    """Load stable candidate, corridor, and landing-partition diagnostics."""
    landing_regions = pd.read_csv(output_dir / "landing_region_catalog.csv")
    corridors = pd.read_csv(
        output_dir / "corridor_catalog.csv",
        usecols=["corridor_id"],
    )
    required_columns = {
        "atomic_segment_id",
        "link_id",
        "cable_id",
        "corridor_id",
        "exact_landing_pair_id",
        "landing_region_entry_id",
        "landing_region_exit_id",
        "candidate_scope",
        "is_inter_region_candidate",
    }
    feasible = pd.read_csv(
        output_dir / "trace_feasible_candidate_space.csv",
        usecols=lambda column: column in required_columns,
        low_memory=False,
    )
    inter_region = _boolean_mask(feasible, "is_inter_region_candidate")
    if not inter_region.any() and "candidate_scope" in feasible:
        inter_region = feasible["candidate_scope"].isin(
            ["international_inter_region", "domestic_inter_region"]
        )
    observed = feasible.loc[inter_region].copy()
    segment_column = (
        "atomic_segment_id" if "atomic_segment_id" in observed else "link_id"
    )
    observed = observed.dropna(subset=[segment_column]).copy()
    observed[segment_column] = observed[segment_column].astype(str)

    all_exact_pair_values = feasible.get(
        "exact_landing_pair_id",
        pd.Series(index=feasible.index, dtype=object),
    )
    all_cable_values = feasible.get(
        "cable_id",
        pd.Series(index=feasible.index, dtype=object),
    )
    parsed_pairs = all_exact_pair_values.apply(split_exact_landing_pair)
    valid_pair = (
        parsed_pairs.notna()
        & all_cable_values.notna()
        & feasible[segment_column].notna()
    )
    stable_rows = pd.DataFrame(
        {
            segment_column: feasible.loc[valid_pair, segment_column].astype(str),
            "cable_id": all_cable_values.loc[valid_pair],
        }
    )
    stable_rows["landing_pair_tuple"] = parsed_pairs.loc[valid_pair]
    stable_rows["stable_exact_candidate_id"] = [
        stable_exact_candidate_id(cable_id, pair[0], pair[1])
        for cable_id, pair in zip(
            stable_rows["cable_id"],
            stable_rows["landing_pair_tuple"],
        )
    ]
    stable_rows["cable_id"] = stable_rows["cable_id"].astype(str)

    segment_exact_candidate_sets = _candidate_sets(
        stable_rows,
        segment_column,
        "stable_exact_candidate_id",
    )
    segment_cable_sets = _candidate_sets(
        stable_rows,
        segment_column,
        "cable_id",
    )
    corridor_rows = observed.dropna(subset=["corridor_id"]).copy()
    corridor_rows["corridor_id"] = corridor_rows["corridor_id"].astype(str)
    segment_corridor_sets = _candidate_sets(
        corridor_rows,
        segment_column,
        "corridor_id",
    )
    incidence = {
        (segment_id, corridor_id)
        for segment_id, corridor_set in segment_corridor_sets.items()
        for corridor_id in corridor_set
    }

    observed_station_ids = {
        station_id
        for pair in parsed_pairs.dropna()
        for station_id in pair
    }
    station_to_region = (
        {
            str(station): str(region)
            for station, region in zip(
                landing_regions["landing_station_id"],
                landing_regions["landing_region_id"],
            )
            if pd.notna(station) and pd.notna(region)
        }
        if "landing_station_id" in landing_regions
        else {}
    )
    observed_region_ids = {
        station_to_region[station]
        for station in observed_station_ids
        if station in station_to_region
    }
    if not observed_region_ids:
        for column in [
            "landing_region_entry_id",
            "landing_region_exit_id",
        ]:
            if column in observed:
                observed_region_ids.update(
                    observed[column].dropna().astype(str)
                )
    return {
        "global_landing_region_count": int(
            landing_regions["landing_region_id"].dropna().astype(str).nunique()
        ),
        "observed_landing_region_count": int(len(observed_region_ids)),
        "global_corridor_count": int(
            corridors["corridor_id"].dropna().astype(str).nunique()
        ),
        "observed_corridor_count": int(
            corridor_rows["corridor_id"].nunique()
        ),
        "observed_station_ids": observed_station_ids,
        "station_to_region": station_to_region,
        "segment_exact_candidate_sets": segment_exact_candidate_sets,
        "segment_cable_sets": segment_cable_sets,
        "inter_region_segment_ids": set(segment_corridor_sets),
        "segment_corridor_sets": segment_corridor_sets,
        "segment_corridor_incidence": incidence,
    }


def _set_comparison(
    current_sets: dict[str, frozenset[str]],
    baseline_sets: dict[str, frozenset[str]],
    shared_segments: Sequence[str],
    prefix: str,
) -> Dict[str, Any]:
    """Compare candidate sets on shared candidate-bearing segments."""
    jaccards: list[float] = []
    exact_matches = 0
    for segment_id in shared_segments:
        current = current_sets[segment_id]
        baseline = baseline_sets[segment_id]
        union = current | baseline
        score = len(current & baseline) / len(union) if union else 1.0
        if not 0.0 <= score <= 1.0:
            raise AssertionError(f"Invalid {prefix} Jaccard: {score}")
        jaccards.append(float(score))
        exact_matches += int(current == baseline)
    count = len(shared_segments)
    return {
        f"{prefix}_jaccard_mean": float(np.mean(jaccards)) if jaccards else np.nan,
        f"{prefix}_jaccard_median": float(np.median(jaccards)) if jaccards else np.nan,
        f"{prefix}_exact_match_share": _safe_ratio(exact_matches, count),
        f"segments_with_changed_{prefix}": int(count - exact_matches),
    }


def compare_projection_diagnostics(
    current: Dict[str, Any],
    baseline: Dict[str, Any],
    same_diameter: bool = True,
) -> Dict[str, Any]:
    """Compare stable candidates, corridor labels, and observed partitions."""
    current_incidence = current["segment_corridor_incidence"]
    baseline_incidence = baseline["segment_corridor_incidence"]
    incidence_union = current_incidence | baseline_incidence
    corridor_jaccard = (
        len(current_incidence & baseline_incidence) / len(incidence_union)
        if incidence_union
        else np.nan
    )
    current_corridors = current["segment_corridor_sets"]
    baseline_corridors = baseline["segment_corridor_sets"]
    all_corridor_segments = set(current_corridors) | set(baseline_corridors)
    changed_corridors = sum(
        current_corridors.get(segment_id, frozenset())
        != baseline_corridors.get(segment_id, frozenset())
        for segment_id in all_corridor_segments
    )

    current_exact_sets = current.get("segment_exact_candidate_sets", {})
    baseline_exact_sets = baseline.get("segment_exact_candidate_sets", {})
    current_cable_sets = current.get("segment_cable_sets", {})
    baseline_cable_sets = baseline.get("segment_cable_sets", {})
    shared_segments = sorted(
        set(current_exact_sets)
        & set(baseline_exact_sets)
        & set(current.get("inter_region_segment_ids", current_exact_sets))
        & set(baseline.get("inter_region_segment_ids", baseline_exact_sets))
    )
    stable_metrics = {
        "shared_candidate_bearing_segment_count": int(len(shared_segments)),
        **_set_comparison(
            current_exact_sets,
            baseline_exact_sets,
            shared_segments,
            "exact_candidate_set",
        ),
        **_set_comparison(
            current_cable_sets,
            baseline_cable_sets,
            shared_segments,
            "cable_set",
        ),
    }

    observed_stations = set(current.get("observed_station_ids", set())) | set(
        baseline.get("observed_station_ids", set())
    )
    current_pairs = _comember_pairs(
        current.get("station_to_region", {}),
        observed_stations,
    )
    baseline_pairs = _comember_pairs(
        baseline.get("station_to_region", {}),
        observed_stations,
    )
    pair_union = current_pairs | baseline_pairs
    partition_jaccard = (
        len(current_pairs & baseline_pairs) / len(pair_union)
        if pair_union
        else 1.0
    )
    result = {
        "segment_corridor_set_jaccard_with_baseline": float(corridor_jaccard),
        "segments_with_changed_corridor_set": int(changed_corridors),
        "corridor_id_comparison_semantics": (
            "direct_corridor_id_comparison"
            if same_diameter
            else "resolution_dependent_corridor_id_comparison"
        ),
        "observed_landing_station_count": int(len(observed_stations)),
        "baseline_comember_pair_count": int(len(baseline_pairs)),
        "current_comember_pair_count": int(len(current_pairs)),
        "comember_pair_intersection_count": int(
            len(current_pairs & baseline_pairs)
        ),
        "comember_pair_union_count": int(len(pair_union)),
        "landing_partition_comembership_jaccard": float(partition_jaccard),
        **stable_metrics,
    }
    for column, value in result.items():
        if ("jaccard" in column or column.endswith("_share")) and pd.notna(value):
            if not 0.0 <= float(value) <= 1.0:
                raise AssertionError(f"{column} outside [0, 1]: {value}")
    return result


def auditable_unit_keys(frame: pd.DataFrame) -> set[tuple[str, ...]]:
    """Return stable paper-auditable country-service/path-scope unit keys."""
    if frame.empty:
        return set()
    with_ids = add_stable_unit_id(frame)
    return {(value,) for value in with_ids["stable_unit_id"].astype(str)}


def compare_auditable_units(
    current: pd.DataFrame,
    baseline: pd.DataFrame,
) -> Dict[str, int]:
    """Count baseline, current, shared, newly included, and excluded units."""
    current_units = {item[0] for item in auditable_unit_keys(current)}
    baseline_units = {item[0] for item in auditable_unit_keys(baseline)}
    shared = current_units & baseline_units
    new = current_units - baseline_units
    excluded = baseline_units - current_units
    result = {
        "baseline_auditable_unit_count": int(len(baseline_units)),
        "current_auditable_unit_count": int(len(current_units)),
        "shared_auditable_unit_count": int(len(shared)),
        "newly_included_unit_count": int(len(new)),
        "excluded_baseline_unit_count": int(len(excluded)),
        # Deprecated aliases.
        "newly_included_units": int(len(new)),
        "excluded_units": int(len(excluded)),
    }
    if result["current_auditable_unit_count"] != (
        result["shared_auditable_unit_count"]
        + result["newly_included_unit_count"]
    ):
        raise AssertionError("Current cohort accounting failed.")
    if result["baseline_auditable_unit_count"] != (
        result["shared_auditable_unit_count"]
        + result["excluded_baseline_unit_count"]
    ):
        raise AssertionError("Baseline cohort accounting failed.")
    return result


def compare_shared_cohort(
    current: pd.DataFrame,
    baseline: pd.DataFrame,
    setting: str,
) -> tuple[Dict[str, Any], pd.DataFrame]:
    """Compare paper metrics on the stable baseline-shared unit cohort."""
    current = add_stable_unit_id(current)
    baseline = add_stable_unit_id(baseline)
    merged = baseline.merge(
        current,
        on="stable_unit_id",
        how="inner",
        suffixes=("_baseline", "_current"),
    )
    label_base = merged.get(
        "cross_layer_distribution_class_baseline",
        pd.Series(index=merged.index, dtype=object),
    )
    label_current = merged.get(
        "cross_layer_distribution_class_current",
        pd.Series(index=merged.index, dtype=object),
    )
    valid_base = label_base.notna() & ~label_base.astype(str).str.startswith("unknown")
    valid_current = label_current.notna() & ~label_current.astype(str).str.startswith(
        "unknown"
    )
    valid = valid_base & valid_current
    agreement = (
        label_base.loc[valid].astype(str) == label_current.loc[valid].astype(str)
    )
    denominator = int(valid.sum())
    numerator = int(agreement.sum())

    for suffix in ["baseline", "current"]:
        network_top2 = pd.to_numeric(
            merged.get(f"top2_network_transition_share_{suffix}"),
            errors="coerce",
        )
        corridor_top2 = pd.to_numeric(
            merged.get(f"top2_corridor_share_{suffix}"),
            errors="coerce",
        )
        merged[f"top2_shift_{suffix}"] = corridor_top2 - network_top2
        network_entropy = pd.to_numeric(
            merged.get(f"network_transition_normalized_entropy_{suffix}"),
            errors="coerce",
        )
        corridor_entropy = pd.to_numeric(
            merged.get(f"corridor_normalized_entropy_{suffix}"),
            errors="coerce",
        )
        merged[f"entropy_reduction_{suffix}"] = network_entropy - corridor_entropy
    merged.insert(0, "setting", setting)
    merged["classification_comparable"] = valid
    merged["classification_agrees"] = np.where(valid, agreement.reindex(merged.index), np.nan)

    result = {
        "shared_median_network_top2": median_numeric(
            merged, "top2_network_transition_share_current"
        ),
        "baseline_shared_median_network_top2": median_numeric(
            merged, "top2_network_transition_share_baseline"
        ),
        "current_shared_median_network_top2": median_numeric(
            merged, "top2_network_transition_share_current"
        ),
        "baseline_shared_median_corridor_top2": median_numeric(
            merged, "top2_corridor_share_baseline"
        ),
        "current_shared_median_corridor_top2": median_numeric(
            merged, "top2_corridor_share_current"
        ),
        "baseline_shared_median_top2_shift": median_numeric(
            merged, "top2_shift_baseline"
        ),
        "current_shared_median_top2_shift": median_numeric(
            merged, "top2_shift_current"
        ),
        "shared_median_network_normalized_entropy": median_numeric(
            merged, "network_transition_normalized_entropy_current"
        ),
        "baseline_shared_median_network_normalized_entropy": median_numeric(
            merged, "network_transition_normalized_entropy_baseline"
        ),
        "current_shared_median_network_normalized_entropy": median_numeric(
            merged, "network_transition_normalized_entropy_current"
        ),
        "baseline_shared_median_corridor_normalized_entropy": median_numeric(
            merged, "corridor_normalized_entropy_baseline"
        ),
        "current_shared_median_corridor_normalized_entropy": median_numeric(
            merged, "corridor_normalized_entropy_current"
        ),
        "baseline_shared_median_entropy_reduction": median_numeric(
            merged, "entropy_reduction_baseline"
        ),
        "current_shared_median_entropy_reduction": median_numeric(
            merged, "entropy_reduction_current"
        ),
        "baseline_shared_positive_entropy_reduction_share": mean_positive(
            merged, "entropy_reduction_baseline"
        ),
        "current_shared_positive_entropy_reduction_share": mean_positive(
            merged, "entropy_reduction_current"
        ),
        "classification_agreement_numerator": numerator,
        "classification_agreement_denominator": denominator,
        "classification_agreement_rate": _safe_ratio(numerator, denominator),
        # Deprecated alias.
        "classification_agreement_with_baseline": _safe_ratio(
            numerator, denominator
        ),
    }
    return result, merged


def _manifest_inputs(output_root: Path, settings: Sequence[tuple[int, int, int]]) -> list[dict[str, Any]]:
    """Describe every file read by the sensitivity summarizer."""
    files: list[dict[str, Any]] = []
    for catchment, diameter, rtt in settings:
        output_dir = output_root / setting_name(catchment, diameter, rtt)
        for filename in SETTING_INPUT_FILES:
            path = output_dir / filename
            if path.exists():
                item = file_manifest(path, REPO_ROOT)
                item["setting"] = setting_name(catchment, diameter, rtt)
                files.append(item)
    return files


def write_sensitivity_manifest(
    output_root: Path,
    input_path: Path,
    settings: Sequence[tuple[int, int, int]],
    summary_path: Path,
    shared_path: Path,
) -> None:
    """Write reproducible sensitivity provenance without inventing commits."""
    method_manifests = [
        read_json(
            output_root / setting_name(*setting) / "method_manifest.json"
        )
        for setting in settings
    ]
    postprocess_versions = sorted(
        {
            str(item.get("postprocess_schema_version"))
            for item in method_manifests
            if item.get("postprocess_schema_version")
        }
    )
    identity_versions = sorted(
        {
            str(item.get("identity_schema_version"))
            for item in method_manifests
            if item.get("identity_schema_version")
        }
    )
    generation = git_generation_state(REPO_ROOT)
    manifest = {
        "sensitivity_schema_version": SENSITIVITY_SCHEMA_VERSION,
        "core_analysis_commit": inherited_commit(
            method_manifests,
            ["core_analysis_commit", "git_commit", "git_commit_sha"],
        ),
        "packaging_commit": "unknown",
        "sensitivity_analysis_commit": (
            "unknown"
            if generation["generation_worktree_dirty"]
            else generation["generation_git_head"]
        ),
        "identity_schema_version": (
            identity_versions[0] if len(identity_versions) == 1 else "unknown"
        ),
        "postprocess_schema_version": (
            postprocess_versions[0] if len(postprocess_versions) == 1 else "unknown"
        ),
        **generation,
        "source_file_sha256": source_hashes(
            [
                REPO_ROOT / "pipeline" / "run_a_root_sensitivity.py",
                REPO_ROOT / "source" / "main_analysis.py",
                REPO_ROOT / "source" / "postprocess_candidate_output.py",
                REPO_ROOT / "source" / "physical_corridor_model.py",
                REPO_ROOT / "source" / "result_provenance.py",
            ],
            REPO_ROOT,
        ),
        "input_file_sha256": sha256_file(input_path),
        "raw_traceroute_input": file_manifest(input_path, REPO_ROOT),
        "input_files": _manifest_inputs(output_root, settings),
        "generated_outputs": [
            file_manifest(summary_path, REPO_ROOT),
            file_manifest(shared_path, REPO_ROOT),
        ],
        "settings": [
            {
                "setting": setting_name(*setting),
                "landing_catchment_radius_km": setting[0],
                "landing_region_maximum_diameter_km": setting[1],
                "rtt_tolerance_ms": setting[2],
                "is_baseline": setting == BASELINE,
            }
            for setting in settings
        ],
        "baseline_setting": {
            "landing_catchment_radius_km": BASELINE[0],
            "landing_region_maximum_diameter_km": BASELINE[1],
            "rtt_tolerance_ms": BASELINE[2],
        },
        "paper_primary_filter": PAPER_SCOPE,
        "deprecated_columns": {
            "uniquely_resolved_share": "single-corridor count divided by all atomic segments",
            "bounded_candidate_set_share": "bounded multi-corridor count divided by all atomic segments",
            "newly_included_units": "alias of newly_included_unit_count",
            "excluded_units": "alias of excluded_baseline_unit_count",
            "classification_agreement_with_baseline": "alias of classification_agreement_rate",
        },
        "sensitivity_semantics": {
            "coverage_sensitivity": [
                "candidate_bearing_segment_count",
                "current_auditable_unit_count",
                "newly_included_unit_count",
                "excluded_baseline_unit_count",
            ],
            "resolution_sensitivity": [
                "landing_partition_comembership_jaccard",
                "observed_corridor_count",
                "single_corridor_share_among_candidate_bearing_segments",
                "bounded_multi_corridor_share_among_candidate_bearing_segments",
            ],
            "stable_candidate_sensitivity": [
                "exact_candidate_set_jaccard_mean",
                "cable_set_jaccard_mean",
            ],
            "shared_cohort_conclusion_stability": [
                "current_shared_median_corridor_top2",
                "current_shared_median_entropy_reduction",
                "classification_agreement_rate",
            ],
        },
        "warnings": [
            "core_analysis_commit is unknown unless inherited from a historical stage manifest",
            "corridor-ID comparisons across different diameters are resolution-dependent diagnostics",
            "Top-2, effective count, normalized entropy, and descriptive concentration classes are distinct summaries",
        ],
    }
    (output_root / "a_root_sensitivity_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def validate_sensitivity_summary(frame: pd.DataFrame) -> None:
    """Apply hard accounting and range checks to the 27-setting summary."""
    if len(frame) != 27 or frame["setting"].nunique() != 27:
        raise AssertionError("Sensitivity summary must contain 27 unique settings.")
    baseline_mask = (
        frame["landing_catchment_radius_km"].eq(BASELINE[0])
        & frame["landing_region_maximum_diameter_km"].eq(BASELINE[1])
        & frame["rtt_tolerance_ms"].eq(BASELINE[2])
    )
    if int(baseline_mask.sum()) != 1:
        raise AssertionError("Sensitivity summary must contain exactly one baseline.")
    if not (
        frame["single_corridor_segment_count"]
        + frame["bounded_multi_corridor_segment_count"]
        == frame["candidate_bearing_segment_count"]
    ).all():
        raise AssertionError("Candidate-bearing resolution accounting failed.")
    candidate_rows = frame["candidate_bearing_segment_count"].gt(0)
    sums = (
        frame.loc[
            candidate_rows,
            "single_corridor_share_among_candidate_bearing_segments",
        ]
        + frame.loc[
            candidate_rows,
            "bounded_multi_corridor_share_among_candidate_bearing_segments",
        ]
    )
    if not np.allclose(sums, 1.0, atol=1e-9):
        raise AssertionError("Candidate-bearing shares do not sum to one.")
    bounded_columns = [
        column
        for column in frame
        if "jaccard" in column
        or column.endswith("_share")
        or column.endswith("_rate")
    ]
    for column in bounded_columns:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if not values.between(0, 1).all():
            raise AssertionError(f"{column} contains values outside [0, 1].")


def main() -> None:
    """Run missing settings and write corrected paper-facing sensitivity outputs."""
    args = parse_args()
    input_path = resolve_a_root_input(args.input)
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    settings = list(
        itertools.product([30, 50, 75], [30, 50, 75], [0, 5, 10])
    )

    for catchment, diameter, rtt in settings:
        output_dir = output_root / setting_name(catchment, diameter, rtt)
        summary_path = output_dir / "cross_layer_normalized_entropy_audit.csv"
        if args.skip_existing and summary_path.exists() and summary_path.stat().st_size > 0:
            continue
        output_dir.mkdir(parents=True, exist_ok=True)
        run_command(
            [
                sys.executable,
                "source/main_analysis.py",
                "--traceroute-input",
                str(input_path),
                "--output-dir",
                str(output_dir),
                "--as-precompute-file",
                str(args.as_precompute_file.resolve()),
                "--landing-catchment-radius-km",
                str(catchment),
                "--landing-region-maximum-diameter-km",
                str(diameter),
                "--rtt-tolerance-ms",
                str(rtt),
            ],
            args.dry_run,
        )
        run_command(
            [
                sys.executable,
                "source/build_atomic_segment_inventory.py",
                "--traceroute-input",
                str(input_path),
                "--output-dir",
                str(output_dir),
            ],
            args.dry_run,
        )
        run_command(
            [
                sys.executable,
                "source/postprocess_candidate_output.py",
                "--input",
                str(output_dir / "cable_matching_output.json"),
                "--output",
                str(output_dir),
                "--landing-region-maximum-diameter-km",
                str(diameter),
            ],
            args.dry_run,
        )

    if args.dry_run:
        return

    rows: list[Dict[str, Any]] = []
    units_by_setting: Dict[tuple[int, int, int], pd.DataFrame] = {}
    diagnostics_by_setting: Dict[tuple[int, int, int], Dict[str, Any]] = {}
    for catchment, diameter, rtt in settings:
        key = (catchment, diameter, rtt)
        output_dir = output_root / setting_name(*key)
        row, units = load_setting_summary(output_dir, *key)
        diagnostics = load_projection_diagnostics(output_dir)
        row.update(
            {
                name: diagnostics[name]
                for name in [
                    "global_landing_region_count",
                    "observed_landing_region_count",
                    "global_corridor_count",
                    "observed_corridor_count",
                ]
            }
        )
        rows.append(row)
        units_by_setting[key] = units
        diagnostics_by_setting[key] = diagnostics

    baseline_units = units_by_setting[BASELINE]
    baseline_diagnostics = diagnostics_by_setting[BASELINE]
    shared_frames: list[pd.DataFrame] = []
    for row in rows:
        key = (
            int(row["landing_catchment_radius_km"]),
            int(row["landing_region_maximum_diameter_km"]),
            int(row["rtt_tolerance_ms"]),
        )
        row.update(compare_auditable_units(units_by_setting[key], baseline_units))
        shared_metrics, shared_frame = compare_shared_cohort(
            units_by_setting[key],
            baseline_units,
            str(row["setting"]),
        )
        row.update(shared_metrics)
        row.update(
            compare_projection_diagnostics(
                diagnostics_by_setting[key],
                baseline_diagnostics,
                same_diameter=key[1] == BASELINE[1],
            )
        )
        shared_frames.append(shared_frame)

    summary = pd.DataFrame(rows)
    validate_sensitivity_summary(summary)
    summary_path = output_root / "a_root_sensitivity_summary.csv"
    shared_path = output_root / "a_root_sensitivity_shared_unit_comparison.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.concat(shared_frames, ignore_index=True, sort=False).to_csv(
        shared_path,
        index=False,
        encoding="utf-8-sig",
    )
    write_sensitivity_manifest(
        output_root,
        input_path,
        settings,
        summary_path,
        shared_path,
    )
    print(f"Saved corrected 27-setting A-Root sensitivity outputs to {output_root}")


if __name__ == "__main__":
    main()
