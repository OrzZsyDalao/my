import argparse
import math
import os
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else "."
BASE_DIR = os.path.dirname(SOURCE_DIR)
DEFAULT_INPUT = os.path.join(BASE_DIR, "output", "result", "trace_candidate_support.csv")
DEFAULT_OUTPUT = os.path.join(BASE_DIR, "output", "result")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Compare physical-candidate metrics across evidence settings.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input trace_candidate_support.csv file.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output directory.")
    return parser.parse_args()


def shannon_entropy(values: Iterable[float]) -> float:
    """Compute Shannon entropy for a non-negative sequence."""
    array = np.asarray([value for value in values if value > 0], dtype=float)
    total = array.sum()
    if total <= 0 or array.size == 0:
        return 0.0
    probs = array / total
    return float(-(probs * np.log(probs)).sum())


def gini_coefficient(values: Iterable[float]) -> float:
    """Compute the Gini coefficient."""
    array = np.asarray([max(value, 0.0) for value in values], dtype=float)
    if array.size == 0 or np.allclose(array.sum(), 0.0):
        return 0.0
    sorted_array = np.sort(array)
    n_items = sorted_array.size
    cumulative = np.cumsum(sorted_array)
    return float((n_items + 1 - 2 * (cumulative.sum() / cumulative[-1])) / n_items)


def normalize_within_links(frame: pd.DataFrame, score_col: str, out_col: str) -> pd.DataFrame:
    """Normalize a score column within each link."""
    result = frame.copy()
    grouped = result.groupby("link_id")[score_col].transform("sum")
    result[out_col] = np.where(grouped > 0, result[score_col] / grouped, 0.0)
    return result


def aggregate_mode_metrics(frame: pd.DataFrame, support_col: str, candidate_col: str) -> pd.DataFrame:
    """Aggregate support into per-unit physical-candidate metrics."""
    aggregated = (
        frame.groupby(["unit_id", candidate_col], dropna=False)[support_col]
        .sum()
        .reset_index(name="aggregate_support")
    )
    aggregated["aggregate_support_share"] = aggregated.groupby("unit_id")["aggregate_support"].transform(
        lambda values: values / values.sum() if values.sum() > 0 else 0.0
    )

    rows: List[Dict[str, float]] = []
    for unit_id, group in aggregated.groupby("unit_id"):
        shares = group["aggregate_support_share"].tolist()
        top_row = group.sort_values("aggregate_support_share", ascending=False).iloc[0]
        entropy_value = shannon_entropy(shares)
        rows.append(
            {
                "unit_id": unit_id,
                "dominant_candidate_support_share": float(top_row["aggregate_support_share"]),
                "candidate_entropy": entropy_value,
                "effective_num_candidates": float(math.exp(entropy_value)) if entropy_value > 0 else (1.0 if shares else 0.0),
                "gini_candidate_support": gini_coefficient(shares),
            }
        )
    return pd.DataFrame(rows)


def spearman_corr(left: pd.Series, right: pd.Series) -> float:
    """Compute a Spearman correlation with graceful fallback."""
    if left.empty or right.empty:
        return 0.0
    return float(left.corr(right, method="spearman"))


def top_k_overlap(left: pd.DataFrame, right: pd.DataFrame, metric: str, top_k: int) -> float:
    """Compute overlap ratio between top-k units under a metric."""
    if left.empty or right.empty or top_k <= 0:
        return 0.0
    left_ids = set(left.nlargest(top_k, metric)["unit_id"])
    right_ids = set(right.nlargest(top_k, metric)["unit_id"])
    if not left_ids and not right_ids:
        return 1.0
    return float(len(left_ids & right_ids) / max(len(left_ids | right_ids), 1))


def main() -> None:
    """Compare fused, geo-only, as-only, and filtered candidate-support views."""
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)

    frame = pd.read_csv(args.input)
    if frame.empty:
        raise ValueError("Input trace_candidate_support.csv is empty.")

    frame["geo_spatial_score"] = frame["geo_spatial_score"].fillna(0.0)
    frame["as_economic_score"] = frame["as_economic_score"].fillna(0.0)
    frame["normalized_candidate_support"] = frame["normalized_candidate_support"].fillna(0.0)

    geo_frame = normalize_within_links(frame, "geo_spatial_score", "geo_only_support")
    as_frame = normalize_within_links(frame, "as_economic_score", "as_only_support")
    high_conf_frame = frame[
        (frame["confidence_bucket"] == "high") | (frame["core_agreement"] == "dual_core_agreement")
    ].copy()

    mode_frames = {
        "fused_dual_core": aggregate_mode_metrics(frame, "normalized_candidate_support", "cable_id"),
        "geo_only": aggregate_mode_metrics(geo_frame, "geo_only_support", "cable_id"),
        "as_only": aggregate_mode_metrics(as_frame, "as_only_support", "cable_id"),
        "high_confidence_subset": aggregate_mode_metrics(
            high_conf_frame if not high_conf_frame.empty else frame.iloc[0:0],
            "normalized_candidate_support",
            "cable_id",
        ),
        "corridor_segment": aggregate_mode_metrics(frame, "normalized_candidate_support", "segment"),
    }

    baseline = mode_frames["fused_dual_core"]
    top_k = max(1, min(10, len(baseline)))
    rows: List[Dict[str, float]] = []

    for mode_name, mode_frame in mode_frames.items():
        merged = baseline.merge(mode_frame, on="unit_id", suffixes=("_baseline", "_mode"))
        if merged.empty:
            rows.append(
                {
                    "mode": mode_name,
                    "num_units_compared": 0,
                    "spearman_dominant_candidate_support_share": 0.0,
                    "spearman_effective_num_candidates": 0.0,
                    "topk_dominant_share_overlap": 0.0,
                }
            )
            continue

        rows.append(
            {
                "mode": mode_name,
                "num_units_compared": int(len(merged)),
                "spearman_dominant_candidate_support_share": spearman_corr(
                    merged["dominant_candidate_support_share_baseline"],
                    merged["dominant_candidate_support_share_mode"],
                ),
                "spearman_effective_num_candidates": spearman_corr(
                    merged["effective_num_candidates_baseline"],
                    merged["effective_num_candidates_mode"],
                ),
                "topk_dominant_share_overlap": top_k_overlap(
                    baseline,
                    mode_frame,
                    "dominant_candidate_support_share",
                    top_k,
                ),
            }
        )

    summary = pd.DataFrame(rows).sort_values("mode")
    summary.to_csv(os.path.join(args.output, "robustness_summary.csv"), index=False, encoding="utf-8-sig")
    print(f"Saved robustness summary to {os.path.join(args.output, 'robustness_summary.csv')}")


if __name__ == "__main__":
    main()
