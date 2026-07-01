import argparse
import json
import math
import os
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else "."
BASE_DIR = os.path.dirname(SOURCE_DIR)
DEFAULT_INPUT = os.path.join(BASE_DIR, "output", "result", "cable_matching_output.json")
DEFAULT_OUTPUT = os.path.join(BASE_DIR, "output", "result")
DEFAULT_UNIT_FIELDS = ["src_country", "msm_id", "file_name"]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Post-process candidate-support outputs into diversity and mismatch tables."
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
    if array.size == 0:
        return 0.0
    if np.allclose(array.sum(), 0.0):
        return 0.0
    sorted_array = np.sort(array)
    n_items = sorted_array.size
    cumulative = np.cumsum(sorted_array)
    return float((n_items + 1 - 2 * (cumulative.sum() / cumulative[-1])) / n_items)


def safe_log1p(value: float) -> float:
    """A tiny helper used when building logical-diversity scores."""
    return float(math.log1p(max(value, 0.0)))


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


def aggregate_candidate_support(frame: pd.DataFrame, candidate_id_col: str) -> pd.DataFrame:
    """Aggregate normalized candidate support per unit."""
    aggregated = (
        frame.groupby(["unit_id", candidate_id_col], dropna=False)["normalized_candidate_support"]
        .sum()
        .reset_index(name="aggregate_support")
    )
    aggregated["aggregate_support_share"] = aggregated.groupby("unit_id")["aggregate_support"].transform(
        lambda values: values / values.sum() if values.sum() > 0 else 0.0
    )
    return aggregated


def build_unit_physical_candidate_diversity(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute physical-candidate diversity metrics per unit."""
    aggregated = aggregate_candidate_support(frame, "cable_id")
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
                "dominant_candidate_id": top_row["cable_id"],
                "dominant_candidate_support_share": float(top_row["aggregate_support_share"]),
                "expected_candidate_support_total": total_support,
                "candidate_entropy": entropy_value,
                "effective_num_candidates": effective_num,
                "gini_candidate_support": gini_coefficient(support_values),
                "num_candidates_with_support": int((group["aggregate_support_share"] > 0).sum()),
                "num_matched_links": int(link_counts.get(unit_id, 0)),
                "num_probes": int(probe_counts.get(unit_id, 0)),
                "physical_candidate_diversity_score": effective_num,
            }
        )
    return pd.DataFrame(rows).sort_values("unit_id")


def build_unit_logical_diversity(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute simplified logical-diversity metrics per unit."""
    link_level = frame.drop_duplicates(subset=["unit_id", "link_id"]).copy()
    link_level["country_pair"] = link_level["src_country"].fillna("NA") + "->" + link_level["dst_country"].fillna("NA")

    rows: List[Dict[str, Any]] = []
    for unit_id, group in link_level.groupby("unit_id"):
        sequence_counts = group["country_pair"].value_counts().tolist()
        sequence_entropy = shannon_entropy(sequence_counts)
        num_probes = int(group["probe_id"].nunique())
        num_dst_countries = int(group["dst_country"].dropna().nunique())
        num_country_pairs = int(group["country_pair"].nunique())
        num_files_or_targets = int(group["file_name"].dropna().nunique())
        num_measurements = int(group["msm_id"].dropna().nunique())

        logical_diversity_score = (
            sequence_entropy
            + safe_log1p(num_dst_countries)
            + 0.5 * safe_log1p(num_probes)
            + 0.5 * safe_log1p(num_files_or_targets)
            + 0.25 * safe_log1p(num_measurements)
        )

        rows.append(
            {
                "unit_id": unit_id,
                "num_probes": num_probes,
                "num_dst_countries": num_dst_countries,
                "num_src_dst_country_pairs": num_country_pairs,
                "num_files_or_targets": num_files_or_targets,
                "num_measurements": num_measurements,
                "link_country_sequence_entropy": sequence_entropy,
                "logical_diversity_score": float(logical_diversity_score),
            }
        )
    return pd.DataFrame(rows).sort_values("unit_id")


def build_unit_mismatch(
    logical_frame: pd.DataFrame,
    physical_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Join logical and physical diversity metrics and classify mismatch types."""
    merged = logical_frame.merge(physical_frame, on="unit_id", how="inner")
    if merged.empty:
        return merged

    logical_median = merged["logical_diversity_score"].median()
    physical_median = merged["physical_candidate_diversity_score"].median()
    merged["logical_high"] = merged["logical_diversity_score"] >= logical_median
    merged["physical_low"] = merged["physical_candidate_diversity_score"] <= physical_median

    def classify(row: pd.Series) -> str:
        if row["logical_high"] and row["physical_low"]:
            return "logical_high_physical_low"
        if row["logical_high"] and not row["physical_low"]:
            return "logical_high_physical_high"
        if not row["logical_high"] and row["physical_low"]:
            return "logical_low_physical_low"
        return "logical_low_physical_high"

    merged["mismatch_category"] = merged.apply(classify, axis=1)
    merged["logical_physical_gap"] = (
        merged["logical_diversity_score"] - merged["physical_candidate_diversity_score"]
    )
    return merged.sort_values(["mismatch_category", "unit_id"])


def build_dataset_summary(
    candidate_frame: pd.DataFrame,
    physical_frame: pd.DataFrame,
    logical_frame: pd.DataFrame,
    mismatch_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Build a compact dataset-level summary table."""
    summary_rows = [
        {"metric": "candidate_rows", "value": int(len(candidate_frame))},
        {"metric": "units_with_physical_diversity", "value": int(len(physical_frame))},
        {"metric": "units_with_logical_diversity", "value": int(len(logical_frame))},
        {"metric": "units_with_mismatch", "value": int(len(mismatch_frame))},
        {
            "metric": "median_physical_candidate_diversity_score",
            "value": float(physical_frame["physical_candidate_diversity_score"].median()) if not physical_frame.empty else 0.0,
        },
        {
            "metric": "median_logical_diversity_score",
            "value": float(logical_frame["logical_diversity_score"].median()) if not logical_frame.empty else 0.0,
        },
    ]
    if not mismatch_frame.empty:
        for category, count in mismatch_frame["mismatch_category"].value_counts().items():
            summary_rows.append({"metric": f"mismatch_{category}", "value": int(count)})
    return pd.DataFrame(summary_rows)


def main() -> None:
    """Read candidate-support JSON output and emit diversity/mismatch tables."""
    args = parse_args()
    unit_fields = [field.strip() for field in args.unit_fields.split(",") if field.strip()]
    if not unit_fields:
        unit_fields = list(DEFAULT_UNIT_FIELDS)

    os.makedirs(args.output, exist_ok=True)
    records = read_candidate_output(args.input)
    candidate_frame = explode_candidate_rows(records, unit_fields)

    if candidate_frame.empty:
        raise ValueError("No candidate rows were found in the input output JSON.")

    candidate_frame.to_csv(os.path.join(args.output, "trace_candidate_support.csv"), index=False, encoding="utf-8-sig")

    physical_frame = build_unit_physical_candidate_diversity(candidate_frame)
    logical_frame = build_unit_logical_diversity(candidate_frame)
    mismatch_frame = build_unit_mismatch(logical_frame, physical_frame)
    summary_frame = build_dataset_summary(candidate_frame, physical_frame, logical_frame, mismatch_frame)

    physical_frame.to_csv(
        os.path.join(args.output, "unit_physical_candidate_diversity.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    logical_frame.to_csv(
        os.path.join(args.output, "unit_logical_diversity.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    mismatch_frame.to_csv(
        os.path.join(args.output, "unit_mismatch.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    summary_frame.to_csv(
        os.path.join(args.output, "dataset_summary.csv"),
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Saved trace candidate table to {os.path.join(args.output, 'trace_candidate_support.csv')}")
    print(f"Saved physical-candidate diversity table to {os.path.join(args.output, 'unit_physical_candidate_diversity.csv')}")
    print(f"Saved logical diversity table to {os.path.join(args.output, 'unit_logical_diversity.csv')}")
    print(f"Saved mismatch table to {os.path.join(args.output, 'unit_mismatch.csv')}")
    print(f"Saved dataset summary table to {os.path.join(args.output, 'dataset_summary.csv')}")


if __name__ == "__main__":
    main()
