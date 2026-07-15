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
    """Greedily select nearest same-probe pairs without reusing either trace."""
    required = ["probe_id", "timestamp_dt", "trace_id"]
    if any(column not in left.columns or column not in right.columns for column in required):
        return pd.DataFrame()
    left_frame = left.dropna(subset=["timestamp_dt"]).copy()
    right_frame = right.dropna(subset=["timestamp_dt"]).copy()
    if left_frame.empty or right_frame.empty:
        return pd.DataFrame()
    left_frame = left_frame.reset_index(drop=True)
    right_frame = right_frame.reset_index(drop=True)
    left_frame["probe_key"] = left_frame["probe_id"].astype(str)
    right_frame["probe_key"] = right_frame["probe_id"].astype(str)
    tolerance = float(tolerance_seconds)
    selected: List[Dict[str, Any]] = []
    common_probes = sorted(set(left_frame["probe_key"]) & set(right_frame["probe_key"]))
    for probe_key in common_probes:
        left_group = left_frame.loc[left_frame["probe_key"] == probe_key]
        right_group = right_frame.loc[right_frame["probe_key"] == probe_key]
        candidate_pairs: List[tuple[float, pd.Timestamp, pd.Timestamp, int, int]] = []
        for left_index, left_row in left_group.iterrows():
            deltas = (right_group["timestamp_dt"] - left_row["timestamp_dt"]).abs().dt.total_seconds()
            for right_index, delta in deltas.loc[deltas <= tolerance].items():
                candidate_pairs.append(
                    (
                        float(delta),
                        left_row["timestamp_dt"],
                        right_group.loc[right_index, "timestamp_dt"],
                        int(left_index),
                        int(right_index),
                    )
                )
        used_left: set[int] = set()
        used_right: set[int] = set()
        for delta, _, _, left_index, right_index in sorted(candidate_pairs):
            if left_index in used_left or right_index in used_right:
                continue
            used_left.add(left_index)
            used_right.add(right_index)
            row = left_frame.loc[left_index].to_dict()
            right_row = right_frame.loc[right_index]
            row.update(
                {
                    "matched_timestamp_dt": right_row["timestamp_dt"],
                    "matched_trace_id": right_row["trace_id"],
                    "matched_has_candidate": bool(right_row.get("has_candidate", False)),
                    "matched_time_delta_seconds": delta,
                }
            )
            selected.append(row)
    return pd.DataFrame(selected)


def build_shared_service_time_snapshots(
    frame: pd.DataFrame,
    services: List[str],
    tolerance_seconds: float,
) -> pd.DataFrame:
    """Build a common probe-time cohort present in every requested service."""
    columns = [
        "snapshot_id",
        "probe_id",
        "service_id",
        "comparison_service_id",
        "trace_id",
        "timestamp",
        "matched_time_delta_seconds",
        "inter_region_candidate_exposure",
    ]
    if len(services) < 3 or frame.empty:
        return pd.DataFrame(columns=columns)
    anchor_service = services[0]
    anchor = frame.loc[frame["service_id"].astype(str) == anchor_service].copy()
    if anchor.empty:
        return pd.DataFrame(columns=columns)
    matches_by_service: Dict[str, pd.DataFrame] = {}
    shared_anchor_ids = set(anchor["trace_id"].astype(str))
    for service in services[1:]:
        other = frame.loc[frame["service_id"].astype(str) == service].copy()
        matches = nearest_time_probe_matches(anchor, other, tolerance_seconds)
        matches_by_service[service] = matches
        shared_anchor_ids &= set(matches.get("trace_id", pd.Series(dtype=object)).astype(str))
    if not shared_anchor_ids:
        return pd.DataFrame(columns=columns)

    anchor_lookup = anchor.set_index(anchor["trace_id"].astype(str), drop=False)
    rows: List[Dict[str, Any]] = []
    for snapshot_number, anchor_trace_id in enumerate(sorted(shared_anchor_ids), start=1):
        anchor_row = anchor_lookup.loc[anchor_trace_id]
        if isinstance(anchor_row, pd.DataFrame):
            anchor_row = anchor_row.iloc[0]
        snapshot_id = f"snapshot-{snapshot_number}:{anchor_trace_id}"
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "probe_id": anchor_row["probe_id"],
                "service_id": anchor_service,
                "comparison_service_id": "ALL_SERVICES",
                "trace_id": anchor_trace_id,
                "timestamp": anchor_row.get("timestamp"),
                "matched_time_delta_seconds": 0.0,
                "inter_region_candidate_exposure": bool(anchor_row.get("has_candidate", False)),
            }
        )
        for service in services[1:]:
            matched_row = matches_by_service[service].loc[
                matches_by_service[service]["trace_id"].astype(str) == anchor_trace_id
            ].iloc[0]
            rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "probe_id": anchor_row["probe_id"],
                    "service_id": service,
                    "comparison_service_id": "ALL_SERVICES",
                    "trace_id": matched_row["matched_trace_id"],
                    "timestamp": matched_row["matched_timestamp_dt"],
                    "matched_time_delta_seconds": float(matched_row["matched_time_delta_seconds"]),
                    "inter_region_candidate_exposure": bool(matched_row["matched_has_candidate"]),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def main() -> None:
    """Write strict probe-and-nearest-time matched service comparison tables."""
    args = parse_args()
    services = [item.strip() for item in args.comparison_services.split(",") if item.strip()]
    run_root = REPO_DIR / "runs" / args.run_id
    frame = load_trace_frames(run_root, services)
    output = run_root / "matched_comparisons" / "__vs__".join(services)
    output.mkdir(parents=True, exist_ok=True)
    if frame.empty:
        empty = pd.DataFrame(columns=[
            "service_id",
            "comparison_service_id",
            "matched_probe_count",
            "matched_trace_tuple_count",
            "unmatched_trace_count",
            "candidate_exposure_mean",
            "mean_matched_time_delta_seconds",
        ])
        empty.to_csv(output / "paper_matched_service_comparison.csv", index=False)
        empty.to_csv(output / "paper_matched_service_pairwise_differences.csv", index=False)
        empty.to_csv(output / "paper_matched_service_common_probe_coverage.csv", index=False)
        empty.to_csv(output / "matched_service_shared_snapshots.csv", index=False)
        return
    frame["timestamp_dt"] = pd.to_datetime(frame.get("timestamp"), errors="coerce", utc=True)
    if "has_inter_region_candidate" not in frame.columns:
        raise RuntimeError(
            "Matched comparison requires `has_inter_region_candidate`; rerun Stage 1 with the current code."
        )
    frame["has_candidate"] = frame["has_inter_region_candidate"].fillna(False).astype(bool)
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
            comparison_rows.extend([
                {"service_id": left_service, "comparison_service_id": right_service, "aggregation": "probe_time_matched", "matched_probe_count": 0, "matched_trace_tuple_count": 0, "unmatched_trace_count": int(len(left)), "candidate_exposure_mean": np.nan, "mean_matched_time_delta_seconds": np.nan},
                {"service_id": right_service, "comparison_service_id": left_service, "aggregation": "probe_time_matched", "matched_probe_count": 0, "matched_trace_tuple_count": 0, "unmatched_trace_count": int(len(right)), "candidate_exposure_mean": np.nan, "mean_matched_time_delta_seconds": np.nan},
            ])
            continue
        left_mean = matches.groupby("probe_key", dropna=False)["has_candidate"].mean().mean()
        right_mean = matches.groupby("probe_key", dropna=False)["matched_has_candidate"].mean().mean()
        comparison_rows.extend([
            {"service_id": left_service, "comparison_service_id": right_service, "aggregation": "probe_time_matched", "matched_probe_count": int(matches["probe_key"].nunique()), "matched_trace_tuple_count": int(len(matches)), "unmatched_trace_count": int(len(left) - len(matches)), "candidate_exposure_mean": float(left_mean), "mean_matched_time_delta_seconds": float(matches["matched_time_delta_seconds"].mean())},
            {"service_id": right_service, "comparison_service_id": left_service, "aggregation": "probe_time_matched", "matched_probe_count": int(matches["probe_key"].nunique()), "matched_trace_tuple_count": int(len(matches)), "unmatched_trace_count": int(len(right) - matches["matched_trace_id"].nunique()), "candidate_exposure_mean": float(right_mean), "mean_matched_time_delta_seconds": float(matches["matched_time_delta_seconds"].mean())},
        ])
        difference_rows.append({"service_id_left": left_service, "service_id_right": right_service, "matched_probe_count": int(matches["probe_key"].nunique()), "matched_trace_tuple_count": int(len(matches)), "probe_balanced_exposure_difference": float(left_mean - right_mean), "mean_matched_time_delta_seconds": float(matches["matched_time_delta_seconds"].mean()), "max_matched_time_delta_seconds": float(matches["matched_time_delta_seconds"].max()), "time_match_tolerance_seconds": args.time_match_tolerance_seconds})
    coverage = pd.DataFrame(coverage_rows)
    comparison = pd.DataFrame(comparison_rows)
    differences = pd.DataFrame(difference_rows)
    shared_snapshots = build_shared_service_time_snapshots(
        frame,
        services,
        args.time_match_tolerance_seconds,
    )
    if not shared_snapshots.empty:
        shared_tuple_count = int(shared_snapshots["snapshot_id"].nunique())
        shared_probe_count = int(shared_snapshots["probe_id"].astype(str).nunique())
        for service in services:
            service_rows = shared_snapshots.loc[shared_snapshots["service_id"] == service]
            comparison_rows_for_service = {
                "service_id": service,
                "comparison_service_id": "ALL_SERVICES",
                "aggregation": "shared_probe_time_snapshot",
                "matched_probe_count": shared_probe_count,
                "matched_trace_tuple_count": shared_tuple_count,
                "unmatched_trace_count": int(
                    len(frame.loc[frame["service_id"].astype(str) == service]) - service_rows["trace_id"].nunique()
                ),
                "candidate_exposure_mean": float(service_rows["inter_region_candidate_exposure"].mean()),
                "mean_matched_time_delta_seconds": float(service_rows["matched_time_delta_seconds"].mean()),
            }
            comparison = pd.concat([comparison, pd.DataFrame([comparison_rows_for_service])], ignore_index=True)
    comparison.to_csv(output / "paper_matched_service_comparison.csv", index=False, encoding="utf-8-sig")
    differences.to_csv(output / "paper_matched_service_pairwise_differences.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(output / "paper_matched_service_common_probe_coverage.csv", index=False, encoding="utf-8-sig")
    shared_snapshots.to_csv(output / "matched_service_shared_snapshots.csv", index=False, encoding="utf-8-sig")
    print(f"Wrote strict probe-time matched comparison for {len(difference_rows)} service pairs: {output}")


if __name__ == "__main__":
    main()
