"""Construct common-probe, nearest-time service comparisons inside one isolated run."""

from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from pipeline.common import REPO_DIR


def parse_args() -> argparse.Namespace:
    """Parse matched service comparison inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--comparison-services", required=True, help="Comma-separated service IDs.")
    parser.add_argument("--time-match-tolerance-seconds", type=float, default=900.0)
    return parser.parse_args()


def load_trace_frames(run_root: Path, services: List[str]) -> pd.DataFrame:
    """Load trace summaries from completed measurements in this run only."""
    index = pd.read_csv(run_root / "run_index.csv", dtype=str)
    frames = []
    for _, row in index.loc[index["status"] == "completed"].iterrows():
        path = REPO_DIR / row["output_dir"] / "trace_observation_summary.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if "service_id" in frame.columns:
            frames.append(frame.loc[frame["service_id"].astype(str).isin(services)].copy())
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def nearest_time_probe_matches(left: pd.DataFrame, right: pd.DataFrame, tolerance_seconds: float) -> pd.DataFrame:
    """Match one service pair by probe ID and nearest observed timestamp within the strict tolerance."""
    required = ["probe_id", "timestamp_dt", "trace_id"]
    if any(column not in left.columns or column not in right.columns for column in required):
        return pd.DataFrame()
    left_frame = left.dropna(subset=["timestamp_dt"]).copy()
    right_frame = right.dropna(subset=["timestamp_dt"]).copy()
    if left_frame.empty or right_frame.empty:
        return pd.DataFrame()
    left_frame["probe_key"] = left_frame["probe_id"].astype(str)
    right_frame["probe_key"] = right_frame["probe_id"].astype(str)
    # merge_asof requires the time key to be globally monotonic even with a by-key.
    left_frame = left_frame.sort_values(["timestamp_dt", "probe_key"])
    right_frame = right_frame.sort_values(["timestamp_dt", "probe_key"])
    right_columns = right_frame[["probe_key", "timestamp_dt", "trace_id", "has_candidate"]].rename(
        columns={"timestamp_dt": "matched_timestamp_dt", "trace_id": "matched_trace_id", "has_candidate": "matched_has_candidate"}
    )
    matched = pd.merge_asof(
        left_frame,
        right_columns.sort_values(["matched_timestamp_dt", "probe_key"]),
        left_on="timestamp_dt",
        right_on="matched_timestamp_dt",
        by="probe_key",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=float(tolerance_seconds)),
    )
    matched = matched.loc[matched["matched_trace_id"].notna()].copy()
    if matched.empty:
        return matched
    matched["matched_time_delta_seconds"] = (
        matched["timestamp_dt"] - matched["matched_timestamp_dt"]
    ).abs().dt.total_seconds()
    return matched


def main() -> None:
    """Write strict probe-and-nearest-time matched service comparison tables."""
    args = parse_args()
    services = [item.strip() for item in args.comparison_services.split(",") if item.strip()]
    run_root = REPO_DIR / "runs" / args.run_id
    frame = load_trace_frames(run_root, services)
    output = run_root / "matched_comparisons" / "__vs__".join(services)
    output.mkdir(parents=True, exist_ok=True)
    if frame.empty:
        empty = pd.DataFrame(columns=["service_id", "matched_probe_count", "matched_trace_tuple_count", "unmatched_trace_count"])
        empty.to_csv(output / "paper_matched_service_comparison.csv", index=False)
        empty.to_csv(output / "paper_matched_service_pairwise_differences.csv", index=False)
        empty.to_csv(output / "paper_matched_service_common_probe_coverage.csv", index=False)
        return
    frame["timestamp_dt"] = pd.to_datetime(frame.get("timestamp"), errors="coerce", utc=True)
    frame["has_candidate"] = frame.get("has_at_least_one_feasible_submarine_corridor", False).fillna(False).astype(bool)
    coverage_rows: List[Dict[str, Any]] = []
    comparison_rows: List[Dict[str, Any]] = []
    difference_rows: List[Dict[str, Any]] = []
    for left_service, right_service in combinations(services, 2):
        left = frame.loc[frame["service_id"].astype(str) == left_service].copy()
        right = frame.loc[frame["service_id"].astype(str) == right_service].copy()
        matches = nearest_time_probe_matches(left, right, args.time_match_tolerance_seconds)
        common_probes = set(left["probe_id"].dropna().astype(str)) & set(right["probe_id"].dropna().astype(str))
        coverage_rows.extend([
            {"service_id": left_service, "comparison_service_id": right_service, "matched_probe_count": int(matches["probe_key"].nunique()) if not matches.empty else 0, "matched_trace_tuple_count": int(len(matches)), "unmatched_trace_count": int(len(left) - len(matches)), "time_match_tolerance_seconds": args.time_match_tolerance_seconds},
            {"service_id": right_service, "comparison_service_id": left_service, "matched_probe_count": int(matches["probe_key"].nunique()) if not matches.empty else 0, "matched_trace_tuple_count": int(len(matches)), "unmatched_trace_count": int(len(right) - matches["matched_trace_id"].nunique()) if not matches.empty else int(len(right)), "time_match_tolerance_seconds": args.time_match_tolerance_seconds},
        ])
        if matches.empty:
            continue
        left_mean = matches.groupby("probe_key", dropna=False)["has_candidate"].mean().mean()
        right_mean = matches.groupby("probe_key", dropna=False)["matched_has_candidate"].mean().mean()
        comparison_rows.extend([
            {"service_id": left_service, "comparison_service_id": right_service, "aggregation": "probe_time_matched", "matched_probe_count": int(matches["probe_key"].nunique()), "matched_trace_tuple_count": int(len(matches)), "candidate_exposure_mean": float(left_mean), "mean_matched_time_delta_seconds": float(matches["matched_time_delta_seconds"].mean())},
            {"service_id": right_service, "comparison_service_id": left_service, "aggregation": "probe_time_matched", "matched_probe_count": int(matches["probe_key"].nunique()), "matched_trace_tuple_count": int(len(matches)), "candidate_exposure_mean": float(right_mean), "mean_matched_time_delta_seconds": float(matches["matched_time_delta_seconds"].mean())},
        ])
        difference_rows.append({"service_id_left": left_service, "service_id_right": right_service, "matched_probe_count": int(matches["probe_key"].nunique()), "matched_trace_tuple_count": int(len(matches)), "probe_balanced_exposure_difference": float(left_mean - right_mean), "mean_matched_time_delta_seconds": float(matches["matched_time_delta_seconds"].mean()), "max_matched_time_delta_seconds": float(matches["matched_time_delta_seconds"].max()), "time_match_tolerance_seconds": args.time_match_tolerance_seconds})
    coverage = pd.DataFrame(coverage_rows)
    comparison = pd.DataFrame(comparison_rows)
    differences = pd.DataFrame(difference_rows)
    comparison.to_csv(output / "paper_matched_service_comparison.csv", index=False, encoding="utf-8-sig")
    differences.to_csv(output / "paper_matched_service_pairwise_differences.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(output / "paper_matched_service_common_probe_coverage.csv", index=False, encoding="utf-8-sig")
    print(f"Wrote strict probe-time matched comparison for {len(difference_rows)} service pairs: {output}")


if __name__ == "__main__":
    main()
