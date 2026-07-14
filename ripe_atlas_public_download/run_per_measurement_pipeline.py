#!/usr/bin/env python3
"""Run the analysis pipeline separately for downloaded public Atlas measurements."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DEFAULT_INPUT_DIR = REPO_DIR / "data" / "traceroute_rundnsroot" / "ripe_atlas_public_20260701_0000_0100"
DEFAULT_OUTPUT_ROOT = REPO_DIR / "output" / "public_traceroute_by_msmid"
DEFAULT_AS_PRECOMPUTE = REPO_DIR / "output" / "preprocessed" / "as_graph_owner_reachability.pkl.gz"


def parse_args() -> argparse.Namespace:
    """Parse CLI options for per-measurement pipeline execution."""
    parser = argparse.ArgumentParser(
        description="Run main_analysis, postprocess, and robustness separately for each downloaded RIPE Atlas msm_id."
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Directory containing downloaded RIPE Atlas result JSON files.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Root directory for per-msm_id result folders.",
    )
    parser.add_argument(
        "--as-precompute-file",
        default=str(DEFAULT_AS_PRECOMPUTE),
        help="AS-graph precompute file passed to main_analysis.py.",
    )
    parser.add_argument(
        "--measurement-id",
        type=int,
        action="append",
        default=None,
        help="Optional msm_id filter. Repeat to run only selected measurements.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a measurement when the full postprocess output already exists in its output folder.",
    )
    parser.add_argument(
        "--skip-robustness",
        action="store_true",
        help="Skip robustness_compare.py for faster smoke tests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned commands without running them.",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    """Return a filesystem-safe slug."""
    return re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower() or "unnamed"


def extract_measurement_id(path: Path) -> Optional[int]:
    """Extract msm_id from a downloaded result filename."""
    match = re.search(r"_msm(\d+)_", path.name)
    if not match:
        return None
    return int(match.group(1))


def extract_dataset_label(path: Path) -> str:
    """Return the filename prefix before the msm_id token."""
    return path.name.split("_msm", 1)[0]


def discover_measurement_files(input_dir: Path, selected_ids: Optional[Iterable[int]]) -> List[Dict[str, Any]]:
    """Discover downloaded measurement result files."""
    selected = set(selected_ids or [])
    records: List[Dict[str, Any]] = []
    for path in sorted(input_dir.glob("*.json")):
        msm_id = extract_measurement_id(path)
        if msm_id is None:
            continue
        if selected and msm_id not in selected:
            continue
        label = extract_dataset_label(path)
        records.append(
            {
                "msm_id": msm_id,
                "label": label,
                "input_file": path,
                "output_dir_name": f"msm{msm_id}_{slugify(label)}",
            }
        )
    return records


def run_command(command: List[str], cwd: Path, dry_run: bool) -> int:
    """Run one subprocess command and return its exit code."""
    print("Running:", " ".join(command))
    if dry_run:
        return 0
    completed = subprocess.run(command, cwd=str(cwd), check=False)
    return int(completed.returncode)


def load_json_if_exists(path: Path) -> Dict[str, Any]:
    """Load a JSON object when present."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def file_size(path: Path) -> int:
    """Return file size or zero."""
    return path.stat().st_size if path.exists() else 0


def build_summary_row(record: Dict[str, Any], output_dir: Path, status: str) -> Dict[str, Any]:
    """Build one row for the per-measurement run index."""
    manifest = load_json_if_exists(output_dir / "cable_matching_manifest.json")
    stats = load_json_if_exists(output_dir / "cable_matching_stats_5051.json")
    return {
        "msm_id": record["msm_id"],
        "label": record["label"],
        "status": status,
        "input_file": str(record["input_file"].relative_to(REPO_DIR)),
        "output_dir": str(output_dir.relative_to(REPO_DIR)),
        "input_bytes": file_size(record["input_file"]),
        "total_files_processed": manifest.get("total_files_processed", ""),
        "total_traces_processed": manifest.get("total_traces_processed", ""),
        "empty_trace_count": manifest.get("empty_trace_count", ""),
        "links_with_feasible_candidates": manifest.get("links_with_feasible_candidates", ""),
        "matched_links_above_threshold": manifest.get("matched_links_above_threshold", ""),
        "total_links_seen": stats.get("total_links_seen", ""),
        "total_candidates_generated": stats.get("total_candidates_generated", ""),
        "total_candidates_after_threshold": stats.get("total_candidates_after_threshold", ""),
        "cable_matching_output_bytes": file_size(output_dir / "cable_matching_output.json"),
        "trace_candidate_support_bytes": file_size(output_dir / "trace_candidate_support.csv"),
        "trace_feasible_candidate_space_bytes": file_size(output_dir / "trace_feasible_candidate_space.csv"),
    }


def has_completed_pipeline_output(output_dir: Path) -> bool:
    """Return whether a per-measurement output folder completed Stage 1 and postprocess."""
    return (
        (output_dir / "cable_matching_manifest.json").exists()
        and (output_dir / "dataset_summary.csv").exists()
        and (output_dir / "trace_feasible_candidate_space.csv").exists()
    )


def write_run_index(output_root: Path, rows: List[Dict[str, Any]]) -> None:
    """Write CSV and JSON run indexes."""
    output_root.mkdir(parents=True, exist_ok=True)
    csv_path = output_root / "per_msmid_run_index.csv"
    json_path = output_root / "per_msmid_run_index.json"
    fieldnames = list(rows[0].keys()) if rows else [
        "msm_id",
        "label",
        "status",
        "input_file",
        "output_dir",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "rows": rows,
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )


def main() -> None:
    """Run per-measurement analysis jobs."""
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_root = Path(args.output_root).resolve()
    records = discover_measurement_files(input_dir, args.measurement_id)
    if not records:
        raise ValueError(f"No downloaded measurement JSON files found under {input_dir}")

    output_root.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    print(f"Discovered {len(records)} downloaded measurement files.")

    for index, record in enumerate(records, start=1):
        output_dir = output_root / record["output_dir_name"]
        print(f"[{index}/{len(records)}] msm_id={record['msm_id']} label={record['label']}")
        if args.skip_existing and has_completed_pipeline_output(output_dir):
            print(f"  skipping existing output: {output_dir}")
            rows.append(build_summary_row(record, output_dir, "skipped_existing"))
            write_run_index(output_root, rows)
            continue

        output_dir.mkdir(parents=True, exist_ok=True)
        main_command = [
            sys.executable,
            "source/main_analysis.py",
            "--traceroute-input",
            str(record["input_file"]),
            "--output-dir",
            str(output_dir),
            "--as-precompute-file",
            str(Path(args.as_precompute_file).resolve()),
        ]
        postprocess_command = [
            sys.executable,
            "source/postprocess_candidate_output.py",
            "--input",
            str(output_dir / "cable_matching_output.json"),
            "--output",
            str(output_dir),
        ]
        robustness_command = [
            sys.executable,
            "source/robustness_compare.py",
            "--input",
            str(output_dir / "trace_candidate_support.csv"),
            "--output",
            str(output_dir),
        ]

        status = "completed"
        for command in [main_command, postprocess_command]:
            return_code = run_command(command, REPO_DIR, args.dry_run)
            if return_code != 0:
                status = f"failed_{Path(command[1]).stem}"
                break
        if status == "completed" and not args.skip_robustness:
            return_code = run_command(robustness_command, REPO_DIR, args.dry_run)
            if return_code != 0:
                status = "failed_robustness_compare"

        rows.append(build_summary_row(record, output_dir, status))
        write_run_index(output_root, rows)
        if status != "completed":
            raise RuntimeError(f"Pipeline failed for msm_id={record['msm_id']} with status={status}")

    print(f"Per-measurement run index written under {output_root}")


if __name__ == "__main__":
    main()
