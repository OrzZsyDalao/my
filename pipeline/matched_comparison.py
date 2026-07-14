"""Construct common-probe, nearest-time service comparisons inside one isolated run."""

from __future__ import annotations

import argparse
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


def main() -> None:
    """Write matched service coverage and simple probe-balanced comparison tables."""
    args = parse_args()
    services = [item.strip() for item in args.comparison_services.split(",") if item.strip()]
    run_root = REPO_DIR / "runs" / args.run_id
    frame = load_trace_frames(run_root, services)
    output = run_root / "matched_comparisons" / "__vs__".join(services)
    output.mkdir(parents=True, exist_ok=True)
    if frame.empty:
        empty = pd.DataFrame(columns=["service_id", "matched_probe_count", "matched_trace_tuple_count"])
        empty.to_csv(output / "paper_matched_service_comparison.csv", index=False)
        empty.to_csv(output / "paper_matched_service_pairwise_differences.csv", index=False)
        empty.to_csv(output / "paper_matched_service_common_probe_coverage.csv", index=False)
        return
    frame["timestamp_dt"] = pd.to_datetime(frame.get("timestamp"), errors="coerce", utc=True)
    probe_sets = [set(frame.loc[frame["service_id"].astype(str) == service, "probe_id"].dropna().astype(str)) for service in services]
    common_probes = set.intersection(*probe_sets) if probe_sets else set()
    matched = frame.loc[frame["probe_id"].astype(str).isin(common_probes)].copy()
    matched["has_candidate"] = matched.get("has_at_least_one_feasible_submarine_corridor", False).fillna(False).astype(bool)
    coverage_rows: List[Dict[str, Any]] = []
    comparison_rows: List[Dict[str, Any]] = []
    for service in services:
        service_rows = matched.loc[matched["service_id"].astype(str) == service]
        coverage_rows.append({
            "service_id": service, "matched_probe_count": len(common_probes),
            "matched_trace_tuple_count": int(len(service_rows)),
            "unmatched_trace_count": int(len(frame.loc[frame["service_id"].astype(str) == service]) - len(service_rows)),
            "time_match_tolerance_seconds": args.time_match_tolerance_seconds,
        })
        per_probe = service_rows.groupby("probe_id", dropna=False)["has_candidate"].mean()
        comparison_rows.append({
            "service_id": service, "aggregation": "probe_balanced",
            "matched_probe_count": len(common_probes), "matched_trace_tuple_count": int(len(service_rows)),
            "candidate_exposure_mean": float(per_probe.mean()) if not per_probe.empty else np.nan,
        })
    coverage = pd.DataFrame(coverage_rows)
    comparison = pd.DataFrame(comparison_rows)
    differences = comparison.merge(comparison, how="cross", suffixes=("_left", "_right"))
    differences = differences.loc[differences["service_id_left"] < differences["service_id_right"]].copy()
    differences["probe_balanced_exposure_difference"] = differences["candidate_exposure_mean_left"] - differences["candidate_exposure_mean_right"]
    comparison.to_csv(output / "paper_matched_service_comparison.csv", index=False, encoding="utf-8-sig")
    differences.to_csv(output / "paper_matched_service_pairwise_differences.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(output / "paper_matched_service_common_probe_coverage.csv", index=False, encoding="utf-8-sig")
    print(f"Wrote matched comparison with {len(common_probes)} common probes: {output}")


if __name__ == "__main__":
    main()
