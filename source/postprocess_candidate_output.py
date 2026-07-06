import argparse
import json
import math
import os
from html import escape
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else "."
BASE_DIR = os.path.dirname(SOURCE_DIR)
DEFAULT_INPUT = os.path.join(BASE_DIR, "output", "result", "cable_matching_output.json")
DEFAULT_OUTPUT = os.path.join(BASE_DIR, "output", "result")
PEERINGDB_DESCRIPTOR_PATH = os.path.join(DEFAULT_OUTPUT, "country_peeringdb_descriptors.csv")
DEFAULT_UNIT_FIELDS = ["src_country", "msm_id", "file_name"]
# Paper-primary relative target for the upper-bound mismatch view.
TARGET_MISMATCH_CATEGORY = "network_high_physical_upper_low"
LEGACY_WEIGHTED_TARGET_MISMATCH_CATEGORY = "network_high_physical_low"
PAPER_PRIMARY_NETWORK_DEFINITION = "as_egress_primary"
PAPER_PRIMARY_PHYSICAL_LEVEL = "corridor"
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
    """Build a stable service identifier from explicit service_id, file_name, or msm_id."""
    explicit = normalize_token(service_value)
    if explicit != "NA":
        return explicit
    file_token = normalize_token(file_name)
    msm_token = normalize_token(msm_id)
    if file_token != "NA":
        base_name = os.path.splitext(os.path.basename(file_token))[0]
        if base_name and base_name.lower() != "nan":
            return base_name
    if msm_token != "NA":
        return f"msm_{msm_token}"
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

    file_name_values = (
        result.get("file_name", pd.Series(index=result.index, dtype=object))
        .fillna("")
        .astype(str)
        .str.strip()
    )
    msm_values = (
        result.get("msm_id", pd.Series(index=result.index, dtype=object))
        .fillna("")
        .astype(str)
        .str.strip()
    )
    use_file_name = file_name_values[file_name_values.ne("") & file_name_values.str.lower().ne("nan")].nunique() > 1
    result["service_id"] = [
        derive_service_id_value(
            None,
            file_value if use_file_name else None,
            msm_value,
        )
        for file_value, msm_value in zip(file_name_values.tolist(), msm_values.tolist())
    ]
    return result


def normalize_link_level_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare a de-duplicated link-level frame with normalized AS and service identifiers."""
    link_level = frame.drop_duplicates(subset=["link_id"]).copy()
    link_level = attach_service_id(link_level)
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


def ensure_corridor_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure corridor-level identifiers exist and gracefully fall back to segment."""
    result = frame.copy()
    if "corridor_id" not in result.columns:
        result["corridor_id"] = np.nan
    if "parallel_group_id" not in result.columns:
        result["parallel_group_id"] = np.nan
    result["corridor_id_fallback"] = result["corridor_id"].where(
        result["corridor_id"].notna() & (result["corridor_id"].astype(str).str.strip() != ""),
        result["segment"],
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


def merge_peeringdb_descriptors(frame: pd.DataFrame, peeringdb_frame: pd.DataFrame) -> pd.DataFrame:
    """Attach optional PeeringDB country descriptors to a unit-level frame via src_country."""
    if frame.empty or peeringdb_frame.empty or "src_country" not in frame.columns:
        return frame
    result = frame.copy()
    descriptor_columns = [column for column in peeringdb_frame.columns if column != "country"]
    result["src_country"] = result["src_country"].fillna("").astype(str).str.upper()
    return result.merge(
        peeringdb_frame.rename(columns={"country": "src_country"})[["src_country", *descriptor_columns]],
        on="src_country",
        how="left",
    )


def build_unit_id(link_info: Dict[str, Any], unit_fields: List[str]) -> str:
    """Build a stable unit identifier from chosen link_info fields."""
    return "|".join(f"{field}={link_info.get(field, 'NA')}" for field in unit_fields)


def build_link_id(link_info: Dict[str, Any], record_index: int) -> str:
    """Build a stable link identifier used across weighted and feasible candidate views."""
    return "|".join(
        [
            str(link_info.get("file_name", "NA")),
            str(link_info.get("msm_id", "NA")),
            str(link_info.get("probe_id", "NA")),
            str(link_info.get("timestamp", "NA")),
            str(link_info.get("hop_range", "NA")),
            str(record_index),
        ]
    )


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
                "probe_id": link_info.get("probe_id"),
                "msm_id": link_info.get("msm_id"),
                "file_name": link_info.get("file_name"),
                "timestamp": link_info.get("timestamp"),
                "src_country": link_info.get("src_country"),
                "dst_country": link_info.get("dst_country"),
                "src_city": link_info.get("src_city"),
                "dst_city": link_info.get("dst_city"),
                "src_ip": link_info.get("src_ip"),
                "dst_ip": link_info.get("dst_ip"),
                "rtt_delta_ms": link_info.get("rtt_delta_ms"),
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


def build_group_identifier_frame(frame: pd.DataFrame, group_fields: Sequence[str]) -> pd.DataFrame:
    """Build stable identifier columns for cross-layer audit outputs."""
    columns = ["unit_id", "src_country", "service_id", "msm_id", "file_name"]
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
        row["service_id"] = (
            str(row["service_id"])
            if "service_id" in group_fields
            else summarize_identifier_value(group.get("service_id", pd.Series(dtype=object)))
        )
        row["msm_id"] = summarize_identifier_value(group.get("msm_id", pd.Series(dtype=object)))
        row["file_name"] = summarize_identifier_value(group.get("file_name", pd.Series(dtype=object)))
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def build_group_network_metrics(frame: pd.DataFrame, group_fields: Sequence[str]) -> pd.DataFrame:
    """Compute application-layer richness and network effective diversity for arbitrary groupings."""
    identifier_columns = ["unit_id", "src_country", "service_id", "msm_id", "file_name"]
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

    result = identifier_frame.merge(pd.DataFrame(rows), on=list(group_fields), how="inner")
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
    identifier_columns = ["unit_id", "src_country", "service_id", "msm_id", "file_name"]
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

    result = identifier_frame.merge(pd.DataFrame(rows), on=list(group_fields), how="inner")
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
    audit_frame = merge_peeringdb_descriptors(audit_frame, peeringdb_frame)

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
    """Combine paper-ready country and service-country audit frames for case selection."""
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
    """Select paper-ready cases where the best-case corridor candidate space remains narrow."""
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
    """Select paper-ready corridor cases with both concentration and network-to-physical compression."""
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
    for physical_level, physical_frame in physical_frames.items():
        if physical_frame.empty:
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
        "method_name": "network_physical_diversity_auditing",
        "claim_boundary": "candidate_support_not_ground_truth_cable_attribution",
        "main_question": "whether network-layer diversity remains broad after projection into the best-case feasible physical-candidate space",
        "primary_target_quadrant": TARGET_MISMATCH_CATEGORY,
        "primary_network_definition": PAPER_PRIMARY_NETWORK_DEFINITION,
        "primary_cross_layer_metrics": "best-case physical-candidate space width, physical-candidate concentration, and network-to-physical compression over application, network, and feasible physical-candidate layers",
        "relative_comparison_metrics": "rank and percentile outputs remain auxiliary corpus-relative comparison views",
        "analysis_scope_note": "the same non-rank best-case physical-candidate audit metrics support both global datasets and single-country datasets",
        "best_case_physical_candidate_audit": "physical_candidate_diversity_upper_bound reports the upper-bound width of the best-case feasible physical-candidate space under hard feasibility constraints",
        "physical_candidate_concentration_interpretation": "physical-candidate concentration means the best-case feasible candidate space itself is narrow",
        "network_physical_compression_interpretation": "network-to-physical compression means network effective diversity exceeds the best-case physical-candidate upper bound",
        "physical_exposure_note": "no network-to-physical compression does not imply no physical-candidate exposure",
        "peeringdb_descriptor_note": "PeeringDB descriptors are external interconnection-footprint descriptors only and are not used for physical-candidate construction or candidate-support scoring",
        "evidence_cores": [
            "geo_spatial_core",
            "as_economic_core",
            "rtt_physical_feasibility_core",
        ],
        "fusion_model": "product_of_experts",
        "physical_levels": ["corridor", "cable"],
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
            "unit_network_layer_diversity.csv",
            "trace_feasible_candidate_space.csv",
            "unit_cross_layer_audit.csv",
            "country_cross_layer_audit.csv",
            "service_country_cross_layer_audit.csv",
            "paper_country_cross_layer_audit.csv",
            "paper_service_country_cross_layer_audit.csv",
            "cross_layer_metric_summary.csv",
            "physical_candidate_concentration_summary.csv",
            "joint_cross_layer_risk_summary.csv",
            "paper_physical_concentration_cases.csv",
            "paper_joint_mismatch_cases.csv",
            "paper_broad_physical_space_cases.csv",
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
        ],
        "network_definitions": list(NETWORK_DEFINITION_COLUMNS.keys()),
        "interpretation": "best-case feasible physical-candidate audit with non-rank concentration and compression metrics as the primary interpretation",
    }


def build_conservative_candidate_audit_manifest() -> Dict[str, Any]:
    """Return a compact manifest for the infeasibility-first conservative candidate audit view."""
    return {
        "pipeline_version": "infeasibility_first_conservative_candidate_audit_v1",
        "interpretation": "best_case_physical_candidate_audit",
        "support_semantics": "evidence support, not ground-truth probability",
        "weighted_view_description": "support-thresholded candidate-support view used for backward-compatible weighted expectation analysis",
        "conservative_set_view_description": "all hard-feasible candidates are retained before support thresholding to audit the width of the best-case feasible physical-candidate space",
        "primary_cross_layer_metrics": "best-case physical-candidate concentration and network-to-physical compression are first-class outputs",
        "relative_comparison_metrics": "rank and percentile mismatch outputs remain auxiliary relative comparison views over the chosen corpus",
        "single_country_and_global_support": "the same best-case physical-candidate audit metrics apply to both single-country studies and multi-country corpora",
        "physical_candidate_concentration_interpretation": "physical-candidate concentration means the best-case feasible candidate space itself is narrow",
        "network_physical_compression_interpretation": "network-to-physical compression means network effective diversity exceeds the best-case physical-candidate upper bound",
        "physical_exposure_note": "no network-to-physical compression does not imply no physical-candidate exposure",
        "peeringdb_descriptor_note": "PeeringDB descriptors are external interconnection-footprint descriptors only and are not used for physical-candidate construction or candidate-support scoring",
        "primary_physical_level": "corridor",
        "primary_network_definition": PAPER_PRIMARY_NETWORK_DEFINITION,
        "legacy_all_segments_semantics": "support-thresholded legacy candidate list",
        "all_feasible_segments_semantics": "all hard-feasible candidates preserved before support thresholding",
        "generated_outputs": [
            "trace_feasible_candidate_space.csv",
            "unit_cross_layer_audit.csv",
            "country_cross_layer_audit.csv",
            "service_country_cross_layer_audit.csv",
            "paper_country_cross_layer_audit.csv",
            "paper_service_country_cross_layer_audit.csv",
            "cross_layer_metric_summary.csv",
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
        ],
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
    args = parse_args()
    unit_fields = [field.strip() for field in args.unit_fields.split(",") if field.strip()]
    if not unit_fields:
        unit_fields = list(DEFAULT_UNIT_FIELDS)

    os.makedirs(args.output, exist_ok=True)
    records = read_candidate_output(args.input)
    candidate_frame = explode_candidate_rows(records, unit_fields)
    feasible_frame = explode_feasible_candidate_rows(records, unit_fields)

    if candidate_frame.empty and feasible_frame.empty:
        raise ValueError("No candidate rows were found in the input output JSON.")

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

    trace_output = os.path.join(args.output, "trace_candidate_support.csv")
    trace_feasible_output = os.path.join(args.output, "trace_feasible_candidate_space.csv")
    candidate_frame.to_csv(trace_output, index=False, encoding="utf-8-sig")
    feasible_frame.to_csv(trace_feasible_output, index=False, encoding="utf-8-sig")

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
    upper_bound_mismatch = merge_peeringdb_descriptors(upper_bound_mismatch, peeringdb_descriptors)
    unit_cross_layer_audit = build_cross_layer_audit_frame(
        feasible_frame,
        ["unit_id"],
        corridor_candidate_col,
        peeringdb_descriptors,
    )
    country_cross_layer_audit = build_cross_layer_audit_frame(
        feasible_frame,
        ["src_country"],
        corridor_candidate_col,
        peeringdb_descriptors,
    )
    service_country_cross_layer_audit = build_cross_layer_audit_frame(
        feasible_frame,
        ["src_country", "service_id"],
        corridor_candidate_col,
        peeringdb_descriptors,
    )
    paper_country_cross_layer_audit = (
        country_cross_layer_audit.loc[
            country_cross_layer_audit["physical_level"].astype(str) == PAPER_PRIMARY_PHYSICAL_LEVEL
        ].reset_index(drop=True)
        if not country_cross_layer_audit.empty
        else pd.DataFrame(columns=PRIMARY_CROSS_LAYER_COLUMNS)
    )
    paper_service_country_cross_layer_audit = (
        service_country_cross_layer_audit.loc[
            service_country_cross_layer_audit["physical_level"].astype(str) == PAPER_PRIMARY_PHYSICAL_LEVEL
        ].reset_index(drop=True)
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
    cross_layer_metric_summary_path = os.path.join(args.output, "cross_layer_metric_summary.csv")
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
    method_manifest_path = os.path.join(args.output, "method_manifest.json")
    conservative_manifest_path = os.path.join(args.output, "conservative_candidate_audit_manifest.json")
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
    corridor_physical_uniform.to_csv(paper_physical_path, index=False, encoding="utf-8-sig")
    paper_unit_network_physical_mismatch = upper_bound_mismatch.loc[
        (upper_bound_mismatch["physical_level"].astype(str) == PAPER_PRIMARY_PHYSICAL_LEVEL)
        & (upper_bound_mismatch["network_definition"].astype(str) == PAPER_PRIMARY_NETWORK_DEFINITION)
    ].copy()
    if upper_bound_mismatch.empty and not paper_unit_network_physical_mismatch.empty:
        raise RuntimeError("paper_unit_network_physical_mismatch has rows while the full upper-bound mismatch table is empty.")
    paper_unit_network_physical_mismatch.to_csv(paper_mismatch_path, index=False, encoding="utf-8-sig")
    network_metric_catalog.to_csv(network_metric_catalog_path, index=False, encoding="utf-8-sig")
    peeringdb_footprint_summary.to_csv(peeringdb_summary_path, index=False, encoding="utf-8-sig")
    unit_cross_layer_audit.to_csv(unit_cross_layer_audit_path, index=False, encoding="utf-8-sig")
    country_cross_layer_audit.to_csv(country_cross_layer_audit_path, index=False, encoding="utf-8-sig")
    service_country_cross_layer_audit.to_csv(service_country_cross_layer_audit_path, index=False, encoding="utf-8-sig")
    paper_country_cross_layer_audit.to_csv(paper_country_cross_layer_audit_path, index=False, encoding="utf-8-sig")
    paper_service_country_cross_layer_audit.to_csv(
        paper_service_country_cross_layer_audit_path,
        index=False,
        encoding="utf-8-sig",
    )
    cross_layer_metric_summary.to_csv(cross_layer_metric_summary_path, index=False, encoding="utf-8-sig")
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
    paper_physical_concentration_cases.to_csv(
        paper_physical_concentration_cases_path,
        index=False,
        encoding="utf-8-sig",
    )
    paper_joint_mismatch_cases.to_csv(
        paper_joint_mismatch_cases_path,
        index=False,
        encoding="utf-8-sig",
    )
    paper_broad_physical_space_cases.to_csv(
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
    summary_frame.to_csv(summary_path, index=False, encoding="utf-8-sig")
    with open(method_manifest_path, "w", encoding="utf-8") as handle:
        json.dump(method_manifest, handle, indent=2, ensure_ascii=False)
    with open(conservative_manifest_path, "w", encoding="utf-8") as handle:
        json.dump(conservative_manifest, handle, indent=2, ensure_ascii=False)

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
    print(f"Saved paper-ready physical diversity alias to {paper_physical_path}")
    print(f"Saved paper-ready mismatch alias to {paper_mismatch_path}")
    print(f"Saved network-diversity metric catalog to {network_metric_catalog_path}")
    print(f"Saved PeeringDB footprint mismatch summary to {peeringdb_summary_path}")
    print(f"Saved unit cross-layer audit table to {unit_cross_layer_audit_path}")
    print(f"Saved country cross-layer audit table to {country_cross_layer_audit_path}")
    print(f"Saved service-country cross-layer audit table to {service_country_cross_layer_audit_path}")
    print(f"Saved paper country cross-layer audit alias to {paper_country_cross_layer_audit_path}")
    print(f"Saved paper service-country cross-layer audit alias to {paper_service_country_cross_layer_audit_path}")
    print(f"Saved cross-layer metric summary to {cross_layer_metric_summary_path}")
    print(f"Saved physical-candidate concentration summary to {physical_candidate_concentration_summary_path}")
    print(f"Saved joint cross-layer risk summary to {joint_cross_layer_risk_summary_path}")
    print(f"Saved paper physical concentration cases to {paper_physical_concentration_cases_path}")
    print(f"Saved paper joint mismatch cases to {paper_joint_mismatch_cases_path}")
    print(f"Saved paper broad physical-space cases to {paper_broad_physical_space_cases_path}")
    print(f"Saved cable-vs-corridor comparison table to {cable_corridor_path}")
    print(f"Saved candidate-space profile to {candidate_space_profile_path}")
    print(f"Saved weighted-vs-conservative diversity table to {weighted_vs_conservative_path}")
    print(f"Saved unit ambiguity profile to {unit_ambiguity_profile_path}")
    print(f"Saved ambiguity summary to {ambiguity_summary_path}")
    print(f"Saved ambiguity taxonomy to {ambiguity_taxonomy_path}")
    print(f"Saved core agreement summary to {core_agreement_summary_path}")
    print(f"Saved AS reranking effect to {as_reranking_effect_path}")
    print(f"Saved filtering breakdown to {filtering_breakdown_path}")
    print(f"Saved method manifest to {method_manifest_path}")
    print(f"Saved conservative candidate-audit manifest to {conservative_manifest_path}")
    print(f"Saved quadrant summary table to {quadrant_summary_path}")
    print(f"Saved dataset summary table to {summary_path}")


if __name__ == "__main__":
    main()
