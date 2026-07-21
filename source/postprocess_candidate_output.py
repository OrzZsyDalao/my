import argparse
import hashlib
import json
import math
import os
from html import escape
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd

from measurement_catalog import lookup_measurement


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else "."
BASE_DIR = os.path.dirname(SOURCE_DIR)
DEFAULT_INPUT = os.path.join(BASE_DIR, "output", "result", "cable_matching_output.json")
DEFAULT_OUTPUT = os.path.join(BASE_DIR, "output", "result")
PEERINGDB_DESCRIPTOR_PATH = os.path.join(DEFAULT_OUTPUT, "country_peeringdb_descriptors.csv")
DEFAULT_COUNTRY_GEOGRAPHY_CATALOG = os.path.join(BASE_DIR, "data", "country_geography_types.json")
DEFAULT_UNIT_FIELDS = ["probe_country", "service_id"]
# Paper-primary relative target for the upper-bound mismatch view.
TARGET_MISMATCH_CATEGORY = "network_high_physical_upper_low"
LEGACY_WEIGHTED_TARGET_MISMATCH_CATEGORY = "network_high_physical_low"
PAPER_PRIMARY_NETWORK_DEFINITION = "as_egress_primary"
PAPER_PRIMARY_PHYSICAL_LEVEL = "corridor"
MINIMUM_MAPPABLE_SEGMENTS = 30
MINIMUM_UNIQUE_PROBES = 10
MINIMUM_UNIQUE_PROBE_ASNS = 3
MAXIMUM_COUNTRY_FALLBACK_SHARE = 0.3
COUNTRY_DEPENDENCY_PROXY_THRESHOLDS = {
    "low": 0.05,
    "moderate": 0.15,
    "high": 0.30,
}
QUADRANT_ORDER = [
    "network_high_physical_low",
    "network_high_physical_high",
    "network_low_physical_low",
    "network_low_physical_high",
]
QUADRANT_COLORS = {
    "network_high_physical_low": "#c0392b",
    "network_high_physical_high": "#2874a6",
    "network_low_physical_low": "#af7ac5",
    "network_low_physical_high": "#52be80",
}
# `as_egress_primary` is the paper-primary network diversity view.
# `geographic_transition_supplementary` is a supplementary geographic descriptor, not
# the primary network diversity measure.
# `application_observation_supplementary` captures coverage/richness rather than
# effective network-path diversity.
# Rank/percentile mismatch outputs remain auxiliary relative views over the chosen corpus.
NETWORK_DEFINITION_COLUMNS = {
    "composite": "network_layer_diversity_score",
    "as_only": "network_layer_diversity_score_as_only",
    "country_only": "network_layer_diversity_score_country_only",
    "probe_target_only": "network_layer_diversity_score_probe_target_only",
    "as_egress_primary": "network_diversity_as_egress_primary",
    "as_pair_primary": "network_layer_diversity_score_as_only",
    "dst_asn_primary": "network_diversity_dst_asn_primary",
    "geographic_transition_supplementary": "network_layer_diversity_score_country_only",
    "application_observation_supplementary": "network_layer_diversity_score_probe_target_only",
    "combined_supplementary": "network_layer_diversity_score",
}
KNOWN_AMBIGUITY_TAGS = [
    "parallel_candidate_corridor",
    "many_candidates",
    "large_landing_radius",
    "rtt_inconclusive",
    "geo_dominant_as_weak",
    "as_dominant_geo_ambiguous",
    "domestic_submarine_candidate",
    "multi_segment_possible",
]
PROJECTION_QUALITY_CLASSES = ["strong", "moderate", "weak", "ambiguous"]
ABSOLUTE_COMPRESSION_TIER_ORDER = [
    "no_compression",
    "weak_compression",
    "moderate_compression",
    "severe_compression",
]
PRIMARY_CROSS_LAYER_COLUMNS = [
    "unit_id",
    "probe_country",
    "src_country",
    "service_id",
    "msm_id",
    "file_name",
    "num_measurements",
    "num_probes",
    "num_probe_asns",
    "num_files_or_targets",
    "num_egress_links",
    "num_egress_asns",
    "num_next_asns_after_egress",
    "num_egress_transitions",
    "egress_transition_entropy",
    "effective_egress_transitions",
    "num_src_dst_as_pairs",
    "src_dst_as_pair_entropy",
    "effective_as_pair_transitions",
    "network_effective_diversity",
    "physical_level",
    "num_feasible_candidates",
    "num_feasible_corridors",
    "effective_feasible_candidates",
    "effective_feasible_corridors",
    "physical_candidate_diversity_upper_bound",
    "best_case_physical_candidate_diversity_upper_bound",
    "physical_candidate_concentration_tier",
    "is_physical_candidate_concentrated",
    "physical_candidate_exposure_class",
    "sufficient_observation_for_physical_concentration",
    "concentration_interpretation",
    "network_to_physical_compression_ratio",
    "log_network_physical_compression_gap",
    "physical_coverage_ratio",
    "absolute_compression_tier",
    "network_physical_compression_tier",
    "joint_cross_layer_risk_class",
    "is_network_physical_mismatch",
    "is_physical_candidate_concentration_only",
    "is_joint_physical_concentration_and_mismatch",
    "network_percentile",
    "physical_upper_bound_percentile",
    "rank_gap_upper_bound",
    "strict_upper_bound_mismatch_75_25",
    "upper_bound_mismatch_category",
    "pdb_interconnection_footprint_score",
    "pdb_interconnection_footprint_percentile",
    "pdb_interconnection_footprint_tier",
    "peeringdb_join_country_field",
]
AMBIGUITY_TAXONOMY_ROWS = [
    {
        "ambiguity_class": "parallel_candidate_corridor",
        "reviewer_concern": "Parallel cables on the same landing-pair corridor may be over-separated.",
        "treatment": "Report both cable-level and corridor-level diversity and preserve corridor_id in outputs.",
        "interpretation_boundary": "A cable-level split is candidate-support evidence, not a claim about unique cable utilization.",
    },
    {
        "ambiguity_class": "many_candidates",
        "reviewer_concern": "A large candidate set may indicate diffuse evidence rather than strong path specificity.",
        "treatment": "Keep normalized support across all retained candidates and expose ambiguity support shares per unit.",
        "interpretation_boundary": "High candidate multiplicity reflects uncertainty in physical-candidate support, not routing error.",
    },
    {
        "ambiguity_class": "large_landing_radius",
        "reviewer_concern": "Wide landing-station radii weaken fine-grained spatial interpretation.",
        "treatment": "Retain the candidate with an explicit ambiguity tag and expose its support contribution.",
        "interpretation_boundary": "Spatial proximity is only one evidence core and does not by itself identify a unique physical candidate.",
    },
    {
        "ambiguity_class": "rtt_inconclusive",
        "reviewer_concern": "Tight RTT margins reduce the discriminative value of latency feasibility.",
        "treatment": "Keep feasible candidates but tag their RTT evidence as inconclusive for downstream interpretation.",
        "interpretation_boundary": "Feasibility indicates consistency with a candidate, not proof of cable traversal.",
    },
    {
        "ambiguity_class": "geo_dominant_as_weak",
        "reviewer_concern": "Spatial evidence may dominate while AS-economic evidence stays weak.",
        "treatment": "Expose dual-core disagreement through ambiguity tags and core-agreement summaries.",
        "interpretation_boundary": "A geo-dominant candidate remains a candidate-support hypothesis, not a ground-truth route label.",
    },
    {
        "ambiguity_class": "as_dominant_geo_ambiguous",
        "reviewer_concern": "AS-economic support may be stronger than the geo-spatial signal.",
        "treatment": "Retain the candidate with explicit disagreement labeling instead of forcing a single interpretation.",
        "interpretation_boundary": "AS proximity alone is insufficient to assert physical cable use.",
    },
    {
        "ambiguity_class": "domestic_submarine_candidate",
        "reviewer_concern": "Domestic links can still map to submarine candidates and complicate naive filtering assumptions.",
        "treatment": "Keep tagged candidates visible so domestic-submarine support remains auditable rather than silently removed.",
        "interpretation_boundary": "A domestic submarine candidate is a feasible support candidate, not a certainty claim.",
    },
    {
        "ambiguity_class": "multi_segment_possible",
        "reviewer_concern": "Long corridors with slack RTT headroom may hide multi-segment infrastructure possibilities.",
        "treatment": "Preserve the candidate but tag the interpretation as potentially multi-segment.",
        "interpretation_boundary": "Single-segment cable identifiers should not be read as exact physical path recovery.",
    },
]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Post-process candidate-support outputs into network-layer diversity and mismatch tables."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input candidate-support JSON file.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output directory for CSV tables.")
    parser.add_argument(
        "--unit-fields",
        default=",".join(DEFAULT_UNIT_FIELDS),
        help="Comma-separated link_info fields used to define a unit.",
    )
    parser.add_argument("--minimum-mappable-segments", type=int, default=MINIMUM_MAPPABLE_SEGMENTS)
    parser.add_argument("--minimum-unique-probes", type=int, default=MINIMUM_UNIQUE_PROBES)
    parser.add_argument("--minimum-unique-probe-asns", type=int, default=MINIMUM_UNIQUE_PROBE_ASNS)
    parser.add_argument("--maximum-country-fallback-share", type=float, default=MAXIMUM_COUNTRY_FALLBACK_SHARE)
    parser.add_argument(
        "--country-geography-catalog",
        default=DEFAULT_COUNTRY_GEOGRAPHY_CATALOG,
        help="JSON catalog used to classify probe countries by broad geography type.",
    )
    return parser.parse_args()


def shannon_entropy(values: Iterable[float]) -> float:
    """Compute Shannon entropy over a non-negative sequence."""
    array = np.asarray([value for value in values if value > 0], dtype=float)
    total = array.sum()
    if total <= 0 or array.size == 0:
        return 0.0
    probs = array / total
    return float(-(probs * np.log(probs)).sum())


def gini_coefficient(values: Iterable[float]) -> float:
    """Compute the Gini coefficient for a non-negative vector."""
    array = np.asarray([max(value, 0.0) for value in values], dtype=float)
    if array.size == 0 or np.allclose(array.sum(), 0.0):
        return 0.0
    sorted_array = np.sort(array)
    n_items = sorted_array.size
    cumulative = np.cumsum(sorted_array)
    return float((n_items + 1 - 2 * (cumulative.sum() / cumulative[-1])) / n_items)


def safe_log1p(value: float) -> float:
    """Compute log1p on non-negative inputs."""
    return float(math.log1p(max(value, 0.0)))


def dominant_non_missing_value(series: pd.Series, default: str = "NA") -> str:
    """Return the dominant non-missing token from a Series with a stable fallback."""
    if series.empty:
        return default
    values = (
        series.fillna("")
        .astype(str)
        .str.strip()
    )
    values = values[(values != "") & (values.str.lower() != "nan") & (values != "NA")]
    if values.empty:
        return default
    modes = values.mode()
    if modes.empty:
        return default
    return str(modes.iloc[0])


def summarize_identifier_value(series: pd.Series, default: str = "NA") -> str:
    """Return a stable identifier summary for grouped outputs."""
    if series.empty:
        return default
    values = (
        series.fillna("")
        .astype(str)
        .str.strip()
    )
    values = values[(values != "") & (values.str.lower() != "nan") & (values != "NA")]
    if values.empty:
        return default
    unique_values = pd.Index(values.unique().tolist())
    if len(unique_values) == 1:
        return str(unique_values[0])
    return "MULTI"


def normalize_token(value: Any, prefix: str = "") -> str:
    """Normalize identifiers while keeping missing values explicit."""
    if value is None:
        return "NA"
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return "NA"
    if prefix and text.upper().startswith(prefix.upper()):
        return text.upper()
    return text


def effective_count_from_entropy(entropy_value: float, category_count: int) -> float:
    """Convert entropy back to an effective count with a zero-data safeguard."""
    return float(math.exp(entropy_value)) if category_count > 0 else 0.0


def derive_service_id_value(service_value: Any, file_name: Any, msm_id: Any) -> str:
    """Build a stable service identifier from explicit service_id or the shared measurement catalog."""
    explicit = normalize_token(service_value)
    if explicit != "NA":
        return explicit
    msm_token = normalize_token(msm_id)
    if msm_token != "NA":
        return lookup_measurement(msm_token)["service_id"]
    file_token = normalize_token(file_name)
    if file_token != "NA":
        return lookup_measurement(file_token)["service_id"]
    return "NA"


def attach_service_id(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach a service_id column using explicit identifiers when available, else file_name/msm_id."""
    result = frame.copy()
    existing_service = (
        "service_id" in result.columns
        and result["service_id"].fillna("").astype(str).str.strip().ne("").any()
    )
    if existing_service:
        result["service_id"] = result["service_id"].apply(lambda value: normalize_token(value))
        return result

    msm_values = (
        result.get("msm_id", pd.Series(index=result.index, dtype=object))
        .fillna("")
        .astype(str)
        .str.strip()
    )
    result["service_id"] = [
        derive_service_id_value(
            None,
            None,
            msm_value,
        )
        for msm_value in msm_values.tolist()
    ]
    return result


def normalize_link_level_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare a de-duplicated link-level frame with normalized AS and service identifiers."""
    link_level = frame.drop_duplicates(subset=["link_id"]).copy()
    link_level = attach_service_id(link_level)
    link_level["probe_country"] = link_level.get("probe_country", pd.Series(index=link_level.index, dtype=object)).fillna("NA").astype(str)
    link_level["src_country"] = link_level.get("src_country", pd.Series(index=link_level.index, dtype=object)).fillna("NA").astype(str)
    link_level["dst_country"] = link_level.get("dst_country", pd.Series(index=link_level.index, dtype=object)).fillna("NA").astype(str)
    link_level["country_pair"] = link_level["src_country"] + "->" + link_level["dst_country"]
    link_level["src_asn_norm"] = link_level.get("src_asn", pd.Series(index=link_level.index, dtype=object)).apply(
        lambda value: normalize_token(value, prefix="AS")
    )
    link_level["dst_asn_norm"] = link_level.get("dst_asn", pd.Series(index=link_level.index, dtype=object)).apply(
        lambda value: normalize_token(value, prefix="AS")
    )
    link_level["src_dst_as_pair"] = link_level["src_asn_norm"] + "->" + link_level["dst_asn_norm"]
    return link_level


def safe_parse_tags(value: Any) -> List[str]:
    """Safely parse ambiguity-tag fields from JSON strings, lists, or empty values."""
    if isinstance(value, list):
        tags = value
    elif value is None:
        tags = []
    else:
        text = str(value).strip()
        if not text or text.lower() == "nan":
            tags = []
        else:
            try:
                parsed = json.loads(text)
                tags = parsed if isinstance(parsed, list) else [text]
            except json.JSONDecodeError:
                tags = [part.strip() for part in text.split(",") if part.strip()]
    unique_tags = []
    for tag in tags:
        tag_text = str(tag).strip()
        if tag_text and tag_text not in unique_tags:
            unique_tags.append(tag_text)
    return unique_tags


def normalize_tag_list(value: Any) -> List[str]:
    """Backward-compatible wrapper around safe ambiguity-tag parsing."""
    return safe_parse_tags(value)


def safe_parse_owners(value: Any) -> List[str]:
    """Safely parse cable-owner fields from JSON strings, lists, comma strings, or empty values."""
    if isinstance(value, list):
        owners = value
    elif value is None:
        owners = []
    else:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "na"}:
            owners = []
        else:
            try:
                parsed = json.loads(text)
                owners = parsed if isinstance(parsed, list) else [text]
            except json.JSONDecodeError:
                owners = [part.strip() for part in text.split(",") if part.strip()]
    unique_owners = []
    for owner in owners:
        owner_text = str(owner).strip()
        if owner_text and owner_text not in unique_owners:
            unique_owners.append(owner_text)
    return unique_owners


def ensure_corridor_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure corridor-level identifiers exist and gracefully fall back to segment."""
    result = frame.copy()
    if "segment" not in result.columns:
        result["segment"] = np.nan
    if "corridor_id" not in result.columns:
        result["corridor_id"] = np.nan
    if "parallel_group_id" not in result.columns:
        result["parallel_group_id"] = np.nan
    segment_fallback = result["segment"].where(
        result["segment"].notna() & (result["segment"].astype(str).str.strip() != ""),
        result.get("cable_id", pd.Series(index=result.index, dtype=object)),
    )
    result["corridor_id_fallback"] = result["corridor_id"].where(
        result["corridor_id"].notna() & (result["corridor_id"].astype(str).str.strip() != ""),
        segment_fallback,
    )
    result["parallel_group_id_fallback"] = result["parallel_group_id"].where(
        result["parallel_group_id"].notna() & (result["parallel_group_id"].astype(str).str.strip() != ""),
        result["corridor_id_fallback"],
    )
    if "physical_candidate_group_id" not in result.columns:
        result["physical_candidate_group_id"] = np.nan
    if "physical_candidate_group_type" not in result.columns:
        result["physical_candidate_group_type"] = "srlg_like_corridor_group"
    result["physical_candidate_group_id_fallback"] = result["physical_candidate_group_id"].where(
        result["physical_candidate_group_id"].notna() & (result["physical_candidate_group_id"].astype(str).str.strip() != ""),
        result["parallel_group_id_fallback"],
    )
    return result


def resolve_corridor_candidate_column(frame: pd.DataFrame) -> str:
    """Choose the corridor aggregation identifier, preferring corridor_id over segment."""
    if "corridor_id" in frame.columns:
        values = frame["corridor_id"].dropna().astype(str).str.strip()
        if not values.empty and (values != "").any():
            return "corridor_id"
    return "segment"


def build_support_series(frame: pd.DataFrame) -> pd.Series:
    """Return a non-negative support series with graceful fallbacks."""
    if "normalized_candidate_support" in frame.columns:
        series = pd.to_numeric(frame["normalized_candidate_support"], errors="coerce")
    elif "candidate_support" in frame.columns:
        series = pd.to_numeric(frame["candidate_support"], errors="coerce")
    else:
        series = pd.Series(np.zeros(len(frame)), index=frame.index, dtype=float)
    if "candidate_support" in frame.columns:
        fallback = pd.to_numeric(frame["candidate_support"], errors="coerce").fillna(0.0)
        series = series.fillna(fallback)
    return series.fillna(0.0).clip(lower=0.0)


def classify_link_physical_projection_group(group: pd.DataFrame) -> str:
    """Infer a link-level physical projection class from candidate rows."""
    if group.empty:
        return "no_physical_candidate"

    corridor_col = "corridor_id_fallback" if "corridor_id_fallback" in group.columns else "segment"
    corridor_ids = {
        str(value).strip()
        for value in group.get(corridor_col, pd.Series(index=group.index, dtype=object))
        if str(value).strip() and str(value).strip().lower() != "nan"
    }
    cable_ids = {
        str(value).strip()
        for value in group.get("cable_id", pd.Series(index=group.index, dtype=object))
        if str(value).strip() and str(value).strip().lower() != "nan"
    }
    parallel_sizes = pd.to_numeric(group.get("parallel_group_size", pd.Series(index=group.index, dtype=float)), errors="coerce").fillna(0.0)
    parallel_flags = group.get("is_parallel_ambiguous", pd.Series(index=group.index, dtype=object)).fillna(False).astype(bool)
    tag_flags = group.get("ambiguity_tags", pd.Series(index=group.index, dtype=object)).apply(safe_parse_tags)
    has_parallel_group = bool(parallel_flags.any()) or bool((parallel_sizes > 1).any()) or bool(
        tag_flags.apply(lambda tags: "parallel_candidate_corridor" in tags).any()
    )

    if len(corridor_ids) == 1 and len(cable_ids) == 1 and not has_parallel_group:
        return "single_cable_single_corridor"
    if len(corridor_ids) == 1 and has_parallel_group:
        return "parallel_cable_same_corridor"
    if len(corridor_ids) == 1 and len(cable_ids) > 1:
        return "multi_cable_single_corridor"
    if len(corridor_ids) > 1:
        return "multi_corridor_projection"
    return "mixed_or_unknown_projection"


def infer_projection_quality_group(group: pd.DataFrame) -> str:
    """Infer a conservative projection-quality label for one link-level candidate set."""
    if group.empty:
        return "ambiguous"

    candidate_count = int(group["cable_id"].astype(str).replace("nan", np.nan).dropna().nunique()) if "cable_id" in group.columns else int(len(group))
    corridor_class = str(group.get("link_physical_projection_class", pd.Series([""])).iloc[0] or "")
    confidence_bucket = str(group.get("confidence_bucket", pd.Series([""])).iloc[0] or "").strip().lower()
    top_gap = pd.to_numeric(group.get("top1_top2_gap", pd.Series([0.0])), errors="coerce").fillna(0.0).iloc[0]
    max_landing_distance = max(
        pd.to_numeric(group.get("d_in", pd.Series([0.0])), errors="coerce").fillna(0.0).max(),
        pd.to_numeric(group.get("d_out", pd.Series([0.0])), errors="coerce").fillna(0.0).max(),
    )
    min_rtt_margin = pd.to_numeric(group.get("rtt_margin_ms", pd.Series([0.0])), errors="coerce").fillna(0.0).min()
    core_agreements = (
        group.get("core_agreement", pd.Series(index=group.index, dtype=object))
        .fillna("")
        .astype(str)
        .tolist()
    )
    tag_lists = group.get("ambiguity_tags", pd.Series(index=group.index, dtype=object)).apply(safe_parse_tags)
    has_parallel = bool(
        group.get("is_parallel_ambiguous", pd.Series(index=group.index, dtype=object)).fillna(False).astype(bool).any()
    ) or bool(
        pd.to_numeric(group.get("parallel_group_size", pd.Series(index=group.index, dtype=float)), errors="coerce").fillna(0.0).gt(1).any()
    ) or bool(tag_lists.apply(lambda tags: "parallel_candidate_corridor" in tags).any())
    has_many_candidates = bool(tag_lists.apply(lambda tags: "many_candidates" in tags).any()) or candidate_count > 4
    has_large_radius = bool(tag_lists.apply(lambda tags: "large_landing_radius" in tags).any()) or max_landing_distance > 80.0
    has_inconclusive_rtt = bool(tag_lists.apply(lambda tags: "rtt_inconclusive" in tags).any()) or min_rtt_margin < 2.0
    has_dual_core = any(value == "dual_core_agreement" for value in core_agreements)

    if (
        candidate_count == 1
        and confidence_bucket == "high"
        and top_gap >= 0.2
        and not has_parallel
        and corridor_class == "single_cable_single_corridor"
        and max_landing_distance <= 60.0
        and min_rtt_margin >= 5.0
        and has_dual_core
    ):
        return "strong"
    if (
        candidate_count <= 2
        and confidence_bucket in {"high", "medium"}
        and not has_many_candidates
        and corridor_class not in {"multi_corridor_projection", "mixed_or_unknown_projection"}
        and max_landing_distance <= 100.0
    ):
        return "moderate"
    if has_parallel or has_many_candidates or corridor_class == "multi_corridor_projection" or confidence_bucket == "ambiguous":
        return "ambiguous"
    if has_large_radius or has_inconclusive_rtt or not has_dual_core:
        return "weak"
    return "weak"


def annotate_link_projection_classes(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure the flattened candidate table carries a link-level physical projection class."""
    result = frame.copy()
    existing = (
        "link_physical_projection_class" in result.columns
        and result["link_physical_projection_class"].fillna("").astype(str).str.strip().ne("").any()
    )
    if existing:
        return result
    if "link_id" not in result.columns:
        result["link_physical_projection_class"] = "mixed_or_unknown_projection"
        return result

    projection_map = {
        link_id: classify_link_physical_projection_group(group)
        for link_id, group in result.groupby("link_id", dropna=False)
    }
    result["link_physical_projection_class"] = result["link_id"].map(projection_map).fillna("mixed_or_unknown_projection")
    return result


def annotate_projection_quality(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure every flattened candidate row carries a projection-quality label."""
    result = frame.copy()
    if "projection_class" in result.columns:
        values = result["projection_class"].fillna("").astype(str).str.strip()
        if values.ne("").all():
            return result

    if "link_id" not in result.columns:
        result["projection_class"] = "ambiguous"
        return result

    projection_map = {
        link_id: infer_projection_quality_group(group)
        for link_id, group in result.groupby("link_id", dropna=False)
    }
    result["projection_class"] = result.get("projection_class", pd.Series(index=result.index, dtype=object))
    missing_mask = result["projection_class"].fillna("").astype(str).str.strip().eq("")
    result.loc[missing_mask, "projection_class"] = result.loc[missing_mask, "link_id"].map(projection_map).fillna("ambiguous")
    result["projection_class"] = result["projection_class"].fillna("ambiguous")
    return result


def read_candidate_output(path: str) -> List[Dict[str, Any]]:
    """Read the link-level candidate-support JSON output."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("Expected cable_matching_output.json to be a JSON array.")
    return payload


def load_peeringdb_descriptors(output_dir: str) -> pd.DataFrame:
    """Load optional country-level PeeringDB descriptors from the standard result location."""
    path = os.path.join(output_dir, "country_peeringdb_descriptors.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    if "country" not in frame.columns:
        return pd.DataFrame()
    frame["country"] = frame["country"].fillna("").astype(str).str.upper()
    return frame


def load_country_geography_catalog(path: str) -> Dict[str, Any]:
    """Load the transparent country-geography taxonomy used for stratified analysis."""
    empty_catalog = {
        "schema_version": "missing",
        "classification_name": "operational_country_geography_type",
        "types": ["landlocked", "island_or_archipelagic", "coastal_mainland_or_mixed", "unknown"],
        "landlocked_country_codes": set(),
        "island_or_archipelagic_country_codes": set(),
        "unknown_country_codes": {"", "NA", "UNKNOWN", "ZZ"},
        "default_valid_alpha2_type": "unknown",
        "classification_boundary": "Country geography is unavailable; no dependency interpretation is permitted.",
        "catalog_path": path,
        "catalog_loaded": False,
    }
    if not path or not os.path.exists(path):
        print(f"Warning: country geography catalog not found: {path}")
        return empty_catalog
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Warning: failed to read country geography catalog at {path}: {exc}")
        return empty_catalog
    if not isinstance(payload, dict):
        return empty_catalog
    result = dict(payload)
    for key in (
        "landlocked_country_codes",
        "island_or_archipelagic_country_codes",
        "unknown_country_codes",
    ):
        result[key] = {
            str(value).strip().upper()
            for value in payload.get(key, [])
        }
    result["catalog_path"] = path
    result["catalog_loaded"] = True
    return result


def classify_country_geography_type(country: Any, catalog: Dict[str, Any]) -> Tuple[str, str]:
    """Classify one ISO-like country code using the configured operational taxonomy."""
    code = str(country or "").strip().upper()
    if code in catalog.get("unknown_country_codes", set()) or len(code) != 2 or not code.isalpha():
        return "unknown", "unclassified_or_missing_country_code"
    if code in catalog.get("landlocked_country_codes", set()):
        return "landlocked", "catalog_landlocked_list"
    if code in catalog.get("island_or_archipelagic_country_codes", set()):
        return "island_or_archipelagic", "catalog_island_or_archipelagic_list"
    return str(catalog.get("default_valid_alpha2_type", "unknown")), "catalog_default_alpha2_rule"


def attach_country_geography_type(
    frame: pd.DataFrame,
    catalog: Dict[str, Any],
    country_column: str = "probe_country",
) -> pd.DataFrame:
    """Attach geography type and provenance without changing the analysis population."""
    result = frame.copy()
    if country_column not in result.columns:
        result[country_column] = "NA"
    classified = result[country_column].apply(lambda value: classify_country_geography_type(value, catalog))
    result["country_geography_type"] = classified.apply(lambda value: value[0])
    result["country_geography_classification_source"] = classified.apply(lambda value: value[1])
    return result


def classify_candidate_dependency_proxy(rate: Any) -> str:
    """Map an inter-region candidate-exposure rate to transparent descriptive tiers."""
    numeric = pd.to_numeric(pd.Series([rate]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "unknown_candidate_dependency_proxy"
    numeric = float(numeric)
    if numeric <= 0:
        return "no_observed_inter_region_candidate_exposure"
    if numeric < COUNTRY_DEPENDENCY_PROXY_THRESHOLDS["low"]:
        return "low_candidate_dependency_proxy"
    if numeric < COUNTRY_DEPENDENCY_PROXY_THRESHOLDS["moderate"]:
        return "moderate_candidate_dependency_proxy"
    if numeric < COUNTRY_DEPENDENCY_PROXY_THRESHOLDS["high"]:
        return "high_candidate_dependency_proxy"
    return "very_high_candidate_dependency_proxy"


def _count_unique_non_missing(frame: pd.DataFrame, column: str) -> int:
    """Count stable non-empty identifiers in a possibly sparse frame."""
    if column not in frame.columns or frame.empty:
        return 0
    values = frame[column].astype(str).str.strip().replace(
        {"": np.nan, "nan": np.nan, "None": np.nan, "NA": np.nan}
    )
    return int(values.dropna().nunique())


def build_country_geography_candidate_dependency(
    trace_frame: pd.DataFrame,
    catalog: Dict[str, Any],
) -> pd.DataFrame:
    """Recompute country candidate-exposure proxies directly from trace observations."""
    columns = [
        "probe_country",
        "country_geography_type",
        "country_geography_classification_source",
        "path_scope_stratum",
        "total_valid_traces",
        "mappable_traces",
        "traces_with_inter_region_candidates",
        "traces_with_domestic_inter_region_candidates",
        "traces_with_international_inter_region_candidates",
        "traces_with_intra_region_candidates",
        "inter_region_candidate_exposure_rate",
        "inter_region_candidate_rate_among_mappable_traces",
        "domestic_inter_region_candidate_exposure_rate",
        "international_inter_region_candidate_exposure_rate",
        "intra_region_candidate_rate",
        "candidate_dependency_proxy_rate",
        "candidate_dependency_proxy_tier",
        "unique_services",
        "unique_probes",
        "unique_probe_asns",
        "service_entry_resolution_rate",
        "geography_summary_eligible",
        "geography_summary_eligibility_reason",
        "candidate_dependency_proxy_interpretation",
    ]
    if trace_frame.empty:
        return pd.DataFrame(columns=columns)
    rows: List[Dict[str, Any]] = []
    for probe_country, country_group in trace_frame.groupby("probe_country", dropna=False):
        resolved_mask = country_group.get(
            "service_entry_resolved",
            pd.Series(False, index=country_group.index, dtype=bool),
        ).fillna(False).astype(bool)
        for path_scope_stratum, scoped_group in (
            ("all_publicly_visible", country_group),
            ("resolved_entry_only", country_group.loc[resolved_mask]),
        ):
            dedup = scoped_group.drop_duplicates(subset=["trace_id"]).copy()
            total = int(len(dedup))
            mappable = int(
                dedup.get("has_at_least_one_mappable_segment", pd.Series(index=dedup.index, dtype=bool))
                .fillna(False)
                .astype(bool)
                .sum()
            )
            inter_region = int(
                dedup.get("has_inter_region_candidate", pd.Series(index=dedup.index, dtype=bool))
                .fillna(False)
                .astype(bool)
                .sum()
            )
            domestic = int(
                dedup.get("has_domestic_inter_region_candidate", pd.Series(index=dedup.index, dtype=bool))
                .fillna(False)
                .astype(bool)
                .sum()
            )
            international = int(
                dedup.get("has_international_inter_region_candidate", pd.Series(index=dedup.index, dtype=bool))
                .fillna(False)
                .astype(bool)
                .sum()
            )
            intra_region = int(
                dedup.get("has_intra_region_candidate", pd.Series(index=dedup.index, dtype=bool))
                .fillna(False)
                .astype(bool)
                .sum()
            )
            unique_probes = _count_unique_non_missing(dedup, "probe_id")
            unique_probe_asns = _count_unique_non_missing(dedup, "probe_asn_norm")
            eligible = bool(
                mappable >= MINIMUM_MAPPABLE_SEGMENTS
                and unique_probes >= MINIMUM_UNIQUE_PROBES
                and unique_probe_asns >= MINIMUM_UNIQUE_PROBE_ASNS
            )
            failed = []
            if mappable < MINIMUM_MAPPABLE_SEGMENTS:
                failed.append("minimum_mappable_traces")
            if unique_probes < MINIMUM_UNIQUE_PROBES:
                failed.append("minimum_unique_probes")
            if unique_probe_asns < MINIMUM_UNIQUE_PROBE_ASNS:
                failed.append("minimum_unique_probe_asns")
            dependency_rate = float(inter_region / total) if total else np.nan
            geography_type, geography_source = classify_country_geography_type(probe_country, catalog)
            rows.append(
                {
                    "probe_country": str(probe_country),
                    "country_geography_type": geography_type,
                    "country_geography_classification_source": geography_source,
                    "path_scope_stratum": path_scope_stratum,
                    "total_valid_traces": total,
                    "mappable_traces": mappable,
                    "traces_with_inter_region_candidates": inter_region,
                    "traces_with_domestic_inter_region_candidates": domestic,
                    "traces_with_international_inter_region_candidates": international,
                    "traces_with_intra_region_candidates": intra_region,
                    "inter_region_candidate_exposure_rate": dependency_rate,
                    "inter_region_candidate_rate_among_mappable_traces": float(inter_region / mappable) if mappable else np.nan,
                    "domestic_inter_region_candidate_exposure_rate": float(domestic / total) if total else np.nan,
                    "international_inter_region_candidate_exposure_rate": float(international / total) if total else np.nan,
                    "intra_region_candidate_rate": float(intra_region / total) if total else np.nan,
                    "candidate_dependency_proxy_rate": dependency_rate,
                    "candidate_dependency_proxy_tier": classify_candidate_dependency_proxy(dependency_rate),
                    "unique_services": _count_unique_non_missing(dedup, "service_id"),
                    "unique_probes": unique_probes,
                    "unique_probe_asns": unique_probe_asns,
                    "service_entry_resolution_rate": (
                        float(dedup.get("service_entry_resolved", pd.Series(index=dedup.index, dtype=bool)).fillna(False).astype(bool).mean())
                        if total
                        else np.nan
                    ),
                    "geography_summary_eligible": eligible,
                    "geography_summary_eligibility_reason": "eligible" if eligible else "insufficient_" + ",".join(failed),
                    "candidate_dependency_proxy_interpretation": (
                        "trace share with at least one feasible domestic or international inter-region submarine-corridor candidate; "
                        "not actual cable use or traffic dependency"
                    ),
                }
            )
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["probe_country", "path_scope_stratum"]
    ).reset_index(drop=True)


def build_service_country_geography_candidate_dependency(
    service_exposure: pd.DataFrame,
    corridor_summary: pd.DataFrame,
    cross_layer_summary: pd.DataFrame,
    catalog: Dict[str, Any],
) -> pd.DataFrame:
    """Enrich service-country exposure with geography and corridor-distribution context."""
    result = attach_country_geography_type(service_exposure, catalog, "probe_country")
    if result.empty:
        for column in [
            "candidate_dependency_proxy_rate",
            "candidate_dependency_proxy_rate_among_mappable_traces",
            "candidate_dependency_proxy_tier",
            "candidate_dependency_proxy_interpretation",
        ]:
            result[column] = pd.Series(dtype=object)
        return result
    result["candidate_dependency_proxy_rate"] = pd.to_numeric(
        result.get("inter_region_candidate_exposure_rate"), errors="coerce"
    )
    exposed = pd.to_numeric(
        result.get("traces_with_feasible_submarine_corridor_candidates"), errors="coerce"
    )
    mappable = pd.to_numeric(result.get("mappable_traces"), errors="coerce")
    result["candidate_dependency_proxy_rate_among_mappable_traces"] = np.where(
        mappable > 0,
        exposed / mappable,
        np.nan,
    )
    result["candidate_dependency_proxy_tier"] = result["candidate_dependency_proxy_rate"].apply(
        classify_candidate_dependency_proxy
    )
    result["candidate_dependency_proxy_interpretation"] = (
        "descriptive inter-region feasible-corridor candidate exposure; not actual cable use or traffic dependency"
    )
    join_fields = ["probe_country", "service_id", "path_scope_stratum"]
    if not corridor_summary.empty:
        corridor_columns = join_fields + [
            column
            for column in [
                "total_mappable_segments",
                "top1_corridor_share",
                "top3_corridor_share",
                "effective_corridor_count",
                "corridor_concentration_tier",
            ]
            if column in corridor_summary.columns
        ]
        result = result.merge(
            corridor_summary[corridor_columns].drop_duplicates(subset=join_fields),
            on=join_fields,
            how="left",
        )
    if not cross_layer_summary.empty:
        cross_columns = join_fields + [
            column
            for column in [
                "effective_network_transition_count",
                "network_transition_concentration_tier",
                "cross_layer_distribution_class",
            ]
            if column in cross_layer_summary.columns
        ]
        result = result.merge(
            cross_layer_summary[cross_columns].drop_duplicates(subset=join_fields),
            on=join_fields,
            how="left",
        )
    return result


def build_geography_type_candidate_dependency_summary(
    country_dependency: pd.DataFrame,
    service_dependency: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize trace-weighted exposure and country-level distributions by geography type."""
    columns = [
        "country_geography_type",
        "path_scope_stratum",
        "num_countries",
        "num_geography_summary_eligible_countries",
        "total_valid_traces",
        "traces_with_inter_region_candidates",
        "trace_weighted_candidate_dependency_proxy_rate",
        "eligible_trace_weighted_candidate_dependency_proxy_rate",
        "median_country_candidate_dependency_proxy_rate",
        "country_candidate_dependency_proxy_rate_p25",
        "country_candidate_dependency_proxy_rate_p75",
        "high_or_very_high_country_share",
        "num_service_country_units",
        "num_auditable_service_country_units",
        "auditable_corridor_concentrated_unit_share",
        "auditable_network_broad_physical_concentrated_unit_share",
        "interpretation_boundary",
    ]
    if country_dependency.empty:
        return pd.DataFrame(columns=columns)
    rows: List[Dict[str, Any]] = []
    for (geography_type, path_scope), group in country_dependency.groupby(
        ["country_geography_type", "path_scope_stratum"], dropna=False
    ):
        observed_group = group.loc[
            pd.to_numeric(group["total_valid_traces"], errors="coerce").fillna(0) > 0
        ].copy()
        total = float(pd.to_numeric(observed_group["total_valid_traces"], errors="coerce").fillna(0).sum())
        exposed = float(
            pd.to_numeric(observed_group["traces_with_inter_region_candidates"], errors="coerce").fillna(0).sum()
        )
        eligible = observed_group.loc[
            observed_group["geography_summary_eligible"].fillna(False).astype(bool)
        ].copy()
        eligible_total = float(pd.to_numeric(eligible.get("total_valid_traces"), errors="coerce").fillna(0).sum())
        eligible_exposed = float(
            pd.to_numeric(eligible.get("traces_with_inter_region_candidates"), errors="coerce").fillna(0).sum()
        )
        rates = pd.to_numeric(eligible.get("candidate_dependency_proxy_rate"), errors="coerce").dropna()
        high_tiers = {"high_candidate_dependency_proxy", "very_high_candidate_dependency_proxy"}
        matching_services = service_dependency.loc[
            service_dependency.get("country_geography_type", pd.Series(index=service_dependency.index, dtype=object)).astype(str).eq(str(geography_type))
            & service_dependency.get("path_scope_stratum", pd.Series(index=service_dependency.index, dtype=object)).astype(str).eq(str(path_scope))
        ].copy()
        matching_services = matching_services.loc[
            pd.to_numeric(
                matching_services.get("total_valid_traces", pd.Series(index=matching_services.index, dtype=float)),
                errors="coerce",
            ).fillna(0) > 0
        ]
        auditable_services = matching_services.loc[
            matching_services.get("auditable_paper_case", pd.Series(index=matching_services.index, dtype=bool))
            .fillna(False)
            .astype(bool)
        ]
        concentrated = auditable_services.get(
            "corridor_concentration_tier", pd.Series(index=auditable_services.index, dtype=object)
        ).isin(
            {
                "severe_corridor_observation_concentration",
                "moderate_corridor_observation_concentration",
            }
        )
        main_cross_layer = auditable_services.get(
            "cross_layer_distribution_class", pd.Series(index=auditable_services.index, dtype=object)
        ).eq("network_broad_physical_concentrated")
        rows.append(
            {
                "country_geography_type": geography_type,
                "path_scope_stratum": path_scope,
                "num_countries": int(observed_group["probe_country"].nunique()),
                "num_geography_summary_eligible_countries": int(eligible["probe_country"].nunique()),
                "total_valid_traces": int(total),
                "traces_with_inter_region_candidates": int(exposed),
                "trace_weighted_candidate_dependency_proxy_rate": float(exposed / total) if total else np.nan,
                "eligible_trace_weighted_candidate_dependency_proxy_rate": (
                    float(eligible_exposed / eligible_total) if eligible_total else np.nan
                ),
                "median_country_candidate_dependency_proxy_rate": float(rates.median()) if not rates.empty else np.nan,
                "country_candidate_dependency_proxy_rate_p25": float(rates.quantile(0.25)) if not rates.empty else np.nan,
                "country_candidate_dependency_proxy_rate_p75": float(rates.quantile(0.75)) if not rates.empty else np.nan,
                "high_or_very_high_country_share": (
                    float(eligible["candidate_dependency_proxy_tier"].isin(high_tiers).mean())
                    if not eligible.empty
                    else np.nan
                ),
                "num_service_country_units": int(len(matching_services)),
                "num_auditable_service_country_units": int(len(auditable_services)),
                "auditable_corridor_concentrated_unit_share": (
                    float(concentrated.mean()) if not auditable_services.empty else np.nan
                ),
                "auditable_network_broad_physical_concentrated_unit_share": (
                    float(main_cross_layer.mean()) if not auditable_services.empty else np.nan
                ),
                "interpretation_boundary": (
                    "geography-stratified feasible-corridor candidate exposure; not real traffic, cable use, or national resilience"
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["path_scope_stratum", "country_geography_type"]
    ).reset_index(drop=True)


def write_country_geography_dependency_outputs(
    output_dir: str,
    trace_frame: pd.DataFrame,
    service_exposure: pd.DataFrame,
    corridor_summary: pd.DataFrame,
    cross_layer_summary: pd.DataFrame,
    catalog_path: str,
) -> Dict[str, str]:
    """Build and write all geography-stratified candidate-dependency artifacts."""
    catalog = load_country_geography_catalog(catalog_path)
    country_dependency = build_country_geography_candidate_dependency(trace_frame, catalog)
    service_dependency = build_service_country_geography_candidate_dependency(
        service_exposure,
        corridor_summary,
        cross_layer_summary,
        catalog,
    )
    geography_summary = build_geography_type_candidate_dependency_summary(
        country_dependency,
        service_dependency,
    )
    resolved_catalog = (
        country_dependency[
            [
                "probe_country",
                "country_geography_type",
                "country_geography_classification_source",
            ]
        ]
        .drop_duplicates()
        .sort_values("probe_country")
        .reset_index(drop=True)
        if not country_dependency.empty
        else pd.DataFrame(
            columns=[
                "probe_country",
                "country_geography_type",
                "country_geography_classification_source",
            ]
        )
    )
    paths = {
        "country": os.path.join(output_dir, "country_geography_candidate_dependency.csv"),
        "service_country": os.path.join(output_dir, "service_country_geography_candidate_dependency.csv"),
        "summary": os.path.join(output_dir, "geography_type_candidate_dependency_summary.csv"),
        "paper": os.path.join(output_dir, "paper_service_country_geography_candidate_dependency.csv"),
        "resolved_catalog": os.path.join(output_dir, "country_geography_catalog_resolved.csv"),
        "manifest": os.path.join(output_dir, "country_geography_dependency_manifest.json"),
    }
    country_dependency.to_csv(paths["country"], index=False, encoding="utf-8-sig")
    service_dependency.to_csv(paths["service_country"], index=False, encoding="utf-8-sig")
    geography_summary.to_csv(paths["summary"], index=False, encoding="utf-8-sig")
    filter_auditable_paper_rows(service_dependency).to_csv(paths["paper"], index=False, encoding="utf-8-sig")
    resolved_catalog.to_csv(paths["resolved_catalog"], index=False, encoding="utf-8-sig")
    catalog_sha256 = None
    if catalog_path and os.path.exists(catalog_path):
        with open(catalog_path, "rb") as handle:
            catalog_sha256 = hashlib.sha256(handle.read()).hexdigest()
    try:
        manifest_catalog_path = os.path.relpath(catalog_path, BASE_DIR) if catalog_path else None
    except ValueError:
        manifest_catalog_path = os.path.abspath(catalog_path) if catalog_path else None
    manifest = {
        "method_name": "country_geography_candidate_dependency_proxy_analysis",
        "catalog_path": manifest_catalog_path,
        "catalog_sha256": catalog_sha256,
        "catalog_loaded": bool(catalog.get("catalog_loaded")),
        "country_geography_types": catalog.get("types", []),
        "primary_rate": "traces_with_inter_region_candidates / total_valid_traces",
        "conditional_rate": "traces_with_inter_region_candidates / mappable_traces",
        "candidate_dependency_proxy_thresholds": COUNTRY_DEPENDENCY_PROXY_THRESHOLDS,
        "paper_filter": "auditable_paper_case == True",
        "path_scope_strata": ["all_publicly_visible", "resolved_entry_only"],
        "intra_region_treatment": "reported separately and excluded from the primary candidate dependency proxy",
        "interpretation_boundary": (
            "The dependency proxy is feasible inter-region submarine-corridor candidate exposure. "
            "It is not observed cable use, traffic volume, causal dependency, or resilience ground truth."
        ),
        "generated_outputs": [os.path.basename(path) for path in paths.values() if path != paths["manifest"]],
    }
    with open(paths["manifest"], "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
    return paths


def load_stage1_stats(output_dir: str) -> Dict[str, Any]:
    """Load Stage 1 matcher stats when present for framework-alignment reporting."""
    for filename in ["cable_matching_stats_5051.json", "cable_matching_stats.json"]:
        path = os.path.join(output_dir, filename)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            print(f"Warning: failed to read Stage 1 stats at {path}: {exc}")
            return {}
    return {}


def load_trace_observation_summary(output_dir: str) -> pd.DataFrame:
    """Load Stage 1 trace-level observation summary when available."""
    path = os.path.join(output_dir, "trace_observation_summary.csv")
    if not os.path.exists(path):
        print(
            "Warning: trace_observation_summary.csv is missing; "
            "service physical exposure outputs will be header-only."
        )
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        print(f"Warning: failed to read trace observation summary at {path}: {exc}")
        return pd.DataFrame()
    if frame.empty:
        return frame
    frame = attach_service_id(frame)
    for column in ["probe_country", "service_class", "deployment_type", "target_ip", "target_asn", "probe_asn"]:
        if column not in frame.columns:
            frame[column] = "NA"
    frame["probe_country"] = frame["probe_country"].fillna("NA").astype(str).str.strip()
    frame["probe_asn_norm"] = frame["probe_asn"].apply(lambda value: normalize_token(value, prefix="AS"))
    frame["target_asn_norm"] = frame["target_asn"].apply(lambda value: normalize_token(value, prefix="AS"))
    for column in [
        "has_at_least_one_mappable_segment",
        "has_at_least_one_feasible_submarine_corridor",
        "service_entry_resolved",
    ]:
        if column not in frame.columns:
            frame[column] = False
        frame[column] = frame[column].fillna(False).astype(bool)
    if "trace_id" not in frame.columns:
        frame["trace_id"] = frame.apply(
            lambda row: "|".join(
                str(row.get(field, "NA"))
                for field in ["file_name", "msm_id", "probe_id", "timestamp", "target_ip"]
            ),
            axis=1,
        )
    return frame


def annotate_trace_candidate_scope_exposure(trace_frame: pd.DataFrame, feasible_frame: pd.DataFrame) -> pd.DataFrame:
    """Attach all/inter-region candidate exposure flags to trace summaries without dropping intra-region candidates."""
    if trace_frame.empty:
        return trace_frame.copy()
    result = trace_frame.copy()
    flags = [
        "has_any_candidate",
        "has_inter_region_candidate",
        "has_domestic_inter_region_candidate",
        "has_international_inter_region_candidate",
        "has_intra_region_candidate",
    ]
    for flag in flags:
        result[flag] = False
    if feasible_frame.empty or "trace_id" not in feasible_frame:
        return result
    working = feasible_frame.copy()
    scope = working.get("candidate_scope", pd.Series(index=working.index, dtype=object)).fillna("").astype(str)
    if scope.eq("").any():
        entry = working.get("landing_region_entry_id", pd.Series(index=working.index, dtype=object)).fillna("").astype(str)
        exit_ = working.get("landing_region_exit_id", pd.Series(index=working.index, dtype=object)).fillna("").astype(str)
        inferred = np.where(entry.ne("") & entry.eq(exit_), "intra_landing_region", np.where(
            working.get("src_country", pd.Series(index=working.index, dtype=object)).astype(str).eq(
                working.get("dst_country", pd.Series(index=working.index, dtype=object)).astype(str)
            ),
            "domestic_inter_region",
            "international_inter_region",
        ))
        scope = np.where(scope.eq(""), inferred, scope)
    working["candidate_scope"] = scope
    grouped = working.groupby("trace_id", dropna=False)["candidate_scope"].agg(lambda values: set(values.astype(str)))
    for trace_id, scopes in grouped.items():
        mask = result["trace_id"].astype(str).eq(str(trace_id))
        result.loc[mask, "has_any_candidate"] = bool(scopes)
        result.loc[mask, "has_inter_region_candidate"] = bool(scopes & {"domestic_inter_region", "international_inter_region"})
        result.loc[mask, "has_domestic_inter_region_candidate"] = "domestic_inter_region" in scopes
        result.loc[mask, "has_international_inter_region_candidate"] = "international_inter_region" in scopes
        result.loc[mask, "has_intra_region_candidate"] = "intra_landing_region" in scopes
    return result


def build_service_country_physical_exposure_summary(trace_frame: pd.DataFrame) -> pd.DataFrame:
    """Compute trace-level service exposure, with inter-region candidates as the paper-primary view."""
    columns = [
        "probe_country",
        "service_id",
        "service_class",
        "deployment_type",
        "path_scope_stratum",
        "total_valid_traces",
        "mappable_traces",
        "traces_with_feasible_submarine_corridor_candidates",
        "submarine_candidate_exposure_rate",
        "any_candidate_exposure_rate",
        "inter_region_candidate_exposure_rate",
        "domestic_inter_region_candidate_exposure_rate",
        "international_inter_region_candidate_exposure_rate",
        "intra_region_candidate_rate",
        "submarine_exposed_traces",
        "service_physical_exposure_rate",
        "mappable_trace_rate",
        "unique_probes",
        "unique_probe_asns",
        "unique_target_ips",
        "unique_target_asns",
        "service_entry_resolution_rate",
        "sufficient_trace_observation",
        "auditable_paper_case",
        "observation_sufficiency_reason",
        "failed_thresholds",
    ]
    if trace_frame.empty:
        return pd.DataFrame(columns=columns)
    rows: List[Dict[str, Any]] = []
    for group_key, group in trace_frame.groupby(["probe_country", "service_id"], dropna=False):
        probe_country, service_id = group_key
        for path_scope_stratum, scoped_group in (
            ("all_publicly_visible", group),
            ("resolved_entry_only", group.loc[group["service_entry_resolved"].fillna(False).astype(bool)]),
        ):
            dedup = scoped_group.drop_duplicates(subset=["trace_id"]).copy()
            total_valid = int(len(dedup))
            mappable = int(dedup["has_at_least_one_mappable_segment"].sum())
            any_candidate = int(dedup.get("has_any_candidate", pd.Series(index=dedup.index, dtype=bool)).sum())
            inter_region = int(dedup.get("has_inter_region_candidate", pd.Series(index=dedup.index, dtype=bool)).sum())
            domestic_inter = int(dedup.get("has_domestic_inter_region_candidate", pd.Series(index=dedup.index, dtype=bool)).sum())
            international_inter = int(dedup.get("has_international_inter_region_candidate", pd.Series(index=dedup.index, dtype=bool)).sum())
            intra_region = int(dedup.get("has_intra_region_candidate", pd.Series(index=dedup.index, dtype=bool)).sum())
            unique_probes = int(dedup.get("probe_id", pd.Series(dtype=object)).astype(str).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique())
            unique_probe_asns = int(dedup.get("probe_asn_norm", pd.Series(dtype=object)).replace("NA", np.nan).dropna().nunique())
            unique_target_ips = int(dedup.get("target_ip", pd.Series(dtype=object)).astype(str).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique())
            unique_target_asns = int(dedup.get("target_asn_norm", pd.Series(dtype=object)).replace("NA", np.nan).dropna().nunique())
            sufficiency = evaluate_paper_observation_sufficiency(
                total_observations=total_valid,
                unique_probes=unique_probes,
                unique_probe_asns=unique_probe_asns,
            )
            rows.append({
                "probe_country": probe_country,
                "service_id": service_id,
                "service_class": dominant_non_missing_value(dedup.get("service_class", pd.Series(dtype=object))),
                "deployment_type": dominant_non_missing_value(dedup.get("deployment_type", pd.Series(dtype=object))),
                "path_scope_stratum": path_scope_stratum,
                "total_valid_traces": total_valid,
                "mappable_traces": mappable,
                "traces_with_feasible_submarine_corridor_candidates": inter_region,
                "submarine_candidate_exposure_rate": float(inter_region / total_valid) if total_valid else np.nan,
                "any_candidate_exposure_rate": float(any_candidate / total_valid) if total_valid else np.nan,
                "inter_region_candidate_exposure_rate": float(inter_region / total_valid) if total_valid else np.nan,
                "domestic_inter_region_candidate_exposure_rate": float(domestic_inter / total_valid) if total_valid else np.nan,
                "international_inter_region_candidate_exposure_rate": float(international_inter / total_valid) if total_valid else np.nan,
                "intra_region_candidate_rate": float(intra_region / total_valid) if total_valid else np.nan,
                # Deprecated compatibility aliases.
                "submarine_exposed_traces": inter_region,
                "service_physical_exposure_rate": float(inter_region / total_valid) if total_valid else np.nan,
                "mappable_trace_rate": float(mappable / total_valid) if total_valid else np.nan,
                "unique_probes": unique_probes,
                "unique_probe_asns": unique_probe_asns,
                "unique_target_ips": unique_target_ips,
                "unique_target_asns": unique_target_asns,
                "service_entry_resolution_rate": float(dedup["service_entry_resolved"].sum() / total_valid) if total_valid else np.nan,
                "sufficient_trace_observation": sufficiency["sufficient_trace_observation"],
                "auditable_paper_case": sufficiency["auditable_paper_case"],
                "observation_sufficiency_reason": sufficiency["observation_sufficiency_reason"],
                "failed_thresholds": sufficiency["failed_thresholds"],
            })
    return pd.DataFrame(rows, columns=columns).sort_values(["probe_country", "service_id"]).reset_index(drop=True)


def build_country_physical_exposure_summary(trace_frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate probe-country physical exposure directly from trace-level observations."""
    columns = [
        "probe_country",
        "total_valid_traces",
        "mappable_traces",
        "submarine_exposed_traces",
        "service_physical_exposure_rate",
        "mappable_trace_rate",
        "unique_services",
        "unique_probes",
        "unique_probe_asns",
        "unique_target_ips",
        "unique_target_asns",
    ]
    if trace_frame.empty:
        return pd.DataFrame(columns=columns)
    rows: List[Dict[str, Any]] = []
    for probe_country, group in trace_frame.groupby("probe_country", dropna=False):
        dedup = group.drop_duplicates(subset=["trace_id"]).copy()
        total_valid = int(len(dedup))
        mappable = int(dedup["has_at_least_one_mappable_segment"].sum())
        exposed = int(dedup["has_at_least_one_feasible_submarine_corridor"].sum())
        rows.append(
            {
                "probe_country": probe_country,
                "total_valid_traces": total_valid,
                "mappable_traces": mappable,
                "submarine_exposed_traces": exposed,
                "service_physical_exposure_rate": float(exposed / total_valid) if total_valid else np.nan,
                "mappable_trace_rate": float(mappable / total_valid) if total_valid else np.nan,
                "unique_services": int(dedup.get("service_id", pd.Series(dtype=object)).astype(str).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique()),
                "unique_probes": int(dedup.get("probe_id", pd.Series(dtype=object)).astype(str).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique()),
                "unique_probe_asns": int(dedup.get("probe_asn_norm", pd.Series(dtype=object)).replace("NA", np.nan).dropna().nunique()),
                "unique_target_ips": int(dedup.get("target_ip", pd.Series(dtype=object)).astype(str).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique()),
                "unique_target_asns": int(dedup.get("target_asn_norm", pd.Series(dtype=object)).replace("NA", np.nan).dropna().nunique()),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("probe_country").reset_index(drop=True)


def build_framework_alignment_report(
    trace_frame: pd.DataFrame,
    prepared_segments: pd.DataFrame,
    service_country_cross_layer: pd.DataFrame,
    method_manifest: Dict[str, Any],
    stage1_stats: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Report trace, atomic-segment, and candidate-row populations without mixing denominators."""
    stage1_stats = stage1_stats or {}
    trace_dedup = trace_frame.drop_duplicates(subset=["trace_id"]).copy() if not trace_frame.empty and "trace_id" in trace_frame else trace_frame.copy()
    trace_count = int(len(trace_dedup))
    stage1_atomic_total = int(stage1_stats.get("atomic_segments_total", 0) or 0)
    stage1_atomic_valid_rtt = int(stage1_stats.get("atomic_segments_with_valid_rtt_evidence", 0) or 0)
    stage1_atomic_inconclusive_rtt = int(stage1_stats.get("atomic_segments_with_inconclusive_rtt", 0) or 0)
    projection_segments = (
        prepared_segments.drop_duplicates(subset=["atomic_segment_id"]).copy()
        if not prepared_segments.empty and "atomic_segment_id" in prepared_segments
        else pd.DataFrame()
    )
    projection_atomic_total = int(len(projection_segments))
    def _trace_count_with(column: str) -> int:
        if trace_dedup.empty or column not in trace_dedup:
            return 0
        return int(trace_dedup[column].replace({"": np.nan, "NA": np.nan, "nan": np.nan}).dropna().shape[0])

    def _unique_count(column: str) -> int:
        if trace_dedup.empty or column not in trace_dedup:
            return 0
        return int(trace_dedup[column].replace({"": np.nan, "NA": np.nan, "nan": np.nan}).dropna().nunique())

    projection_fallback = (
        projection_segments.get("used_country_fallback_transition", pd.Series(index=projection_segments.index, dtype=bool))
        .fillna(True)
        .astype(bool)
        if not projection_segments.empty
        else pd.Series(dtype=bool)
    )
    projection_atomic_with_as = int((~projection_fallback).sum())
    projection_atomic_using_fallback = int(projection_fallback.sum())
    for subset_name, subset_value in (
        ("stage1_atomic_segments_with_valid_rtt", stage1_atomic_valid_rtt),
        ("stage1_atomic_segments_with_inconclusive_rtt", stage1_atomic_inconclusive_rtt),
    ):
        if subset_value > stage1_atomic_total:
            raise RuntimeError(f"Invalid framework accounting: {subset_name} exceeds stage1_atomic_segments_total")
    if stage1_atomic_valid_rtt + stage1_atomic_inconclusive_rtt != stage1_atomic_total:
        raise RuntimeError("Invalid framework accounting: Stage 1 RTT atomic-segment partition is incomplete")
    for subset_name, subset_value in (
        ("projection_atomic_segments_with_as_transition", projection_atomic_with_as),
        ("projection_atomic_segments_using_country_fallback", projection_atomic_using_fallback),
    ):
        if subset_value > projection_atomic_total:
            raise RuntimeError(f"Invalid framework accounting: {subset_name} exceeds projection_atomic_segments_total")
    if projection_atomic_with_as + projection_atomic_using_fallback != projection_atomic_total:
        raise RuntimeError("Invalid framework accounting: projection AS/fallback partition is incomplete")
    candidate_rows_total = int(stage1_stats.get("candidate_rows_total", 0) or 0)
    candidate_row_counts = {
        "candidate_rows_lifecycle_filtered": int(stage1_stats.get("candidate_rows_lifecycle_filtered", 0) or 0),
        "candidate_rows_rtt_infeasible": int(stage1_stats.get("candidate_rows_rtt_infeasible", 0) or 0),
        "candidate_rows_rtt_feasible": int(stage1_stats.get("candidate_rows_rtt_feasible", 0) or 0),
        "candidate_rows_rtt_inconclusive": int(stage1_stats.get("candidate_rows_rtt_inconclusive", 0) or 0),
    }
    for subset_name, subset_value in candidate_row_counts.items():
        if subset_value > candidate_rows_total:
            raise RuntimeError(f"Invalid framework accounting: {subset_name} exceeds candidate_rows_total")
    return {
        "total_traces": trace_count,
        "traces_with_probe_country": _trace_count_with("probe_country"),
        "unique_probe_countries": _unique_count("probe_country"),
        "traces_with_probe_asn": _trace_count_with("probe_asn_norm"),
        "unique_probe_asns": _unique_count("probe_asn_norm"),
        "traces_with_target_ip": _trace_count_with("target_ip"),
        "unique_target_ips": _unique_count("target_ip"),
        "traces_with_target_asn": _trace_count_with("target_asn_norm"),
        "unique_target_asns": _unique_count("target_asn_norm"),
        "traces_with_service_entry_resolved": int(trace_dedup["service_entry_resolved"].fillna(False).astype(bool).sum()) if not trace_dedup.empty and "service_entry_resolved" in trace_dedup else 0,
        "service_entry_resolution_rate": float(trace_dedup["service_entry_resolved"].fillna(False).astype(bool).mean()) if not trace_dedup.empty and "service_entry_resolved" in trace_dedup else np.nan,
        "stage1_atomic_segments_total": stage1_atomic_total,
        "stage1_atomic_segments_with_valid_rtt": stage1_atomic_valid_rtt,
        "stage1_atomic_segments_with_inconclusive_rtt": stage1_atomic_inconclusive_rtt,
        "stage1_valid_rtt_share": float(stage1_atomic_valid_rtt / stage1_atomic_total) if stage1_atomic_total else np.nan,
        "stage1_inconclusive_rtt_share": float(stage1_atomic_inconclusive_rtt / stage1_atomic_total) if stage1_atomic_total else np.nan,
        "projection_atomic_segments_total": projection_atomic_total,
        "projection_atomic_segments_with_as_transition": projection_atomic_with_as,
        "projection_atomic_segments_using_country_fallback": projection_atomic_using_fallback,
        "projection_as_transition_share": float(projection_atomic_with_as / projection_atomic_total) if projection_atomic_total else np.nan,
        "projection_country_fallback_share": float(projection_atomic_using_fallback / projection_atomic_total) if projection_atomic_total else np.nan,
        "candidate_rows_total": candidate_rows_total,
        **candidate_row_counts,
        # Deprecated compatibility aliases. These now point to explicit atomic-segment populations.
        "total_atomic_segments": stage1_atomic_total,
        "segments_with_as_transition": projection_atomic_with_as,
        "segments_using_country_fallback": projection_atomic_using_fallback,
        "country_fallback_share": float(projection_atomic_using_fallback / projection_atomic_total) if projection_atomic_total else np.nan,
        "segments_with_feasible_corridors": projection_atomic_total,
        "segments_with_valid_rtt": stage1_atomic_valid_rtt,
        "segments_with_inconclusive_rtt": stage1_atomic_inconclusive_rtt,
        "candidates_filtered_by_rtt": int(stage1_stats.get("candidate_rows_rtt_infeasible", 0) or 0),
        "candidates_filtered_by_cable_lifecycle": int(stage1_stats.get("candidate_rows_lifecycle_filtered", 0) or 0),
        "candidates_with_unknown_cable_status": int(stage1_stats.get("candidates_with_unknown_cable_status", 0) or 0),
        "landing_region_count": int(prepared_segments.get("corridor_id", pd.Series(dtype=object)).astype(str).str.split("::").explode().replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique()) if not prepared_segments.empty and "corridor_id" in prepared_segments else 0,
        "exact_landing_pair_count": int(prepared_segments.get("exact_landing_pair_id", prepared_segments.get("landing_pair", pd.Series(dtype=object))).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique()) if not prepared_segments.empty else 0,
        "landing_region_corridor_count": int(prepared_segments.get("corridor_id", pd.Series(dtype=object)).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique()) if not prepared_segments.empty and "corridor_id" in prepared_segments else 0,
        "service_country_unit_count": int(len(service_country_cross_layer)) if service_country_cross_layer is not None else 0,
        "auditable_service_country_unit_count": int(service_country_cross_layer.get("auditable_cross_layer_case", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if service_country_cross_layer is not None and not service_country_cross_layer.empty else 0,
        "paper_primary_framework": method_manifest.get("primary_outputs", []),
        "supplementary_frameworks": method_manifest.get("supplementary_views", []),
        "legacy_outputs_generated": [
            "unit_logical_diversity.csv",
            "unit_mismatch.csv",
            "unit_physical_candidate_diversity.csv",
        ],
    }


def merge_peeringdb_descriptors(
    frame: pd.DataFrame,
    peeringdb_frame: pd.DataFrame,
    country_column: str = "probe_country",
) -> pd.DataFrame:
    """Attach optional PeeringDB descriptors using the caller-specified country role."""
    if frame.empty or peeringdb_frame.empty or country_column not in frame.columns:
        return frame
    result = frame.copy()
    descriptor_columns = [column for column in peeringdb_frame.columns if column != "country"]
    join_key = "__peeringdb_join_country"
    result[join_key] = result[country_column].fillna("").astype(str).str.upper()
    merged = result.merge(
        peeringdb_frame.rename(columns={"country": join_key})[[join_key, *descriptor_columns]],
        on=join_key,
        how="left",
    )
    merged["peeringdb_join_country_field"] = country_column
    merged.drop(columns=[join_key], inplace=True)
    return merged


def build_unit_id(link_info: Dict[str, Any], unit_fields: List[str]) -> str:
    """Build a stable unit identifier from chosen link_info fields."""
    return "|".join(f"{field}={link_info.get(field, 'NA')}" for field in unit_fields)


def build_link_id(link_info: Dict[str, Any], record_index: int) -> str:
    """Build a stable link identifier used across weighted and feasible candidate views."""
    return "|".join(
        [
            str(link_info.get("trace_id", "NA")),
            str(link_info.get("msm_id", "NA")),
            str(link_info.get("probe_id", "NA")),
            str(link_info.get("timestamp", "NA")),
            str(link_info.get("hop_range", "NA")),
            str(link_info.get("src_ip", "NA")),
            str(link_info.get("dst_ip", "NA")),
        ]
    )


def build_atomic_segment_id(row: pd.Series) -> str:
    """Build a stable atomic path-transition segment identifier with deterministic hashing fallback."""
    explicit_link_id = str(row.get("link_id", "")).strip()
    if explicit_link_id and explicit_link_id.lower() != "nan":
        return explicit_link_id

    fields = [
        "trace_id",
        "msm_id",
        "probe_id",
        "timestamp",
        "hop_range",
        "src_ip",
        "dst_ip",
        "src_country",
        "dst_country",
        "src_asn",
        "dst_asn",
        "rtt_delta_ms",
    ]
    payload = "|".join(f"{field}={row.get(field, 'NA')}" for field in fields)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"hashed_atomic_segment::{digest}"


def build_atomic_segment_id_diagnostics(frame: pd.DataFrame) -> Dict[str, Any]:
    """Describe how atomic segment identifiers were constructed for the current dataset."""
    preferred_fields = [
        "link_id",
        "file_name",
        "msm_id",
        "probe_id",
        "timestamp",
        "hop_range",
        "src_ip",
        "dst_ip",
        "src_country",
        "dst_country",
        "src_asn",
        "dst_asn",
        "rtt_delta_ms",
    ]
    available_fields = [field for field in preferred_fields if field in frame.columns]
    link_id_present = (
        "link_id" in frame.columns
        and frame["link_id"].fillna("").astype(str).str.strip().ne("").any()
    )
    missing_link_id_rows = 0
    if "link_id" in frame.columns:
        missing_link_id_rows = int(
            frame["link_id"].fillna("").astype(str).str.strip().eq("").sum()
        )
    return {
        "segment_id_strategy": "link_id_with_hashed_fallback" if link_id_present else "hashed_field_bundle",
        "preferred_fields": preferred_fields,
        "available_fields": available_fields,
        "link_id_present": bool(link_id_present),
        "rows_missing_link_id": missing_link_id_rows,
        "fallback_hash_fields": [
            field
            for field in preferred_fields
            if field != "link_id"
        ],
        "interpretation": "Atomic path-transition segments are identified from stable hop-pair metadata. Each segment remains independently mappable even when multiple segments appear within the same traceroute.",
    }


def explode_candidate_rows_from_field(
    records: List[Dict[str, Any]],
    unit_fields: List[str],
    candidate_field: str,
    fallback_field: str = "",
    warn_if_fallback: bool = False,
) -> pd.DataFrame:
    """Flatten a chosen candidate array field from the Stage 1 JSON output."""
    rows: List[Dict[str, Any]] = []
    fallback_used = False
    for record_index, record in enumerate(records):
        link_info = record.get("link_info", {})
        match_summary = record.get("match_summary", {})
        candidate_rows = record.get(candidate_field, [])
        if not candidate_rows and fallback_field:
            fallback_candidates = record.get(fallback_field, [])
            if fallback_candidates:
                candidate_rows = fallback_candidates
                fallback_used = True

        unit_id = build_unit_id(link_info, unit_fields)
        link_id = build_link_id(link_info, record_index)

        for candidate in candidate_rows:
            row = {
                "unit_id": unit_id,
                "link_id": link_id,
                "record_index": record_index,
                "trace_id": link_info.get("trace_id"),
                "probe_id": link_info.get("probe_id"),
                "probe_country": link_info.get("probe_country"),
                "probe_asn": link_info.get("probe_asn"),
                "msm_id": link_info.get("msm_id"),
                "service_id": link_info.get("service_id"),
                "service_class": link_info.get("service_class"),
                "service_role": link_info.get("service_role"),
                "deployment_type": link_info.get("deployment_type"),
                "file_name": link_info.get("file_name"),
                "timestamp": link_info.get("timestamp"),
                "source_address": link_info.get("source_address"),
                "target_ip": link_info.get("target_ip"),
                "target_asn": link_info.get("target_asn"),
                "target_hostname": link_info.get("target_hostname"),
                "service_entry_hop": link_info.get("service_entry_hop"),
                "service_entry_asn": link_info.get("service_entry_asn"),
                "service_entry_resolved": link_info.get("service_entry_resolved"),
                "path_scope": link_info.get("path_scope"),
                "transition_near_country": link_info.get("transition_near_country", link_info.get("src_country")),
                "transition_far_country": link_info.get("transition_far_country", link_info.get("dst_country")),
                "src_country": link_info.get("src_country"),
                "dst_country": link_info.get("dst_country"),
                "src_city": link_info.get("src_city"),
                "dst_city": link_info.get("dst_city"),
                "src_ip": link_info.get("src_ip"),
                "dst_ip": link_info.get("dst_ip"),
                "src_asn": link_info.get("src_asn"),
                "dst_asn": link_info.get("dst_asn"),
                "rtt_delta_ms": link_info.get("rtt_delta_ms"),
                "source_ttl": link_info.get("source_ttl"),
                "destination_ttl": link_info.get("destination_ttl"),
                "hop_gap": link_info.get("hop_gap"),
                "hidden_hop_count": link_info.get("hidden_hop_count"),
                "is_consecutive_visible_hop": link_info.get("is_consecutive_visible_hop"),
                "crosses_timeout_gap": link_info.get("crosses_timeout_gap"),
                "timeout_gap_policy": link_info.get("timeout_gap_policy"),
                "hop_reply_ip_count": link_info.get("hop_reply_ip_count"),
                "hop_selected_reply_rule": link_info.get("hop_selected_reply_rule"),
                "confidence_bucket": match_summary.get("confidence_bucket"),
                "num_candidates_above_threshold": match_summary.get("num_candidates_above_threshold"),
                "num_feasible_candidates_total": match_summary.get("num_feasible_candidates_total"),
                "num_feasible_corridors_total": match_summary.get("num_feasible_corridors_total"),
                "support_threshold_value": match_summary.get("support_threshold_value"),
                "support_threshold_used_for_legacy_all_segments": match_summary.get("support_threshold_used_for_legacy_all_segments"),
                "feasible_candidate_retention_mode": match_summary.get("feasible_candidate_retention_mode"),
                "support_sum": match_summary.get("support_sum"),
                "link_physical_projection_class": match_summary.get("link_physical_projection_class"),
                "projection_class": match_summary.get("projection_class"),
            }
            for key, value in candidate.items():
                if isinstance(value, list):
                    row[key] = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, dict):
                    row[key] = json.dumps(value, ensure_ascii=False)
                else:
                    row[key] = value
            rows.append(row)

    if warn_if_fallback and fallback_used:
        print(
            f"Warning: `{candidate_field}` was missing in part of the input JSON; "
            f"falling back to `{fallback_field}` for conservative candidate-space analysis."
        )
    return pd.DataFrame(rows)


def explode_candidate_rows(records: List[Dict[str, Any]], unit_fields: List[str]) -> pd.DataFrame:
    """Flatten the legacy support-thresholded candidate outputs into a candidate row table."""
    return explode_candidate_rows_from_field(records, unit_fields, "all_segments")


def explode_feasible_candidate_rows(records: List[Dict[str, Any]], unit_fields: List[str]) -> pd.DataFrame:
    """Flatten the infeasibility-first feasible candidate space, with legacy fallback for old JSON files."""
    return explode_candidate_rows_from_field(
        records,
        unit_fields,
        "all_feasible_segments",
        fallback_field="all_segments",
        warn_if_fallback=True,
    )


def build_traceroute_observation_id(frame: pd.DataFrame) -> pd.Series:
    """Construct a stable traceroute-level observation identifier for diagnostics and counts."""
    components = [
        frame.get("msm_id", pd.Series(index=frame.index, dtype=object)).fillna("NA").astype(str).str.strip(),
        frame.get("probe_id", pd.Series(index=frame.index, dtype=object)).fillna("NA").astype(str).str.strip(),
        frame.get("timestamp", pd.Series(index=frame.index, dtype=object)).fillna("NA").astype(str).str.strip(),
        frame.get("target_ip", pd.Series(index=frame.index, dtype=object)).fillna("NA").astype(str).str.strip(),
    ]
    return components[0] + "|" + components[1] + "|" + components[2] + "|" + components[3]


def classify_candidate_breadth_tier(num_corridors: Any) -> str:
    """Classify unique-corridor candidate breadth as a breadth descriptor, not concentration."""
    numeric = pd.to_numeric(pd.Series([num_corridors]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "unknown_candidate_breadth"
    if numeric <= 1:
        return "very_narrow_candidate_breadth"
    if numeric <= 2:
        return "narrow_candidate_breadth"
    if numeric <= 4:
        return "moderate_candidate_breadth"
    return "broad_candidate_breadth"


def classify_corridor_observation_concentration_tier(
    top1_share: Any,
    top2_share: Any,
    top3_share: Any,
    effective_corridor_count: Any,
) -> str:
    """Classify corridor observation concentration using observation-mass concentration tiers."""
    top1 = pd.to_numeric(pd.Series([top1_share]), errors="coerce").iloc[0]
    top2 = pd.to_numeric(pd.Series([top2_share]), errors="coerce").iloc[0]
    top3 = pd.to_numeric(pd.Series([top3_share]), errors="coerce").iloc[0]
    effective = pd.to_numeric(pd.Series([effective_corridor_count]), errors="coerce").iloc[0]
    if pd.isna(top1) or pd.isna(top2) or pd.isna(top3) or pd.isna(effective):
        return "unknown_corridor_observation_concentration"
    if top1 >= 0.80 or effective <= 1.5:
        return "severe_corridor_observation_concentration"
    if top2 >= 0.80 or effective <= 2.5:
        return "moderate_corridor_observation_concentration"
    if top3 >= 0.80 or effective <= 4.0:
        return "weak_corridor_observation_concentration"
    return "broad_corridor_observation_distribution"


def classify_network_transition_concentration_tier(
    top1_share: Any,
    top2_share: Any,
    top3_share: Any,
    effective_transition_count: Any,
) -> str:
    """Classify network transition concentration over the same atomic segment population."""
    top1 = pd.to_numeric(pd.Series([top1_share]), errors="coerce").iloc[0]
    top2 = pd.to_numeric(pd.Series([top2_share]), errors="coerce").iloc[0]
    top3 = pd.to_numeric(pd.Series([top3_share]), errors="coerce").iloc[0]
    effective = pd.to_numeric(pd.Series([effective_transition_count]), errors="coerce").iloc[0]
    if pd.isna(top1) or pd.isna(top2) or pd.isna(top3) or pd.isna(effective):
        return "unknown_network_transition_concentration"
    if top1 >= 0.80 or effective <= 1.5:
        return "severe_network_transition_concentration"
    if top2 >= 0.80 or effective <= 2.5:
        return "moderate_network_transition_concentration"
    if top3 >= 0.80 or effective <= 4.0:
        return "weak_network_transition_concentration"
    return "broad_network_transition_distribution"


def prepare_atomic_segment_projection_frame(
    feasible_frame: pd.DataFrame,
    corridor_col: str = "corridor_id",
) -> pd.DataFrame:
    """Prepare row-level feasible candidates for atomic segment and corridor observation auditing."""
    if feasible_frame.empty:
        return pd.DataFrame()

    working = ensure_corridor_columns(attach_service_id(feasible_frame.copy()))
    working["transition_near_country"] = (
        working.get("transition_near_country", working.get("src_country", pd.Series(index=working.index, dtype=object)))
        .fillna("NA")
        .astype(str)
        .str.strip()
    )
    working["transition_far_country"] = (
        working.get("transition_far_country", working.get("dst_country", pd.Series(index=working.index, dtype=object)))
        .fillna("NA")
        .astype(str)
        .str.strip()
    )
    working["probe_country"] = (
        working.get("probe_country", pd.Series(index=working.index, dtype=object))
        .fillna("NA")
        .astype(str)
        .str.strip()
    )
    working["probe_asn_norm"] = working.get("probe_asn", pd.Series(index=working.index, dtype=object)).apply(
        lambda value: normalize_token(value, prefix="AS")
    )
    working["country"] = working["transition_near_country"]
    working["src_country"] = working["transition_near_country"]
    working["dst_country"] = working["transition_far_country"]
    working["service_id"] = working.get("service_id", pd.Series(index=working.index, dtype=object)).fillna("NA").astype(str).str.strip()
    for metadata_column in ["service_class", "deployment_type", "target_ip", "target_asn"]:
        if metadata_column not in working.columns:
            working[metadata_column] = "NA"
        working[metadata_column] = working[metadata_column].fillna("NA").astype(str).str.strip()
    working["msm_id"] = working.get("msm_id", pd.Series(index=working.index, dtype=object)).fillna("NA")
    working["file_name"] = working.get("file_name", pd.Series(index=working.index, dtype=object)).fillna("NA").astype(str).str.strip()
    working["probe_id"] = working.get("probe_id", pd.Series(index=working.index, dtype=object)).fillna("NA")
    working["timestamp"] = working.get("timestamp", pd.Series(index=working.index, dtype=object)).fillna("NA")
    working["service_entry_resolved"] = (
        working.get("service_entry_resolved", pd.Series(False, index=working.index))
        .fillna(False)
        .astype(bool)
    )
    if "path_scope_stratum" not in working.columns:
        working["path_scope_stratum"] = "all_publicly_visible"
    working["path_scope_stratum"] = working["path_scope_stratum"].fillna("all_publicly_visible").astype(str)
    working["src_asn_norm"] = working.get("src_asn", pd.Series(index=working.index, dtype=object)).apply(
        lambda value: normalize_token(value, prefix="AS")
    )
    working["dst_asn_norm"] = working.get("dst_asn", pd.Series(index=working.index, dtype=object)).apply(
        lambda value: normalize_token(value, prefix="AS")
    )
    explicit_link_ids = working.get("link_id", pd.Series(index=working.index, dtype=object)).fillna("").astype(str).str.strip()
    working["atomic_segment_id"] = explicit_link_ids
    missing_segment_mask = working["atomic_segment_id"].eq("") | working["atomic_segment_id"].str.lower().eq("nan")
    if missing_segment_mask.any():
        working.loc[missing_segment_mask, "atomic_segment_id"] = working.loc[missing_segment_mask].apply(
            build_atomic_segment_id,
            axis=1,
        )
    working["traceroute_observation_id"] = build_traceroute_observation_id(working)
    corridor_series = working.get(corridor_col, pd.Series(index=working.index, dtype=object))
    if corridor_col != "corridor_id_fallback":
        corridor_series = corridor_series.where(
            corridor_series.notna() & corridor_series.astype(str).str.strip().ne(""),
            working.get("corridor_id_fallback", pd.Series(index=working.index, dtype=object)),
        )
    working["corridor_observation_id"] = corridor_series.fillna("").astype(str).str.strip()
    working = working[
        working["corridor_observation_id"].ne("")
        & working["corridor_observation_id"].str.lower().ne("nan")
    ].copy()
    if "exact_landing_pair_label" not in working.columns:
        working["exact_landing_pair_label"] = (
            working.get("landing_pair", pd.Series(index=working.index, dtype=object))
            .fillna("")
            .astype(str)
            .str.strip()
        )
    entry_label = working.get("landing_region_entry_label", pd.Series(index=working.index, dtype=object)).fillna("").astype(str).str.strip()
    exit_label = working.get("landing_region_exit_label", pd.Series(index=working.index, dtype=object)).fillna("").astype(str).str.strip()
    region_pair_label = entry_label + " -> " + exit_label
    existing_corridor_label = (
        working.get("corridor_label", pd.Series(index=working.index, dtype=object))
        .fillna("")
        .astype(str)
        .str.strip()
    )
    working["corridor_label"] = existing_corridor_label
    missing_label_mask = working["corridor_label"].eq("") | working["corridor_label"].str.lower().eq("nan")
    region_label_mask = region_pair_label.str.strip().ne("->") & entry_label.ne("") & exit_label.ne("")
    working.loc[missing_label_mask & region_label_mask, "corridor_label"] = region_pair_label[missing_label_mask & region_label_mask]
    missing_label_mask = working["corridor_label"].eq("") | working["corridor_label"].str.lower().eq("nan")
    working.loc[missing_label_mask, "corridor_label"] = working.loc[missing_label_mask, "corridor_observation_id"]
    working["corridor_label"] = working.groupby("corridor_observation_id", dropna=False)["corridor_label"].transform(
        dominant_non_missing_value
    )
    entry_region = working.get("landing_region_entry_id", pd.Series(index=working.index, dtype=object)).fillna("").astype(str)
    exit_region = working.get("landing_region_exit_id", pd.Series(index=working.index, dtype=object)).fillna("").astype(str)
    inferred_scope = np.where(
        entry_region.ne("") & entry_region.eq(exit_region),
        "intra_landing_region",
        np.where(
            working["src_country"].astype(str).eq(working["dst_country"].astype(str)),
            "domestic_inter_region",
            "international_inter_region",
        ),
    )
    existing_scope = working.get("candidate_scope", pd.Series(index=working.index, dtype=object)).fillna("").astype(str).str.strip()
    working["candidate_scope"] = np.where(existing_scope.ne(""), existing_scope, inferred_scope)
    working["is_inter_region_candidate"] = working["candidate_scope"].ne("intra_landing_region")
    intra_label_mask = working["candidate_scope"].eq("intra_landing_region") & entry_label.ne("")
    working.loc[intra_label_mask, "corridor_label"] = entry_label[intra_label_mask] + " intra-region"
    working["is_domestic_segment"] = (
        working["src_country"].astype(str).str.strip().ne("")
        & (working["src_country"].astype(str) == working["dst_country"].astype(str))
    )
    has_both_asns = (
        working["src_asn_norm"].astype(str).ne("NA")
        & working["dst_asn_norm"].astype(str).ne("NA")
    )
    working["network_transition_key"] = np.where(
        has_both_asns,
        working["src_asn_norm"].astype(str) + "->" + working["dst_asn_norm"].astype(str),
        "COUNTRY_FALLBACK:" + working["src_country"].astype(str) + "->" + working["dst_country"].astype(str),
    )
    working["used_country_fallback_transition"] = ~has_both_asns
    return working


def build_service_path_scope_projections(prepared: pd.DataFrame) -> pd.DataFrame:
    """Return explicit all-visible and resolved-entry-only strata from one projection population."""
    if prepared.empty:
        result = prepared.copy()
        result["path_scope_stratum"] = pd.Series(dtype=object)
        return result
    parts: List[pd.DataFrame] = []
    all_visible = prepared.copy()
    all_visible["path_scope_stratum"] = "all_publicly_visible"
    parts.append(all_visible)
    resolved = prepared.loc[
        prepared.get("service_entry_resolved", pd.Series(False, index=prepared.index))
        .fillna(False)
        .astype(bool)
    ].copy()
    resolved["path_scope_stratum"] = "resolved_entry_only"
    parts.append(resolved)
    return pd.concat(parts, ignore_index=True, sort=False)


def build_segment_corridor_mass_frame(
    feasible_frame: pd.DataFrame,
    corridor_col: str = "corridor_id",
    mass_mode: str = "uniform",
    include_intra_landing_region: bool = False,
) -> pd.DataFrame:
    """Project atomic segments onto corridors, excluding intra-region candidates by default for paper concentration."""
    working = prepare_atomic_segment_projection_frame(feasible_frame, corridor_col)
    if not include_intra_landing_region and not working.empty:
        working = working.loc[working["candidate_scope"].ne("intra_landing_region")].copy()
    columns = [
        "country",
        "probe_country",
        "service_id",
        "service_class",
        "deployment_type",
        "msm_id",
        "file_name",
        "probe_id",
        "probe_asn_norm",
        "target_ip",
        "target_asn",
        "timestamp",
        "path_scope_stratum",
        "traceroute_observation_id",
        "atomic_segment_id",
        "corridor_id",
        "corridor_label",
        "observation_mass",
        "raw_segment_count_with_corridor_feasible",
        "domestic_segment_mass",
        "international_segment_mass",
        "network_transition_key",
        "used_country_fallback_transition",
    ]
    if working.empty:
        return pd.DataFrame(columns=columns)

    support_series = pd.to_numeric(
        working.get("fused_candidate_support", pd.Series(index=working.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    working["corridor_support_value"] = support_series.clip(lower=0.0)

    rows: List[Dict[str, Any]] = []
    for atomic_segment_id, segment_group in working.groupby("atomic_segment_id", dropna=False):
        corridor_rows = (
            segment_group.groupby("corridor_observation_id", dropna=False)
            .agg(
                corridor_label=("corridor_label", dominant_non_missing_value),
                corridor_support_value=("corridor_support_value", "sum"),
                country=("country", dominant_non_missing_value),
                probe_country=("probe_country", dominant_non_missing_value),
                service_id=("service_id", dominant_non_missing_value),
                service_class=("service_class", dominant_non_missing_value),
                deployment_type=("deployment_type", dominant_non_missing_value),
                msm_id=("msm_id", lambda series: summarize_identifier_value(series, default="NA")),
                file_name=("file_name", lambda series: summarize_identifier_value(series, default="NA")),
                probe_id=("probe_id", lambda series: summarize_identifier_value(series, default="NA")),
                probe_asn_norm=("probe_asn_norm", dominant_non_missing_value),
                target_ip=("target_ip", dominant_non_missing_value),
                target_asn=("target_asn", dominant_non_missing_value),
                timestamp=("timestamp", lambda series: summarize_identifier_value(series, default="NA")),
                path_scope_stratum=("path_scope_stratum", dominant_non_missing_value),
                traceroute_observation_id=("traceroute_observation_id", dominant_non_missing_value),
                network_transition_key=("network_transition_key", dominant_non_missing_value),
                used_country_fallback_transition=("used_country_fallback_transition", "max"),
                is_domestic_segment=("is_domestic_segment", "max"),
            )
            .reset_index()
            .rename(columns={"corridor_observation_id": "corridor_id"})
        )
        corridor_count = int(len(corridor_rows))
        if corridor_count <= 0:
            continue

        if mass_mode == "support_weighted":
            total_support = float(pd.to_numeric(corridor_rows["corridor_support_value"], errors="coerce").fillna(0.0).sum())
            if total_support > 0:
                corridor_rows["observation_mass"] = corridor_rows["corridor_support_value"] / total_support
            else:
                corridor_rows["observation_mass"] = 1.0 / corridor_count
        else:
            corridor_rows["observation_mass"] = 1.0 / corridor_count

        corridor_rows["raw_segment_count_with_corridor_feasible"] = 1
        corridor_rows["domestic_segment_mass"] = np.where(
            corridor_rows["is_domestic_segment"].fillna(False).astype(bool),
            corridor_rows["observation_mass"],
            0.0,
        )
        corridor_rows["international_segment_mass"] = np.where(
            corridor_rows["is_domestic_segment"].fillna(False).astype(bool),
            0.0,
            corridor_rows["observation_mass"],
        )
        corridor_rows["atomic_segment_id"] = atomic_segment_id
        rows.extend(corridor_rows[columns].to_dict("records"))

    return pd.DataFrame(rows, columns=columns)


def rank_within_group(frame: pd.DataFrame, group_fields: Sequence[str], value_col: str, out_col: str) -> pd.DataFrame:
    """Attach dense descending ranks within each group."""
    result = frame.copy()
    result[out_col] = (
        result.groupby(list(group_fields), dropna=False)[value_col]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    return result


def build_corridor_observation_distribution(
    feasible_frame: pd.DataFrame,
    group_fields: Sequence[str],
    corridor_col: str = "corridor_id",
    mass_mode: str = "uniform",
    include_intra_landing_region: bool = False,
) -> pd.DataFrame:
    """Aggregate atomic segments into a corridor observation-mass distribution with corridor deduplication."""
    segment_corridor_mass = build_segment_corridor_mass_frame(
        feasible_frame,
        corridor_col=corridor_col,
        mass_mode=mass_mode,
        include_intra_landing_region=include_intra_landing_region,
    )
    return summarize_corridor_observation_distribution(segment_corridor_mass, group_fields)


def summarize_corridor_observation_distribution(
    segment_corridor_mass: pd.DataFrame,
    group_fields: Sequence[str],
) -> pd.DataFrame:
    """Aggregate a prepared atomic-segment corridor mass table into grouped corridor observation distributions."""
    distribution_columns = [
        *group_fields,
        "msm_id",
        "file_name",
        "corridor_id",
        "corridor_label",
        "observation_mass",
        "raw_segment_count_with_corridor_feasible",
        "unique_atomic_segments",
        "unique_traceroutes",
        "unique_probes",
        "unique_probe_asns",
        "group_unique_probes",
        "group_unique_probe_asns",
        "share_of_observation_mass",
        "rank_within_group",
        "is_top1_corridor",
        "is_top2_corridor",
        "is_top3_corridor",
        "domestic_segment_mass",
        "international_segment_mass",
    ]
    if segment_corridor_mass.empty:
        return pd.DataFrame(columns=distribution_columns)

    aggregated = (
        segment_corridor_mass.groupby([*group_fields, "corridor_id"], dropna=False)
        .agg(
            corridor_label=("corridor_label", dominant_non_missing_value),
            msm_id=("msm_id", lambda series: summarize_identifier_value(series, default="NA")),
            file_name=("file_name", lambda series: summarize_identifier_value(series, default="NA")),
            observation_mass=("observation_mass", "sum"),
            raw_segment_count_with_corridor_feasible=("raw_segment_count_with_corridor_feasible", "sum"),
            unique_atomic_segments=("atomic_segment_id", pd.Series.nunique),
            unique_traceroutes=("traceroute_observation_id", pd.Series.nunique),
            unique_probes=("probe_id", pd.Series.nunique),
            unique_probe_asns=("probe_asn_norm", lambda series: series.replace("NA", np.nan).dropna().nunique()),
            domestic_segment_mass=("domestic_segment_mass", "sum"),
            international_segment_mass=("international_segment_mass", "sum"),
        )
        .reset_index()
    )
    group_probe_counts = (
        segment_corridor_mass.groupby(list(group_fields), dropna=False)
        .agg(
            group_unique_probes=(
                "probe_id",
                lambda series: series.astype(str).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique(),
            ),
            group_unique_probe_asns=(
                "probe_asn_norm",
                lambda series: series.astype(str).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique(),
            ),
        )
        .reset_index()
    )
    aggregated = aggregated.merge(group_probe_counts, on=list(group_fields), how="left", validate="many_to_one")
    total_mass = aggregated.groupby(list(group_fields), dropna=False)["observation_mass"].transform("sum")
    aggregated["share_of_observation_mass"] = np.where(total_mass > 0, aggregated["observation_mass"] / total_mass, np.nan)
    aggregated = rank_within_group(aggregated, group_fields, "observation_mass", "rank_within_group")
    aggregated["is_top1_corridor"] = aggregated["rank_within_group"] == 1
    aggregated["is_top2_corridor"] = aggregated["rank_within_group"] == 2
    aggregated["is_top3_corridor"] = aggregated["rank_within_group"] == 3
    return aggregated[distribution_columns].sort_values([*group_fields, "rank_within_group", "corridor_id"]).reset_index(drop=True)


def compute_topk_share(shares: Sequence[float], top_k: int) -> float:
    """Compute cumulative share of the top-k items from a share distribution."""
    if top_k <= 0 or not shares:
        return 0.0
    return float(sum(sorted([float(value) for value in shares if pd.notna(value)], reverse=True)[:top_k]))


def compute_effective_count_from_shares(shares: Sequence[float]) -> float:
    """Compute the effective number of observed categories from a share distribution."""
    valid = [float(value) for value in shares if pd.notna(value) and float(value) > 0]
    if not valid:
        return float("nan")
    return float(math.exp(shannon_entropy(valid)))


def evaluate_paper_observation_sufficiency(
    *,
    total_observations: Any,
    unique_probes: Any,
    unique_probe_asns: Any,
    country_fallback_share: Any = None,
    require_country_fallback: bool = False,
) -> Dict[str, Any]:
    """Evaluate paper-primary observation thresholds from the shared CLI configuration."""
    total = pd.to_numeric(pd.Series([total_observations]), errors="coerce").iloc[0]
    probes = pd.to_numeric(pd.Series([unique_probes]), errors="coerce").iloc[0]
    asns = pd.to_numeric(pd.Series([unique_probe_asns]), errors="coerce").iloc[0]
    fallback = pd.to_numeric(pd.Series([country_fallback_share]), errors="coerce").iloc[0] if require_country_fallback else np.nan
    total = 0 if pd.isna(total) else float(total)
    probes = 0 if pd.isna(probes) else float(probes)
    asns = 0 if pd.isna(asns) else float(asns)
    failed: List[str] = []
    if total < MINIMUM_MAPPABLE_SEGMENTS:
        failed.append("minimum_mappable_segments")
    if probes < MINIMUM_UNIQUE_PROBES:
        failed.append("minimum_unique_probes")
    if asns < MINIMUM_UNIQUE_PROBE_ASNS:
        failed.append("minimum_unique_probe_asns")
    if require_country_fallback:
        if pd.isna(fallback) or float(fallback) > MAXIMUM_COUNTRY_FALLBACK_SHARE:
            failed.append("maximum_country_fallback_share")
    return {
        "sufficient_trace_observation": bool(total >= MINIMUM_MAPPABLE_SEGMENTS and probes >= MINIMUM_UNIQUE_PROBES and asns >= MINIMUM_UNIQUE_PROBE_ASNS),
        "sufficient_corridor_observation": bool(total >= MINIMUM_MAPPABLE_SEGMENTS and probes >= MINIMUM_UNIQUE_PROBES and asns >= MINIMUM_UNIQUE_PROBE_ASNS),
        "sufficient_network_transition_resolution": bool(
            not require_country_fallback or (not pd.isna(fallback) and float(fallback) <= MAXIMUM_COUNTRY_FALLBACK_SHARE)
        ),
        "auditable_paper_case": not failed,
        "observation_sufficiency_reason": "auditable" if not failed else "insufficient_" + ",".join(failed),
        "failed_thresholds": ",".join(failed),
    }


def filter_auditable_paper_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return only explicitly auditable rows for every paper-facing CSV."""
    result = frame.copy()
    if "auditable_paper_case" not in result.columns:
        result["auditable_paper_case"] = False
    return result.loc[result["auditable_paper_case"].fillna(False).astype(bool)].reset_index(drop=True)


def apply_cross_layer_audit_eligibility(
    frame: pd.DataFrame,
    cross_layer_audit: pd.DataFrame,
    group_fields: Sequence[str],
) -> pd.DataFrame:
    """Apply the shared segment/probe/ASN/fallback audit decision to a paper-source summary."""
    if frame.empty or cross_layer_audit.empty:
        return frame.copy()
    audit_columns = [
        "country_fallback_share",
        "sufficient_network_transition_resolution",
        "auditable_paper_case",
        "observation_sufficiency_reason",
        "failed_thresholds",
    ]
    available = [column for column in audit_columns if column in cross_layer_audit.columns]
    audit_frame = cross_layer_audit[[*group_fields, *available]].drop_duplicates(subset=list(group_fields))
    result = frame.drop(columns=[column for column in available if column in frame.columns]).merge(
        audit_frame,
        on=list(group_fields),
        how="left",
    )
    if "auditable_paper_case" in result.columns:
        result["auditable_paper_case"] = result["auditable_paper_case"].fillna(False).astype(bool)
    return result


def ensure_service_path_scope_summary_rows(
    frame: pd.DataFrame,
    exposure_frame: pd.DataFrame,
    summary_kind: str,
) -> pd.DataFrame:
    """Retain every service-country path-scope stratum, including zero-projection strata."""
    keys = ["probe_country", "service_id", "path_scope_stratum"]
    if exposure_frame.empty or any(column not in exposure_frame.columns for column in keys):
        return frame.copy()
    base = exposure_frame[keys].drop_duplicates().copy()
    result = base.merge(frame, on=keys, how="left")
    missing_projection = result.get("total_mappable_segments", pd.Series(index=result.index, dtype=float)).isna()
    defaults: Dict[str, Any] = {
        "total_mappable_segments": 0,
        "unique_probes": 0,
        "unique_probe_asns": 0,
        "auditable_paper_case": False,
        "observation_sufficiency_reason": "insufficient_no_inter_region_projection_segments",
        "failed_thresholds": "minimum_mappable_segments,minimum_unique_probes,minimum_unique_probe_asns,maximum_country_fallback_share",
    }
    if summary_kind == "corridor":
        defaults.update(
            {
                "total_observation_mass": 0.0,
                "unique_corridors_observed": 0,
                "corridor_concentration_tier": "unknown_corridor_observation_concentration",
                "is_corridor_concentrated": False,
                "auditable_corridor_concentration": False,
                "sufficient_corridor_observation": False,
                "sufficient_network_transition_resolution": False,
            }
        )
    elif summary_kind == "network":
        defaults.update(
            {
                "unique_network_transitions_observed": 0,
                "network_transition_concentration_tier": "unknown_network_transition_concentration",
                "country_fallback_share": np.nan,
                "sufficient_network_transition_resolution": False,
            }
        )
    elif summary_kind == "cross_layer":
        defaults.update(
            {
                "cross_layer_distribution_class": "unknown_cross_layer_distribution_class",
                "auditable_cross_layer_case": False,
                "sufficient_trace_observation": False,
                "sufficient_corridor_observation": False,
                "sufficient_network_transition_resolution": False,
            }
        )
    for column, default in defaults.items():
        if column not in result.columns:
            result[column] = pd.Series(
                index=result.index,
                dtype=object if isinstance(default, (str, bool)) else float,
            )
        elif isinstance(default, (str, bool)):
            result[column] = result[column].astype(object)
        result.loc[missing_projection, column] = default
    return result.sort_values(keys).reset_index(drop=True)


def sufficient_observation_for_corridor_concentration(
    total_mappable_segments: Any,
    unique_probes: Any,
    unique_probe_asns: Any,
) -> bool:
    """Decide whether observed segment volume is sufficient for an auditable concentration reading."""
    return bool(
        evaluate_paper_observation_sufficiency(
            total_observations=total_mappable_segments,
            unique_probes=unique_probes,
            unique_probe_asns=unique_probe_asns,
        )["auditable_paper_case"]
    )


def build_corridor_concentration_summary(
    distribution_frame: pd.DataFrame,
    group_fields: Sequence[str],
) -> pd.DataFrame:
    """Summarize corridor observation concentration from the observation-mass distribution."""
    columns = [
        *group_fields,
        "msm_id",
        "file_name",
        "total_mappable_segments",
        "total_observation_mass",
        "unique_corridors_observed",
        "top1_corridor_id",
        "top1_corridor_share",
        "top2_corridor_share",
        "top3_corridor_share",
        "effective_corridor_count",
        "corridor_concentration_tier",
        "is_corridor_concentrated",
        "auditable_corridor_concentration",
        "sufficient_corridor_observation",
        "auditable_paper_case",
        "observation_sufficiency_reason",
        "failed_thresholds",
        "unique_probes",
        "unique_probe_asns",
        "unique_measurements_or_targets",
        "domestic_segment_share",
        "international_segment_share",
    ]
    if distribution_frame.empty:
        return pd.DataFrame(columns=columns)

    rows: List[Dict[str, Any]] = []
    for group_key, group in distribution_frame.groupby(list(group_fields), dropna=False):
        row = group_key_to_dict(group_fields, group_key)
        shares = pd.to_numeric(group["share_of_observation_mass"], errors="coerce").fillna(0.0).tolist()
        top_row = group.sort_values("observation_mass", ascending=False).iloc[0]
        top1_share = float(top_row["share_of_observation_mass"]) if pd.notna(top_row["share_of_observation_mass"]) else float("nan")
        top2_share = compute_topk_share(shares, 2)
        top3_share = compute_topk_share(shares, 3)
        effective_corridor_count = compute_effective_count_from_shares(shares)
        concentration_tier = classify_corridor_observation_concentration_tier(
            top1_share,
            top2_share,
            top3_share,
            effective_corridor_count,
        )
        is_concentrated = concentration_tier in {
            "severe_corridor_observation_concentration",
            "moderate_corridor_observation_concentration",
            "weak_corridor_observation_concentration",
        }
        total_mass = float(pd.to_numeric(group["observation_mass"], errors="coerce").sum())
        domestic_mass = float(pd.to_numeric(group["domestic_segment_mass"], errors="coerce").sum())
        international_mass = float(pd.to_numeric(group["international_segment_mass"], errors="coerce").sum())
        group_probe_values = pd.to_numeric(group["group_unique_probes"], errors="coerce").dropna().unique()
        group_probe_asn_values = pd.to_numeric(group["group_unique_probe_asns"], errors="coerce").dropna().unique()
        if len(group_probe_values) != 1 or len(group_probe_asn_values) != 1:
            raise RuntimeError(
                "Corridor concentration requires one group-level probe union count per analysis group."
            )
        unique_probes = int(group_probe_values[0])
        unique_probe_asns = int(group_probe_asn_values[0])
        total_segments = int(round(total_mass)) if pd.notna(total_mass) else 0
        sufficiency = evaluate_paper_observation_sufficiency(
            total_observations=total_segments,
            unique_probes=unique_probes,
            unique_probe_asns=unique_probe_asns,
        )
        rows.append(
            {
                **row,
                "msm_id": summarize_identifier_value(group.get("msm_id", pd.Series(dtype=object)), default="NA"),
                "file_name": summarize_identifier_value(group.get("file_name", pd.Series(dtype=object)), default="NA"),
                "total_mappable_segments": total_segments,
                "total_observation_mass": total_mass,
                "unique_corridors_observed": int(group["corridor_id"].astype(str).replace("nan", np.nan).dropna().nunique()),
                "top1_corridor_id": str(top_row["corridor_id"]),
                "top1_corridor_share": top1_share,
                "top2_corridor_share": top2_share,
                "top3_corridor_share": top3_share,
                "effective_corridor_count": effective_corridor_count,
                "corridor_concentration_tier": concentration_tier,
                "is_corridor_concentrated": is_concentrated,
                "auditable_corridor_concentration": is_concentrated and sufficiency["auditable_paper_case"],
                "sufficient_corridor_observation": sufficiency["sufficient_corridor_observation"],
                "auditable_paper_case": sufficiency["auditable_paper_case"],
                "observation_sufficiency_reason": sufficiency["observation_sufficiency_reason"],
                "failed_thresholds": sufficiency["failed_thresholds"],
                "unique_probes": unique_probes,
                "unique_probe_asns": unique_probe_asns,
                "unique_measurements_or_targets": int(group.get("msm_id", pd.Series(dtype=object)).astype(str).replace({"": np.nan, "nan": np.nan, "NA": np.nan}).dropna().nunique()),
                "domestic_segment_share": float(domestic_mass / total_mass) if total_mass > 0 else np.nan,
                "international_segment_share": float(international_mass / total_mass) if total_mass > 0 else np.nan,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(list(group_fields)).reset_index(drop=True)


def build_network_transition_concentration_summary(
    feasible_frame: pd.DataFrame,
    group_fields: Sequence[str],
    corridor_col: str = "corridor_id",
) -> pd.DataFrame:
    """Summarize network transition concentration over the same atomic segment population."""
    prepared = prepare_atomic_segment_projection_frame(feasible_frame, corridor_col)
    return summarize_network_transition_concentration(prepared, group_fields)


def build_network_transition_distribution(
    prepared: pd.DataFrame,
    group_fields: Sequence[str],
) -> pd.DataFrame:
    """Build q_u(t) over unique atomic segments, with explicit country fallback rows."""
    columns = [
        *group_fields,
        "msm_id",
        "file_name",
        "network_transition_key",
        "network_transition_representation",
        "network_transition_observation_count",
        "unique_atomic_segments",
        "share_of_network_transition_observations",
        "rank_within_unit",
        "is_top1_network_transition",
        "is_top2_network_transition",
        "is_top3_network_transition",
        "used_country_fallback_transition",
        "group_total_mappable_segments",
        "group_unique_probes",
        "group_unique_probe_asns",
        "domestic_segment_count",
        "international_segment_count",
    ]
    if prepared.empty:
        return pd.DataFrame(columns=columns)
    segment_identity_fields = [*group_fields, "atomic_segment_id"]
    transition_cardinality = prepared.groupby(segment_identity_fields, dropna=False)[
        "network_transition_key"
    ].nunique(dropna=False)
    if (transition_cardinality > 1).any():
        raise RuntimeError(
            "Candidate rows for one atomic segment disagree on the network transition key."
        )
    segment_level = prepared.drop_duplicates(subset=segment_identity_fields).copy()
    rows: List[Dict[str, Any]] = []
    for group_key, group in segment_level.groupby(list(group_fields), dropna=False):
        group_values = group_key_to_dict(group_fields, group_key)
        total_segments = int(group["atomic_segment_id"].nunique())
        unique_probes = _count_unique_non_missing(group, "probe_id")
        unique_probe_asns = _count_unique_non_missing(group, "probe_asn_norm")
        transition_counts = group["network_transition_key"].value_counts(dropna=False)
        for rank, (transition_key, observation_count) in enumerate(transition_counts.items(), start=1):
            transition_mask = group["network_transition_key"].eq(transition_key)
            transition_group = group.loc[transition_mask]
            fallback = bool(
                transition_group["used_country_fallback_transition"].fillna(False).astype(bool).any()
            )
            domestic_count = int(
                transition_group["is_domestic_segment"].fillna(False).astype(bool).sum()
            )
            count = int(observation_count)
            rows.append(
                {
                    **group_values,
                    "msm_id": summarize_identifier_value(
                        transition_group.get("msm_id", pd.Series(dtype=object)), default="NA"
                    ),
                    "file_name": summarize_identifier_value(
                        transition_group.get("file_name", pd.Series(dtype=object)), default="NA"
                    ),
                    "network_transition_key": str(transition_key),
                    "network_transition_representation": "country_fallback" if fallback else "as_transition",
                    "network_transition_observation_count": count,
                    "unique_atomic_segments": int(transition_group["atomic_segment_id"].nunique()),
                    "share_of_network_transition_observations": (
                        float(count / total_segments) if total_segments else np.nan
                    ),
                    "rank_within_unit": rank,
                    "is_top1_network_transition": rank == 1,
                    "is_top2_network_transition": rank == 2,
                    "is_top3_network_transition": rank == 3,
                    "used_country_fallback_transition": fallback,
                    "group_total_mappable_segments": total_segments,
                    "group_unique_probes": unique_probes,
                    "group_unique_probe_asns": unique_probe_asns,
                    "domestic_segment_count": domestic_count,
                    "international_segment_count": count - domestic_count,
                }
            )
    result = pd.DataFrame(rows, columns=columns)
    if not result.empty:
        group_share_sums = result.groupby(list(group_fields), dropna=False)[
            "share_of_network_transition_observations"
        ].sum()
        if not np.allclose(group_share_sums.to_numpy(dtype=float), 1.0, atol=1e-9):
            raise RuntimeError("Network transition shares q_u(t) must sum to one within every analysis unit.")
    return result


def summarize_network_transition_distribution(
    distribution: pd.DataFrame,
    group_fields: Sequence[str],
) -> pd.DataFrame:
    """Summarize concentration metrics from the explicit q_u(t) distribution."""
    columns = [
        *group_fields,
        "msm_id",
        "file_name",
        "total_mappable_segments",
        "unique_network_transitions_observed",
        "top1_network_transition_key",
        "top1_network_transition_share",
        "top2_network_transition_share",
        "top3_network_transition_share",
        "effective_network_transition_count",
        "network_transition_concentration_tier",
        "country_fallback_share",
        "sufficient_network_transition_resolution",
        "auditable_paper_case",
        "observation_sufficiency_reason",
        "failed_thresholds",
        "unique_probes",
        "unique_probe_asns",
        "domestic_segment_share",
        "international_segment_share",
    ]
    if distribution.empty:
        return pd.DataFrame(columns=columns)
    rows: List[Dict[str, Any]] = []
    for group_key, group in distribution.groupby(list(group_fields), dropna=False):
        row = group_key_to_dict(group_fields, group_key)
        ordered = group.sort_values("rank_within_unit")
        shares = pd.to_numeric(
            ordered["share_of_network_transition_observations"], errors="coerce"
        ).fillna(0.0).tolist()
        top1_share = float(shares[0]) if shares else float("nan")
        top2_share = compute_topk_share(shares, 2)
        top3_share = compute_topk_share(shares, 3)
        effective_count = compute_effective_count_from_shares(shares)
        total_values = pd.to_numeric(group["group_total_mappable_segments"], errors="coerce").dropna().unique()
        probe_values = pd.to_numeric(group["group_unique_probes"], errors="coerce").dropna().unique()
        probe_asn_values = pd.to_numeric(group["group_unique_probe_asns"], errors="coerce").dropna().unique()
        if len(total_values) != 1 or len(probe_values) != 1 or len(probe_asn_values) != 1:
            raise RuntimeError("Network transition distribution requires stable group-level segment/probe counts.")
        total_segments = int(total_values[0])
        unique_probes = int(probe_values[0])
        unique_probe_asns = int(probe_asn_values[0])
        counts = pd.to_numeric(group["network_transition_observation_count"], errors="coerce").fillna(0)
        fallback_count = float(
            counts.loc[group["used_country_fallback_transition"].fillna(False).astype(bool)].sum()
        )
        domestic_count = float(pd.to_numeric(group["domestic_segment_count"], errors="coerce").fillna(0).sum())
        fallback_share = float(fallback_count / total_segments) if total_segments else np.nan
        sufficiency = evaluate_paper_observation_sufficiency(
            total_observations=total_segments,
            unique_probes=unique_probes,
            unique_probe_asns=unique_probe_asns,
            country_fallback_share=fallback_share,
            require_country_fallback=True,
        )
        rows.append(
            {
                **row,
                "msm_id": summarize_identifier_value(group.get("msm_id", pd.Series(dtype=object)), default="NA"),
                "file_name": summarize_identifier_value(group.get("file_name", pd.Series(dtype=object)), default="NA"),
                "total_mappable_segments": total_segments,
                "unique_network_transitions_observed": int(len(group)),
                "top1_network_transition_key": str(ordered.iloc[0]["network_transition_key"]),
                "top1_network_transition_share": top1_share,
                "top2_network_transition_share": top2_share,
                "top3_network_transition_share": top3_share,
                "effective_network_transition_count": effective_count,
                "network_transition_concentration_tier": classify_network_transition_concentration_tier(
                    top1_share,
                    top2_share,
                    top3_share,
                    effective_count,
                ),
                "country_fallback_share": fallback_share,
                "sufficient_network_transition_resolution": sufficiency[
                    "sufficient_network_transition_resolution"
                ],
                "auditable_paper_case": sufficiency["auditable_paper_case"],
                "observation_sufficiency_reason": sufficiency["observation_sufficiency_reason"],
                "failed_thresholds": sufficiency["failed_thresholds"],
                "unique_probes": unique_probes,
                "unique_probe_asns": unique_probe_asns,
                "domestic_segment_share": float(domestic_count / total_segments) if total_segments else np.nan,
                "international_segment_share": (
                    float((total_segments - domestic_count) / total_segments) if total_segments else np.nan
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(list(group_fields)).reset_index(drop=True)


def summarize_network_transition_concentration(
    prepared: pd.DataFrame,
    group_fields: Sequence[str],
) -> pd.DataFrame:
    """Summarize network transition concentration from a prepared atomic segment projection frame."""
    distribution = build_network_transition_distribution(prepared, group_fields)
    return summarize_network_transition_distribution(distribution, group_fields)


def build_network_corridor_segment_population_alignment(
    prepared: pd.DataFrame,
    segment_corridor_mass: pd.DataFrame,
    group_fields: Sequence[str],
    analysis_scope: str,
) -> pd.DataFrame:
    """Verify that q_u and p_u use exactly the same unique atomic segment sets."""
    columns = [
        "analysis_scope",
        *group_fields,
        "network_atomic_segments",
        "corridor_atomic_segments",
        "shared_atomic_segments",
        "network_only_atomic_segments",
        "corridor_only_atomic_segments",
        "segment_population_aligned",
    ]
    network_sets: Dict[Tuple[Any, ...], set] = {}
    corridor_sets: Dict[Tuple[Any, ...], set] = {}
    if not prepared.empty:
        network_level = prepared.drop_duplicates(subset=[*group_fields, "atomic_segment_id"])
        for group_key, group in network_level.groupby(list(group_fields), dropna=False):
            key = group_key if isinstance(group_key, tuple) else (group_key,)
            network_sets[key] = set(group["atomic_segment_id"].astype(str))
    if not segment_corridor_mass.empty:
        corridor_level = segment_corridor_mass.drop_duplicates(subset=[*group_fields, "atomic_segment_id"])
        for group_key, group in corridor_level.groupby(list(group_fields), dropna=False):
            key = group_key if isinstance(group_key, tuple) else (group_key,)
            corridor_sets[key] = set(group["atomic_segment_id"].astype(str))
    rows: List[Dict[str, Any]] = []
    for key in sorted(set(network_sets) | set(corridor_sets), key=lambda value: tuple(map(str, value))):
        network_ids = network_sets.get(key, set())
        corridor_ids = corridor_sets.get(key, set())
        row = {field: value for field, value in zip(group_fields, key)}
        rows.append(
            {
                "analysis_scope": analysis_scope,
                **row,
                "network_atomic_segments": len(network_ids),
                "corridor_atomic_segments": len(corridor_ids),
                "shared_atomic_segments": len(network_ids & corridor_ids),
                "network_only_atomic_segments": len(network_ids - corridor_ids),
                "corridor_only_atomic_segments": len(corridor_ids - network_ids),
                "segment_population_aligned": network_ids == corridor_ids,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def classify_cross_layer_distribution_class(
    network_tier: str,
    corridor_tier: str,
) -> str:
    """Classify how network-transition concentration overlaps with corridor observation concentration."""
    network_broad_like = {
        "weak_network_transition_concentration",
        "broad_network_transition_distribution",
    }
    network_concentrated = {
        "severe_network_transition_concentration",
        "moderate_network_transition_concentration",
        "weak_network_transition_concentration",
    }
    physical_strong_concentration = {
        "severe_corridor_observation_concentration",
        "moderate_corridor_observation_concentration",
    }
    physical_any_concentration = {
        "severe_corridor_observation_concentration",
        "moderate_corridor_observation_concentration",
        "weak_corridor_observation_concentration",
    }
    if network_tier in network_broad_like and corridor_tier in physical_strong_concentration:
        return "network_broad_physical_concentrated"
    if network_tier in network_concentrated and corridor_tier in physical_any_concentration:
        return "network_and_physical_both_concentrated"
    if network_tier in {"severe_network_transition_concentration", "moderate_network_transition_concentration"} and corridor_tier == "broad_corridor_observation_distribution":
        return "network_concentrated_physical_broad"
    if network_tier in network_broad_like and corridor_tier in {
        "weak_corridor_observation_concentration",
        "broad_corridor_observation_distribution",
    }:
        return "network_and_physical_both_broad"
    return "unknown_cross_layer_distribution_class"


def build_cross_layer_distribution_audit(
    corridor_summary: pd.DataFrame,
    network_summary: pd.DataFrame,
    group_fields: Sequence[str],
) -> pd.DataFrame:
    """Merge network-transition and corridor observation concentration summaries into a cross-layer audit."""
    columns = [
        *group_fields,
        "msm_id",
        "file_name",
        "total_mappable_segments",
        "top1_network_transition_share",
        "top2_network_transition_share",
        "top3_network_transition_share",
        "effective_network_transition_count",
        "network_transition_concentration_tier",
        "top1_corridor_share",
        "top2_corridor_share",
        "top3_corridor_share",
        "effective_corridor_count",
        "corridor_concentration_tier",
        "cross_layer_distribution_class",
        "country_fallback_share",
        "auditable_cross_layer_case",
        "sufficient_trace_observation",
        "sufficient_corridor_observation",
        "sufficient_network_transition_resolution",
        "auditable_paper_case",
        "observation_sufficiency_reason",
        "failed_thresholds",
        "unique_probes",
        "unique_probe_asns",
        "domestic_segment_share",
        "international_segment_share",
    ]
    if corridor_summary.empty or network_summary.empty:
        return pd.DataFrame(columns=columns)

    merged = corridor_summary.merge(
        network_summary,
        on=list(group_fields),
        how="outer",
        suffixes=("_corridor", "_network"),
    )
    if merged.empty:
        return pd.DataFrame(columns=columns)

    merged["msm_id"] = merged.get("msm_id_corridor", merged.get("msm_id_network", "NA"))
    merged["file_name"] = merged.get("file_name_corridor", merged.get("file_name_network", "NA"))
    merged["total_mappable_segments"] = pd.to_numeric(
        merged.get("total_mappable_segments_corridor", merged.get("total_mappable_segments_network", np.nan)),
        errors="coerce",
    )
    missing_segment_mask = merged["total_mappable_segments"].isna()
    merged.loc[missing_segment_mask, "total_mappable_segments"] = pd.to_numeric(
        merged.loc[missing_segment_mask, "total_mappable_segments_network"],
        errors="coerce",
    )
    merged["unique_probes"] = pd.to_numeric(
        merged.get("unique_probes_corridor", merged.get("unique_probes_network", np.nan)),
        errors="coerce",
    )
    merged["unique_probe_asns"] = pd.to_numeric(
        merged.get("unique_probe_asns_corridor", merged.get("unique_probe_asns_network", np.nan)),
        errors="coerce",
    )
    merged["domestic_segment_share"] = pd.to_numeric(
        merged.get("domestic_segment_share_corridor", merged.get("domestic_segment_share_network", np.nan)),
        errors="coerce",
    )
    merged["international_segment_share"] = pd.to_numeric(
        merged.get("international_segment_share_corridor", merged.get("international_segment_share_network", np.nan)),
        errors="coerce",
    )
    merged["cross_layer_distribution_class"] = merged.apply(
        lambda row: classify_cross_layer_distribution_class(
            str(row.get("network_transition_concentration_tier", "")),
            str(row.get("corridor_concentration_tier", "")),
        ),
        axis=1,
    )
    fallback_share = pd.to_numeric(merged.get("country_fallback_share", np.nan), errors="coerce")
    total_segments = pd.to_numeric(merged["total_mappable_segments"], errors="coerce")
    unique_probes = pd.to_numeric(merged["unique_probes"], errors="coerce")
    unique_probe_asns = pd.to_numeric(merged["unique_probe_asns"], errors="coerce")
    sufficiency_rows = [
        evaluate_paper_observation_sufficiency(
            total_observations=total_segments.loc[index],
            unique_probes=unique_probes.loc[index],
            unique_probe_asns=unique_probe_asns.loc[index],
            country_fallback_share=fallback_share.loc[index] if index in fallback_share.index else np.nan,
            require_country_fallback=True,
        )
        for index in merged.index
    ]
    auditable = pd.Series([row["auditable_paper_case"] for row in sufficiency_rows], index=merged.index)
    reasons = []
    failed_thresholds = []
    for index in merged.index:
        row = sufficiency_rows[list(merged.index).index(index)]
        reasons.append(row["observation_sufficiency_reason"])
        failed_thresholds.append(row["failed_thresholds"])
    merged["auditable_cross_layer_case"] = auditable
    merged["auditable_paper_case"] = auditable
    merged["observation_sufficiency_reason"] = reasons
    merged["failed_thresholds"] = failed_thresholds
    merged["sufficient_trace_observation"] = [row["sufficient_trace_observation"] for row in sufficiency_rows]
    merged["sufficient_corridor_observation"] = [row["sufficient_corridor_observation"] for row in sufficiency_rows]
    merged["sufficient_network_transition_resolution"] = [row["sufficient_network_transition_resolution"] for row in sufficiency_rows]
    rows = pd.DataFrame(
        {
            **{field: merged[field] for field in group_fields},
            "msm_id": merged["msm_id"],
            "file_name": merged["file_name"],
            "total_mappable_segments": merged["total_mappable_segments"],
            "top1_network_transition_share": merged["top1_network_transition_share"],
            "top2_network_transition_share": merged["top2_network_transition_share"],
            "top3_network_transition_share": merged["top3_network_transition_share"],
            "effective_network_transition_count": merged["effective_network_transition_count"],
            "network_transition_concentration_tier": merged["network_transition_concentration_tier"],
            "top1_corridor_share": merged["top1_corridor_share"],
            "top2_corridor_share": merged["top2_corridor_share"],
            "top3_corridor_share": merged["top3_corridor_share"],
            "effective_corridor_count": merged["effective_corridor_count"],
            "corridor_concentration_tier": merged["corridor_concentration_tier"],
            "cross_layer_distribution_class": merged["cross_layer_distribution_class"],
            "country_fallback_share": fallback_share,
            "auditable_cross_layer_case": merged["auditable_cross_layer_case"],
            "sufficient_trace_observation": merged["sufficient_trace_observation"],
            "sufficient_corridor_observation": merged["sufficient_corridor_observation"],
            "sufficient_network_transition_resolution": merged["sufficient_network_transition_resolution"],
            "auditable_paper_case": merged["auditable_paper_case"],
            "observation_sufficiency_reason": merged["observation_sufficiency_reason"],
            "failed_thresholds": merged["failed_thresholds"],
            "unique_probes": merged["unique_probes"],
            "unique_probe_asns": merged["unique_probe_asns"],
            "domestic_segment_share": merged["domestic_segment_share"],
            "international_segment_share": merged["international_segment_share"],
        }
    )
    return rows[columns].sort_values(list(group_fields)).reset_index(drop=True)


def combine_distribution_case_frames(
    country_frame: pd.DataFrame,
    service_country_frame: pd.DataFrame,
    scope_label_country: str,
    scope_label_service_country: str,
) -> pd.DataFrame:
    """Combine country and service-country distribution tables for paper case selection."""
    frames: List[pd.DataFrame] = []
    if not country_frame.empty:
        left = country_frame.copy()
        left["paper_case_scope"] = scope_label_country
        frames.append(left)
    if not service_country_frame.empty:
        right = service_country_frame.copy()
        right["paper_case_scope"] = scope_label_service_country
        frames.append(right)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def build_paper_corridor_observation_concentration_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Select paper-primary cases with auditable severe/moderate corridor observation concentration."""
    if frame.empty:
        return frame.copy()
    filtered = frame.loc[
        frame["corridor_concentration_tier"].astype(str).isin(
            [
                "severe_corridor_observation_concentration",
                "moderate_corridor_observation_concentration",
            ]
        )
        & pd.Series(frame.get("auditable_corridor_concentration", False)).fillna(False).astype(bool)
    ].copy()
    return filtered.sort_values(
        ["top1_corridor_share", "total_mappable_segments", "unique_probes"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def build_paper_network_broad_physical_concentrated_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Select paper-primary cases where network observations stay broad while corridor observations concentrate."""
    if frame.empty:
        return frame.copy()
    filtered = frame.loc[
        (frame["cross_layer_distribution_class"].astype(str) == "network_broad_physical_concentrated")
        & pd.Series(frame.get("auditable_cross_layer_case", False)).fillna(False).astype(bool)
    ].copy()
    return filtered.sort_values(
        ["top1_corridor_share", "effective_network_transition_count", "total_mappable_segments"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def build_paper_broad_corridor_distribution_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Select counterexamples where corridor observation mass remains broad."""
    if frame.empty:
        return frame.copy()
    effective_threshold = pd.to_numeric(frame["effective_network_transition_count"], errors="coerce").quantile(0.75)
    filtered = frame.loc[
        frame["corridor_concentration_tier"].astype(str).eq("broad_corridor_observation_distribution")
        & pd.Series(frame.get("auditable_paper_case", frame.get("auditable_cross_layer_case", False))).fillna(False).astype(bool)
        & (
            frame["network_transition_concentration_tier"].astype(str).eq("broad_network_transition_distribution")
            | (pd.to_numeric(frame["effective_network_transition_count"], errors="coerce") >= effective_threshold)
        )
    ].copy()
    return filtered.sort_values(
        ["effective_corridor_count", "total_mappable_segments"],
        ascending=[False, False],
    ).reset_index(drop=True)


def build_paper_physical_exposure_cases(exposure_frame: pd.DataFrame) -> pd.DataFrame:
    """Select service-country cases with measurable trace-level physical exposure."""
    if exposure_frame.empty:
        return exposure_frame.copy()
    working = exposure_frame.copy()
    working = working.loc[
        pd.Series(working.get("auditable_paper_case", False)).fillna(False).astype(bool)
        & (pd.to_numeric(working.get("service_physical_exposure_rate", 0), errors="coerce").fillna(0) > 0)
    ].copy()
    return working.sort_values(
        ["service_physical_exposure_rate", "submarine_exposed_traces", "unique_probes"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def build_supplementary_owner_concentration(
    feasible_frame: pd.DataFrame,
    segment_corridor_mass: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate owner exposure using split ownership over corridor observation mass."""
    columns = [
        "probe_country",
        "service_id",
        "owner",
        "owner_observation_mass",
        "owner_observation_share",
        "unique_atomic_segments",
        "unique_corridors",
        "owner_multi_entity_mode",
        "interpretation",
    ]
    if feasible_frame.empty or segment_corridor_mass.empty or "cable_owners" not in feasible_frame.columns:
        return pd.DataFrame(columns=columns)

    working = prepare_atomic_segment_projection_frame(feasible_frame, corridor_col="corridor_id")
    if working.empty:
        return pd.DataFrame(columns=columns)
    working["owners_list"] = working["cable_owners"].apply(safe_parse_owners)
    mass_lookup = segment_corridor_mass[
        ["atomic_segment_id", "corridor_id", "observation_mass", "probe_country", "service_id"]
    ].drop_duplicates()
    owner_rows: List[Dict[str, Any]] = []
    for _, mass_row in mass_lookup.iterrows():
        subset = working.loc[
            (working["atomic_segment_id"].astype(str) == str(mass_row["atomic_segment_id"]))
            & (working["corridor_observation_id"].astype(str) == str(mass_row["corridor_id"]))
        ]
        raw_owner_weights: Dict[str, float] = {}
        for _, candidate in subset.drop_duplicates(subset=["cable_id"]).iterrows():
            owners = candidate.get("owners_list", [])
            if not owners:
                continue
            split = 1.0 / len(owners)
            for owner in owners:
                raw_owner_weights[owner] = raw_owner_weights.get(owner, 0.0) + split
        total_raw = sum(raw_owner_weights.values())
        if total_raw <= 0:
            continue
        for owner, raw_weight in raw_owner_weights.items():
            owner_rows.append(
                {
                    "probe_country": mass_row["probe_country"],
                    "service_id": mass_row["service_id"],
                    "owner": owner,
                    "atomic_segment_id": mass_row["atomic_segment_id"],
                    "corridor_id": mass_row["corridor_id"],
                    "owner_observation_mass": float(mass_row["observation_mass"]) * raw_weight / total_raw,
                }
            )
    if not owner_rows:
        return pd.DataFrame(columns=columns)
    owner_frame = pd.DataFrame(owner_rows)
    aggregated = (
        owner_frame.groupby(["probe_country", "service_id", "owner"], dropna=False)
        .agg(
            owner_observation_mass=("owner_observation_mass", "sum"),
            unique_atomic_segments=("atomic_segment_id", pd.Series.nunique),
            unique_corridors=("corridor_id", pd.Series.nunique),
        )
        .reset_index()
    )
    total_mass = aggregated.groupby(["probe_country", "service_id"], dropna=False)["owner_observation_mass"].transform("sum")
    aggregated["owner_observation_share"] = np.where(total_mass > 0, aggregated["owner_observation_mass"] / total_mass, np.nan)
    aggregated["owner_multi_entity_mode"] = "split"
    aggregated["interpretation"] = "supplementary owner exposure over feasible corridor observation mass, not owner probability"
    return aggregated[columns].sort_values(
        ["probe_country", "service_id", "owner_observation_mass"],
        ascending=[True, True, False],
    ).reset_index(drop=True)


def add_candidate_breadth_aliases(frame: pd.DataFrame) -> pd.DataFrame:
    """Add paper-facing candidate-breadth aliases to legacy unique-corridor breadth tables."""
    result = frame.copy()
    if result.empty:
        return result
    result["unique_corridor_candidate_breadth"] = pd.to_numeric(
        result.get("num_feasible_corridors", pd.Series(index=result.index, dtype=float)),
        errors="coerce",
    )
    result["candidate_breadth_tier"] = result["unique_corridor_candidate_breadth"].apply(classify_candidate_breadth_tier)
    result["small_candidate_breadth"] = result["unique_corridor_candidate_breadth"] <= 4
    result["candidate_breadth_interpretation"] = (
        "candidate-set breadth descriptor; not the paper-primary corridor observation concentration metric"
    )
    return result

def aggregate_candidate_support(frame: pd.DataFrame, candidate_id_col: str, support_col: str) -> pd.DataFrame:
    """Aggregate candidate support per unit."""
    aggregated = (
        frame.groupby(["unit_id", candidate_id_col], dropna=False)[support_col]
        .sum()
        .reset_index(name="aggregate_support")
    )
    aggregated["aggregate_support_share"] = aggregated.groupby("unit_id")["aggregate_support"].transform(
        lambda values: values / values.sum() if values.sum() > 0 else 0.0
    )
    return aggregated


def group_key_to_dict(group_fields: Sequence[str], group_key: Any) -> Dict[str, Any]:
    """Convert a pandas groupby key into a field-to-value dictionary."""
    if len(group_fields) == 1:
        if isinstance(group_key, tuple):
            values = group_key
        else:
            values = (group_key,)
    else:
        values = tuple(group_key)
    return {field: values[index] for index, field in enumerate(group_fields)}


def normalize_group_key_columns(frame: pd.DataFrame, group_fields: Sequence[str]) -> pd.DataFrame:
    """Normalize grouping key columns before pandas merges across sparse legacy outputs."""
    result = frame.copy()
    for field in group_fields:
        if field not in result.columns:
            result[field] = "NA"
        result[field] = result[field].astype(object).where(pd.notna(result[field]), "NA").astype(str)
        result[field] = result[field].replace(
            {
                "": "NA",
                "nan": "NA",
                "NaN": "NA",
                "None": "NA",
                "<NA>": "NA",
            }
        )
    return result


def build_group_identifier_frame(frame: pd.DataFrame, group_fields: Sequence[str]) -> pd.DataFrame:
    """Build stable identifier columns for cross-layer audit outputs."""
    columns = ["unit_id", "probe_country", "src_country", "service_id", "msm_id", "file_name"]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    working = attach_service_id(frame.copy())
    rows: List[Dict[str, Any]] = []
    for group_key, group in working.groupby(list(group_fields), dropna=False):
        row = {column: "NA" for column in columns}
        row.update(group_key_to_dict(group_fields, group_key))
        row["unit_id"] = str(row["unit_id"]) if row.get("unit_id", "NA") != "NA" else "NA"
        row["src_country"] = (
            str(row["src_country"])
            if "src_country" in group_fields
            else summarize_identifier_value(group.get("src_country", pd.Series(dtype=object)))
        )
        row["probe_country"] = (
            str(row["probe_country"])
            if "probe_country" in group_fields
            else summarize_identifier_value(group.get("probe_country", pd.Series(dtype=object)))
        )
        row["service_id"] = (
            str(row["service_id"])
            if "service_id" in group_fields
            else summarize_identifier_value(group.get("service_id", pd.Series(dtype=object)))
        )
        row["msm_id"] = summarize_identifier_value(group.get("msm_id", pd.Series(dtype=object)))
        row["file_name"] = summarize_identifier_value(group.get("file_name", pd.Series(dtype=object)))
        rows.append(row)
    return normalize_group_key_columns(pd.DataFrame(rows, columns=columns), group_fields)


def build_group_network_metrics(frame: pd.DataFrame, group_fields: Sequence[str]) -> pd.DataFrame:
    """Compute application-layer richness and network effective diversity for arbitrary groupings."""
    identifier_columns = ["unit_id", "probe_country", "src_country", "service_id", "msm_id", "file_name"]
    if frame.empty:
        return pd.DataFrame(columns=identifier_columns + [
            "num_measurements",
            "num_probes",
            "num_probe_asns",
            "num_files_or_targets",
            "num_egress_links",
            "num_egress_asns",
            "num_next_asns_after_egress",
            "num_egress_transitions",
            "egress_transition_entropy",
            "effective_egress_transitions",
            "num_src_dst_as_pairs",
            "src_dst_as_pair_entropy",
            "effective_as_pair_transitions",
            "network_effective_diversity",
        ])

    link_level = normalize_link_level_frame(frame)
    identifier_frame = build_group_identifier_frame(link_level, group_fields)
    rows: List[Dict[str, Any]] = []
    for group_key, group in link_level.groupby(list(group_fields), dropna=False):
        row = group_key_to_dict(group_fields, group_key)
        source_country = (
            str(row["src_country"])
            if "src_country" in row
            else dominant_non_missing_value(group["src_country"], default="NA")
        )
        num_measurements = int(group.get("msm_id", pd.Series(index=group.index, dtype=object)).replace("", np.nan).dropna().nunique())
        num_probes = int(group.get("probe_id", pd.Series(index=group.index, dtype=object)).replace("", np.nan).dropna().nunique())
        num_probe_asns = int(group["src_asn_norm"].replace("NA", np.nan).dropna().nunique())
        num_files_or_targets = int(group.get("file_name", pd.Series(index=group.index, dtype=object)).replace("", np.nan).dropna().nunique())
        num_src_dst_as_pairs = int(group["src_dst_as_pair"].replace("NA->NA", np.nan).dropna().nunique())
        as_pair_entropy = shannon_entropy(group["src_dst_as_pair"].value_counts().tolist())
        effective_as_pair_transitions = effective_count_from_entropy(as_pair_entropy, num_src_dst_as_pairs)

        egress_group = group[
            (group["src_country"].astype(str) == source_country)
            & (group["dst_country"].astype(str) != source_country)
            & (group["src_asn_norm"].astype(str) != "NA")
            & (group["dst_asn_norm"].astype(str) != "NA")
        ].copy()
        if not egress_group.empty:
            egress_group["egress_asn"] = egress_group["src_asn_norm"].astype(str)
            egress_group["next_asn_after_egress"] = egress_group["dst_asn_norm"].astype(str)
            egress_group["egress_transition"] = egress_group["egress_asn"] + "->" + egress_group["next_asn_after_egress"]
        num_egress_links = int(len(egress_group))
        num_egress_asns = int(egress_group["egress_asn"].nunique()) if not egress_group.empty else 0
        num_next_asns_after_egress = int(egress_group["next_asn_after_egress"].nunique()) if not egress_group.empty else 0
        num_egress_transitions = int(egress_group["egress_transition"].nunique()) if not egress_group.empty else 0
        egress_transition_entropy = (
            shannon_entropy(egress_group["egress_transition"].value_counts().tolist())
            if not egress_group.empty
            else 0.0
        )
        effective_egress_transitions = (
            effective_count_from_entropy(egress_transition_entropy, num_egress_transitions)
            if num_egress_links > 0
            else 0.0
        )
        network_effective_diversity = (
            effective_egress_transitions
            if num_egress_links > 0
            else effective_as_pair_transitions
        )

        rows.append(
            {
                **row,
                "num_measurements": num_measurements,
                "num_probes": num_probes,
                "num_probe_asns": num_probe_asns,
                "num_files_or_targets": num_files_or_targets,
                "num_egress_links": num_egress_links,
                "num_egress_asns": num_egress_asns,
                "num_next_asns_after_egress": num_next_asns_after_egress,
                "num_egress_transitions": num_egress_transitions,
                "egress_transition_entropy": float(egress_transition_entropy),
                "effective_egress_transitions": float(effective_egress_transitions),
                "num_src_dst_as_pairs": num_src_dst_as_pairs,
                "src_dst_as_pair_entropy": float(as_pair_entropy),
                "effective_as_pair_transitions": float(effective_as_pair_transitions),
                "network_effective_diversity": float(network_effective_diversity),
            }
        )

    result = identifier_frame.merge(
        normalize_group_key_columns(pd.DataFrame(rows), group_fields),
        on=list(group_fields),
        how="inner",
    )
    ordered = identifier_columns + [
        "num_measurements",
        "num_probes",
        "num_probe_asns",
        "num_files_or_targets",
        "num_egress_links",
        "num_egress_asns",
        "num_next_asns_after_egress",
        "num_egress_transitions",
        "egress_transition_entropy",
        "effective_egress_transitions",
        "num_src_dst_as_pairs",
        "src_dst_as_pair_entropy",
        "effective_as_pair_transitions",
        "network_effective_diversity",
    ]
    return result[ordered]


def build_group_physical_metrics(
    frame: pd.DataFrame,
    group_fields: Sequence[str],
    physical_level: str,
    corridor_candidate_col: str,
) -> pd.DataFrame:
    """Compute feasible physical-candidate upper-bound metrics for arbitrary groupings."""
    identifier_columns = ["unit_id", "probe_country", "src_country", "service_id", "msm_id", "file_name"]
    columns = identifier_columns + [
        "physical_level",
        "num_feasible_candidates",
        "num_feasible_corridors",
        "effective_feasible_candidates",
        "effective_feasible_corridors",
        "physical_candidate_diversity_upper_bound",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    working = ensure_corridor_columns(attach_service_id(frame.copy()))
    identifier_frame = build_group_identifier_frame(working, group_fields)
    rows: List[Dict[str, Any]] = []
    for group_key, group in working.groupby(list(group_fields), dropna=False):
        row = group_key_to_dict(group_fields, group_key)
        candidate_ids = (
            group.get("cable_id", pd.Series(index=group.index, dtype=object))
            .astype(str)
            .str.strip()
            .replace({"": np.nan, "nan": np.nan, "NA": np.nan})
            .dropna()
            .unique()
            .tolist()
        )
        corridor_ids = (
            group.get(corridor_candidate_col, pd.Series(index=group.index, dtype=object))
            .astype(str)
            .str.strip()
            .replace({"": np.nan, "nan": np.nan, "NA": np.nan})
            .dropna()
            .unique()
            .tolist()
        )
        num_feasible_candidates = int(len(candidate_ids))
        num_feasible_corridors = int(len(corridor_ids))
        effective_feasible_candidates = float(num_feasible_candidates)
        effective_feasible_corridors = float(num_feasible_corridors)
        physical_candidate_diversity_upper_bound = (
            effective_feasible_corridors if physical_level == "corridor" else effective_feasible_candidates
        )
        rows.append(
            {
                **row,
                "physical_level": physical_level,
                "num_feasible_candidates": num_feasible_candidates,
                "num_feasible_corridors": num_feasible_corridors,
                "effective_feasible_candidates": effective_feasible_candidates,
                "effective_feasible_corridors": effective_feasible_corridors,
                "physical_candidate_diversity_upper_bound": float(physical_candidate_diversity_upper_bound),
            }
        )

    result = identifier_frame.merge(
        normalize_group_key_columns(pd.DataFrame(rows), group_fields),
        on=list(group_fields),
        how="inner",
    )
    return result[columns]


def classify_absolute_compression_tier(log_gap: float) -> str:
    """Classify the absolute network-to-physical compression magnitude."""
    if pd.isna(log_gap) or log_gap <= 0:
        return "no_compression"
    if log_gap < math.log(2):
        return "weak_compression"
    if log_gap < math.log(4):
        return "moderate_compression"
    return "severe_compression"


def classify_physical_candidate_concentration_tier(d_phys: Any) -> str:
    """Classify how narrow the best-case feasible physical-candidate space is."""
    numeric = pd.to_numeric(pd.Series([d_phys]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "unknown_physical_candidate_concentration"
    if numeric <= 1:
        return "severe_physical_candidate_concentration"
    if numeric <= 2:
        return "moderate_physical_candidate_concentration"
    if numeric <= 4:
        return "weak_physical_candidate_concentration"
    return "broad_physical_candidate_space"


def classify_network_physical_compression_tier(log_gap: Any) -> str:
    """Classify whether network effective diversity exceeds the best-case physical upper bound."""
    numeric = pd.to_numeric(pd.Series([log_gap]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "unknown_network_physical_compression"
    if numeric <= 0:
        return "no_network_physical_compression"
    if numeric < math.log(2):
        return "weak_network_physical_compression"
    if numeric < math.log(4):
        return "moderate_network_physical_compression"
    return "severe_network_physical_compression"


def add_best_case_physical_candidate_audit_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach best-case physical-candidate concentration and joint cross-layer risk metrics."""
    result = frame.copy()
    if result.empty:
        return result

    result["best_case_physical_candidate_diversity_upper_bound"] = pd.to_numeric(
        result.get("physical_candidate_diversity_upper_bound", pd.Series(index=result.index, dtype=float)),
        errors="coerce",
    )
    result["physical_candidate_concentration_tier"] = result[
        "best_case_physical_candidate_diversity_upper_bound"
    ].apply(classify_physical_candidate_concentration_tier)
    concentrated_tiers = {
        "severe_physical_candidate_concentration",
        "moderate_physical_candidate_concentration",
        "weak_physical_candidate_concentration",
    }
    result["is_physical_candidate_concentrated"] = result["physical_candidate_concentration_tier"].isin(concentrated_tiers)
    result["physical_candidate_exposure_class"] = np.where(
        result["is_physical_candidate_concentrated"],
        "concentrated_best_case_physical_candidate_space",
        np.where(
            result["physical_candidate_concentration_tier"] == "broad_physical_candidate_space",
            "broad_best_case_physical_candidate_space",
            "unknown_best_case_physical_candidate_space",
        ),
    )
    num_probes = pd.to_numeric(result.get("num_probes", pd.Series(index=result.index, dtype=float)), errors="coerce").fillna(0.0)
    num_egress_links = pd.to_numeric(
        result.get("num_egress_links", pd.Series(index=result.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    num_measurements = pd.to_numeric(
        result.get("num_measurements", pd.Series(index=result.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    result["sufficient_observation_for_physical_concentration"] = (
        (num_probes >= 3) | (num_egress_links >= 3) | (num_measurements >= 2)
    )
    result["concentration_interpretation"] = np.where(
        result["physical_candidate_concentration_tier"] == "broad_physical_candidate_space",
        "broad_physical_candidate_space",
        np.where(
            result["is_physical_candidate_concentrated"] & result["sufficient_observation_for_physical_concentration"],
            "auditable_physical_candidate_concentration",
            np.where(
                result["is_physical_candidate_concentrated"],
                "low_observation_concentration_signal",
                "unknown_physical_candidate_concentration",
            ),
        ),
    )
    result["network_physical_compression_tier"] = result["log_network_physical_compression_gap"].apply(
        classify_network_physical_compression_tier
    )
    compression_tiers = {
        "weak_network_physical_compression",
        "moderate_network_physical_compression",
        "severe_network_physical_compression",
    }
    result["is_network_physical_mismatch"] = result["network_physical_compression_tier"].isin(compression_tiers)
    result["joint_cross_layer_risk_class"] = np.where(
        result["is_physical_candidate_concentrated"] & result["is_network_physical_mismatch"],
        "physical_concentration_with_network_physical_compression",
        np.where(
            result["is_physical_candidate_concentrated"]
            & (result["network_physical_compression_tier"] == "no_network_physical_compression"),
            "physical_concentration_without_compression",
            np.where(
                (~result["is_physical_candidate_concentrated"])
                & (result["physical_candidate_concentration_tier"] == "broad_physical_candidate_space")
                & result["is_network_physical_mismatch"],
                "compression_without_physical_concentration",
                np.where(
                    (~result["is_physical_candidate_concentrated"])
                    & (result["physical_candidate_concentration_tier"] == "broad_physical_candidate_space")
                    & (result["network_physical_compression_tier"] == "no_network_physical_compression"),
                    "broad_physical_candidate_space_no_compression",
                    "unknown_joint_cross_layer_risk",
                ),
            ),
        ),
    )
    result["is_physical_candidate_concentration_only"] = (
        result["joint_cross_layer_risk_class"] == "physical_concentration_without_compression"
    )
    result["is_joint_physical_concentration_and_mismatch"] = (
        result["joint_cross_layer_risk_class"] == "physical_concentration_with_network_physical_compression"
    )
    return result


def add_cross_layer_relative_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach optional relative rank/percentile comparison metrics to a cross-layer audit table."""
    result = frame.copy()
    if result.empty:
        return result

    result["network_percentile"] = np.nan
    result["physical_upper_bound_percentile"] = np.nan
    result["rank_gap_upper_bound"] = np.nan
    result["strict_upper_bound_mismatch_75_25"] = False
    result["upper_bound_mismatch_category"] = "network_low_physical_upper_high"

    for physical_level, group in result.groupby("physical_level", dropna=False):
        current = pd.to_numeric(group["network_effective_diversity"], errors="coerce").fillna(0.0)
        physical = pd.to_numeric(group["physical_candidate_diversity_upper_bound"], errors="coerce").fillna(0.0)
        result.loc[group.index, "network_percentile"] = current.rank(method="average", pct=True, ascending=True)
        result.loc[group.index, "physical_upper_bound_percentile"] = physical.rank(method="average", pct=True, ascending=True)
        network_rank = current.rank(method="dense", ascending=False)
        physical_rank = physical.rank(method="dense", ascending=False)
        result.loc[group.index, "rank_gap_upper_bound"] = physical_rank - network_rank

        network_high = result.loc[group.index, "network_percentile"] >= 0.5
        physical_low = result.loc[group.index, "physical_upper_bound_percentile"] <= 0.5
        categories = np.where(
            network_high & physical_low,
            "network_high_physical_upper_low",
            np.where(
                network_high & ~physical_low,
                "network_high_physical_upper_high",
                np.where(
                    ~network_high & physical_low,
                    "network_low_physical_upper_low",
                    "network_low_physical_upper_high",
                ),
            ),
        )
        result.loc[group.index, "upper_bound_mismatch_category"] = categories
        result.loc[group.index, "strict_upper_bound_mismatch_75_25"] = (
            (result.loc[group.index, "network_percentile"] >= 0.75)
            & (result.loc[group.index, "physical_upper_bound_percentile"] <= 0.25)
        )
    return result


def build_cross_layer_audit_frame(
    feasible_frame: pd.DataFrame,
    group_fields: Sequence[str],
    corridor_candidate_col: str,
    peeringdb_frame: pd.DataFrame,
    peeringdb_country_column: str = "probe_country",
) -> pd.DataFrame:
    """Build a first-class cross-layer audit table with non-rank and optional relative metrics."""
    if feasible_frame.empty:
        return pd.DataFrame(columns=PRIMARY_CROSS_LAYER_COLUMNS)

    network_frame = build_group_network_metrics(feasible_frame, group_fields)
    physical_frames = [
        build_group_physical_metrics(feasible_frame, group_fields, "cable", corridor_candidate_col),
        build_group_physical_metrics(feasible_frame, group_fields, "corridor", corridor_candidate_col),
    ]
    combined_physical = pd.concat(physical_frames, ignore_index=True)
    audit_frame = network_frame.merge(
        combined_physical,
        on=["unit_id", "src_country", "service_id", "msm_id", "file_name"],
        how="inner",
    )
    if audit_frame.empty:
        return pd.DataFrame(columns=PRIMARY_CROSS_LAYER_COLUMNS)

    audit_frame["network_to_physical_compression_ratio"] = np.where(
        pd.to_numeric(audit_frame["physical_candidate_diversity_upper_bound"], errors="coerce").fillna(0.0) > 0,
        pd.to_numeric(audit_frame["network_effective_diversity"], errors="coerce").fillna(0.0)
        / pd.to_numeric(audit_frame["physical_candidate_diversity_upper_bound"], errors="coerce").fillna(0.0),
        np.nan,
    )
    audit_frame["log_network_physical_compression_gap"] = (
        pd.to_numeric(audit_frame["network_effective_diversity"], errors="coerce").fillna(0.0).apply(safe_log1p)
        - pd.to_numeric(audit_frame["physical_candidate_diversity_upper_bound"], errors="coerce").fillna(0.0).apply(safe_log1p)
    )
    audit_frame["physical_coverage_ratio"] = np.where(
        pd.to_numeric(audit_frame["network_effective_diversity"], errors="coerce").fillna(0.0) > 0,
        pd.to_numeric(audit_frame["physical_candidate_diversity_upper_bound"], errors="coerce").fillna(0.0)
        / pd.to_numeric(audit_frame["network_effective_diversity"], errors="coerce").fillna(0.0),
        np.nan,
    )
    audit_frame["absolute_compression_tier"] = audit_frame["log_network_physical_compression_gap"].apply(
        classify_absolute_compression_tier
    )
    audit_frame = add_best_case_physical_candidate_audit_metrics(audit_frame)
    audit_frame = add_cross_layer_relative_metrics(audit_frame)
    audit_frame = merge_peeringdb_descriptors(audit_frame, peeringdb_frame, country_column=peeringdb_country_column)

    for column in PRIMARY_CROSS_LAYER_COLUMNS:
        if column not in audit_frame.columns:
            audit_frame[column] = np.nan if column not in {
                "unit_id",
                "src_country",
                "service_id",
                "msm_id",
                "file_name",
                "physical_level",
                "absolute_compression_tier",
                "physical_candidate_concentration_tier",
                "physical_candidate_exposure_class",
                "concentration_interpretation",
                "network_physical_compression_tier",
                "joint_cross_layer_risk_class",
                "upper_bound_mismatch_category",
                "pdb_interconnection_footprint_tier",
                "peeringdb_join_country_field",
            } else "NA"
    return audit_frame[PRIMARY_CROSS_LAYER_COLUMNS].sort_values(
        ["src_country", "service_id", "msm_id", "file_name", "physical_level", "unit_id"]
    ).reset_index(drop=True)


def build_cross_layer_metric_summary(named_frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a compact summary of first-class cross-layer metrics across output tables."""
    columns = [
        "output_name",
        "physical_level",
        "rows",
        "median_network_effective_diversity",
        "median_physical_candidate_diversity_upper_bound",
        "median_network_to_physical_compression_ratio",
        "median_log_network_physical_compression_gap",
        "median_physical_coverage_ratio",
        "strict_upper_bound_mismatch_rate",
        "severe_physical_concentration_rows",
        "moderate_physical_concentration_rows",
        "weak_physical_concentration_rows",
        "broad_physical_candidate_space_rows",
        "physical_concentration_rows",
        "physical_concentration_share",
        "auditable_physical_concentration_rows",
        "no_compression_rows",
        "weak_compression_rows",
        "moderate_compression_rows",
        "severe_compression_rows",
        "no_network_physical_compression_rows",
        "weak_network_physical_compression_rows",
        "moderate_network_physical_compression_rows",
        "severe_network_physical_compression_rows",
        "physical_concentration_with_network_physical_compression_rows",
        "physical_concentration_without_compression_rows",
        "compression_without_physical_concentration_rows",
        "broad_physical_candidate_space_no_compression_rows",
    ]
    rows: List[Dict[str, Any]] = []
    for output_name, frame in named_frames.items():
        if frame.empty:
            continue
        for physical_level, group in frame.groupby("physical_level", dropna=False):
            tier_counts = group["absolute_compression_tier"].astype(str).value_counts()
            concentration_counts = group["physical_candidate_concentration_tier"].astype(str).value_counts()
            network_compression_counts = group["network_physical_compression_tier"].astype(str).value_counts()
            joint_counts = group["joint_cross_layer_risk_class"].astype(str).value_counts()
            physical_concentration_rows = int(pd.Series(group["is_physical_candidate_concentrated"]).fillna(False).astype(bool).sum())
            rows.append(
                {
                    "output_name": output_name,
                    "physical_level": physical_level,
                    "rows": int(len(group)),
                    "median_network_effective_diversity": float(pd.to_numeric(group["network_effective_diversity"], errors="coerce").median()),
                    "median_physical_candidate_diversity_upper_bound": float(pd.to_numeric(group["physical_candidate_diversity_upper_bound"], errors="coerce").median()),
                    "median_network_to_physical_compression_ratio": float(pd.to_numeric(group["network_to_physical_compression_ratio"], errors="coerce").median()),
                    "median_log_network_physical_compression_gap": float(pd.to_numeric(group["log_network_physical_compression_gap"], errors="coerce").median()),
                    "median_physical_coverage_ratio": float(pd.to_numeric(group["physical_coverage_ratio"], errors="coerce").median()),
                    "strict_upper_bound_mismatch_rate": float(
                        pd.Series(group["strict_upper_bound_mismatch_75_25"]).fillna(False).astype(bool).mean()
                    ),
                    "severe_physical_concentration_rows": int(concentration_counts.get("severe_physical_candidate_concentration", 0)),
                    "moderate_physical_concentration_rows": int(concentration_counts.get("moderate_physical_candidate_concentration", 0)),
                    "weak_physical_concentration_rows": int(concentration_counts.get("weak_physical_candidate_concentration", 0)),
                    "broad_physical_candidate_space_rows": int(concentration_counts.get("broad_physical_candidate_space", 0)),
                    "physical_concentration_rows": physical_concentration_rows,
                    "physical_concentration_share": float(physical_concentration_rows / len(group)) if len(group) > 0 else 0.0,
                    "auditable_physical_concentration_rows": int(
                        (group["concentration_interpretation"].astype(str) == "auditable_physical_candidate_concentration").sum()
                    ),
                    "no_compression_rows": int(tier_counts.get("no_compression", 0)),
                    "weak_compression_rows": int(tier_counts.get("weak_compression", 0)),
                    "moderate_compression_rows": int(tier_counts.get("moderate_compression", 0)),
                    "severe_compression_rows": int(tier_counts.get("severe_compression", 0)),
                    "no_network_physical_compression_rows": int(network_compression_counts.get("no_network_physical_compression", 0)),
                    "weak_network_physical_compression_rows": int(network_compression_counts.get("weak_network_physical_compression", 0)),
                    "moderate_network_physical_compression_rows": int(network_compression_counts.get("moderate_network_physical_compression", 0)),
                    "severe_network_physical_compression_rows": int(network_compression_counts.get("severe_network_physical_compression", 0)),
                    "physical_concentration_with_network_physical_compression_rows": int(
                        joint_counts.get("physical_concentration_with_network_physical_compression", 0)
                    ),
                    "physical_concentration_without_compression_rows": int(
                        joint_counts.get("physical_concentration_without_compression", 0)
                    ),
                    "compression_without_physical_concentration_rows": int(
                        joint_counts.get("compression_without_physical_concentration", 0)
                    ),
                    "broad_physical_candidate_space_no_compression_rows": int(
                        joint_counts.get("broad_physical_candidate_space_no_compression", 0)
                    ),
                }
            )
    return pd.DataFrame(rows, columns=columns).sort_values(["output_name", "physical_level"]).reset_index(drop=True)


def build_physical_candidate_concentration_summary(named_frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Summarize best-case physical-candidate concentration across cross-layer audit outputs."""
    columns = [
        "output_scope",
        "physical_level",
        "rows",
        "severe_physical_concentration_rows",
        "moderate_physical_concentration_rows",
        "weak_physical_concentration_rows",
        "broad_physical_candidate_space_rows",
        "physical_concentration_rows",
        "physical_concentration_share",
        "auditable_physical_concentration_rows",
        "low_observation_concentration_signal_rows",
        "median_physical_candidate_diversity_upper_bound",
        "p25_physical_candidate_diversity_upper_bound",
        "p75_physical_candidate_diversity_upper_bound",
        "median_num_feasible_corridors",
        "median_network_effective_diversity",
        "median_network_to_physical_compression_ratio",
        "median_log_network_physical_compression_gap",
        "median_physical_coverage_ratio",
    ]
    rows: List[Dict[str, Any]] = []
    for output_scope, frame in named_frames.items():
        if frame.empty:
            continue
        for physical_level, group in frame.groupby("physical_level", dropna=False):
            concentration_counts = group["physical_candidate_concentration_tier"].astype(str).value_counts()
            physical_concentration_rows = int(pd.Series(group["is_physical_candidate_concentrated"]).fillna(False).astype(bool).sum())
            rows.append(
                {
                    "output_scope": output_scope,
                    "physical_level": physical_level,
                    "rows": int(len(group)),
                    "severe_physical_concentration_rows": int(concentration_counts.get("severe_physical_candidate_concentration", 0)),
                    "moderate_physical_concentration_rows": int(concentration_counts.get("moderate_physical_candidate_concentration", 0)),
                    "weak_physical_concentration_rows": int(concentration_counts.get("weak_physical_candidate_concentration", 0)),
                    "broad_physical_candidate_space_rows": int(concentration_counts.get("broad_physical_candidate_space", 0)),
                    "physical_concentration_rows": physical_concentration_rows,
                    "physical_concentration_share": float(physical_concentration_rows / len(group)) if len(group) > 0 else 0.0,
                    "auditable_physical_concentration_rows": int(
                        (group["concentration_interpretation"].astype(str) == "auditable_physical_candidate_concentration").sum()
                    ),
                    "low_observation_concentration_signal_rows": int(
                        (group["concentration_interpretation"].astype(str) == "low_observation_concentration_signal").sum()
                    ),
                    "median_physical_candidate_diversity_upper_bound": float(pd.to_numeric(group["physical_candidate_diversity_upper_bound"], errors="coerce").median()),
                    "p25_physical_candidate_diversity_upper_bound": float(pd.to_numeric(group["physical_candidate_diversity_upper_bound"], errors="coerce").quantile(0.25)),
                    "p75_physical_candidate_diversity_upper_bound": float(pd.to_numeric(group["physical_candidate_diversity_upper_bound"], errors="coerce").quantile(0.75)),
                    "median_num_feasible_corridors": float(pd.to_numeric(group["num_feasible_corridors"], errors="coerce").median()),
                    "median_network_effective_diversity": float(pd.to_numeric(group["network_effective_diversity"], errors="coerce").median()),
                    "median_network_to_physical_compression_ratio": float(pd.to_numeric(group["network_to_physical_compression_ratio"], errors="coerce").median()),
                    "median_log_network_physical_compression_gap": float(pd.to_numeric(group["log_network_physical_compression_gap"], errors="coerce").median()),
                    "median_physical_coverage_ratio": float(pd.to_numeric(group["physical_coverage_ratio"], errors="coerce").median()),
                }
            )
    return pd.DataFrame(rows, columns=columns).sort_values(["output_scope", "physical_level"]).reset_index(drop=True)


def build_joint_cross_layer_risk_summary(named_frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Summarize joint physical concentration and network-to-physical compression risk classes."""
    columns = [
        "output_scope",
        "physical_level",
        "joint_cross_layer_risk_class",
        "rows",
        "row_share_within_scope_physical_level",
        "median_network_effective_diversity",
        "median_physical_candidate_diversity_upper_bound",
        "median_network_to_physical_compression_ratio",
        "median_log_network_physical_compression_gap",
        "median_physical_coverage_ratio",
        "median_pdb_interconnection_footprint_percentile",
    ]
    rows: List[Dict[str, Any]] = []
    for output_scope, frame in named_frames.items():
        if frame.empty:
            continue
        for physical_level, group in frame.groupby("physical_level", dropna=False):
            total_rows = max(len(group), 1)
            for risk_class, risk_group in group.groupby("joint_cross_layer_risk_class", dropna=False):
                rows.append(
                    {
                        "output_scope": output_scope,
                        "physical_level": physical_level,
                        "joint_cross_layer_risk_class": str(risk_class),
                        "rows": int(len(risk_group)),
                        "row_share_within_scope_physical_level": float(len(risk_group) / total_rows),
                        "median_network_effective_diversity": float(pd.to_numeric(risk_group["network_effective_diversity"], errors="coerce").median()),
                        "median_physical_candidate_diversity_upper_bound": float(pd.to_numeric(risk_group["physical_candidate_diversity_upper_bound"], errors="coerce").median()),
                        "median_network_to_physical_compression_ratio": float(pd.to_numeric(risk_group["network_to_physical_compression_ratio"], errors="coerce").median()),
                        "median_log_network_physical_compression_gap": float(pd.to_numeric(risk_group["log_network_physical_compression_gap"], errors="coerce").median()),
                        "median_physical_coverage_ratio": float(pd.to_numeric(risk_group["physical_coverage_ratio"], errors="coerce").median()),
                        "median_pdb_interconnection_footprint_percentile": float(
                            pd.to_numeric(risk_group.get("pdb_interconnection_footprint_percentile", pd.Series(dtype=float)), errors="coerce").median()
                        ),
                    }
                )
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["output_scope", "physical_level", "joint_cross_layer_risk_class"]
    ).reset_index(drop=True)


def combine_paper_case_frames(
    paper_country_cross_layer_audit: pd.DataFrame,
    paper_service_country_cross_layer_audit: pd.DataFrame,
) -> pd.DataFrame:
    """Combine supplementary country and service-country audit frames for legacy case selection."""
    frames: List[pd.DataFrame] = []
    if not paper_country_cross_layer_audit.empty:
        country_frame = paper_country_cross_layer_audit.copy()
        country_frame["paper_case_scope"] = "paper_country_cross_layer_audit"
        frames.append(country_frame)
    if not paper_service_country_cross_layer_audit.empty:
        service_frame = paper_service_country_cross_layer_audit.copy()
        service_frame["paper_case_scope"] = "paper_service_country_cross_layer_audit"
        frames.append(service_frame)
    if not frames:
        return pd.DataFrame(columns=["paper_case_scope", *PRIMARY_CROSS_LAYER_COLUMNS])
    return pd.concat(frames, ignore_index=True, sort=False)


def build_paper_physical_concentration_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Select supplementary cases where the best-case corridor candidate space remains narrow."""
    if frame.empty:
        return frame.copy()
    filtered = frame.loc[
        (frame["physical_level"].astype(str) == PAPER_PRIMARY_PHYSICAL_LEVEL)
        & frame["physical_candidate_concentration_tier"].astype(str).isin(
            [
                "severe_physical_candidate_concentration",
                "moderate_physical_candidate_concentration",
                "weak_physical_candidate_concentration",
            ]
        )
    ].copy()
    return filtered.sort_values(
        [
            "physical_candidate_diversity_upper_bound",
            "num_probes",
            "num_egress_links",
            "network_effective_diversity",
        ],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)


def build_paper_joint_mismatch_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Select supplementary corridor cases with both candidate breadth and network-to-physical compression."""
    if frame.empty:
        return frame.copy()
    filtered = frame.loc[
        (frame["physical_level"].astype(str) == PAPER_PRIMARY_PHYSICAL_LEVEL)
        & (
            frame["joint_cross_layer_risk_class"].astype(str)
            == "physical_concentration_with_network_physical_compression"
        )
    ].copy()
    return filtered.sort_values(
        [
            "log_network_physical_compression_gap",
            "network_to_physical_compression_ratio",
            "physical_candidate_diversity_upper_bound",
        ],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def build_paper_broad_physical_space_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Select counterexample cases with broad best-case corridor space and no compression."""
    if frame.empty:
        return frame.copy()
    corridor_rows = frame.loc[frame["physical_level"].astype(str) == PAPER_PRIMARY_PHYSICAL_LEVEL].copy()
    if corridor_rows.empty:
        return corridor_rows
    network_threshold = pd.to_numeric(corridor_rows["network_effective_diversity"], errors="coerce").quantile(0.75)
    filtered = corridor_rows.loc[
        (corridor_rows["joint_cross_layer_risk_class"].astype(str) == "broad_physical_candidate_space_no_compression")
        & (pd.to_numeric(corridor_rows["network_effective_diversity"], errors="coerce") >= network_threshold)
    ].copy()
    return filtered.sort_values(
        [
            "network_effective_diversity",
            "physical_candidate_diversity_upper_bound",
        ],
        ascending=[False, False],
    ).reset_index(drop=True)


def build_unit_physical_candidate_diversity(
    frame: pd.DataFrame,
    candidate_id_col: str,
    physical_level: str,
    support_col: str = "normalized_candidate_support",
) -> pd.DataFrame:
    """Compute physical-candidate diversity metrics per unit."""
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "unit_id",
                "physical_level",
                "dominant_candidate_key",
                "dominant_candidate_support_share",
                "expected_candidate_support_total",
                "candidate_entropy",
                "effective_num_candidates",
                "gini_candidate_support",
                "num_candidates_with_support",
                "feasible_candidate_count",
                "candidate_entropy_uniform",
                "effective_candidate_count_uniform",
                "num_matched_links",
                "num_probes",
                "physical_candidate_diversity_score",
                "candidate_identifier_column",
            ]
        )

    aggregated = aggregate_candidate_support(frame, candidate_id_col, support_col)
    link_counts = frame.groupby("unit_id")["link_id"].nunique()
    probe_counts = frame.groupby("unit_id")["probe_id"].nunique()

    rows: List[Dict[str, Any]] = []
    for unit_id, group in aggregated.groupby("unit_id"):
        support_values = group["aggregate_support_share"].tolist()
        total_support = float(group["aggregate_support"].sum())
        top_row = group.sort_values("aggregate_support_share", ascending=False).iloc[0]
        entropy_value = shannon_entropy(support_values)
        effective_num = float(math.exp(entropy_value)) if entropy_value > 0 else (1.0 if support_values else 0.0)
        feasible_count = int((group["aggregate_support_share"] > 0).sum())
        uniform_entropy = float(math.log(feasible_count)) if feasible_count > 0 else 0.0
        rows.append(
            {
                "unit_id": unit_id,
                "physical_level": physical_level,
                "dominant_candidate_key": top_row[candidate_id_col],
                "dominant_candidate_support_share": float(top_row["aggregate_support_share"]),
                "expected_candidate_support_total": total_support,
                "candidate_entropy": entropy_value,
                "effective_num_candidates": effective_num,
                "gini_candidate_support": gini_coefficient(support_values),
                "num_candidates_with_support": feasible_count,
                "feasible_candidate_count": feasible_count,
                "candidate_entropy_uniform": uniform_entropy,
                "effective_candidate_count_uniform": float(feasible_count),
                "num_matched_links": int(link_counts.get(unit_id, 0)),
                "num_probes": int(probe_counts.get(unit_id, 0)),
                "physical_candidate_diversity_score": effective_num,
                "candidate_identifier_column": candidate_id_col,
            }
        )
    return pd.DataFrame(rows).sort_values("unit_id")


def build_unit_physical_feasible_set_diversity(
    frame: pd.DataFrame,
    candidate_id_col: str,
    physical_level: str,
) -> pd.DataFrame:
    """Compute conservative set-based physical diversity from all feasible candidates."""
    columns = [
        "unit_id",
        "physical_level",
        "feasible_candidate_count",
        "feasible_corridor_count",
        "candidate_entropy_uniform",
        "corridor_entropy_uniform",
        "effective_candidate_count_uniform",
        "effective_corridor_count_uniform",
        "physical_candidate_diversity_upper_bound",
        "num_feasible_links",
        "num_probes",
        "candidate_identifier_column",
        "diversity_weighting",
        "physical_candidate_diversity_score",
        "candidate_entropy",
        "effective_num_candidates",
        "dominant_candidate_support_share",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    working = frame.copy()
    working = ensure_corridor_columns(working)
    working[candidate_id_col] = working[candidate_id_col].fillna("NA")
    corridor_col = resolve_corridor_candidate_column(working)
    link_counts = working.groupby("unit_id")["link_id"].nunique() if "link_id" in working.columns else pd.Series(dtype=int)
    probe_counts = working.groupby("unit_id")["probe_id"].nunique()
    rows: List[Dict[str, Any]] = []
    for unit_id, group in working.groupby("unit_id", dropna=False):
        unique_candidates = [
            value
            for value in group[candidate_id_col].astype(str).str.strip().replace({"": np.nan, "nan": np.nan}).dropna().unique().tolist()
        ]
        unique_corridors = [
            value
            for value in group[corridor_col].astype(str).str.strip().replace({"": np.nan, "nan": np.nan}).dropna().unique().tolist()
        ]
        feasible_count = int(len(unique_candidates))
        feasible_corridor_count = int(len(unique_corridors))
        candidate_entropy_uniform = float(math.log(feasible_count)) if feasible_count > 0 else 0.0
        corridor_entropy_uniform = float(math.log(feasible_corridor_count)) if feasible_corridor_count > 0 else 0.0
        physical_upper_bound = float(feasible_count if physical_level == "cable" else feasible_corridor_count)
        rows.append(
            {
                "unit_id": unit_id,
                "physical_level": physical_level,
                "feasible_candidate_count": feasible_count,
                "feasible_corridor_count": feasible_corridor_count,
                "candidate_entropy_uniform": candidate_entropy_uniform,
                "corridor_entropy_uniform": corridor_entropy_uniform,
                "effective_candidate_count_uniform": float(feasible_count),
                "effective_corridor_count_uniform": float(feasible_corridor_count),
                "physical_candidate_diversity_upper_bound": physical_upper_bound,
                "num_feasible_links": int(link_counts.get(unit_id, 0)),
                "num_probes": int(probe_counts.get(unit_id, 0)),
                "diversity_weighting": "uniform_feasible_set",
                "candidate_identifier_column": candidate_id_col,
                "physical_candidate_diversity_score": physical_upper_bound,
                "candidate_entropy": candidate_entropy_uniform if physical_level == "cable" else corridor_entropy_uniform,
                "effective_num_candidates": physical_upper_bound,
                "dominant_candidate_support_share": float(1.0 / physical_upper_bound) if physical_upper_bound > 0 else 0.0,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("unit_id").reset_index(drop=True)


def build_unit_physical_candidate_upper_bound(
    frame: pd.DataFrame,
    corridor_candidate_col: str,
) -> pd.DataFrame:
    """Compute a concise upper-bound physical diversity summary using feasible candidate and corridor counts."""
    columns = [
        "unit_id",
        "num_feasible_candidates",
        "num_feasible_corridors",
        "candidate_entropy_uniform",
        "corridor_entropy_uniform",
        "effective_candidate_count_uniform",
        "effective_corridor_count_uniform",
        "physical_candidate_diversity_upper_bound",
        "unique_corridor_candidate_breadth",
        "candidate_breadth_tier",
        "small_candidate_breadth",
        "candidate_breadth_interpretation",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    rows: List[Dict[str, Any]] = []
    for unit_id, group in frame.groupby("unit_id", dropna=False):
        candidate_ids = (
            group.get("cable_id", pd.Series(index=group.index, dtype=object))
            .astype(str)
            .str.strip()
            .replace({"": np.nan, "nan": np.nan})
            .dropna()
            .unique()
            .tolist()
        )
        corridor_ids = (
            group.get(corridor_candidate_col, pd.Series(index=group.index, dtype=object))
            .astype(str)
            .str.strip()
            .replace({"": np.nan, "nan": np.nan})
            .dropna()
            .unique()
            .tolist()
        )
        num_candidates = int(len(candidate_ids))
        num_corridors = int(len(corridor_ids))
        rows.append(
            {
                "unit_id": unit_id,
                "num_feasible_candidates": num_candidates,
                "num_feasible_corridors": num_corridors,
                "candidate_entropy_uniform": float(math.log(num_candidates)) if num_candidates > 0 else 0.0,
                "corridor_entropy_uniform": float(math.log(num_corridors)) if num_corridors > 0 else 0.0,
                "effective_candidate_count_uniform": float(num_candidates),
                "effective_corridor_count_uniform": float(num_corridors),
                "physical_candidate_diversity_upper_bound": float(num_corridors if num_corridors > 0 else num_candidates),
                "unique_corridor_candidate_breadth": float(num_corridors),
                "candidate_breadth_tier": classify_candidate_breadth_tier(num_corridors),
                "small_candidate_breadth": bool(num_corridors <= 4),
                "candidate_breadth_interpretation": "candidate-set breadth descriptor; not the paper-primary corridor observation concentration metric",
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("unit_id").reset_index(drop=True)


def build_unit_network_layer_diversity(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute network-layer diversity metrics per unit."""
    if frame.empty:
        return pd.DataFrame()

    link_level = frame.drop_duplicates(subset=["unit_id", "link_id"]).copy()
    link_level["src_country"] = link_level["src_country"].fillna("NA")
    link_level["dst_country"] = link_level["dst_country"].fillna("NA")
    link_level["country_pair"] = link_level["src_country"] + "->" + link_level["dst_country"]
    link_level["src_asn_norm"] = link_level["src_asn"].apply(lambda value: normalize_token(value, prefix="AS"))
    link_level["dst_asn_norm"] = link_level["dst_asn"].apply(lambda value: normalize_token(value, prefix="AS"))
    link_level["src_dst_as_pair"] = link_level["src_asn_norm"] + "->" + link_level["dst_asn_norm"]

    rows: List[Dict[str, Any]] = []
    for unit_id, group in link_level.groupby("unit_id"):
        unit_source_country = dominant_non_missing_value(group["src_country"], default="NA")
        country_counts = group["country_pair"].value_counts().tolist()
        src_as_counts = group["src_asn_norm"].value_counts().tolist()
        dst_as_counts = group["dst_asn_norm"].value_counts().tolist()
        as_pair_counts = group["src_dst_as_pair"].value_counts().tolist()

        country_entropy = shannon_entropy(country_counts)
        src_as_entropy = shannon_entropy(src_as_counts)
        dst_as_entropy = shannon_entropy(dst_as_counts)
        as_pair_entropy = shannon_entropy(as_pair_counts)

        num_probes = int(group["probe_id"].nunique())
        num_dst_countries = int(group["dst_country"].replace("NA", np.nan).dropna().nunique())
        num_country_pairs = int(group["country_pair"].nunique())
        num_files_or_targets = int(group["file_name"].dropna().nunique())
        num_measurements = int(group["msm_id"].dropna().nunique())
        num_src_asns = int(group["src_asn_norm"].replace("NA", np.nan).dropna().nunique())
        num_dst_asns = int(group["dst_asn_norm"].replace("NA", np.nan).dropna().nunique())
        num_src_dst_as_pairs = int(group["src_dst_as_pair"].replace("NA->NA", np.nan).dropna().nunique())
        egress_group = group[
            (group["src_country"].astype(str) == unit_source_country)
            & (group["dst_country"].astype(str) != unit_source_country)
            & (group["src_asn_norm"].astype(str) != "NA")
            & (group["dst_asn_norm"].astype(str) != "NA")
        ].copy()
        if not egress_group.empty:
            egress_group["egress_asn"] = egress_group["src_asn_norm"].astype(str)
            egress_group["next_asn_after_egress"] = egress_group["dst_asn_norm"].astype(str)
            egress_group["egress_transition"] = (
                egress_group["egress_asn"] + "->" + egress_group["next_asn_after_egress"]
            )
            egress_group["egress_country_transition"] = (
                egress_group["src_country"].astype(str) + "->" + egress_group["dst_country"].astype(str)
            )
        num_egress_links = int(len(egress_group))
        num_egress_asns = int(egress_group["egress_asn"].nunique()) if not egress_group.empty else 0
        num_next_asns_after_egress = int(egress_group["next_asn_after_egress"].nunique()) if not egress_group.empty else 0
        num_egress_transitions = int(egress_group["egress_transition"].nunique()) if not egress_group.empty else 0
        egress_asn_entropy = shannon_entropy(
            egress_group["egress_asn"].value_counts().tolist()
        ) if not egress_group.empty else 0.0
        next_asn_after_egress_entropy = shannon_entropy(
            egress_group["next_asn_after_egress"].value_counts().tolist()
        ) if not egress_group.empty else 0.0
        egress_transition_entropy = shannon_entropy(
            egress_group["egress_transition"].value_counts().tolist()
        ) if not egress_group.empty else 0.0

        network_score_component_as_pair = as_pair_entropy + 0.5 * safe_log1p(num_src_dst_as_pairs)
        network_score_component_country_pair = country_entropy + 0.25 * safe_log1p(num_dst_countries)
        network_score_component_endpoint_asn = (
            0.5 * dst_as_entropy
            + 0.25 * src_as_entropy
            + 0.5 * safe_log1p(num_dst_asns)
        )
        network_score_component_probe_target = (
            0.5 * safe_log1p(num_probes)
            + 0.5 * safe_log1p(num_files_or_targets)
            + 0.25 * safe_log1p(num_measurements)
        )
        network_diversity_dst_asn_primary = dst_as_entropy + safe_log1p(num_dst_asns)
        if num_egress_links > 0:
            network_diversity_as_egress_primary = (
                egress_transition_entropy
                + 0.5 * safe_log1p(num_egress_transitions)
                + 0.5 * safe_log1p(num_egress_asns)
                + 0.25 * safe_log1p(num_next_asns_after_egress)
            )
        else:
            network_diversity_as_egress_primary = as_pair_entropy + 0.5 * safe_log1p(num_src_dst_as_pairs)

        network_layer_diversity_score_as_only = (
            network_score_component_as_pair + network_score_component_endpoint_asn
        )
        network_layer_diversity_score_country_only = network_score_component_country_pair
        network_layer_diversity_score_probe_target_only = network_score_component_probe_target
        network_layer_diversity_score = (
            network_score_component_as_pair
            + network_score_component_country_pair
            + network_score_component_endpoint_asn
            + network_score_component_probe_target
        )

        rows.append(
            {
                "unit_id": unit_id,
                "src_country": unit_source_country,
                "num_probes": num_probes,
                "num_dst_countries": num_dst_countries,
                "num_src_dst_country_pairs": num_country_pairs,
                "num_files_or_targets": num_files_or_targets,
                "num_measurements": num_measurements,
                "num_src_asns": num_src_asns,
                "num_dst_asns": num_dst_asns,
                "num_src_dst_as_pairs": num_src_dst_as_pairs,
                "num_egress_links": num_egress_links,
                "num_egress_asns": num_egress_asns,
                "num_next_asns_after_egress": num_next_asns_after_egress,
                "num_egress_transitions": num_egress_transitions,
                "link_country_sequence_entropy": country_entropy,
                "src_asn_entropy": src_as_entropy,
                "dst_asn_entropy": dst_as_entropy,
                "as_pair_entropy": as_pair_entropy,
                "src_dst_as_pair_entropy": as_pair_entropy,
                "egress_asn_entropy": float(egress_asn_entropy),
                "next_asn_after_egress_entropy": float(next_asn_after_egress_entropy),
                "egress_transition_entropy": float(egress_transition_entropy),
                "network_score_component_as_pair": float(network_score_component_as_pair),
                "network_score_component_country_pair": float(network_score_component_country_pair),
                "network_score_component_endpoint_asn": float(network_score_component_endpoint_asn),
                "network_score_component_probe_target": float(network_score_component_probe_target),
                "network_diversity_as_egress_primary": float(network_diversity_as_egress_primary),
                "network_diversity_dst_asn_primary": float(network_diversity_dst_asn_primary),
                "network_layer_diversity_score_as_only": float(network_layer_diversity_score_as_only),
                "network_layer_diversity_score_country_only": float(network_layer_diversity_score_country_only),
                "network_layer_diversity_score_probe_target_only": float(network_layer_diversity_score_probe_target_only),
                "network_layer_diversity_score": float(network_layer_diversity_score),
                "network_diversity_combined": float(network_layer_diversity_score),
                "network_diversity_as_only": float(network_layer_diversity_score_as_only),
                "network_diversity_country_only": float(network_layer_diversity_score_country_only),
                "network_diversity_target_probe": float(network_layer_diversity_score_probe_target_only),
                "logical_diversity_score": float(network_layer_diversity_score),
            }
        )
    return pd.DataFrame(rows).sort_values("unit_id")


def classify_network_physical_quadrant(network_high: bool, physical_low: bool) -> str:
    """Assign a quadrant label for the network-vs-physical comparison."""
    if network_high and physical_low:
        return "network_high_physical_low"
    if network_high and not physical_low:
        return "network_high_physical_high"
    if not network_high and physical_low:
        return "network_low_physical_low"
    return "network_low_physical_high"


def build_network_diversity_metric_catalog() -> pd.DataFrame:
    """Document the supported network-diversity definitions and their paper-facing roles."""
    rows = [
        {
            "network_definition": "as_egress_primary",
            "score_column": "network_diversity_as_egress_primary",
            "metric_role": "primary_network_path_diversity",
            "interpretation": "Source-country AS-egress transition diversity across cross-border traceroute observations.",
            "recommended_for_main_text": True,
        },
        {
            "network_definition": "as_pair_primary",
            "score_column": "network_layer_diversity_score_as_only",
            "metric_role": "primary_network_path_diversity",
            "interpretation": "AS-pair and endpoint-AS diversity when explicit egress observations are sparse.",
            "recommended_for_main_text": True,
        },
        {
            "network_definition": "dst_asn_primary",
            "score_column": "network_diversity_dst_asn_primary",
            "metric_role": "endpoint_network_diversity",
            "interpretation": "Destination-side ASN diversity of observed network endpoints.",
            "recommended_for_main_text": True,
        },
        {
            "network_definition": "geographic_transition_supplementary",
            "score_column": "network_layer_diversity_score_country_only",
            "metric_role": "supplementary_geographic_descriptor",
            "interpretation": "Country-transition diversity used as a supplementary geographic descriptor, not the main network-path measure.",
            "recommended_for_main_text": False,
        },
        {
            "network_definition": "application_observation_supplementary",
            "score_column": "network_layer_diversity_score_probe_target_only",
            "metric_role": "application_observation_richness",
            "interpretation": "Probe/measurement/target multiplicity summarizing application-observation breadth.",
            "recommended_for_main_text": False,
        },
        {
            "network_definition": "combined_supplementary",
            "score_column": "network_layer_diversity_score",
            "metric_role": "supplementary_composite_score",
            "interpretation": "Composite diversity view combining AS, country, endpoint, and probe-target components.",
            "recommended_for_main_text": False,
        },
        {
            "network_definition": "composite",
            "score_column": "network_layer_diversity_score",
            "metric_role": "legacy_compatibility_alias",
            "interpretation": "Backward-compatible alias for the historical composite network diversity score.",
            "recommended_for_main_text": False,
        },
        {
            "network_definition": "as_only",
            "score_column": "network_layer_diversity_score_as_only",
            "metric_role": "legacy_compatibility_alias",
            "interpretation": "Backward-compatible alias for the historical AS-only network diversity score.",
            "recommended_for_main_text": False,
        },
        {
            "network_definition": "country_only",
            "score_column": "network_layer_diversity_score_country_only",
            "metric_role": "legacy_compatibility_alias",
            "interpretation": "Backward-compatible alias for the historical country-only network diversity score.",
            "recommended_for_main_text": False,
        },
        {
            "network_definition": "probe_target_only",
            "score_column": "network_layer_diversity_score_probe_target_only",
            "metric_role": "legacy_compatibility_alias",
            "interpretation": "Backward-compatible alias for the historical probe-target-only observation score.",
            "recommended_for_main_text": False,
        },
    ]
    return pd.DataFrame(rows)


def build_unit_network_physical_mismatch(
    network_frame: pd.DataFrame,
    physical_frame: pd.DataFrame,
    physical_level: str,
    network_score_column: str = "network_layer_diversity_score",
    network_definition: str = "composite",
) -> pd.DataFrame:
    """Join network-layer and physical diversity metrics and classify quadrants."""
    if (
        network_frame.empty
        or physical_frame.empty
        or "unit_id" not in network_frame.columns
        or "unit_id" not in physical_frame.columns
    ):
        return pd.DataFrame(columns=["unit_id", "physical_level", "network_definition"])
    merged = network_frame.merge(physical_frame, on="unit_id", how="inner")
    if merged.empty:
        return merged

    if network_score_column not in merged.columns:
        network_score_column = "network_layer_diversity_score"

    merged["selected_network_diversity_score"] = pd.to_numeric(merged[network_score_column], errors="coerce").fillna(0.0)
    network_median = merged["selected_network_diversity_score"].median()
    physical_median = merged["physical_candidate_diversity_score"].median()
    merged["network_high"] = merged["selected_network_diversity_score"] >= network_median
    merged["physical_low"] = merged["physical_candidate_diversity_score"] <= physical_median
    merged["network_physical_mismatch_category"] = merged.apply(
        lambda row: classify_network_physical_quadrant(bool(row["network_high"]), bool(row["physical_low"])),
        axis=1,
    )
    merged["network_physical_gap"] = (
        merged["selected_network_diversity_score"] - merged["physical_candidate_diversity_score"]
    )
    merged["network_diversity_percentile"] = merged["selected_network_diversity_score"].rank(
        method="average", pct=True, ascending=True
    )
    merged["physical_diversity_percentile"] = merged["physical_candidate_diversity_score"].rank(
        method="average", pct=True, ascending=True
    )
    merged["network_physical_percentile_gap"] = (
        merged["network_diversity_percentile"] - merged["physical_diversity_percentile"]
    )
    merged["network_diversity_rank"] = merged["selected_network_diversity_score"].rank(
        method="dense", ascending=False
    )
    merged["physical_diversity_rank"] = merged["physical_candidate_diversity_score"].rank(
        method="dense", ascending=False
    )
    merged["network_physical_rank_gap"] = merged["physical_diversity_rank"] - merged["network_diversity_rank"]
    merged["logical_physical_gap"] = merged["network_physical_gap"]
    merged["logical_high"] = merged["network_high"]
    merged["mismatch_category"] = merged["network_physical_mismatch_category"]
    merged["physical_level"] = physical_level
    merged["network_definition"] = network_definition
    merged["network_score_column"] = network_score_column
    merged["is_target_quadrant"] = (
        merged["network_physical_mismatch_category"] == LEGACY_WEIGHTED_TARGET_MISMATCH_CATEGORY
    )

    merged["network_physical_mismatch_category"] = pd.Categorical(
        merged["network_physical_mismatch_category"],
        categories=QUADRANT_ORDER,
        ordered=True,
    )
    return merged.sort_values(["network_physical_mismatch_category", "unit_id"]).reset_index(drop=True)


def build_quadrant_summary(mismatch_frame: pd.DataFrame, physical_level: str) -> pd.DataFrame:
    """Summarize quadrant counts and shares."""
    if mismatch_frame.empty:
        return pd.DataFrame(columns=["physical_level", "network_physical_mismatch_category", "unit_count", "unit_share"])

    counts = mismatch_frame["network_physical_mismatch_category"].value_counts().reindex(QUADRANT_ORDER, fill_value=0)
    total = int(counts.sum())
    rows = [
        {
            "physical_level": physical_level,
            "network_physical_mismatch_category": category,
            "unit_count": int(count),
            "unit_share": float(count / total) if total > 0 else 0.0,
        }
        for category, count in counts.items()
    ]
    return pd.DataFrame(rows)


def build_cable_corridor_comparison(
    cable_physical: pd.DataFrame,
    corridor_physical: pd.DataFrame,
    cable_mismatch: pd.DataFrame,
    corridor_mismatch: pd.DataFrame,
) -> pd.DataFrame:
    """Compare cable-level and corridor-level diversity and quadrant labels."""
    if cable_physical.empty or corridor_physical.empty or "unit_id" not in cable_physical.columns or "unit_id" not in corridor_physical.columns:
        return pd.DataFrame(columns=["unit_id", "corridor_minus_cable_physical_diversity"])
    cable_named = cable_physical.rename(
        columns={
            "dominant_candidate_key": "cable_dominant_candidate_key",
            "dominant_candidate_support_share": "cable_dominant_candidate_support_share",
            "expected_candidate_support_total": "cable_expected_candidate_support_total",
            "candidate_entropy": "cable_candidate_entropy",
            "effective_num_candidates": "cable_effective_num_candidates",
            "gini_candidate_support": "cable_gini_candidate_support",
            "num_candidates_with_support": "cable_num_candidates_with_support",
            "num_matched_links": "cable_num_matched_links",
            "num_probes": "cable_num_probes",
            "physical_candidate_diversity_score": "cable_physical_candidate_diversity_score",
        }
    )
    corridor_named = corridor_physical.rename(
        columns={
            "dominant_candidate_key": "corridor_dominant_candidate_key",
            "dominant_candidate_support_share": "corridor_dominant_candidate_support_share",
            "expected_candidate_support_total": "corridor_expected_candidate_support_total",
            "candidate_entropy": "corridor_candidate_entropy",
            "effective_num_candidates": "corridor_effective_num_candidates",
            "gini_candidate_support": "corridor_gini_candidate_support",
            "num_candidates_with_support": "corridor_num_candidates_with_support",
            "num_matched_links": "corridor_num_matched_links",
            "num_probes": "corridor_num_probes",
            "physical_candidate_diversity_score": "corridor_physical_candidate_diversity_score",
        }
    )
    cable_mismatch_named = cable_mismatch[
        ["unit_id", "network_physical_mismatch_category", "is_target_quadrant"]
    ].rename(
        columns={
            "network_physical_mismatch_category": "cable_network_physical_mismatch_category",
            "is_target_quadrant": "cable_is_target_quadrant",
        }
    )
    corridor_mismatch_named = corridor_mismatch[
        ["unit_id", "network_physical_mismatch_category", "is_target_quadrant"]
    ].rename(
        columns={
            "network_physical_mismatch_category": "corridor_network_physical_mismatch_category",
            "is_target_quadrant": "corridor_is_target_quadrant",
        }
    )

    merged = cable_named.merge(corridor_named, on="unit_id", how="inner")
    merged = merged.merge(cable_mismatch_named, on="unit_id", how="left")
    merged = merged.merge(corridor_mismatch_named, on="unit_id", how="left")
    merged["corridor_minus_cable_physical_diversity"] = (
        merged["corridor_physical_candidate_diversity_score"] - merged["cable_physical_candidate_diversity_score"]
    )
    merged["corridor_vs_cable_effective_num_ratio"] = np.where(
        merged["cable_effective_num_candidates"] > 0,
        merged["corridor_effective_num_candidates"] / merged["cable_effective_num_candidates"],
        0.0,
    )
    merged["target_quadrant_preserved"] = (
        merged["cable_is_target_quadrant"].fillna(False) & merged["corridor_is_target_quadrant"].fillna(False)
    )
    merged["quadrant_label_stable"] = (
        merged["cable_network_physical_mismatch_category"].astype(str)
        == merged["corridor_network_physical_mismatch_category"].astype(str)
    )
    return merged.sort_values("unit_id").reset_index(drop=True)


def build_unit_network_physical_upper_bound_mismatch(
    network_frame: pd.DataFrame,
    physical_frames: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Build long-form mismatch rows by comparing network diversity against conservative feasible-set upper bounds."""
    rows: List[pd.DataFrame] = []
    if network_frame.empty or "unit_id" not in network_frame.columns:
        return pd.DataFrame(columns=["unit_id", "network_definition", "physical_level", "candidate_view"])
    for physical_level, physical_frame in physical_frames.items():
        if physical_frame.empty or "unit_id" not in physical_frame.columns:
            continue
        merged = network_frame.merge(physical_frame, on="unit_id", how="inner")
        if merged.empty:
            continue

        for network_definition, network_score_column in NETWORK_DEFINITION_COLUMNS.items():
            if network_score_column not in merged.columns:
                continue
            current = merged.copy()
            current["network_definition"] = network_definition
            current["physical_level"] = physical_level
            current["candidate_view"] = "conservative_set"
            current["physical_diversity_view"] = "upper_bound"
            current["network_diversity_score"] = pd.to_numeric(current[network_score_column], errors="coerce").fillna(0.0)
            current["selected_network_diversity_score"] = current["network_diversity_score"]
            current["network_score_column"] = network_score_column
            current["network_percentile"] = current["network_diversity_score"].rank(method="average", pct=True, ascending=True)
            current["physical_upper_bound_percentile"] = current["physical_candidate_diversity_upper_bound"].rank(
                method="average", pct=True, ascending=True
            )
            current["network_rank_upper_bound"] = current["network_diversity_score"].rank(method="dense", ascending=False)
            current["physical_upper_rank"] = current["physical_candidate_diversity_upper_bound"].rank(method="dense", ascending=False)
            current["rank_gap_upper_bound"] = current["physical_upper_rank"] - current["network_rank_upper_bound"]
            current["network_physical_upper_bound_percentile_gap"] = (
                current["network_percentile"] - current["physical_upper_bound_percentile"]
            )
            current["network_high"] = current["network_percentile"] >= 0.5
            current["physical_upper_low"] = current["physical_upper_bound_percentile"] <= 0.5
            current["upper_bound_mismatch_category"] = np.where(
                current["network_high"] & current["physical_upper_low"],
                "network_high_physical_upper_low",
                np.where(
                    current["network_high"] & ~current["physical_upper_low"],
                    "network_high_physical_upper_high",
                    np.where(
                        ~current["network_high"] & current["physical_upper_low"],
                        "network_low_physical_upper_low",
                        "network_low_physical_upper_high",
                    ),
                ),
            )
            current["strict_upper_bound_mismatch_75_25"] = (
                (current["network_percentile"] >= 0.75)
                & (current["physical_upper_bound_percentile"] <= 0.25)
            )
            rows.append(
                current[
                    [
                        "unit_id",
                        "src_country",
                        "network_definition",
                        "physical_level",
                        "candidate_view",
                        "physical_diversity_view",
                        "network_score_column",
                        "selected_network_diversity_score",
                        "network_diversity_score",
                        "network_diversity_combined",
                        "network_diversity_as_only",
                        "network_diversity_country_only",
                        "network_diversity_target_probe",
                        "network_diversity_as_egress_primary",
                        "network_diversity_dst_asn_primary",
                        "physical_candidate_diversity_upper_bound",
                        "network_percentile",
                        "physical_upper_bound_percentile",
                        "network_rank_upper_bound",
                        "physical_upper_rank",
                        "rank_gap_upper_bound",
                        "network_physical_upper_bound_percentile_gap",
                        "network_high",
                        "physical_upper_low",
                        "upper_bound_mismatch_category",
                        "strict_upper_bound_mismatch_75_25",
                        *[
                            column
                            for column in current.columns
                            if column.startswith("pdb_")
                        ],
                    ]
                ]
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "unit_id",
                "src_country",
                "network_definition",
                "physical_level",
                "candidate_view",
                "physical_diversity_view",
                "network_score_column",
                "selected_network_diversity_score",
                "network_diversity_score",
                "network_diversity_combined",
                "network_diversity_as_only",
                "network_diversity_country_only",
                "network_diversity_target_probe",
                "network_diversity_as_egress_primary",
                "network_diversity_dst_asn_primary",
                "physical_candidate_diversity_upper_bound",
                "network_percentile",
                "physical_upper_bound_percentile",
                "network_rank_upper_bound",
                "physical_upper_rank",
                "rank_gap_upper_bound",
                "network_physical_upper_bound_percentile_gap",
                "network_high",
                "physical_upper_low",
                "upper_bound_mismatch_category",
                "strict_upper_bound_mismatch_75_25",
            ]
        )
    return pd.concat(rows, ignore_index=True).sort_values(
        ["network_definition", "physical_level", "unit_id"]
    ).reset_index(drop=True)


def build_candidate_space_profile(frame: pd.DataFrame, corridor_candidate_col: str) -> pd.DataFrame:
    """Profile how much ambiguity is preserved inside the feasible candidate space for each unit."""
    columns = [
        "unit_id",
        "num_links",
        "num_links_with_feasible_candidates",
        "avg_feasible_candidates_per_link",
        "median_feasible_candidates_per_link",
        "max_feasible_candidates_per_link",
        "avg_feasible_corridors_per_link",
        "median_feasible_corridors_per_link",
        "max_feasible_corridors_per_link",
        "share_links_with_parallel_ambiguity",
        "share_links_with_many_candidates",
        "share_links_with_large_landing_radius",
        "share_links_with_rtt_inconclusive",
        "share_links_with_multi_segment_possible",
        "share_links_with_domestic_submarine_candidate",
        "share_links_with_only_low_support_feasible_candidates",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    working = frame.copy()
    working["ambiguity_tags_list"] = working.get("ambiguity_tags", pd.Series(index=working.index, dtype=object)).apply(safe_parse_tags)
    if "projection_class" not in working.columns:
        working["projection_class"] = "ambiguous"

    link_rows: List[Dict[str, Any]] = []
    for (unit_id, link_id), group in working.groupby(["unit_id", "link_id"], dropna=False):
        link_rows.append(
            {
                "unit_id": unit_id,
                "link_id": link_id,
                "candidate_count": int(group["cable_id"].astype(str).replace("nan", np.nan).dropna().nunique()) if "cable_id" in group.columns else int(len(group)),
                "corridor_count": int(group[corridor_candidate_col].astype(str).replace("nan", np.nan).dropna().nunique()),
                "has_parallel_ambiguity": bool(
                    group["ambiguity_tags_list"].apply(lambda tags: "parallel_candidate_corridor" in tags).any()
                ) or bool(group.get("is_parallel_ambiguous", pd.Series(index=group.index, dtype=object)).fillna(False).astype(bool).any()),
                "has_many_candidates": bool(
                    group["ambiguity_tags_list"].apply(lambda tags: "many_candidates" in tags).any()
                ) or int(group["cable_id"].astype(str).replace("nan", np.nan).dropna().nunique()) > 5,
                "has_large_radius": bool(
                    group["ambiguity_tags_list"].apply(lambda tags: "large_landing_radius" in tags).any()
                ),
                "has_rtt_inconclusive": bool(
                    group["ambiguity_tags_list"].apply(lambda tags: "rtt_inconclusive" in tags).any()
                ),
                "has_multi_segment_possible": bool(
                    group["ambiguity_tags_list"].apply(lambda tags: "multi_segment_possible" in tags).any()
                ),
                "has_domestic_submarine": bool(
                    group["ambiguity_tags_list"].apply(lambda tags: "domestic_submarine_candidate" in tags).any()
                ),
                "only_low_support_feasible": bool(
                    "support_above_threshold" in group.columns
                    and not group["support_above_threshold"].fillna(False).astype(bool).any()
                ),
            }
        )

    link_frame = pd.DataFrame(link_rows)
    rows: List[Dict[str, Any]] = []
    for unit_id, group in link_frame.groupby("unit_id", dropna=False):
        rows.append(
            {
                "unit_id": unit_id,
                "num_links": int(len(group)),
                "num_links_with_feasible_candidates": int(len(group)),
                "avg_feasible_candidates_per_link": float(group["candidate_count"].mean()),
                "median_feasible_candidates_per_link": float(group["candidate_count"].median()),
                "max_feasible_candidates_per_link": int(group["candidate_count"].max()),
                "avg_feasible_corridors_per_link": float(group["corridor_count"].mean()),
                "median_feasible_corridors_per_link": float(group["corridor_count"].median()),
                "max_feasible_corridors_per_link": int(group["corridor_count"].max()),
                "share_links_with_parallel_ambiguity": float(group["has_parallel_ambiguity"].mean()),
                "share_links_with_many_candidates": float(group["has_many_candidates"].mean()),
                "share_links_with_large_landing_radius": float(group["has_large_radius"].mean()),
                "share_links_with_rtt_inconclusive": float(group["has_rtt_inconclusive"].mean()),
                "share_links_with_multi_segment_possible": float(group["has_multi_segment_possible"].mean()),
                "share_links_with_domestic_submarine_candidate": float(group["has_domestic_submarine"].mean()),
                "share_links_with_only_low_support_feasible_candidates": float(group["only_low_support_feasible"].mean()),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("unit_id").reset_index(drop=True)


def build_weighted_vs_conservative_diversity(
    weighted_frames: Dict[str, pd.DataFrame],
    uniform_frames: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Compare weighted expectation metrics with conservative feasible-set diversity for each physical level."""
    frames: List[pd.DataFrame] = []
    for physical_level, weighted_frame in weighted_frames.items():
        uniform_frame = uniform_frames.get(physical_level, pd.DataFrame())
        if weighted_frame.empty or uniform_frame.empty:
            continue
        merged = weighted_frame.merge(
            uniform_frame[
                [
                    "unit_id",
                    "physical_level",
                    "feasible_candidate_count",
                    "candidate_entropy_uniform",
                    "effective_candidate_count_uniform",
                    "feasible_corridor_count",
                    "corridor_entropy_uniform",
                    "effective_corridor_count_uniform",
                ]
            ].rename(
                columns={
                    "feasible_candidate_count": "uniform_feasible_candidate_count",
                    "candidate_entropy_uniform": "uniform_candidate_entropy_cable",
                    "effective_candidate_count_uniform": "uniform_effective_candidate_count_cable",
                    "feasible_corridor_count": "uniform_feasible_corridor_count",
                    "corridor_entropy_uniform": "uniform_candidate_entropy_corridor",
                    "effective_corridor_count_uniform": "uniform_effective_candidate_count_corridor",
                }
            ),
            on=["unit_id", "physical_level"],
            how="inner",
        )
        if merged.empty:
            continue
        if physical_level == "corridor":
            merged["uniform_effective_num_candidates"] = pd.to_numeric(
                merged["uniform_effective_candidate_count_corridor"], errors="coerce"
            ).fillna(0.0)
            merged["uniform_candidate_entropy"] = pd.to_numeric(
                merged["uniform_candidate_entropy_corridor"], errors="coerce"
            ).fillna(0.0)
            merged["feasible_candidate_count_out"] = pd.to_numeric(merged["uniform_feasible_corridor_count"], errors="coerce").fillna(0.0)
        else:
            merged["uniform_effective_num_candidates"] = pd.to_numeric(
                merged["uniform_effective_candidate_count_cable"], errors="coerce"
            ).fillna(0.0)
            merged["uniform_candidate_entropy"] = pd.to_numeric(
                merged["uniform_candidate_entropy_cable"], errors="coerce"
            ).fillna(0.0)
            merged["feasible_candidate_count_out"] = pd.to_numeric(merged["uniform_feasible_candidate_count"], errors="coerce").fillna(0.0)

        merged["weighted_effective_num_candidates"] = pd.to_numeric(merged["effective_num_candidates"], errors="coerce").fillna(0.0)
        merged["weighted_candidate_entropy"] = pd.to_numeric(merged["candidate_entropy"], errors="coerce").fillna(0.0)
        merged["weighted_dominant_support_share"] = pd.to_numeric(merged["dominant_candidate_support_share"], errors="coerce").fillna(0.0)
        merged["weighted_minus_uniform_effective_num"] = (
            merged["weighted_effective_num_candidates"] - merged["uniform_effective_num_candidates"]
        )
        merged["weighted_to_uniform_ratio"] = np.where(
            merged["uniform_effective_num_candidates"] > 0,
            merged["weighted_effective_num_candidates"] / merged["uniform_effective_num_candidates"],
            0.0,
        )
        merged["interpretation"] = merged.apply(
            lambda row: (
                "robust_candidate_concentration"
                if row["uniform_effective_num_candidates"] <= 2 and row["weighted_effective_num_candidates"] <= 2
                else (
                    "support_weight_driven_concentration"
                    if row["uniform_effective_num_candidates"] > 2 and row["weighted_effective_num_candidates"] <= 2
                    else (
                        "check_inconsistent_support_distribution"
                        if row["uniform_effective_num_candidates"] <= 2 and row["weighted_effective_num_candidates"] > 2
                        else "no_clear_concentration"
                    )
                )
            ),
            axis=1,
        )
        frames.append(
            merged[
                [
                    "unit_id",
                    "physical_level",
                    "weighted_effective_num_candidates",
                    "weighted_candidate_entropy",
                    "weighted_dominant_support_share",
                    "uniform_effective_num_candidates",
                    "uniform_candidate_entropy",
                    "feasible_candidate_count_out",
                    "weighted_minus_uniform_effective_num",
                    "weighted_to_uniform_ratio",
                    "interpretation",
                ]
            ].rename(columns={"feasible_candidate_count_out": "feasible_candidate_count"})
        )

    if not frames:
        return pd.DataFrame(
            columns=[
                "unit_id",
                "physical_level",
                "weighted_effective_num_candidates",
                "weighted_candidate_entropy",
                "weighted_dominant_support_share",
                "uniform_effective_num_candidates",
                "uniform_candidate_entropy",
                "feasible_candidate_count",
                "weighted_minus_uniform_effective_num",
                "weighted_to_uniform_ratio",
                "interpretation",
            ]
        )
    return pd.concat(frames, ignore_index=True).sort_values(["physical_level", "unit_id"]).reset_index(drop=True)


def build_peeringdb_footprint_mismatch_summary(upper_bound_mismatch: pd.DataFrame) -> pd.DataFrame:
    """Summarize strict upper-bound mismatch rates by PeeringDB footprint tier."""
    columns = [
        "pdb_interconnection_footprint_tier",
        "physical_level",
        "network_definition",
        "num_units",
        "strict_upper_bound_mismatch_units",
        "strict_upper_bound_mismatch_share",
        "median_network_percentile",
        "median_physical_upper_bound_percentile",
        "median_rank_gap",
    ]
    if upper_bound_mismatch.empty or "pdb_interconnection_footprint_tier" not in upper_bound_mismatch.columns:
        return pd.DataFrame(columns=columns)

    working = upper_bound_mismatch.copy()
    working["pdb_interconnection_footprint_tier"] = (
        working["pdb_interconnection_footprint_tier"].fillna("unknown").astype(str)
    )
    if "rank_gap_upper_bound" not in working.columns:
        working["rank_gap_upper_bound"] = 0.0
    grouped = (
        working.groupby(["pdb_interconnection_footprint_tier", "physical_level", "network_definition"], dropna=False)
        .agg(
            num_units=("unit_id", "nunique"),
            strict_upper_bound_mismatch_units=("strict_upper_bound_mismatch_75_25", "sum"),
            median_network_percentile=("network_percentile", "median"),
            median_physical_upper_bound_percentile=("physical_upper_bound_percentile", "median"),
            median_rank_gap=("rank_gap_upper_bound", "median"),
        )
        .reset_index()
    )
    grouped["strict_upper_bound_mismatch_share"] = np.where(
        grouped["num_units"] > 0,
        grouped["strict_upper_bound_mismatch_units"] / grouped["num_units"],
        0.0,
    )
    return grouped[columns].sort_values(
        ["pdb_interconnection_footprint_tier", "physical_level", "network_definition"]
    ).reset_index(drop=True)


def build_unit_ambiguity_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-unit ambiguity support shares into a wide profile table."""
    columns = [
        "unit_id",
        "num_candidate_rows",
        "num_links",
    ] + [f"{tag}_support_share" for tag in KNOWN_AMBIGUITY_TAGS] + ["no_ambiguity_support_share"]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    working = frame.copy()
    working["ambiguity_tags_list"] = working["ambiguity_tags"].apply(safe_parse_tags)
    working["support_value"] = build_support_series(working)

    rows: List[Dict[str, Any]] = []
    for unit_id, group in working.groupby("unit_id", dropna=False):
        row: Dict[str, Any] = {
            "unit_id": unit_id,
            "num_candidate_rows": int(len(group)),
            "num_links": int(group["link_id"].nunique()) if "link_id" in group.columns else 0,
        }
        total_support = float(group["support_value"].sum())
        for tag in KNOWN_AMBIGUITY_TAGS:
            tagged_support = float(
                group.loc[group["ambiguity_tags_list"].apply(lambda tags: tag in tags), "support_value"].sum()
            )
            row[f"{tag}_support_share"] = float(tagged_support / total_support) if total_support > 0 else 0.0
        no_ambiguity_support = float(
            group.loc[group["ambiguity_tags_list"].apply(lambda tags: len(tags) == 0), "support_value"].sum()
        )
        row["no_ambiguity_support_share"] = float(no_ambiguity_support / total_support) if total_support > 0 else 0.0
        rows.append(row)
    return pd.DataFrame(rows, columns=columns).sort_values("unit_id").reset_index(drop=True)


def build_ambiguity_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate global ambiguity counts and support shares, including no_ambiguity."""
    columns = [
        "ambiguity_class",
        "candidate_rows",
        "candidate_row_share",
        "aggregate_normalized_support",
        "aggregate_support_share",
        "units_affected",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    working = frame.copy()
    working["ambiguity_tags_list"] = working["ambiguity_tags"].apply(safe_parse_tags)
    working["support_value"] = build_support_series(working)
    total_rows = max(len(working), 1)
    total_support = float(working["support_value"].sum())

    summary_rows: List[Dict[str, Any]] = []
    all_classes = list(KNOWN_AMBIGUITY_TAGS) + ["no_ambiguity"]
    for ambiguity_class in all_classes:
        if ambiguity_class == "no_ambiguity":
            mask = working["ambiguity_tags_list"].apply(lambda tags: len(tags) == 0)
        else:
            mask = working["ambiguity_tags_list"].apply(lambda tags: ambiguity_class in tags)
        subset = working.loc[mask]
        candidate_rows = int(len(subset))
        aggregate_support = float(subset["support_value"].sum())
        summary_rows.append(
            {
                "ambiguity_class": ambiguity_class,
                "candidate_rows": candidate_rows,
                "candidate_row_share": float(candidate_rows / total_rows),
                "aggregate_normalized_support": aggregate_support,
                "aggregate_support_share": float(aggregate_support / total_support) if total_support > 0 else 0.0,
                "units_affected": int(subset["unit_id"].nunique()) if "unit_id" in subset.columns else 0,
            }
        )
    return pd.DataFrame(summary_rows, columns=columns).sort_values("ambiguity_class").reset_index(drop=True)


def build_ambiguity_taxonomy() -> pd.DataFrame:
    """Return the fixed ambiguity taxonomy used for interpretation."""
    return pd.DataFrame(
        [
            {
                "ambiguity_class": "parallel_candidate_corridor",
                "reviewer_concern": "parallel cables cannot be reliably distinguished",
                "treatment": "corridor-level aggregation",
                "interpretation_boundary": "no per-cable ground-truth claim",
            },
            {
                "ambiguity_class": "multi_segment_possible",
                "reviewer_concern": "hop transition may hide multiple submarine segments",
                "treatment": "tag and inspect through robustness/profile",
                "interpretation_boundary": "aggregate-only interpretation",
            },
            {
                "ambiguity_class": "domestic_submarine_candidate",
                "reviewer_concern": "same-country paths may still use submarine cable infrastructure",
                "treatment": "separate ambiguity tag and profile",
                "interpretation_boundary": "not treated as purely terrestrial",
            },
            {
                "ambiguity_class": "large_landing_radius",
                "reviewer_concern": "IP geolocation uncertainty",
                "treatment": "weaker confidence and high-confidence subset/profile",
                "interpretation_boundary": "not a high-confidence per-path attribution",
            },
            {
                "ambiguity_class": "rtt_inconclusive",
                "reviewer_concern": "RTT feasibility boundary is weak",
                "treatment": "ambiguity tag",
                "interpretation_boundary": "no strong candidate attribution",
            },
            {
                "ambiguity_class": "many_candidates",
                "reviewer_concern": "underdetermined candidate set",
                "treatment": "preserve candidate-support distribution",
                "interpretation_boundary": "no forced top-1 attribution",
            },
            {
                "ambiguity_class": "geo_dominant_as_weak",
                "reviewer_concern": "spatial evidence and AS-economic evidence disagree",
                "treatment": "core-disagreement tag",
                "interpretation_boundary": "evidence disagreement retained",
            },
            {
                "ambiguity_class": "as_dominant_geo_ambiguous",
                "reviewer_concern": "AS-economic evidence stronger than spatial evidence",
                "treatment": "core-disagreement tag",
                "interpretation_boundary": "evidence disagreement retained",
            },
        ]
    )


def build_method_manifest() -> Dict[str, Any]:
    """Return the method manifest used to interpret post-processing outputs."""
    return {
        "method_name": "application_network_corridor_distribution_audit",
        "main_question": "whether application-visible network-transition diversity remains broad after projection onto feasible submarine-cable corridors",
        "claim_boundary": "feasible corridor support and observation concentration, not ground-truth cable attribution",
        "primary_analysis_unit": "probe_country_x_service_id",
        "primary_atomic_unit": "mappable hop-pair network-transition segment",
        "primary_physical_level": "landing_region_pair_corridor",
        "primary_projection": "uniform observation mass across feasible corridors",
        "primary_network_distribution": "network transitions over the same mappable atomic segments",
        "network_transition_distribution_note": "N_u(t) counts each unique atomic segment once; q_u(t) is emitted as share_of_network_transition_observations, with an explicit country_fallback representation whenever either endpoint ASN is unavailable",
        "network_corridor_population_alignment": "network_corridor_segment_population_alignment.csv verifies that q_u(t) and corridor p_u(c) use identical atomic segment sets",
        "primary_cross_layer_class": "network_broad_physical_concentrated",
        "peeringdb_descriptor_note": "PeeringDB descriptors are external interconnection-footprint descriptors only and are not used for physical-candidate construction or candidate-support scoring",
        "segment_projection_note": "Traceroutes are decomposed into independently mappable path-transition segments; paper-facing service-country outputs are grouped by probe_country and service_id, while transition-country outputs are supplementary geography views",
        "corridor_observation_note": "Corridor observation concentration measures whether measurement-observed path-transition segments concentrate on a small number of feasible corridor candidates",
        "observation_mass_note": "Observation mass reflects traceroute-observed path-transition segments and must not be interpreted as byte or packet traffic volume",
        "candidate_support_note": "candidate_support and normalized_candidate_support are supplementary evidence scores inside the feasible set, not true cable-use probabilities",
        "paper_case_thresholds": {
            "minimum_mappable_segments": MINIMUM_MAPPABLE_SEGMENTS,
            "minimum_unique_probes": MINIMUM_UNIQUE_PROBES,
            "minimum_unique_probe_asns": MINIMUM_UNIQUE_PROBE_ASNS,
            "maximum_country_fallback_share": MAXIMUM_COUNTRY_FALLBACK_SHARE,
        },
        "ambiguity_classes": [
            "parallel_candidate_corridor",
            "many_candidates",
            "large_landing_radius",
            "rtt_inconclusive",
            "domestic_submarine_candidate",
            "multi_segment_possible",
            "geo_dominant_as_weak",
            "as_dominant_geo_ambiguous",
        ],
        "primary_outputs": [
            "paper_service_country_physical_exposure.csv",
            "paper_service_country_geography_candidate_dependency.csv",
            "paper_service_country_corridor_concentration.csv",
            "paper_service_country_cross_layer_distribution.csv",
            "paper_network_broad_physical_concentrated_cases.csv",
            "paper_broad_corridor_distribution_cases.csv",
            "paper_physical_exposure_cases.csv",
            "service_country_corridor_observation_distribution.csv",
            "service_country_network_transition_distribution.csv",
            "network_corridor_segment_population_alignment.csv",
            "service_country_corridor_concentration_summary.csv",
            "service_country_network_transition_concentration_summary.csv",
            "service_country_cross_layer_distribution_audit.csv",
        ],
        "supplementary_views": [
            "cable_level_support",
            "exact_landing_pair",
            "support_weighted_projection",
            "as_owner_reranking",
            "candidate_breadth",
            "best_case_candidate_upper_bound",
            "network_to_physical_compression",
            "rank_and_percentile_mismatch",
        ],
        "supplementary_outputs": [
            "country_geography_candidate_dependency.csv",
            "country_network_transition_distribution.csv",
            "service_country_geography_candidate_dependency.csv",
            "geography_type_candidate_dependency_summary.csv",
            "country_geography_catalog_resolved.csv",
            "country_geography_dependency_manifest.json",
            "unit_network_layer_diversity.csv",
            "trace_candidate_support.csv",
            "unit_cross_layer_audit.csv",
            "country_cross_layer_audit.csv",
            "paper_country_cross_layer_audit.csv",
            "paper_service_country_cross_layer_audit.csv",
            "unit_physical_candidate_diversity_cable.csv",
            "unit_physical_candidate_diversity_corridor.csv",
            "unit_physical_candidate_set_diversity_cable.csv",
            "unit_physical_candidate_set_diversity_corridor.csv",
            "unit_physical_candidate_upper_bound.csv",
            "unit_network_physical_mismatch.csv",
            "unit_network_physical_mismatch_corridor.csv",
            "unit_network_physical_upper_bound_mismatch.csv",
            "paper_unit_physical_candidate_diversity.csv",
            "paper_unit_network_physical_mismatch.csv",
            "network_diversity_metric_catalog.csv",
            "country_peeringdb_descriptors.csv",
            "peeringdb_footprint_mismatch_summary.csv",
            "network_physical_quadrants.csv",
            "cable_vs_corridor_physical_diversity.csv",
            "candidate_space_profile.csv",
            "weighted_vs_conservative_diversity.csv",
            "ambiguity_taxonomy.csv",
            "ambiguity_summary.csv",
            "unit_ambiguity_profile.csv",
            "supplementary_owner_concentration.csv",
        ],
        "legacy_supplementary_outputs": [
            "paper_unit_physical_candidate_diversity.csv",
            "paper_unit_network_physical_mismatch.csv",
            "paper_country_cross_layer_audit.csv",
            "paper_service_country_cross_layer_audit.csv",
            "paper_physical_concentration_cases.csv",
            "paper_joint_mismatch_cases.csv",
            "paper_broad_physical_space_cases.csv",
        ],
        "legacy_supplementary_note": "These compatibility files report candidate-set breadth, compression, or rank/percentile views. They are not the paper-primary corridor observation concentration outputs.",
        "network_definitions": list(NETWORK_DEFINITION_COLUMNS.keys()),
        "interpretation": "application-visible path-transition observations projected onto feasible corridor groups with ambiguity preserved",
    }


def build_conservative_candidate_audit_manifest() -> Dict[str, Any]:
    """Return a compact manifest for the infeasibility-first conservative candidate audit view."""
    return {
        "pipeline_version": "infeasibility_first_conservative_candidate_audit_v1",
        "interpretation": "application_network_corridor_distribution_audit",
        "support_semantics": "evidence support, not ground-truth probability",
        "weighted_view_description": "support-thresholded candidate-support view retained as supplementary evidence/reranking analysis",
        "conservative_set_view_description": "all hard-feasible candidates are retained before support thresholding; paper-primary observation mass is uniform across feasible corridors per atomic segment",
        "primary_cross_layer_metrics": "service physical exposure, corridor observation concentration, and network-vs-corridor distribution class",
        "relative_comparison_metrics": "rank and percentile mismatch outputs remain auxiliary relative comparison views over the chosen corpus",
        "single_country_and_global_support": "the same best-case physical-candidate audit metrics apply to both single-country studies and multi-country corpora",
        "candidate_breadth_interpretation": "best-case feasible candidate counts describe candidate-space breadth, not the paper-primary observation-mass concentration metric",
        "network_physical_compression_interpretation": "network-to-physical compression is retained as a supplementary non-rank descriptor, while paper-primary concentration uses corridor observation distributions",
        "physical_exposure_note": "no network-to-physical compression does not imply no physical-candidate exposure",
        "peeringdb_descriptor_note": "PeeringDB descriptors are external interconnection-footprint descriptors only and are not used for physical-candidate construction or candidate-support scoring",
        "segment_projection_note": "Traceroutes are decomposed into independently mappable path-transition segments anchored to the near-side country of each transition",
        "corridor_observation_note": "Corridor observation concentration measures whether measurement-observed path-transition segments concentrate on a small number of feasible corridor candidates",
        "observation_mass_note": "Observation mass reflects traceroute-observed path-transition segments and must not be interpreted as byte or packet traffic volume",
        "candidate_breadth_note": "Unique feasible corridor count remains a candidate-breadth descriptor rather than the paper-primary observation concentration metric",
        "primary_analysis_unit": "probe_country_x_service_id",
        "primary_physical_level": "landing_region_pair_corridor",
        "primary_projection": "uniform_observation_mass",
        "primary_network_distribution": "network transitions over same atomic segment population",
        "network_transition_distribution_note": "N_u(t) counts each unique atomic segment once; q_u(t) is the normalized share_of_network_transition_observations, with missing endpoint ASNs retained through an explicit country fallback",
        "network_corridor_population_alignment": "network_corridor_segment_population_alignment.csv asserts identical atomic segment sets for the network and corridor representations",
        "legacy_all_segments_semantics": "support-thresholded legacy candidate list",
        "all_feasible_segments_semantics": "all hard-feasible candidates preserved before support thresholding",
        "primary_outputs": [
            "paper_service_country_physical_exposure.csv",
            "paper_service_country_geography_candidate_dependency.csv",
            "paper_service_country_corridor_concentration.csv",
            "paper_service_country_cross_layer_distribution.csv",
            "paper_network_broad_physical_concentrated_cases.csv",
            "paper_broad_corridor_distribution_cases.csv",
        ],
        "supplementary_views": [
            "cable_level_support",
            "exact_landing_pair",
            "support_weighted_projection",
            "as_owner_reranking",
            "candidate_breadth",
            "best_case_candidate_upper_bound",
            "network_to_physical_compression",
            "rank_and_percentile_mismatch",
        ],
        "generated_outputs": [
            "country_geography_candidate_dependency.csv",
            "service_country_geography_candidate_dependency.csv",
            "geography_type_candidate_dependency_summary.csv",
            "paper_service_country_geography_candidate_dependency.csv",
            "country_geography_catalog_resolved.csv",
            "country_geography_dependency_manifest.json",
            "trace_feasible_candidate_space.csv",
            "unit_cross_layer_audit.csv",
            "country_cross_layer_audit.csv",
            "service_country_cross_layer_audit.csv",
            "paper_country_cross_layer_audit.csv",
            "paper_service_country_cross_layer_audit.csv",
            "cross_layer_metric_summary.csv",
            "atomic_segment_id_diagnostics.json",
            "country_corridor_observation_distribution.csv",
            "service_country_corridor_observation_distribution.csv",
            "country_network_transition_distribution.csv",
            "service_country_network_transition_distribution.csv",
            "network_corridor_segment_population_alignment.csv",
            "country_corridor_concentration_summary.csv",
            "service_country_corridor_concentration_summary.csv",
            "country_network_transition_concentration_summary.csv",
            "service_country_network_transition_concentration_summary.csv",
            "country_cross_layer_distribution_audit.csv",
            "service_country_cross_layer_distribution_audit.csv",
            "paper_corridor_observation_concentration_cases.csv",
            "paper_network_broad_physical_concentrated_cases.csv",
            "paper_broad_corridor_distribution_cases.csv",
            "physical_candidate_concentration_summary.csv",
            "joint_cross_layer_risk_summary.csv",
            "paper_physical_concentration_cases.csv",
            "paper_joint_mismatch_cases.csv",
            "paper_broad_physical_space_cases.csv",
            "unit_physical_candidate_set_diversity_cable.csv",
            "unit_physical_candidate_set_diversity_corridor.csv",
            "unit_network_physical_upper_bound_mismatch.csv",
            "paper_unit_physical_candidate_diversity.csv",
            "paper_unit_network_physical_mismatch.csv",
            "network_diversity_metric_catalog.csv",
            "candidate_space_profile.csv",
            "weighted_vs_conservative_diversity.csv",
            "supplementary_owner_concentration.csv",
        ],
        "legacy_supplementary_outputs": [
            "paper_unit_physical_candidate_diversity.csv",
            "paper_unit_network_physical_mismatch.csv",
            "paper_country_cross_layer_audit.csv",
            "paper_service_country_cross_layer_audit.csv",
            "paper_physical_concentration_cases.csv",
            "paper_joint_mismatch_cases.csv",
            "paper_broad_physical_space_cases.csv",
        ],
        "legacy_supplementary_note": "Compatibility files with paper_* names may report candidate breadth or compression views; the paper-primary outputs are the service-country corridor observation concentration and distribution-audit tables.",
    }


def build_core_agreement_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate global core-agreement counts and support shares."""
    columns = [
        "core_agreement",
        "candidate_rows",
        "candidate_row_share",
        "aggregate_normalized_support",
        "aggregate_support_share",
        "units_affected",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    working = frame.copy()
    working["support_value"] = build_support_series(working)
    working["core_agreement_value"] = (
        working.get("core_agreement", pd.Series(index=working.index, dtype=object))
        .fillna("unknown")
        .astype(str)
        .str.strip()
        .replace("", "unknown")
    )
    total_rows = max(len(working), 1)
    total_support = float(working["support_value"].sum())
    summary = (
        working.groupby("core_agreement_value", dropna=False)
        .agg(
            candidate_rows=("core_agreement_value", "size"),
            aggregate_normalized_support=("support_value", "sum"),
            units_affected=("unit_id", pd.Series.nunique),
        )
        .reset_index()
        .rename(columns={"core_agreement_value": "core_agreement"})
    )
    summary["candidate_row_share"] = summary["candidate_rows"] / total_rows
    summary["aggregate_support_share"] = np.where(
        total_support > 0,
        summary["aggregate_normalized_support"] / total_support,
        0.0,
    )
    return summary[columns].sort_values("core_agreement").reset_index(drop=True)


def pick_top_candidate_row(group: pd.DataFrame, rank_col: str, score_col: str, fallback_rank_cols: Sequence[str]) -> pd.Series:
    """Pick a top-ranked candidate row using rank columns first and score fallback second."""
    for candidate_rank_col in [rank_col, *fallback_rank_cols]:
        if candidate_rank_col in group.columns:
            ranked = pd.to_numeric(group[candidate_rank_col], errors="coerce")
            top_group = group.loc[ranked == 1]
            if not top_group.empty:
                return top_group.iloc[0]
    if score_col in group.columns:
        scores = pd.to_numeric(group[score_col], errors="coerce").fillna(-1.0)
        return group.loc[scores.idxmax()]
    return group.iloc[0]


def coerce_rank_value(value: Any, default: float = 1.0) -> float:
    """Convert a rank-like scalar to float with graceful fallback."""
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(numeric) if pd.notna(numeric) else default


def build_as_reranking_effect(frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize how geo-only, AS-only, and fused rankings differ at link level."""
    columns = [
        "total_links",
        "geo_as_top_agreement_rate",
        "geo_fused_top_agreement_rate",
        "as_fused_top_agreement_rate",
        "as_changes_geo_top1_rate",
        "mean_geo_to_fused_rank_shift",
        "mean_as_to_fused_rank_shift",
        "parallel_links",
        "parallel_links_with_dual_core_agreement",
        "parallel_links_remaining_ambiguous",
    ]
    if frame.empty:
        return pd.DataFrame([{column: 0.0 for column in columns}])

    working = frame.copy()
    parallel_group_size_series = working.get("parallel_group_size", pd.Series(index=working.index, dtype=float))
    is_parallel_series = working.get("is_parallel_ambiguous", pd.Series(index=working.index, dtype=object))
    ambiguity_tag_series = working.get("ambiguity_tags", pd.Series(index=working.index, dtype=object))
    dual_core_series = working.get("dual_core_agreement", pd.Series(index=working.index, dtype=object))

    working["parallel_group_size_num"] = pd.to_numeric(parallel_group_size_series, errors="coerce").fillna(0.0)
    working["is_parallel_ambiguous_bool"] = is_parallel_series.fillna(False).astype(bool)
    working["ambiguity_tags_list"] = ambiguity_tag_series.apply(safe_parse_tags)
    working["core_agreement_value"] = (
        working.get("core_agreement", pd.Series(index=working.index, dtype=object))
        .fillna("unknown")
        .astype(str)
    )
    working["dual_core_agreement_bool"] = pd.to_numeric(dual_core_series, errors="coerce").fillna(0).astype(bool)
    confidence_values = working.get("confidence_bucket", pd.Series(index=working.index, dtype=object)).fillna("").astype(str)

    total_links = int(working["link_id"].nunique()) if "link_id" in working.columns else 0
    if total_links == 0:
        return pd.DataFrame([{column: 0.0 for column in columns}])

    geo_as_match = 0
    geo_fused_match = 0
    as_fused_match = 0
    geo_to_fused_shifts: List[float] = []
    as_to_fused_shifts: List[float] = []
    parallel_links = 0
    parallel_links_with_dual_core_agreement = 0
    parallel_links_remaining_ambiguous = 0

    for _, group in working.groupby("link_id", dropna=False):
        geo_top = pick_top_candidate_row(group, "geo_only_rank", "geo_spatial_score", [])
        as_top = pick_top_candidate_row(group, "as_only_rank", "as_economic_score", [])
        fused_top = pick_top_candidate_row(
            group,
            "candidate_rank_by_fused_support",
            "fused_candidate_support",
            ["candidate_rank"],
        )

        geo_key = str(geo_top.get("cable_id", geo_top.name))
        as_key = str(as_top.get("cable_id", as_top.name))
        fused_key = str(fused_top.get("cable_id", fused_top.name))
        if geo_key == as_key:
            geo_as_match += 1
        if geo_key == fused_key:
            geo_fused_match += 1
        if as_key == fused_key:
            as_fused_match += 1

        geo_to_fused_shifts.append(
            max(coerce_rank_value(geo_top.get("candidate_rank_by_fused_support"), 1.0) - 1.0, 0.0)
        )
        as_to_fused_shifts.append(
            max(coerce_rank_value(as_top.get("candidate_rank_by_fused_support"), 1.0) - 1.0, 0.0)
        )

        is_parallel_link = bool(group["is_parallel_ambiguous_bool"].any()) or bool((group["parallel_group_size_num"] > 1).any()) or bool(
            group["ambiguity_tags_list"].apply(lambda tags: "parallel_candidate_corridor" in tags).any()
        )
        if is_parallel_link:
            parallel_links += 1
            if bool((group["core_agreement_value"] == "dual_core_agreement").any()) or bool(group["dual_core_agreement_bool"].any()):
                parallel_links_with_dual_core_agreement += 1
            has_ambiguous_confidence = bool(confidence_values.loc[group.index].str.contains("ambiguous", case=False, na=False).any())
            has_dual_core = bool((group["core_agreement_value"] == "dual_core_agreement").any())
            if (not has_dual_core) or has_ambiguous_confidence:
                parallel_links_remaining_ambiguous += 1

    result = {
        "total_links": total_links,
        "geo_as_top_agreement_rate": geo_as_match / total_links,
        "geo_fused_top_agreement_rate": geo_fused_match / total_links,
        "as_fused_top_agreement_rate": as_fused_match / total_links,
        "as_changes_geo_top1_rate": 1.0 - (geo_as_match / total_links),
        "mean_geo_to_fused_rank_shift": float(np.mean(geo_to_fused_shifts)) if geo_to_fused_shifts else 0.0,
        "mean_as_to_fused_rank_shift": float(np.mean(as_to_fused_shifts)) if as_to_fused_shifts else 0.0,
        "parallel_links": parallel_links,
        "parallel_links_with_dual_core_agreement": parallel_links_with_dual_core_agreement,
        "parallel_links_remaining_ambiguous": parallel_links_remaining_ambiguous,
    }
    return pd.DataFrame([result], columns=columns)


def build_filtering_breakdown(output_dir: str) -> pd.DataFrame:
    """Read stage-1 stats and manifest and expose a lightweight filtering breakdown."""
    columns = [
        "total_traces_processed",
        "empty_trace_count",
        "total_links_seen",
        "same_city_filtered",
        "links_without_landing_candidates",
        "links_without_segment_candidates",
        "links_with_ls_candidates",
        "links_with_geo_candidates",
        "candidate_segments_considered",
        "rtt_infeasible_filtered",
        "candidates_rtt_infeasible",
        "candidates_rtt_feasible",
        "candidates_support_below_threshold",
        "candidates_support_above_threshold",
        "links_with_any_match",
        "links_with_feasible_candidates",
        "links_with_no_feasible_candidate",
        "links_with_only_low_support_feasible_candidates",
        "total_candidates_generated",
        "total_candidates_after_threshold",
        "links_with_parallel_ambiguity",
        "links_with_domestic_candidates",
    ]
    stats_path = os.path.join(output_dir, "cable_matching_stats_5051.json")
    manifest_path = os.path.join(output_dir, "cable_matching_manifest.json")
    if not os.path.exists(stats_path) or not os.path.exists(manifest_path):
        return pd.DataFrame(columns=columns)

    with open(stats_path, "r", encoding="utf-8") as handle:
        stats = json.load(handle)
    with open(manifest_path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    row = {
        "total_traces_processed": manifest.get("total_traces_processed", 0),
        "empty_trace_count": manifest.get("empty_trace_count", 0),
        "total_links_seen": stats.get("total_links_seen", 0),
        "same_city_filtered": stats.get("same_city_filtered", 0),
        "links_without_landing_candidates": stats.get("links_without_landing_candidates", 0),
        "links_without_segment_candidates": stats.get("links_without_segment_candidates", 0),
        "links_with_ls_candidates": stats.get("links_with_ls_candidates", 0),
        "links_with_geo_candidates": stats.get("links_with_geo_candidates", 0),
        "candidate_segments_considered": stats.get("candidate_segments_considered", 0),
        "rtt_infeasible_filtered": stats.get("rtt_infeasible_filtered", 0),
        "candidates_rtt_infeasible": stats.get("candidates_rtt_infeasible", 0),
        "candidates_rtt_feasible": stats.get("candidates_rtt_feasible", 0),
        "candidates_support_below_threshold": stats.get("candidates_support_below_threshold", 0),
        "candidates_support_above_threshold": stats.get("candidates_support_above_threshold", 0),
        "links_with_any_match": stats.get("links_with_any_match", 0),
        "links_with_feasible_candidates": stats.get("links_with_feasible_candidates", 0),
        "links_with_no_feasible_candidate": stats.get("links_with_no_feasible_candidate", 0),
        "links_with_only_low_support_feasible_candidates": stats.get("links_with_only_low_support_feasible_candidates", 0),
        "total_candidates_generated": stats.get("total_candidates_generated", 0),
        "total_candidates_after_threshold": stats.get("total_candidates_after_threshold", 0),
        "links_with_parallel_ambiguity": stats.get("links_with_parallel_ambiguity", 0),
        "links_with_domestic_candidates": stats.get("links_with_domestic_candidates", 0),
    }
    return pd.DataFrame([row], columns=columns)


def scale_series(values: Sequence[float], low: float, high: float) -> List[float]:
    """Linearly map a numeric sequence to a chart range."""
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if math.isclose(minimum, maximum):
        midpoint = (low + high) / 2.0
        return [midpoint for _ in values]
    return [low + (value - minimum) * (high - low) / (maximum - minimum) for value in values]


def scale_value(value: float, minimum: float, maximum: float, low: float, high: float) -> float:
    """Linearly map one value to a chart range."""
    if math.isclose(minimum, maximum):
        return (low + high) / 2.0
    return low + (value - minimum) * (high - low) / (maximum - minimum)


def write_svg(path: str, body: str, width: int = 900, height: int = 620) -> None:
    """Write a compact standalone SVG file."""
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        f"<rect width='100%' height='100%' fill='white'/>"
        f"{body}</svg>"
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(svg)


def write_quadrant_scatter_svg(
    mismatch_frame: pd.DataFrame,
    output_path: str,
    title: str,
) -> None:
    """Render a network-vs-physical scatter plot with quadrant guides."""
    if mismatch_frame.empty:
        write_svg(output_path, "<text x='24' y='36' font-size='18'>No data available.</text>")
        return

    plot_left = 90
    plot_top = 60
    plot_width = 560
    plot_height = 420
    plot_right = plot_left + plot_width
    plot_bottom = plot_top + plot_height

    x_values = mismatch_frame["network_layer_diversity_score"].astype(float).tolist()
    y_values = mismatch_frame["physical_candidate_diversity_score"].astype(float).tolist()
    x_positions = scale_series(x_values, plot_left, plot_right)
    y_positions_raw = scale_series(y_values, plot_top, plot_bottom)
    y_positions = [plot_bottom - (value - plot_top) for value in y_positions_raw]

    x_median = float(mismatch_frame["network_layer_diversity_score"].median())
    y_median = float(mismatch_frame["physical_candidate_diversity_score"].median())
    x_median_pos = scale_value(x_median, min(x_values), max(x_values), plot_left, plot_right) if x_values else plot_left
    y_median_raw = scale_value(y_median, min(y_values), max(y_values), plot_top, plot_bottom) if y_values else plot_top
    y_median_pos = plot_bottom - (y_median_raw - plot_top)

    body_parts = [
        f"<text x='24' y='34' font-size='20' font-family='Arial'>{escape(title)}</text>",
        f"<rect x='{plot_left}' y='{plot_top}' width='{plot_width}' height='{plot_height}' fill='#f8f9f9' stroke='#808b96'/>",
        f"<line x1='{x_median_pos:.2f}' y1='{plot_top}' x2='{x_median_pos:.2f}' y2='{plot_bottom}' stroke='#7b7d7d' stroke-dasharray='6,4'/>",
        f"<line x1='{plot_left}' y1='{y_median_pos:.2f}' x2='{plot_right}' y2='{y_median_pos:.2f}' stroke='#7b7d7d' stroke-dasharray='6,4'/>",
        f"<text x='{plot_left}' y='{plot_bottom + 36}' font-size='15' font-family='Arial'>Network-layer diversity score</text>",
        f"<text x='20' y='{plot_top - 18}' font-size='15' font-family='Arial'>Physical-candidate diversity score</text>",
    ]

    for x_pos, y_pos, category in zip(
        x_positions,
        y_positions,
        mismatch_frame["network_physical_mismatch_category"].astype(str).tolist(),
    ):
        color = QUADRANT_COLORS.get(category, "#95a5a6")
        radius = 5.0 if category == LEGACY_WEIGHTED_TARGET_MISMATCH_CATEGORY else 3.8
        opacity = 0.9 if category == LEGACY_WEIGHTED_TARGET_MISMATCH_CATEGORY else 0.68
        body_parts.append(
            f"<circle cx='{x_pos:.2f}' cy='{y_pos:.2f}' r='{radius}' fill='{color}' fill-opacity='{opacity}'/>"
        )

    legend_x = 690
    legend_y = 110
    for index, category in enumerate(QUADRANT_ORDER):
        y = legend_y + index * 32
        body_parts.append(
            f"<rect x='{legend_x}' y='{y - 12}' width='14' height='14' fill='{QUADRANT_COLORS[category]}'/>"
        )
        body_parts.append(
            f"<text x='{legend_x + 22}' y='{y}' font-size='14' font-family='Arial'>{escape(category)}</text>"
        )

    body_parts.extend(
        [
            f"<text x='{legend_x}' y='280' font-size='14' font-family='Arial'>Median split guide:</text>",
            f"<text x='{legend_x}' y='302' font-size='13' font-family='Arial'>vertical = network median</text>",
            f"<text x='{legend_x}' y='322' font-size='13' font-family='Arial'>horizontal = physical median</text>",
            f"<text x='{legend_x}' y='372' font-size='14' font-family='Arial'>Focus quadrant:</text>",
            f"<text x='{legend_x}' y='394' font-size='14' font-family='Arial' fill='{QUADRANT_COLORS[LEGACY_WEIGHTED_TARGET_MISMATCH_CATEGORY]}'>{LEGACY_WEIGHTED_TARGET_MISMATCH_CATEGORY}</text>",
        ]
    )

    write_svg(output_path, "".join(body_parts))


def write_quadrant_bar_svg(summary_frame: pd.DataFrame, output_path: str, title: str) -> None:
    """Render a simple quadrant count chart."""
    if summary_frame.empty:
        write_svg(output_path, "<text x='24' y='36' font-size='18'>No data available.</text>")
        return

    bar_left = 120
    bar_top = 80
    bar_width = 580
    bar_height = 360
    max_count = max(summary_frame["unit_count"].max(), 1)
    bar_slot_width = bar_width / max(len(QUADRANT_ORDER), 1)
    body_parts = [
        f"<text x='24' y='34' font-size='20' font-family='Arial'>{escape(title)}</text>",
        f"<line x1='{bar_left}' y1='{bar_top + bar_height}' x2='{bar_left + bar_width}' y2='{bar_top + bar_height}' stroke='#566573'/>",
        f"<line x1='{bar_left}' y1='{bar_top}' x2='{bar_left}' y2='{bar_top + bar_height}' stroke='#566573'/>",
    ]

    for index, category in enumerate(QUADRANT_ORDER):
        row = summary_frame[summary_frame["network_physical_mismatch_category"] == category]
        count = int(row["unit_count"].iloc[0]) if not row.empty else 0
        height = 0 if max_count <= 0 else bar_height * (count / max_count)
        x = bar_left + index * bar_slot_width + 30
        y = bar_top + bar_height - height
        color = QUADRANT_COLORS.get(category, "#95a5a6")
        body_parts.append(f"<rect x='{x:.2f}' y='{y:.2f}' width='68' height='{height:.2f}' fill='{color}'/>")
        body_parts.append(f"<text x='{x + 12:.2f}' y='{y - 8:.2f}' font-size='13' font-family='Arial'>{count}</text>")
        body_parts.append(
            f"<text x='{x - 4:.2f}' y='{bar_top + bar_height + 26:.2f}' font-size='11' font-family='Arial'>{escape(category)}</text>"
        )

    write_svg(output_path, "".join(body_parts))


def write_cable_corridor_comparison_svg(comparison_frame: pd.DataFrame, output_path: str) -> None:
    """Render cable-level vs corridor-level diversity comparison."""
    if comparison_frame.empty:
        write_svg(output_path, "<text x='24' y='36' font-size='18'>No data available.</text>")
        return

    plot_left = 100
    plot_top = 60
    plot_width = 520
    plot_height = 420
    plot_right = plot_left + plot_width
    plot_bottom = plot_top + plot_height

    x_values = comparison_frame["cable_physical_candidate_diversity_score"].astype(float).tolist()
    y_values = comparison_frame["corridor_physical_candidate_diversity_score"].astype(float).tolist()
    x_positions = scale_series(x_values, plot_left, plot_right)
    y_positions_raw = scale_series(y_values, plot_top, plot_bottom)
    y_positions = [plot_bottom - (value - plot_top) for value in y_positions_raw]

    max_axis = max(max(x_values, default=0.0), max(y_values, default=0.0), 1.0)
    diagonal_end = plot_left + plot_width
    body_parts = [
        "<text x='24' y='34' font-size='20' font-family='Arial'>Cable-level vs corridor-level physical diversity</text>",
        f"<rect x='{plot_left}' y='{plot_top}' width='{plot_width}' height='{plot_height}' fill='#fdfefe' stroke='#808b96'/>",
        f"<line x1='{plot_left}' y1='{plot_bottom}' x2='{plot_right}' y2='{plot_top}' stroke='#7b7d7d' stroke-dasharray='6,4'/>",
        f"<text x='{plot_left}' y='{plot_bottom + 36}' font-size='15' font-family='Arial'>Cable-level physical diversity score</text>",
        f"<text x='24' y='{plot_top - 18}' font-size='15' font-family='Arial'>Corridor-level physical diversity score</text>",
        f"<text x='680' y='100' font-size='14' font-family='Arial'>Diagonal: corridor = cable</text>",
        f"<text x='680' y='126' font-size='13' font-family='Arial'>Higher above line means corridor aggregation</text>",
        f"<text x='680' y='144' font-size='13' font-family='Arial'>raises physical diversity less than cable split.</text>",
    ]

    for x_pos, y_pos, cable_target, corridor_target in zip(
        x_positions,
        y_positions,
        comparison_frame["cable_is_target_quadrant"].fillna(False).tolist(),
        comparison_frame["corridor_is_target_quadrant"].fillna(False).tolist(),
    ):
        if cable_target and corridor_target:
            color = "#c0392b"
        elif cable_target:
            color = "#d68910"
        elif corridor_target:
            color = "#2471a3"
        else:
            color = "#95a5a6"
        body_parts.append(f"<circle cx='{x_pos:.2f}' cy='{y_pos:.2f}' r='4.0' fill='{color}' fill-opacity='0.78'/>")

    legend = [
        ("#c0392b", "target quadrant at both cable and corridor levels"),
        ("#d68910", "target quadrant only at cable level"),
        ("#2471a3", "target quadrant only at corridor level"),
        ("#95a5a6", "other units"),
    ]
    for index, (color, label) in enumerate(legend):
        y = 220 + index * 26
        body_parts.append(f"<rect x='680' y='{y - 12}' width='14' height='14' fill='{color}'/>")
        body_parts.append(f"<text x='702' y='{y}' font-size='13' font-family='Arial'>{escape(label)}</text>")

    write_svg(output_path, "".join(body_parts))


def build_dataset_summary(
    candidate_frame: pd.DataFrame,
    cable_physical: pd.DataFrame,
    corridor_physical: pd.DataFrame,
    network_frame: pd.DataFrame,
    cable_mismatch: pd.DataFrame,
    corridor_mismatch: pd.DataFrame,
    cable_corridor_comparison: pd.DataFrame,
) -> pd.DataFrame:
    """Build a compact dataset-level summary table."""
    summary_rows = [
        {"metric": "candidate_rows", "value": int(len(candidate_frame))},
        {"metric": "unique_links", "value": int(candidate_frame["link_id"].nunique())},
        {"metric": "unique_units", "value": int(candidate_frame["unit_id"].nunique())},
        {"metric": "units_with_network_layer_diversity", "value": int(len(network_frame))},
        {"metric": "units_with_physical_diversity_cable", "value": int(len(cable_physical))},
        {"metric": "units_with_physical_diversity_corridor", "value": int(len(corridor_physical))},
        {"metric": "units_with_network_physical_mismatch_cable", "value": int(len(cable_mismatch))},
        {"metric": "units_with_network_physical_mismatch_corridor", "value": int(len(corridor_mismatch))},
        {
            "metric": "median_network_layer_diversity_score",
            "value": float(network_frame["network_layer_diversity_score"].median()) if not network_frame.empty else 0.0,
        },
        {
            "metric": "median_cable_physical_candidate_diversity_score",
            "value": float(cable_physical["physical_candidate_diversity_score"].median()) if not cable_physical.empty else 0.0,
        },
        {
            "metric": "median_corridor_physical_candidate_diversity_score",
            "value": float(corridor_physical["physical_candidate_diversity_score"].median()) if not corridor_physical.empty else 0.0,
        },
    ]

    for label, frame in [("cable", cable_mismatch), ("corridor", corridor_mismatch)]:
        if frame.empty:
            continue
        for category, count in (
            frame["network_physical_mismatch_category"].astype(str).value_counts().reindex(QUADRANT_ORDER, fill_value=0).items()
        ):
            summary_rows.append({"metric": f"{label}_mismatch_{category}", "value": int(count)})

    if not cable_corridor_comparison.empty:
        preserved = int(cable_corridor_comparison["target_quadrant_preserved"].sum())
        cable_targets = int(cable_corridor_comparison["cable_is_target_quadrant"].fillna(False).sum())
        corridor_targets = int(cable_corridor_comparison["corridor_is_target_quadrant"].fillna(False).sum())
        union_targets = int(
            (
                cable_corridor_comparison["cable_is_target_quadrant"].fillna(False)
                | cable_corridor_comparison["corridor_is_target_quadrant"].fillna(False)
            ).sum()
        )
        summary_rows.extend(
            [
                {"metric": "cable_corridor_target_quadrant_preserved", "value": preserved},
                {
                    "metric": "cable_corridor_target_quadrant_jaccard",
                    "value": float(preserved / union_targets) if union_targets > 0 else 1.0,
                },
                {
                    "metric": "cable_corridor_target_quadrant_recall_from_cable",
                    "value": float(preserved / cable_targets) if cable_targets > 0 else 0.0,
                },
                {
                    "metric": "cable_corridor_target_quadrant_precision_to_corridor",
                    "value": float(preserved / corridor_targets) if corridor_targets > 0 else 0.0,
                },
                {
                    "metric": "mean_corridor_minus_cable_physical_diversity",
                    "value": float(cable_corridor_comparison["corridor_minus_cable_physical_diversity"].mean()),
                },
                {
                    "metric": "cable_corridor_quadrant_agreement_rate",
                    "value": float(cable_corridor_comparison["quadrant_label_stable"].mean()),
                },
                {
                    "metric": "spearman_cable_corridor_physical_diversity_score",
                    "value": float(
                        cable_corridor_comparison["cable_physical_candidate_diversity_score"].corr(
                            cable_corridor_comparison["corridor_physical_candidate_diversity_score"],
                            method="spearman",
                        )
                    ),
                },
            ]
        )

    return pd.DataFrame(summary_rows)


def main() -> None:
    """Read candidate-support JSON output and emit diversity and mismatch tables."""
    global MINIMUM_MAPPABLE_SEGMENTS, MINIMUM_UNIQUE_PROBES, MINIMUM_UNIQUE_PROBE_ASNS, MAXIMUM_COUNTRY_FALLBACK_SHARE
    args = parse_args()
    MINIMUM_MAPPABLE_SEGMENTS = int(args.minimum_mappable_segments)
    MINIMUM_UNIQUE_PROBES = int(args.minimum_unique_probes)
    MINIMUM_UNIQUE_PROBE_ASNS = int(args.minimum_unique_probe_asns)
    MAXIMUM_COUNTRY_FALLBACK_SHARE = float(args.maximum_country_fallback_share)
    unit_fields = [field.strip() for field in args.unit_fields.split(",") if field.strip()]
    if not unit_fields:
        unit_fields = list(DEFAULT_UNIT_FIELDS)

    os.makedirs(args.output, exist_ok=True)
    records = read_candidate_output(args.input)
    candidate_frame = explode_candidate_rows(records, unit_fields)
    feasible_frame = explode_feasible_candidate_rows(records, unit_fields)

    if candidate_frame.empty and feasible_frame.empty:
        # A strict infeasibility-first topology policy may legitimately retain no
        # physical candidates.  Emit header-valid audit tables rather than
        # converting this substantive result into a pipeline failure.
        print("Warning: no feasible candidate rows were found; writing empty physical audit tables.")
        empty_tables = {
            "trace_candidate_support.csv": ["unit_id", "link_id", "trace_id", "candidate_support"],
            "trace_feasible_candidate_space.csv": ["unit_id", "link_id", "trace_id", "hard_feasible"],
            "dataset_summary.csv": ["metric", "value"],
            "filtering_breakdown.csv": ["metric", "value"],
            "candidate_space_profile.csv": ["unit_id", "num_links_with_feasible_candidates"],
            "paper_service_country_physical_exposure.csv": ["probe_country", "service_id", "analysis_scope"],
            "paper_service_country_corridor_concentration.csv": ["probe_country", "service_id", "analysis_scope"],
            "paper_service_country_cross_layer_distribution.csv": ["probe_country", "service_id", "analysis_scope"],
            "paper_corridor_observation_concentration_cases.csv": ["analysis_scope"],
            "paper_network_broad_physical_concentrated_cases.csv": ["analysis_scope"],
            "paper_broad_corridor_distribution_cases.csv": ["analysis_scope"],
            "unit_network_layer_diversity.csv": ["unit_id"],
            "unit_network_physical_upper_bound_mismatch.csv": ["unit_id", "network_definition", "physical_level"],
            "country_network_transition_distribution.csv": [
                "country",
                "network_transition_key",
                "network_transition_representation",
                "network_transition_observation_count",
                "share_of_network_transition_observations",
            ],
            "service_country_network_transition_distribution.csv": [
                "probe_country",
                "service_id",
                "path_scope_stratum",
                "network_transition_key",
                "network_transition_representation",
                "network_transition_observation_count",
                "share_of_network_transition_observations",
            ],
            "network_corridor_segment_population_alignment.csv": [
                "analysis_scope",
                "network_atomic_segments",
                "corridor_atomic_segments",
                "shared_atomic_segments",
                "segment_population_aligned",
            ],
        }
        for filename, columns in empty_tables.items():
            pd.DataFrame(columns=columns).to_csv(
                os.path.join(args.output, filename), index=False, encoding="utf-8-sig"
            )
        trace_observation_frame = load_trace_observation_summary(args.output)
        trace_observation_frame = annotate_trace_candidate_scope_exposure(
            trace_observation_frame,
            pd.DataFrame(),
        )
        service_exposure = build_service_country_physical_exposure_summary(trace_observation_frame)
        corridor_empty = build_corridor_concentration_summary(
            pd.DataFrame(),
            ["probe_country", "service_id", "path_scope_stratum"],
        )
        network_empty = summarize_network_transition_concentration(
            pd.DataFrame(),
            ["probe_country", "service_id", "path_scope_stratum"],
        )
        cross_empty = build_cross_layer_distribution_audit(
            corridor_empty,
            network_empty,
            ["probe_country", "service_id", "path_scope_stratum"],
        )
        service_corridor = ensure_service_path_scope_summary_rows(corridor_empty, service_exposure, "corridor")
        service_network = ensure_service_path_scope_summary_rows(network_empty, service_exposure, "network")
        service_cross = ensure_service_path_scope_summary_rows(cross_empty, service_exposure, "cross_layer")
        service_exposure = apply_cross_layer_audit_eligibility(
            service_exposure,
            service_cross,
            ["probe_country", "service_id", "path_scope_stratum"],
        )
        service_corridor = apply_cross_layer_audit_eligibility(
            service_corridor,
            service_cross,
            ["probe_country", "service_id", "path_scope_stratum"],
        )
        for frame in (service_exposure, service_corridor, service_cross):
            if not frame.empty:
                frame["analysis_scope"] = "probe_country_service"
        write_country_geography_dependency_outputs(
            args.output,
            trace_observation_frame,
            service_exposure,
            service_corridor,
            service_cross,
            args.country_geography_catalog,
        )
        service_exposure.to_csv(
            os.path.join(args.output, "service_country_physical_exposure_summary.csv"),
            index=False,
            encoding="utf-8-sig",
        )
        service_exposure.to_csv(
            os.path.join(args.output, "service_country_physical_exposure.csv"),
            index=False,
            encoding="utf-8-sig",
        )
        service_corridor.to_csv(
            os.path.join(args.output, "service_country_corridor_concentration_summary.csv"),
            index=False,
            encoding="utf-8-sig",
        )
        service_network.to_csv(
            os.path.join(args.output, "service_country_network_transition_concentration_summary.csv"),
            index=False,
            encoding="utf-8-sig",
        )
        service_cross.to_csv(
            os.path.join(args.output, "service_country_cross_layer_distribution_audit.csv"),
            index=False,
            encoding="utf-8-sig",
        )
        filter_auditable_paper_rows(service_exposure).to_csv(
            os.path.join(args.output, "paper_service_country_physical_exposure.csv"),
            index=False,
            encoding="utf-8-sig",
        )
        filter_auditable_paper_rows(service_corridor).to_csv(
            os.path.join(args.output, "paper_service_country_corridor_concentration.csv"),
            index=False,
            encoding="utf-8-sig",
        )
        filter_auditable_paper_rows(service_cross).to_csv(
            os.path.join(args.output, "paper_service_country_cross_layer_distribution.csv"),
            index=False,
            encoding="utf-8-sig",
        )
        method_manifest = build_method_manifest()
        framework_alignment_report = build_framework_alignment_report(
            trace_observation_frame,
            pd.DataFrame(),
            service_cross,
            method_manifest,
            load_stage1_stats(args.output),
        )
        framework_alignment_report.update(
            {
                "status": "no_feasible_candidate_rows",
                "interpretation": "The configured infeasibility-first projection retained no feasible physical candidates.",
                "paper_outputs_are_empty": True,
            }
        )
        with open(os.path.join(args.output, "method_manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(
                method_manifest,
                handle,
                indent=2,
            )
        with open(os.path.join(args.output, "framework_alignment_report.json"), "w", encoding="utf-8") as handle:
            json.dump(framework_alignment_report, handle, indent=2)
        return

    if not candidate_frame.empty:
        candidate_frame = ensure_corridor_columns(candidate_frame)
        candidate_frame = annotate_link_projection_classes(candidate_frame)
        candidate_frame = annotate_projection_quality(candidate_frame)
    if not feasible_frame.empty:
        feasible_frame = ensure_corridor_columns(feasible_frame)
        feasible_frame = annotate_link_projection_classes(feasible_frame)
        feasible_frame = annotate_projection_quality(feasible_frame)
    if candidate_frame.empty and not feasible_frame.empty:
        candidate_frame = feasible_frame.iloc[0:0].copy()
    corridor_candidate_col = resolve_corridor_candidate_column(
        feasible_frame if not feasible_frame.empty else candidate_frame
    )
    projection_source_frame = feasible_frame if not feasible_frame.empty else candidate_frame
    if feasible_frame.empty:
        print(
            "Warning: no explicit all_feasible_segments rows were found; "
            "corridor observation auditing is falling back to support-filtered candidate rows."
        )

    trace_output = os.path.join(args.output, "trace_candidate_support.csv")
    trace_feasible_output = os.path.join(args.output, "trace_feasible_candidate_space.csv")
    candidate_frame.to_csv(trace_output, index=False, encoding="utf-8-sig")
    feasible_frame.to_csv(trace_feasible_output, index=False, encoding="utf-8-sig")
    trace_observation_frame = load_trace_observation_summary(args.output)
    trace_observation_frame = annotate_trace_candidate_scope_exposure(trace_observation_frame, feasible_frame)
    service_country_physical_exposure = build_service_country_physical_exposure_summary(trace_observation_frame)
    country_physical_exposure = build_country_physical_exposure_summary(trace_observation_frame)

    cable_physical = build_unit_physical_candidate_diversity(candidate_frame, "cable_id", "cable")
    corridor_physical = build_unit_physical_candidate_diversity(candidate_frame, corridor_candidate_col, "corridor")
    cable_physical_uniform = build_unit_physical_feasible_set_diversity(feasible_frame, "cable_id", "cable")
    corridor_physical_uniform = build_unit_physical_feasible_set_diversity(feasible_frame, corridor_candidate_col, "corridor")
    upper_bound_physical = build_unit_physical_candidate_upper_bound(feasible_frame, corridor_candidate_col)
    network_frame = build_unit_network_layer_diversity(feasible_frame if not feasible_frame.empty else candidate_frame)
    cable_mismatch = build_unit_network_physical_mismatch(network_frame, cable_physical, "cable")
    corridor_mismatch = build_unit_network_physical_mismatch(network_frame, corridor_physical, "corridor")
    upper_bound_mismatch = build_unit_network_physical_upper_bound_mismatch(
        network_frame,
        {
            "cable": cable_physical_uniform,
            "corridor": corridor_physical_uniform,
        },
    )
    peeringdb_descriptors = load_peeringdb_descriptors(args.output)
    stage1_stats = load_stage1_stats(args.output)
    upper_bound_mismatch = merge_peeringdb_descriptors(upper_bound_mismatch, peeringdb_descriptors, country_column="src_country")
    unit_cross_layer_audit = build_cross_layer_audit_frame(
        feasible_frame,
        ["unit_id"],
        corridor_candidate_col,
        peeringdb_descriptors,
        peeringdb_country_column="probe_country",
    )
    country_cross_layer_audit = build_cross_layer_audit_frame(
        feasible_frame,
        ["src_country"],
        corridor_candidate_col,
        peeringdb_descriptors,
        peeringdb_country_column="src_country",
    )
    service_country_cross_layer_audit = build_cross_layer_audit_frame(
        feasible_frame,
        ["probe_country", "service_id"],
        corridor_candidate_col,
        peeringdb_descriptors,
        peeringdb_country_column="probe_country",
    )
    paper_country_cross_layer_audit = (
        filter_auditable_paper_rows(country_cross_layer_audit.loc[
            country_cross_layer_audit["physical_level"].astype(str) == PAPER_PRIMARY_PHYSICAL_LEVEL
        ])
        if not country_cross_layer_audit.empty
        else pd.DataFrame(columns=PRIMARY_CROSS_LAYER_COLUMNS)
    )
    paper_service_country_cross_layer_audit = (
        filter_auditable_paper_rows(service_country_cross_layer_audit.loc[
            service_country_cross_layer_audit["physical_level"].astype(str) == PAPER_PRIMARY_PHYSICAL_LEVEL
        ])
        if not service_country_cross_layer_audit.empty
        else pd.DataFrame(columns=PRIMARY_CROSS_LAYER_COLUMNS)
    )
    named_cross_layer_frames = {
        "unit_cross_layer_audit": unit_cross_layer_audit,
        "country_cross_layer_audit": country_cross_layer_audit,
        "service_country_cross_layer_audit": service_country_cross_layer_audit,
        "paper_country_cross_layer_audit": paper_country_cross_layer_audit,
        "paper_service_country_cross_layer_audit": paper_service_country_cross_layer_audit,
    }
    cross_layer_metric_summary = build_cross_layer_metric_summary(named_cross_layer_frames)
    physical_candidate_concentration_summary = build_physical_candidate_concentration_summary(named_cross_layer_frames)
    joint_cross_layer_risk_summary = build_joint_cross_layer_risk_summary(named_cross_layer_frames)
    combined_paper_case_frame = combine_paper_case_frames(
        paper_country_cross_layer_audit,
        paper_service_country_cross_layer_audit,
    )
    paper_physical_concentration_cases = build_paper_physical_concentration_cases(combined_paper_case_frame)
    paper_joint_mismatch_cases = build_paper_joint_mismatch_cases(combined_paper_case_frame)
    paper_broad_physical_space_cases = build_paper_broad_physical_space_cases(combined_paper_case_frame)
    atomic_segment_id_diagnostics = build_atomic_segment_id_diagnostics(projection_source_frame)
    prepared_segment_projection = prepare_atomic_segment_projection_frame(
        projection_source_frame,
        corridor_col=corridor_candidate_col,
    )
    paper_inter_region_projection = prepared_segment_projection.loc[
        prepared_segment_projection.get("candidate_scope", pd.Series(index=prepared_segment_projection.index, dtype=object))
        .fillna("")
        .astype(str)
        .ne("intra_landing_region")
    ].copy()
    service_path_scope_projection = build_service_path_scope_projections(paper_inter_region_projection)
    segment_corridor_mass = build_segment_corridor_mass_frame(
        projection_source_frame,
        corridor_col=corridor_candidate_col,
        mass_mode="uniform",
    )
    service_segment_corridor_mass_parts: List[pd.DataFrame] = []
    for path_scope_stratum, scoped_projection in service_path_scope_projection.groupby(
        "path_scope_stratum",
        dropna=False,
    ):
        scoped_mass = build_segment_corridor_mass_frame(
            scoped_projection,
            corridor_col=corridor_candidate_col,
            mass_mode="uniform",
        )
        if not scoped_mass.empty:
            scoped_mass["path_scope_stratum"] = str(path_scope_stratum)
            service_segment_corridor_mass_parts.append(scoped_mass)
    service_segment_corridor_mass = (
        pd.concat(service_segment_corridor_mass_parts, ignore_index=True, sort=False)
        if service_segment_corridor_mass_parts
        else pd.DataFrame(columns=[*segment_corridor_mass.columns, "path_scope_stratum"])
    )
    supplementary_owner_concentration = build_supplementary_owner_concentration(
        projection_source_frame,
        segment_corridor_mass,
    )
    country_corridor_distribution_internal = summarize_corridor_observation_distribution(
        segment_corridor_mass,
        ["country"],
    )
    transition_country_corridor_distribution_internal = country_corridor_distribution_internal
    service_country_corridor_distribution_internal = summarize_corridor_observation_distribution(
        service_segment_corridor_mass,
        ["probe_country", "service_id", "path_scope_stratum"],
    )
    country_corridor_concentration_summary = build_corridor_concentration_summary(
        country_corridor_distribution_internal,
        ["country"],
    )
    transition_country_corridor_concentration_summary = country_corridor_concentration_summary
    service_country_corridor_concentration_summary = build_corridor_concentration_summary(
        service_country_corridor_distribution_internal,
        ["probe_country", "service_id", "path_scope_stratum"],
    )
    country_network_transition_distribution = build_network_transition_distribution(
        paper_inter_region_projection,
        ["country"],
    )
    country_network_transition_concentration_summary = summarize_network_transition_distribution(
        country_network_transition_distribution,
        ["country"],
    )
    transition_country_network_transition_concentration_summary = country_network_transition_concentration_summary
    service_country_network_transition_distribution = build_network_transition_distribution(
        service_path_scope_projection,
        ["probe_country", "service_id", "path_scope_stratum"],
    )
    service_country_network_transition_concentration_summary = summarize_network_transition_distribution(
        service_country_network_transition_distribution,
        ["probe_country", "service_id", "path_scope_stratum"],
    )
    country_segment_population_alignment = build_network_corridor_segment_population_alignment(
        paper_inter_region_projection,
        segment_corridor_mass,
        ["country"],
        "transition_near_country",
    )
    service_segment_population_alignment = build_network_corridor_segment_population_alignment(
        service_path_scope_projection,
        service_segment_corridor_mass,
        ["probe_country", "service_id", "path_scope_stratum"],
        "probe_country_service",
    )
    network_corridor_segment_population_alignment = pd.concat(
        [country_segment_population_alignment, service_segment_population_alignment],
        ignore_index=True,
        sort=False,
    )
    if (
        not network_corridor_segment_population_alignment.empty
        and not network_corridor_segment_population_alignment["segment_population_aligned"]
        .fillna(False)
        .astype(bool)
        .all()
    ):
        mismatched = network_corridor_segment_population_alignment.loc[
            ~network_corridor_segment_population_alignment["segment_population_aligned"]
            .fillna(False)
            .astype(bool)
        ]
        raise RuntimeError(
            "Network q_u(t) and corridor p_u(c) do not use the same atomic segment population: "
            f"{len(mismatched)} analysis units differ."
        )
    country_cross_layer_distribution_audit = build_cross_layer_distribution_audit(
        country_corridor_concentration_summary,
        country_network_transition_concentration_summary,
        ["country"],
    )
    transition_country_cross_layer_distribution_audit = country_cross_layer_distribution_audit
    service_country_cross_layer_distribution_audit = build_cross_layer_distribution_audit(
        service_country_corridor_concentration_summary,
        service_country_network_transition_concentration_summary,
        ["probe_country", "service_id", "path_scope_stratum"],
    )
    service_audit_group_fields = ["probe_country", "service_id", "path_scope_stratum"]
    service_country_corridor_concentration_summary = ensure_service_path_scope_summary_rows(
        service_country_corridor_concentration_summary,
        service_country_physical_exposure,
        "corridor",
    )
    service_country_network_transition_concentration_summary = ensure_service_path_scope_summary_rows(
        service_country_network_transition_concentration_summary,
        service_country_physical_exposure,
        "network",
    )
    service_country_cross_layer_distribution_audit = ensure_service_path_scope_summary_rows(
        service_country_cross_layer_distribution_audit,
        service_country_physical_exposure,
        "cross_layer",
    )
    service_country_corridor_concentration_summary = apply_cross_layer_audit_eligibility(
        service_country_corridor_concentration_summary,
        service_country_cross_layer_distribution_audit,
        service_audit_group_fields,
    )
    service_country_physical_exposure = apply_cross_layer_audit_eligibility(
        service_country_physical_exposure,
        service_country_cross_layer_distribution_audit,
        service_audit_group_fields,
    )
    geography_dependency_paths = write_country_geography_dependency_outputs(
        args.output,
        trace_observation_frame,
        service_country_physical_exposure,
        service_country_corridor_concentration_summary,
        service_country_cross_layer_distribution_audit,
        args.country_geography_catalog,
    )
    distribution_concentration_cases = combine_distribution_case_frames(
        country_corridor_concentration_summary,
        service_country_corridor_concentration_summary,
        "country_corridor_concentration_summary",
        "service_country_corridor_concentration_summary",
    )
    distribution_audit_cases = combine_distribution_case_frames(
        country_cross_layer_distribution_audit,
        service_country_cross_layer_distribution_audit,
        "country_cross_layer_distribution_audit",
        "service_country_cross_layer_distribution_audit",
    )
    paper_corridor_observation_concentration_cases = build_paper_corridor_observation_concentration_cases(
        distribution_concentration_cases
    )
    paper_network_broad_physical_concentrated_cases = build_paper_network_broad_physical_concentrated_cases(
        distribution_audit_cases
    )
    paper_broad_corridor_distribution_cases = build_paper_broad_corridor_distribution_cases(
        distribution_audit_cases
    )
    paper_physical_exposure_cases = build_paper_physical_exposure_cases(service_country_physical_exposure)
    # Paper tables have one explicit scope per file.  Transition-country views
    # remain supplementary because the main service access question is anchored
    # at the RIPE Atlas probe country.
    for frame in (
        service_country_physical_exposure,
        service_country_corridor_concentration_summary,
        service_country_cross_layer_distribution_audit,
    ):
        if not frame.empty:
            frame["analysis_scope"] = "probe_country_service"
    for frame in (
        country_corridor_concentration_summary,
        country_network_transition_concentration_summary,
        country_cross_layer_distribution_audit,
    ):
        if not frame.empty:
            frame["analysis_scope"] = "transition_near_country"
    country_corridor_observation_distribution = country_corridor_distribution_internal.rename(
        columns={
            "share_of_observation_mass": "share_of_country_observation_mass",
            "rank_within_group": "rank_within_country",
        }
    )
    if not country_corridor_observation_distribution.empty:
        country_corridor_observation_distribution = country_corridor_observation_distribution[
            [
                "country",
                "corridor_id",
                "corridor_label",
                "observation_mass",
                "raw_segment_count_with_corridor_feasible",
                "unique_atomic_segments",
                "unique_traceroutes",
                "unique_probes",
                "unique_probe_asns",
                "group_unique_probes",
                "group_unique_probe_asns",
                "share_of_country_observation_mass",
                "rank_within_country",
                "is_top1_corridor",
                "is_top2_corridor",
                "is_top3_corridor",
                "domestic_segment_mass",
                "international_segment_mass",
            ]
        ]
    service_country_corridor_observation_distribution = service_country_corridor_distribution_internal.rename(
        columns={
            "share_of_observation_mass": "share_of_unit_observation_mass",
            "rank_within_group": "rank_within_unit",
        }
    )
    if not service_country_corridor_observation_distribution.empty:
        service_country_corridor_observation_distribution = service_country_corridor_observation_distribution[
            [
                "probe_country",
                "service_id",
                "path_scope_stratum",
                "msm_id",
                "file_name",
                "corridor_id",
                "corridor_label",
                "observation_mass",
                "raw_segment_count_with_corridor_feasible",
                "unique_atomic_segments",
                "unique_traceroutes",
                "unique_probes",
                "unique_probe_asns",
                "group_unique_probes",
                "group_unique_probe_asns",
                "share_of_unit_observation_mass",
                "rank_within_unit",
                "is_top1_corridor",
                "is_top2_corridor",
                "is_top3_corridor",
                "domestic_segment_mass",
                "international_segment_mass",
            ]
        ]
    if not country_network_transition_concentration_summary.empty:
        country_network_transition_concentration_summary = country_network_transition_concentration_summary[
            [
                "country",
                "total_mappable_segments",
                "unique_network_transitions_observed",
                "top1_network_transition_key",
                "top1_network_transition_share",
                "top2_network_transition_share",
                "top3_network_transition_share",
                "effective_network_transition_count",
                "network_transition_concentration_tier",
                "country_fallback_share",
                "sufficient_network_transition_resolution",
                "auditable_paper_case",
                "observation_sufficiency_reason",
                "failed_thresholds",
                "unique_probes",
                "unique_probe_asns",
                "domestic_segment_share",
                "international_segment_share",
            ]
        ]
    if not service_country_network_transition_concentration_summary.empty:
        service_country_network_transition_concentration_summary = (
            service_country_network_transition_concentration_summary[
                [
                    "probe_country",
                    "service_id",
                    "path_scope_stratum",
                    "msm_id",
                    "file_name",
                    "total_mappable_segments",
                    "unique_network_transitions_observed",
                    "top1_network_transition_key",
                    "top1_network_transition_share",
                    "top2_network_transition_share",
                    "top3_network_transition_share",
                    "effective_network_transition_count",
                    "network_transition_concentration_tier",
                    "country_fallback_share",
                    "sufficient_network_transition_resolution",
                    "auditable_paper_case",
                    "observation_sufficiency_reason",
                    "failed_thresholds",
                    "unique_probes",
                    "unique_probe_asns",
                    "domestic_segment_share",
                    "international_segment_share",
                ]
            ]
        )
    if not country_cross_layer_distribution_audit.empty:
        country_cross_layer_distribution_audit = country_cross_layer_distribution_audit[
            [
                "country",
                "total_mappable_segments",
                "top1_network_transition_share",
                "top2_network_transition_share",
                "top3_network_transition_share",
                "effective_network_transition_count",
                "network_transition_concentration_tier",
                "top1_corridor_share",
                "top2_corridor_share",
                "top3_corridor_share",
                "effective_corridor_count",
                "corridor_concentration_tier",
                "cross_layer_distribution_class",
                "country_fallback_share",
                "auditable_cross_layer_case",
                "sufficient_trace_observation",
                "sufficient_corridor_observation",
                "sufficient_network_transition_resolution",
                "auditable_paper_case",
                "observation_sufficiency_reason",
                "failed_thresholds",
                "unique_probes",
                "unique_probe_asns",
                "domestic_segment_share",
                "international_segment_share",
            ]
        ]
    if not service_country_cross_layer_distribution_audit.empty:
        service_country_cross_layer_distribution_audit = service_country_cross_layer_distribution_audit[
            [
                "probe_country",
                "service_id",
                "path_scope_stratum",
                "msm_id",
                "file_name",
                "total_mappable_segments",
                "top1_network_transition_share",
                "top2_network_transition_share",
                "top3_network_transition_share",
                "effective_network_transition_count",
                "network_transition_concentration_tier",
                "top1_corridor_share",
                "top2_corridor_share",
                "top3_corridor_share",
                "effective_corridor_count",
                "corridor_concentration_tier",
                "cross_layer_distribution_class",
                "country_fallback_share",
                "auditable_cross_layer_case",
                "sufficient_trace_observation",
                "sufficient_corridor_observation",
                "sufficient_network_transition_resolution",
                "auditable_paper_case",
                "observation_sufficiency_reason",
                "failed_thresholds",
                "unique_probes",
                "unique_probe_asns",
                "domestic_segment_share",
                "international_segment_share",
            ]
        ]
    # Add scope after column selection so paper-facing CSVs cannot silently mix
    # probe-country service access and transition-near-country aggregation.
    for frame in (
        service_country_physical_exposure,
        service_country_corridor_concentration_summary,
        service_country_cross_layer_distribution_audit,
    ):
        if not frame.empty:
            frame["analysis_scope"] = "probe_country_service"
    for frame in (
        country_corridor_concentration_summary,
        country_network_transition_concentration_summary,
        country_cross_layer_distribution_audit,
    ):
        if not frame.empty:
            frame["analysis_scope"] = "transition_near_country"

    cable_quadrants = build_quadrant_summary(cable_mismatch, "cable")
    corridor_quadrants = build_quadrant_summary(corridor_mismatch, "corridor")
    quadrant_summary = pd.concat([cable_quadrants, corridor_quadrants], ignore_index=True)
    candidate_space_profile = build_candidate_space_profile(feasible_frame, corridor_candidate_col)
    weighted_vs_conservative = build_weighted_vs_conservative_diversity(
        {
            "cable": cable_physical,
            "corridor": corridor_physical,
        },
        {
            "cable": cable_physical_uniform,
            "corridor": corridor_physical_uniform,
        },
    )
    unit_ambiguity_profile = build_unit_ambiguity_profile(feasible_frame if not feasible_frame.empty else candidate_frame)
    ambiguity_summary = build_ambiguity_summary(feasible_frame if not feasible_frame.empty else candidate_frame)
    ambiguity_taxonomy = build_ambiguity_taxonomy()
    core_agreement_summary = build_core_agreement_summary(feasible_frame if not feasible_frame.empty else candidate_frame)
    as_reranking_effect = build_as_reranking_effect(candidate_frame if not candidate_frame.empty else feasible_frame)
    peeringdb_footprint_summary = build_peeringdb_footprint_mismatch_summary(upper_bound_mismatch)
    cable_corridor_comparison = build_cable_corridor_comparison(
        cable_physical,
        corridor_physical,
        cable_mismatch,
        corridor_mismatch,
    )
    network_metric_catalog = build_network_diversity_metric_catalog()
    method_manifest = build_method_manifest()
    conservative_manifest = build_conservative_candidate_audit_manifest()
    framework_alignment_report = build_framework_alignment_report(
        trace_observation_frame,
        paper_inter_region_projection,
        service_country_cross_layer_distribution_audit,
        method_manifest,
        stage1_stats,
    )
    filtering_breakdown = build_filtering_breakdown(args.output)
    summary_source_frame = candidate_frame if not candidate_frame.empty else feasible_frame
    summary_frame = build_dataset_summary(
        summary_source_frame,
        cable_physical,
        corridor_physical,
        network_frame,
        cable_mismatch,
        corridor_mismatch,
        cable_corridor_comparison,
    )

    cable_physical_path = os.path.join(args.output, "unit_physical_candidate_diversity_cable.csv")
    corridor_physical_path = os.path.join(args.output, "unit_physical_candidate_diversity_corridor.csv")
    legacy_physical_path = os.path.join(args.output, "unit_physical_candidate_diversity.csv")
    cable_set_physical_path = os.path.join(args.output, "unit_physical_candidate_set_diversity_cable.csv")
    corridor_set_physical_path = os.path.join(args.output, "unit_physical_candidate_set_diversity_corridor.csv")
    network_path = os.path.join(args.output, "unit_network_layer_diversity.csv")
    legacy_network_path = os.path.join(args.output, "unit_logical_diversity.csv")
    cable_mismatch_path = os.path.join(args.output, "unit_network_physical_mismatch.csv")
    corridor_mismatch_path = os.path.join(args.output, "unit_network_physical_mismatch_corridor.csv")
    upper_bound_physical_path = os.path.join(args.output, "unit_physical_candidate_upper_bound.csv")
    upper_bound_mismatch_path = os.path.join(args.output, "unit_network_physical_upper_bound_mismatch.csv")
    paper_physical_path = os.path.join(args.output, "paper_unit_physical_candidate_diversity.csv")
    paper_mismatch_path = os.path.join(args.output, "paper_unit_network_physical_mismatch.csv")
    network_metric_catalog_path = os.path.join(args.output, "network_diversity_metric_catalog.csv")
    peeringdb_summary_path = os.path.join(args.output, "peeringdb_footprint_mismatch_summary.csv")
    unit_cross_layer_audit_path = os.path.join(args.output, "unit_cross_layer_audit.csv")
    country_cross_layer_audit_path = os.path.join(args.output, "country_cross_layer_audit.csv")
    service_country_cross_layer_audit_path = os.path.join(args.output, "service_country_cross_layer_audit.csv")
    paper_country_cross_layer_audit_path = os.path.join(args.output, "paper_country_cross_layer_audit.csv")
    paper_service_country_cross_layer_audit_path = os.path.join(args.output, "paper_service_country_cross_layer_audit.csv")
    service_country_physical_exposure_path = os.path.join(args.output, "service_country_physical_exposure_summary.csv")
    service_country_physical_exposure_alias_path = os.path.join(args.output, "service_country_physical_exposure.csv")
    country_physical_exposure_path = os.path.join(args.output, "country_physical_exposure_summary.csv")
    paper_service_country_physical_exposure_path = os.path.join(args.output, "paper_service_country_physical_exposure.csv")
    paper_service_country_corridor_concentration_path = os.path.join(args.output, "paper_service_country_corridor_concentration.csv")
    paper_service_country_cross_layer_distribution_path = os.path.join(args.output, "paper_service_country_cross_layer_distribution.csv")
    paper_transition_country_corridor_concentration_path = os.path.join(
        args.output, "paper_transition_country_corridor_concentration.csv"
    )
    paper_transition_country_network_transition_concentration_path = os.path.join(
        args.output, "paper_transition_country_network_transition_concentration.csv"
    )
    paper_transition_country_cross_layer_distribution_path = os.path.join(
        args.output, "paper_transition_country_cross_layer_distribution.csv"
    )
    cross_layer_metric_summary_path = os.path.join(args.output, "cross_layer_metric_summary.csv")
    atomic_segment_diagnostics_path = os.path.join(args.output, "atomic_segment_id_diagnostics.json")
    country_corridor_observation_distribution_path = os.path.join(
        args.output,
        "country_corridor_observation_distribution.csv",
    )
    service_country_corridor_observation_distribution_path = os.path.join(
        args.output,
        "service_country_corridor_observation_distribution.csv",
    )
    country_corridor_concentration_summary_path = os.path.join(
        args.output,
        "country_corridor_concentration_summary.csv",
    )
    transition_country_corridor_concentration_summary_path = os.path.join(
        args.output,
        "transition_country_corridor_concentration_summary.csv",
    )
    transition_country_corridor_observation_distribution_path = os.path.join(
        args.output,
        "transition_country_corridor_observation_distribution.csv",
    )
    service_country_corridor_concentration_summary_path = os.path.join(
        args.output,
        "service_country_corridor_concentration_summary.csv",
    )
    country_network_transition_distribution_path = os.path.join(
        args.output,
        "country_network_transition_distribution.csv",
    )
    service_country_network_transition_distribution_path = os.path.join(
        args.output,
        "service_country_network_transition_distribution.csv",
    )
    network_corridor_segment_population_alignment_path = os.path.join(
        args.output,
        "network_corridor_segment_population_alignment.csv",
    )
    country_network_transition_concentration_summary_path = os.path.join(
        args.output,
        "country_network_transition_concentration_summary.csv",
    )
    service_country_network_transition_concentration_summary_path = os.path.join(
        args.output,
        "service_country_network_transition_concentration_summary.csv",
    )
    country_cross_layer_distribution_audit_path = os.path.join(
        args.output,
        "country_cross_layer_distribution_audit.csv",
    )
    service_country_cross_layer_distribution_audit_path = os.path.join(
        args.output,
        "service_country_cross_layer_distribution_audit.csv",
    )
    paper_corridor_observation_concentration_cases_path = os.path.join(
        args.output,
        "paper_corridor_observation_concentration_cases.csv",
    )
    paper_network_broad_physical_concentrated_cases_path = os.path.join(
        args.output,
        "paper_network_broad_physical_concentrated_cases.csv",
    )
    paper_broad_corridor_distribution_cases_path = os.path.join(
        args.output,
        "paper_broad_corridor_distribution_cases.csv",
    )
    paper_physical_exposure_cases_path = os.path.join(args.output, "paper_physical_exposure_cases.csv")
    physical_candidate_concentration_summary_path = os.path.join(args.output, "physical_candidate_concentration_summary.csv")
    joint_cross_layer_risk_summary_path = os.path.join(args.output, "joint_cross_layer_risk_summary.csv")
    paper_physical_concentration_cases_path = os.path.join(args.output, "paper_physical_concentration_cases.csv")
    paper_joint_mismatch_cases_path = os.path.join(args.output, "paper_joint_mismatch_cases.csv")
    paper_broad_physical_space_cases_path = os.path.join(args.output, "paper_broad_physical_space_cases.csv")
    legacy_mismatch_path = os.path.join(args.output, "unit_mismatch.csv")
    quadrant_summary_path = os.path.join(args.output, "network_physical_quadrants.csv")
    cable_corridor_path = os.path.join(args.output, "cable_vs_corridor_physical_diversity.csv")
    candidate_space_profile_path = os.path.join(args.output, "candidate_space_profile.csv")
    weighted_vs_conservative_path = os.path.join(args.output, "weighted_vs_conservative_diversity.csv")
    unit_ambiguity_profile_path = os.path.join(args.output, "unit_ambiguity_profile.csv")
    ambiguity_summary_path = os.path.join(args.output, "ambiguity_summary.csv")
    ambiguity_taxonomy_path = os.path.join(args.output, "ambiguity_taxonomy.csv")
    core_agreement_summary_path = os.path.join(args.output, "core_agreement_summary.csv")
    as_reranking_effect_path = os.path.join(args.output, "as_reranking_effect.csv")
    filtering_breakdown_path = os.path.join(args.output, "filtering_breakdown.csv")
    supplementary_owner_concentration_path = os.path.join(args.output, "supplementary_owner_concentration.csv")
    method_manifest_path = os.path.join(args.output, "method_manifest.json")
    conservative_manifest_path = os.path.join(args.output, "conservative_candidate_audit_manifest.json")
    framework_alignment_report_path = os.path.join(args.output, "framework_alignment_report.json")
    summary_path = os.path.join(args.output, "dataset_summary.csv")

    cable_physical.to_csv(cable_physical_path, index=False, encoding="utf-8-sig")
    corridor_physical.to_csv(corridor_physical_path, index=False, encoding="utf-8-sig")
    cable_physical.to_csv(legacy_physical_path, index=False, encoding="utf-8-sig")
    cable_physical_uniform.to_csv(cable_set_physical_path, index=False, encoding="utf-8-sig")
    corridor_physical_uniform.to_csv(corridor_set_physical_path, index=False, encoding="utf-8-sig")
    network_frame.to_csv(network_path, index=False, encoding="utf-8-sig")
    network_frame.to_csv(legacy_network_path, index=False, encoding="utf-8-sig")
    cable_mismatch.to_csv(cable_mismatch_path, index=False, encoding="utf-8-sig")
    corridor_mismatch.to_csv(corridor_mismatch_path, index=False, encoding="utf-8-sig")
    upper_bound_physical.to_csv(upper_bound_physical_path, index=False, encoding="utf-8-sig")
    if upper_bound_mismatch.empty:
        print("Warning: upper-bound mismatch table is empty; writing a header-only CSV.")
    upper_bound_mismatch.to_csv(upper_bound_mismatch_path, index=False, encoding="utf-8-sig")
    filter_auditable_paper_rows(corridor_physical_uniform).to_csv(paper_physical_path, index=False, encoding="utf-8-sig")
    paper_unit_network_physical_mismatch = upper_bound_mismatch.loc[
        (upper_bound_mismatch["physical_level"].astype(str) == PAPER_PRIMARY_PHYSICAL_LEVEL)
        & (upper_bound_mismatch["network_definition"].astype(str) == PAPER_PRIMARY_NETWORK_DEFINITION)
    ].copy()
    if upper_bound_mismatch.empty and not paper_unit_network_physical_mismatch.empty:
        raise RuntimeError("paper_unit_network_physical_mismatch has rows while the full upper-bound mismatch table is empty.")
    filter_auditable_paper_rows(paper_unit_network_physical_mismatch).to_csv(paper_mismatch_path, index=False, encoding="utf-8-sig")
    network_metric_catalog.to_csv(network_metric_catalog_path, index=False, encoding="utf-8-sig")
    peeringdb_footprint_summary.to_csv(peeringdb_summary_path, index=False, encoding="utf-8-sig")
    unit_cross_layer_audit.to_csv(unit_cross_layer_audit_path, index=False, encoding="utf-8-sig")
    country_cross_layer_audit.to_csv(country_cross_layer_audit_path, index=False, encoding="utf-8-sig")
    service_country_cross_layer_audit.to_csv(service_country_cross_layer_audit_path, index=False, encoding="utf-8-sig")
    service_country_physical_exposure.to_csv(service_country_physical_exposure_path, index=False, encoding="utf-8-sig")
    service_country_physical_exposure.to_csv(service_country_physical_exposure_alias_path, index=False, encoding="utf-8-sig")
    country_physical_exposure.to_csv(country_physical_exposure_path, index=False, encoding="utf-8-sig")
    filter_auditable_paper_rows(service_country_physical_exposure).to_csv(
        paper_service_country_physical_exposure_path,
        index=False,
        encoding="utf-8-sig",
    )
    paper_country_cross_layer_audit.to_csv(paper_country_cross_layer_audit_path, index=False, encoding="utf-8-sig")
    paper_service_country_cross_layer_audit.to_csv(
        paper_service_country_cross_layer_audit_path,
        index=False,
        encoding="utf-8-sig",
    )
    cross_layer_metric_summary.to_csv(cross_layer_metric_summary_path, index=False, encoding="utf-8-sig")
    country_corridor_observation_distribution.to_csv(
        country_corridor_observation_distribution_path,
        index=False,
        encoding="utf-8-sig",
    )
    country_corridor_observation_distribution.to_csv(
        transition_country_corridor_observation_distribution_path,
        index=False,
        encoding="utf-8-sig",
    )
    service_country_corridor_observation_distribution.to_csv(
        service_country_corridor_observation_distribution_path,
        index=False,
        encoding="utf-8-sig",
    )
    country_corridor_concentration_summary.to_csv(
        country_corridor_concentration_summary_path,
        index=False,
        encoding="utf-8-sig",
    )
    transition_country_corridor_concentration_summary.to_csv(
        transition_country_corridor_concentration_summary_path,
        index=False,
        encoding="utf-8-sig",
    )
    service_country_corridor_concentration_summary.to_csv(
        service_country_corridor_concentration_summary_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(service_country_corridor_concentration_summary).to_csv(
        paper_service_country_corridor_concentration_path,
        index=False,
        encoding="utf-8-sig",
    )
    country_network_transition_distribution.to_csv(
        country_network_transition_distribution_path,
        index=False,
        encoding="utf-8-sig",
    )
    service_country_network_transition_distribution.to_csv(
        service_country_network_transition_distribution_path,
        index=False,
        encoding="utf-8-sig",
    )
    network_corridor_segment_population_alignment.to_csv(
        network_corridor_segment_population_alignment_path,
        index=False,
        encoding="utf-8-sig",
    )
    country_network_transition_concentration_summary.to_csv(
        country_network_transition_concentration_summary_path,
        index=False,
        encoding="utf-8-sig",
    )
    service_country_network_transition_concentration_summary.to_csv(
        service_country_network_transition_concentration_summary_path,
        index=False,
        encoding="utf-8-sig",
    )
    country_cross_layer_distribution_audit.to_csv(
        country_cross_layer_distribution_audit_path,
        index=False,
        encoding="utf-8-sig",
    )
    service_country_cross_layer_distribution_audit.to_csv(
        service_country_cross_layer_distribution_audit_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(service_country_cross_layer_distribution_audit).to_csv(
        paper_service_country_cross_layer_distribution_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(country_corridor_concentration_summary).to_csv(
        paper_transition_country_corridor_concentration_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(country_network_transition_concentration_summary).to_csv(
        paper_transition_country_network_transition_concentration_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(country_cross_layer_distribution_audit).to_csv(
        paper_transition_country_cross_layer_distribution_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(paper_corridor_observation_concentration_cases).to_csv(
        paper_corridor_observation_concentration_cases_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(paper_network_broad_physical_concentrated_cases).to_csv(
        paper_network_broad_physical_concentrated_cases_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(paper_broad_corridor_distribution_cases).to_csv(
        paper_broad_corridor_distribution_cases_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(paper_physical_exposure_cases).to_csv(
        paper_physical_exposure_cases_path,
        index=False,
        encoding="utf-8-sig",
    )
    physical_candidate_concentration_summary.to_csv(
        physical_candidate_concentration_summary_path,
        index=False,
        encoding="utf-8-sig",
    )
    joint_cross_layer_risk_summary.to_csv(
        joint_cross_layer_risk_summary_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(paper_physical_concentration_cases).to_csv(
        paper_physical_concentration_cases_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(paper_joint_mismatch_cases).to_csv(
        paper_joint_mismatch_cases_path,
        index=False,
        encoding="utf-8-sig",
    )
    filter_auditable_paper_rows(paper_broad_physical_space_cases).to_csv(
        paper_broad_physical_space_cases_path,
        index=False,
        encoding="utf-8-sig",
    )
    cable_mismatch.to_csv(legacy_mismatch_path, index=False, encoding="utf-8-sig")
    quadrant_summary.to_csv(quadrant_summary_path, index=False, encoding="utf-8-sig")
    cable_corridor_comparison.to_csv(cable_corridor_path, index=False, encoding="utf-8-sig")
    candidate_space_profile.to_csv(candidate_space_profile_path, index=False, encoding="utf-8-sig")
    weighted_vs_conservative.to_csv(weighted_vs_conservative_path, index=False, encoding="utf-8-sig")
    unit_ambiguity_profile.to_csv(unit_ambiguity_profile_path, index=False, encoding="utf-8-sig")
    ambiguity_summary.to_csv(ambiguity_summary_path, index=False, encoding="utf-8-sig")
    ambiguity_taxonomy.to_csv(ambiguity_taxonomy_path, index=False, encoding="utf-8-sig")
    core_agreement_summary.to_csv(core_agreement_summary_path, index=False, encoding="utf-8-sig")
    as_reranking_effect.to_csv(as_reranking_effect_path, index=False, encoding="utf-8-sig")
    filtering_breakdown.to_csv(filtering_breakdown_path, index=False, encoding="utf-8-sig")
    supplementary_owner_concentration.to_csv(
        supplementary_owner_concentration_path,
        index=False,
        encoding="utf-8-sig",
    )
    summary_frame.to_csv(summary_path, index=False, encoding="utf-8-sig")
    with open(atomic_segment_diagnostics_path, "w", encoding="utf-8") as handle:
        json.dump(atomic_segment_id_diagnostics, handle, indent=2, ensure_ascii=False)
    with open(method_manifest_path, "w", encoding="utf-8") as handle:
        json.dump(method_manifest, handle, indent=2, ensure_ascii=False)
    with open(conservative_manifest_path, "w", encoding="utf-8") as handle:
        json.dump(conservative_manifest, handle, indent=2, ensure_ascii=False)
    with open(framework_alignment_report_path, "w", encoding="utf-8") as handle:
        json.dump(framework_alignment_report, handle, indent=2, ensure_ascii=False)

    write_quadrant_scatter_svg(
        cable_mismatch,
        os.path.join(args.output, "network_physical_quadrant_scatter_cable.svg"),
        "Network-layer diversity vs cable-level physical diversity",
    )
    write_quadrant_scatter_svg(
        corridor_mismatch,
        os.path.join(args.output, "network_physical_quadrant_scatter_corridor.svg"),
        "Network-layer diversity vs corridor-level physical diversity",
    )
    write_quadrant_bar_svg(
        cable_quadrants,
        os.path.join(args.output, "network_physical_quadrant_counts_cable.svg"),
        "Network-physical quadrant counts (cable level)",
    )
    write_quadrant_bar_svg(
        corridor_quadrants,
        os.path.join(args.output, "network_physical_quadrant_counts_corridor.svg"),
        "Network-physical quadrant counts (corridor level)",
    )
    write_cable_corridor_comparison_svg(
        cable_corridor_comparison,
        os.path.join(args.output, "cable_vs_corridor_physical_diversity.svg"),
    )

    print(f"Saved trace candidate table to {trace_output}")
    print(f"Saved feasible candidate-space table to {trace_feasible_output}")
    print(f"Saved network-layer diversity table to {network_path}")
    print(f"Saved cable-level physical diversity table to {cable_physical_path}")
    print(f"Saved corridor-level physical diversity table to {corridor_physical_path}")
    print(f"Saved cable-level feasible-set diversity table to {cable_set_physical_path}")
    print(f"Saved corridor-level feasible-set diversity table to {corridor_set_physical_path}")
    print(f"Saved network-physical mismatch table to {cable_mismatch_path}")
    print(f"Saved corridor-level mismatch table to {corridor_mismatch_path}")
    print(f"Saved physical upper-bound table to {upper_bound_physical_path}")
    print(f"Saved upper-bound mismatch table to {upper_bound_mismatch_path}")
    print(f"Saved supplementary legacy physical-diversity alias to {paper_physical_path}")
    print(f"Saved supplementary legacy upper-bound mismatch alias to {paper_mismatch_path}")
    print(f"Saved network-diversity metric catalog to {network_metric_catalog_path}")
    print(f"Saved PeeringDB footprint mismatch summary to {peeringdb_summary_path}")
    print(f"Saved unit cross-layer audit table to {unit_cross_layer_audit_path}")
    print(f"Saved country cross-layer audit table to {country_cross_layer_audit_path}")
    print(f"Saved service-country cross-layer audit table to {service_country_cross_layer_audit_path}")
    print(f"Saved supplementary legacy country cross-layer audit alias to {paper_country_cross_layer_audit_path}")
    print(f"Saved supplementary legacy service-country cross-layer audit alias to {paper_service_country_cross_layer_audit_path}")
    print(f"Saved cross-layer metric summary to {cross_layer_metric_summary_path}")
    print(f"Saved atomic segment ID diagnostics to {atomic_segment_diagnostics_path}")
    print(f"Saved country corridor observation distribution to {country_corridor_observation_distribution_path}")
    print(f"Saved service-country corridor observation distribution to {service_country_corridor_observation_distribution_path}")
    print(f"Saved country corridor concentration summary to {country_corridor_concentration_summary_path}")
    print(f"Saved service-country corridor concentration summary to {service_country_corridor_concentration_summary_path}")
    print(f"Saved country network-transition distribution to {country_network_transition_distribution_path}")
    print(f"Saved service-country network-transition distribution to {service_country_network_transition_distribution_path}")
    print(f"Saved network/corridor atomic-segment alignment audit to {network_corridor_segment_population_alignment_path}")
    print(f"Saved country network-transition concentration summary to {country_network_transition_concentration_summary_path}")
    print(f"Saved service-country network-transition concentration summary to {service_country_network_transition_concentration_summary_path}")
    print(f"Saved country cross-layer distribution audit to {country_cross_layer_distribution_audit_path}")
    print(f"Saved service-country cross-layer distribution audit to {service_country_cross_layer_distribution_audit_path}")
    print(f"Saved paper corridor observation concentration cases to {paper_corridor_observation_concentration_cases_path}")
    print(f"Saved paper network-broad physical-concentrated cases to {paper_network_broad_physical_concentrated_cases_path}")
    print(f"Saved paper broad corridor-distribution cases to {paper_broad_corridor_distribution_cases_path}")
    print(f"Saved physical-candidate concentration summary to {physical_candidate_concentration_summary_path}")
    print(f"Saved joint cross-layer risk summary to {joint_cross_layer_risk_summary_path}")
    print(f"Saved supplementary candidate-breadth concentration cases to {paper_physical_concentration_cases_path}")
    print(f"Saved supplementary compression/candidate-breadth cases to {paper_joint_mismatch_cases_path}")
    print(f"Saved supplementary broad candidate-breadth cases to {paper_broad_physical_space_cases_path}")
    print(f"Saved cable-vs-corridor comparison table to {cable_corridor_path}")
    print(f"Saved candidate-space profile to {candidate_space_profile_path}")
    print(f"Saved weighted-vs-conservative diversity table to {weighted_vs_conservative_path}")
    print(f"Saved unit ambiguity profile to {unit_ambiguity_profile_path}")
    print(f"Saved ambiguity summary to {ambiguity_summary_path}")
    print(f"Saved ambiguity taxonomy to {ambiguity_taxonomy_path}")
    print(f"Saved core agreement summary to {core_agreement_summary_path}")
    print(f"Saved AS reranking effect to {as_reranking_effect_path}")
    print(f"Saved filtering breakdown to {filtering_breakdown_path}")
    print(f"Saved supplementary owner concentration to {supplementary_owner_concentration_path}")
    print(f"Saved country geography candidate-dependency table to {geography_dependency_paths['country']}")
    print(f"Saved geography-type candidate-dependency summary to {geography_dependency_paths['summary']}")
    print(f"Saved paper geography candidate-dependency table to {geography_dependency_paths['paper']}")
    print(f"Saved method manifest to {method_manifest_path}")
    print(f"Saved conservative candidate-audit manifest to {conservative_manifest_path}")
    print(f"Saved quadrant summary table to {quadrant_summary_path}")
    print(f"Saved dataset summary table to {summary_path}")

    paper_primary_distribution_frame = (
        service_country_corridor_concentration_summary
        if not service_country_corridor_concentration_summary.empty
        else country_corridor_concentration_summary
    )
    paper_primary_cross_layer_frame = (
        service_country_cross_layer_distribution_audit
        if not service_country_cross_layer_distribution_audit.empty
        else country_cross_layer_distribution_audit
    )
    num_countries_audited = int(len(country_corridor_concentration_summary))
    num_service_country_units_audited = int(len(service_country_corridor_concentration_summary))
    median_top1_corridor_share = (
        float(pd.to_numeric(paper_primary_distribution_frame["top1_corridor_share"], errors="coerce").median())
        if not paper_primary_distribution_frame.empty
        else float("nan")
    )
    median_top3_corridor_share = (
        float(pd.to_numeric(paper_primary_distribution_frame["top3_corridor_share"], errors="coerce").median())
        if not paper_primary_distribution_frame.empty
        else float("nan")
    )
    concentration_counts = (
        paper_primary_distribution_frame["corridor_concentration_tier"].astype(str).value_counts()
        if not paper_primary_distribution_frame.empty
        else pd.Series(dtype=int)
    )
    total_distribution_units = max(int(len(paper_primary_distribution_frame)), 1)
    severe_count = int(concentration_counts.get("severe_corridor_observation_concentration", 0))
    moderate_count = int(concentration_counts.get("moderate_corridor_observation_concentration", 0))
    weak_count = int(concentration_counts.get("weak_corridor_observation_concentration", 0))
    broad_count = int(concentration_counts.get("broad_corridor_observation_distribution", 0))
    network_broad_physical_concentrated_count = (
        int(
            paper_primary_cross_layer_frame["cross_layer_distribution_class"]
            .astype(str)
            .eq("network_broad_physical_concentrated")
            .sum()
        )
        if not paper_primary_cross_layer_frame.empty
        else 0
    )
    total_cross_layer_units = max(int(len(paper_primary_cross_layer_frame)), 1)
    print(
        "Corridor observation audit summary: "
        f"countries={num_countries_audited}, "
        f"service_country_units={num_service_country_units_audited}, "
        f"median_top1_corridor_share={median_top1_corridor_share:.4f}, "
        f"median_top3_corridor_share={median_top3_corridor_share:.4f}"
    )
    print(
        "Corridor observation concentration tiers: "
        f"severe={severe_count} ({severe_count / total_distribution_units:.2%}), "
        f"moderate={moderate_count} ({moderate_count / total_distribution_units:.2%}), "
        f"weak={weak_count} ({weak_count / total_distribution_units:.2%}), "
        f"broad={broad_count} ({broad_count / total_distribution_units:.2%})"
    )
    print(
        "Cross-layer distribution concentration signal: "
        f"network_broad_physical_concentrated={network_broad_physical_concentrated_count} "
        f"({network_broad_physical_concentrated_count / total_cross_layer_units:.2%})"
    )


if __name__ == "__main__":
    main()
