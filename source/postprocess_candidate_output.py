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
DEFAULT_UNIT_FIELDS = ["src_country", "msm_id", "file_name"]
TARGET_MISMATCH_CATEGORY = "network_high_physical_low"
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
        "interpretation_boundary": "Spatial proximity is only one evidence core and does not by itself identify a used cable.",
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


def normalize_tag_list(value: Any) -> List[str]:
    """Normalize ambiguity-tag fields into a deterministic list."""
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
    return result


def read_candidate_output(path: str) -> List[Dict[str, Any]]:
    """Read the link-level candidate-support JSON output."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("Expected cable_matching_output.json to be a JSON array.")
    return payload


def build_unit_id(link_info: Dict[str, Any], unit_fields: List[str]) -> str:
    """Build a stable unit identifier from chosen link_info fields."""
    return "|".join(f"{field}={link_info.get(field, 'NA')}" for field in unit_fields)


def explode_candidate_rows(records: List[Dict[str, Any]], unit_fields: List[str]) -> pd.DataFrame:
    """Flatten link-level candidate outputs into a candidate row table."""
    rows: List[Dict[str, Any]] = []
    for record_index, record in enumerate(records):
        link_info = record.get("link_info", {})
        match_summary = record.get("match_summary", {})
        all_segments = record.get("all_segments", [])

        unit_id = build_unit_id(link_info, unit_fields)
        link_id = "|".join(
            [
                str(link_info.get("file_name", "NA")),
                str(link_info.get("msm_id", "NA")),
                str(link_info.get("probe_id", "NA")),
                str(link_info.get("timestamp", "NA")),
                str(link_info.get("hop_range", "NA")),
                str(record_index),
            ]
        )

        for candidate in all_segments:
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
                "support_sum": match_summary.get("support_sum"),
            }
            for key, value in candidate.items():
                if isinstance(value, list):
                    row[key] = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, dict):
                    row[key] = json.dumps(value, ensure_ascii=False)
                else:
                    row[key] = value
            rows.append(row)

    return pd.DataFrame(rows)


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
                "num_candidates_with_support": int((group["aggregate_support_share"] > 0).sum()),
                "num_matched_links": int(link_counts.get(unit_id, 0)),
                "num_probes": int(probe_counts.get(unit_id, 0)),
                "physical_candidate_diversity_score": effective_num,
                "candidate_identifier_column": candidate_id_col,
            }
        )
    return pd.DataFrame(rows).sort_values("unit_id")


def build_unit_network_layer_diversity(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute network-layer diversity metrics per unit."""
    link_level = frame.drop_duplicates(subset=["unit_id", "link_id"]).copy()
    link_level["src_country"] = link_level["src_country"].fillna("NA")
    link_level["dst_country"] = link_level["dst_country"].fillna("NA")
    link_level["country_pair"] = link_level["src_country"] + "->" + link_level["dst_country"]
    link_level["src_asn_norm"] = link_level["src_asn"].apply(lambda value: normalize_token(value, prefix="AS"))
    link_level["dst_asn_norm"] = link_level["dst_asn"].apply(lambda value: normalize_token(value, prefix="AS"))
    link_level["src_dst_as_pair"] = link_level["src_asn_norm"] + "->" + link_level["dst_asn_norm"]

    rows: List[Dict[str, Any]] = []
    for unit_id, group in link_level.groupby("unit_id"):
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

        network_score_component_as_pair = as_pair_entropy + 0.5 * safe_log1p(num_src_dst_as_pairs)
        network_score_component_country_pair = country_entropy + 0.25 * safe_log1p(num_dst_countries)
        network_score_component_endpoint_asn = (
            0.5 * dst_as_entropy
            + 0.25 * src_as_entropy
            + 0.5 * safe_log1p(num_dst_asns)
            + 0.25 * safe_log1p(num_src_asns)
        )
        network_score_component_probe_target = (
            0.5 * safe_log1p(num_probes)
            + 0.5 * safe_log1p(num_files_or_targets)
            + 0.25 * safe_log1p(num_measurements)
        )

        network_layer_diversity_score_as_only = (
            network_score_component_as_pair + network_score_component_endpoint_asn
        )
        network_layer_diversity_score_country_only = network_score_component_country_pair
        network_layer_diversity_score = (
            network_score_component_as_pair
            + network_score_component_country_pair
            + network_score_component_endpoint_asn
            + network_score_component_probe_target
        )

        rows.append(
            {
                "unit_id": unit_id,
                "num_probes": num_probes,
                "num_dst_countries": num_dst_countries,
                "num_src_dst_country_pairs": num_country_pairs,
                "num_files_or_targets": num_files_or_targets,
                "num_measurements": num_measurements,
                "num_src_asns": num_src_asns,
                "num_dst_asns": num_dst_asns,
                "num_src_dst_as_pairs": num_src_dst_as_pairs,
                "link_country_sequence_entropy": country_entropy,
                "src_asn_entropy": src_as_entropy,
                "dst_asn_entropy": dst_as_entropy,
                "as_pair_entropy": as_pair_entropy,
                "src_dst_as_pair_entropy": as_pair_entropy,
                "network_score_component_as_pair": float(network_score_component_as_pair),
                "network_score_component_country_pair": float(network_score_component_country_pair),
                "network_score_component_endpoint_asn": float(network_score_component_endpoint_asn),
                "network_score_component_probe_target": float(network_score_component_probe_target),
                "network_layer_diversity_score_as_only": float(network_layer_diversity_score_as_only),
                "network_layer_diversity_score_country_only": float(network_layer_diversity_score_country_only),
                "network_layer_diversity_score": float(network_layer_diversity_score),
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


def build_unit_network_physical_mismatch(
    network_frame: pd.DataFrame,
    physical_frame: pd.DataFrame,
    physical_level: str,
) -> pd.DataFrame:
    """Join network-layer and physical diversity metrics and classify quadrants."""
    merged = network_frame.merge(physical_frame, on="unit_id", how="inner")
    if merged.empty:
        return merged

    network_median = merged["network_layer_diversity_score"].median()
    physical_median = merged["physical_candidate_diversity_score"].median()
    merged["network_high"] = merged["network_layer_diversity_score"] >= network_median
    merged["physical_low"] = merged["physical_candidate_diversity_score"] <= physical_median
    merged["network_physical_mismatch_category"] = merged.apply(
        lambda row: classify_network_physical_quadrant(bool(row["network_high"]), bool(row["physical_low"])),
        axis=1,
    )
    merged["network_physical_gap"] = (
        merged["network_layer_diversity_score"] - merged["physical_candidate_diversity_score"]
    )
    merged["logical_physical_gap"] = merged["network_physical_gap"]
    merged["logical_high"] = merged["network_high"]
    merged["mismatch_category"] = merged["network_physical_mismatch_category"]
    merged["physical_level"] = physical_level
    merged["is_target_quadrant"] = merged["network_physical_mismatch_category"] == TARGET_MISMATCH_CATEGORY

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


def build_unit_ambiguity_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ambiguity-tag support shares per unit."""
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "unit_id",
                "ambiguity_tag",
                "ambiguity_support",
                "ambiguity_support_share",
                "num_candidates_with_tag",
                "num_links_with_tag",
            ]
        )

    working = frame.copy()
    working["ambiguity_tags_list"] = working["ambiguity_tags"].apply(normalize_tag_list)
    expanded_rows: List[Dict[str, Any]] = []
    for row in working.itertuples(index=False):
        tags = list(getattr(row, "ambiguity_tags_list", []))
        for tag in tags:
            expanded_rows.append(
                {
                    "unit_id": getattr(row, "unit_id"),
                    "link_id": getattr(row, "link_id"),
                    "ambiguity_tag": tag,
                    "normalized_candidate_support": float(getattr(row, "normalized_candidate_support", 0.0) or 0.0),
                }
            )

    if not expanded_rows:
        return pd.DataFrame(
            columns=[
                "unit_id",
                "ambiguity_tag",
                "ambiguity_support",
                "ambiguity_support_share",
                "num_candidates_with_tag",
                "num_links_with_tag",
            ]
        )

    expanded = pd.DataFrame(expanded_rows)
    totals = (
        working.groupby("unit_id", dropna=False)["normalized_candidate_support"]
        .sum()
        .reset_index(name="unit_total_support")
    )
    summary = (
        expanded.groupby(["unit_id", "ambiguity_tag"], dropna=False)
        .agg(
            ambiguity_support=("normalized_candidate_support", "sum"),
            num_candidates_with_tag=("ambiguity_tag", "size"),
            num_links_with_tag=("link_id", pd.Series.nunique),
        )
        .reset_index()
    )
    summary = summary.merge(totals, on="unit_id", how="left")
    summary["ambiguity_support_share"] = np.where(
        summary["unit_total_support"] > 0,
        summary["ambiguity_support"] / summary["unit_total_support"],
        0.0,
    )
    return summary.sort_values(["unit_id", "ambiguity_tag"]).reset_index(drop=True)


def build_ambiguity_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ambiguity-tag counts and support shares globally."""
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "ambiguity_tag",
                "candidate_count",
                "link_count",
                "unit_count",
                "ambiguity_support",
                "ambiguity_support_share",
            ]
        )

    working = frame.copy()
    working["ambiguity_tags_list"] = working["ambiguity_tags"].apply(normalize_tag_list)
    total_support = float(working["normalized_candidate_support"].sum())
    expanded_rows: List[Dict[str, Any]] = []
    for row in working.itertuples(index=False):
        tags = list(getattr(row, "ambiguity_tags_list", []))
        for tag in tags:
            expanded_rows.append(
                {
                    "ambiguity_tag": tag,
                    "unit_id": getattr(row, "unit_id"),
                    "link_id": getattr(row, "link_id"),
                    "normalized_candidate_support": float(getattr(row, "normalized_candidate_support", 0.0) or 0.0),
                }
            )

    if not expanded_rows:
        return pd.DataFrame(
            columns=[
                "ambiguity_tag",
                "candidate_count",
                "link_count",
                "unit_count",
                "ambiguity_support",
                "ambiguity_support_share",
            ]
        )

    expanded = pd.DataFrame(expanded_rows)
    summary = (
        expanded.groupby("ambiguity_tag", dropna=False)
        .agg(
            candidate_count=("ambiguity_tag", "size"),
            link_count=("link_id", pd.Series.nunique),
            unit_count=("unit_id", pd.Series.nunique),
            ambiguity_support=("normalized_candidate_support", "sum"),
        )
        .reset_index()
    )
    summary["ambiguity_support_share"] = np.where(
        total_support > 0,
        summary["ambiguity_support"] / total_support,
        0.0,
    )
    return summary.sort_values("ambiguity_tag").reset_index(drop=True)


def build_ambiguity_taxonomy() -> pd.DataFrame:
    """Return a fixed ambiguity taxonomy for interpretation guidance."""
    return pd.DataFrame(AMBIGUITY_TAXONOMY_ROWS)


def build_method_manifest() -> Dict[str, Any]:
    """Return a compact method manifest for downstream interpretation."""
    return {
        "method_name": "network_physical_diversity_auditing",
        "claim_boundary": "candidate_support_not_ground_truth_cable_attribution",
        "main_question": (
            "Given observed network-layer diversity, does that diversity remain present in the physical-candidate space?"
        ),
        "evidence_cores": [
            "Geo-spatial Core",
            "AS-economic Core",
            "RTT/Physical Feasibility Core",
        ],
        "fusion_model": "dual_core_candidate_support_with_rtt_feasibility",
        "primary_target_quadrant": TARGET_MISMATCH_CATEGORY,
        "physical_levels": ["cable", "corridor"],
        "ambiguity_classes": list(KNOWN_AMBIGUITY_TAGS),
        "interpretation": (
            "Candidate support is an evidence score for physical-candidate support consistency, not a ground-truth cable attribution."
        ),
    }


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
        radius = 5.0 if category == TARGET_MISMATCH_CATEGORY else 3.8
        opacity = 0.9 if category == TARGET_MISMATCH_CATEGORY else 0.68
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
            f"<text x='{legend_x}' y='394' font-size='14' font-family='Arial' fill='{QUADRANT_COLORS[TARGET_MISMATCH_CATEGORY]}'>{TARGET_MISMATCH_CATEGORY}</text>",
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

    if candidate_frame.empty:
        raise ValueError("No candidate rows were found in the input output JSON.")

    candidate_frame = ensure_corridor_columns(candidate_frame)

    trace_output = os.path.join(args.output, "trace_candidate_support.csv")
    candidate_frame.to_csv(trace_output, index=False, encoding="utf-8-sig")

    cable_physical = build_unit_physical_candidate_diversity(candidate_frame, "cable_id", "cable")
    corridor_physical = build_unit_physical_candidate_diversity(candidate_frame, "corridor_id_fallback", "corridor")
    network_frame = build_unit_network_layer_diversity(candidate_frame)
    cable_mismatch = build_unit_network_physical_mismatch(network_frame, cable_physical, "cable")
    corridor_mismatch = build_unit_network_physical_mismatch(network_frame, corridor_physical, "corridor")
    cable_quadrants = build_quadrant_summary(cable_mismatch, "cable")
    corridor_quadrants = build_quadrant_summary(corridor_mismatch, "corridor")
    quadrant_summary = pd.concat([cable_quadrants, corridor_quadrants], ignore_index=True)
    unit_ambiguity_profile = build_unit_ambiguity_profile(candidate_frame)
    ambiguity_summary = build_ambiguity_summary(candidate_frame)
    ambiguity_taxonomy = build_ambiguity_taxonomy()
    cable_corridor_comparison = build_cable_corridor_comparison(
        cable_physical,
        corridor_physical,
        cable_mismatch,
        corridor_mismatch,
    )
    method_manifest = build_method_manifest()
    summary_frame = build_dataset_summary(
        candidate_frame,
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
    network_path = os.path.join(args.output, "unit_network_layer_diversity.csv")
    legacy_network_path = os.path.join(args.output, "unit_logical_diversity.csv")
    cable_mismatch_path = os.path.join(args.output, "unit_network_physical_mismatch.csv")
    corridor_mismatch_path = os.path.join(args.output, "unit_network_physical_mismatch_corridor.csv")
    legacy_mismatch_path = os.path.join(args.output, "unit_mismatch.csv")
    quadrant_summary_path = os.path.join(args.output, "network_physical_quadrants.csv")
    cable_corridor_path = os.path.join(args.output, "cable_vs_corridor_physical_diversity.csv")
    unit_ambiguity_profile_path = os.path.join(args.output, "unit_ambiguity_profile.csv")
    ambiguity_summary_path = os.path.join(args.output, "ambiguity_summary.csv")
    ambiguity_taxonomy_path = os.path.join(args.output, "ambiguity_taxonomy.csv")
    method_manifest_path = os.path.join(args.output, "method_manifest.json")
    summary_path = os.path.join(args.output, "dataset_summary.csv")

    cable_physical.to_csv(cable_physical_path, index=False, encoding="utf-8-sig")
    corridor_physical.to_csv(corridor_physical_path, index=False, encoding="utf-8-sig")
    cable_physical.to_csv(legacy_physical_path, index=False, encoding="utf-8-sig")
    network_frame.to_csv(network_path, index=False, encoding="utf-8-sig")
    network_frame.to_csv(legacy_network_path, index=False, encoding="utf-8-sig")
    cable_mismatch.to_csv(cable_mismatch_path, index=False, encoding="utf-8-sig")
    corridor_mismatch.to_csv(corridor_mismatch_path, index=False, encoding="utf-8-sig")
    cable_mismatch.to_csv(legacy_mismatch_path, index=False, encoding="utf-8-sig")
    quadrant_summary.to_csv(quadrant_summary_path, index=False, encoding="utf-8-sig")
    cable_corridor_comparison.to_csv(cable_corridor_path, index=False, encoding="utf-8-sig")
    unit_ambiguity_profile.to_csv(unit_ambiguity_profile_path, index=False, encoding="utf-8-sig")
    ambiguity_summary.to_csv(ambiguity_summary_path, index=False, encoding="utf-8-sig")
    ambiguity_taxonomy.to_csv(ambiguity_taxonomy_path, index=False, encoding="utf-8-sig")
    summary_frame.to_csv(summary_path, index=False, encoding="utf-8-sig")
    with open(method_manifest_path, "w", encoding="utf-8") as handle:
        json.dump(method_manifest, handle, indent=2, ensure_ascii=False)

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
    print(f"Saved network-layer diversity table to {network_path}")
    print(f"Saved cable-level physical diversity table to {cable_physical_path}")
    print(f"Saved corridor-level physical diversity table to {corridor_physical_path}")
    print(f"Saved network-physical mismatch table to {cable_mismatch_path}")
    print(f"Saved corridor-level mismatch table to {corridor_mismatch_path}")
    print(f"Saved cable-vs-corridor comparison table to {cable_corridor_path}")
    print(f"Saved unit ambiguity profile to {unit_ambiguity_profile_path}")
    print(f"Saved ambiguity summary to {ambiguity_summary_path}")
    print(f"Saved ambiguity taxonomy to {ambiguity_taxonomy_path}")
    print(f"Saved method manifest to {method_manifest_path}")
    print(f"Saved quadrant summary table to {quadrant_summary_path}")
    print(f"Saved dataset summary table to {summary_path}")


if __name__ == "__main__":
    main()
