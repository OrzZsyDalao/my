"""Execute Stage 1/2/robustness in a new, run-isolated experiment directory.

This is the paper pipeline entry point.  It intentionally never reuses output
directories and records every completed measurement in the current run index.
Optional cross-service matched comparisons are intentionally excluded.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pipeline.common import (
    DEFAULT_EXPERIMENT_CONFIG,
    REPO_DIR,
    git_commit_sha,
    json_hash,
    make_run_id,
    sha256_file,
    write_json,
)


DEFAULT_INPUT_DIR = REPO_DIR / "data" / "traceroute_rundnsroot" / "ripe_atlas_public_20260701_0000_0100"
DEFAULT_AS_PRECOMPUTE = REPO_DIR / "output" / "preprocessed" / "as_graph_owner_reachability.pkl.gz"


def parse_args() -> argparse.Namespace:
    """Parse isolated experiment options without changing legacy CLI contracts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--measurement-id", action="append", type=int, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--resume-run-id",
        default=None,
        help="Resume a failed or interrupted isolated run, skipping measurements already marked completed.",
    )
    parser.add_argument("--config", default=str(REPO_DIR / "config" / "default_experiment.json"))
    parser.add_argument("--as-precompute-file", default=str(DEFAULT_AS_PRECOMPUTE))
    parser.add_argument("--skip-robustness", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_config(path: Path) -> Dict[str, Any]:
    """Load a JSON configuration over the documented stable defaults."""
    config = dict(DEFAULT_EXPERIMENT_CONFIG)
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Experiment config must be a JSON object.")
        config.update(payload)
    return config


def discover_measurements(input_dir: Path, selected: List[int] | None) -> List[Dict[str, Any]]:
    """Discover downloaded Atlas measurement files deterministically."""
    wanted = set(selected or [])
    records: List[Dict[str, Any]] = []
    for path in sorted(input_dir.glob("*.json")):
        match = re.search(r"_msm(\d+)_", path.name)
        if not match:
            continue
        msm_id = int(match.group(1))
        if wanted and msm_id not in wanted:
            continue
        label = path.name.split("_msm", 1)[0]
        window_match = re.search(r"_(\d{8}T\d{6}Z)_(\d{6}Z)\.json$", path.name)
        requested_window_start = None
        requested_window_end = None
        if window_match:
            start_token, end_token = window_match.groups()
            start = datetime.strptime(start_token, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            end = datetime.strptime(start_token[:8] + "T" + end_token, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            requested_window_start = start.isoformat().replace("+00:00", "Z")
            requested_window_end = end.isoformat().replace("+00:00", "Z")
        records.append({
            "msm_id": msm_id,
            "label": label,
            "input_file": path,
            "requested_window_start": requested_window_start,
            "requested_window_end": requested_window_end,
        })
    if not records:
        raise ValueError(f"No selected RIPE Atlas JSON measurements found in {input_dir}")
    return records


def run_command(command: List[str], log_path: Path, dry_run: bool) -> None:
    """Execute one stage and capture its combined terminal output in the run log."""
    print("Running:", " ".join(command))
    if dry_run:
        return
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n$ {' '.join(command)}\n")
        completed = subprocess.run(command, cwd=REPO_DIR, stdout=log, stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write a stable CSV even when an isolated smoke run selects no rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    names = list(rows[0]) if rows else ["msm_id", "label", "status", "output_dir"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def load_json(path: Path) -> Dict[str, Any]:
    """Read a JSON object when a completed stage produced one."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    return value if isinstance(value, dict) else {}


def read_csv(path: Path) -> List[Dict[str, str]]:
    """Read a UTF-8 CSV into dictionaries, returning no rows for a missing file."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def upsert_index_row(rows: List[Dict[str, Any]], replacement: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Replace the current measurement row while preserving all other run-index rows."""
    msm_id = str(replacement["msm_id"])
    retained = [row for row in rows if str(row.get("msm_id")) != msm_id]
    retained.append(replacement)
    return retained


def trace_audit_value(path: Path, column: str) -> str:
    """Read one value from the stage-one trace denominator audit CSV."""
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle), {})
    return str(row.get(column, ""))


def reference_input_descriptors(as_precompute_file: Path) -> List[Dict[str, Any]]:
    """Describe fixed reference inputs used by every measurement in the run."""
    paths = [
        REPO_DIR / "data" / "cable" / "landing-point-geo.json",
        REPO_DIR / "data" / "ipinfo" / "ipinfo_location.mmdb",
        REPO_DIR / "data" / "ipinfo" / "ipinfo_asn.mmdb",
        REPO_DIR / "data" / "asrelationship" / "20250901.as-rel2.txt",
        REPO_DIR / "data" / "owner2asn" / "owner_to_asn.csv",
        REPO_DIR / "data" / "probe" / "20251201.json",
        as_precompute_file,
    ]
    rows = []
    for path in paths:
        rows.append({
            "path": str(path.relative_to(REPO_DIR)) if path.exists() else str(path),
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
            "sha256": sha256_file(path) if path.exists() else "",
        })
    return rows


def main() -> None:
    """Run only per-measurement Stage 1, postprocess, and robustness stages."""
    args = parse_args()
    if args.run_id and args.resume_run_id:
        raise ValueError("Use either --run-id or --resume-run-id, not both.")
    input_dir = Path(args.input_dir).resolve()
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    commit_sha = git_commit_sha()
    run_id = args.resume_run_id or args.run_id or make_run_id(commit_sha)
    run_root = REPO_DIR / "runs" / run_id
    records = discover_measurements(input_dir, args.measurement_id)
    if args.dry_run:
        for record in records:
            print(f"Would run msm_id={record['msm_id']} from {record['input_file']}")
        return
    if args.resume_run_id:
        manifest_path = run_root / "run_manifest.json"
        resolved_config_path = run_root / "inputs" / "resolved_config.json"
        if not manifest_path.exists() or not resolved_config_path.exists():
            raise FileNotFoundError(f"Resume run is missing its manifest or resolved config: {run_root}")
        run_manifest = load_json(manifest_path)
        if run_manifest.get("status") == "completed":
            raise RuntimeError(f"Run is already completed: {run_id}")
        config = load_config(resolved_config_path)
        config_digest = json_hash(config)
        if config_digest != run_manifest.get("config_hash"):
            raise RuntimeError("Resolved resume configuration does not match the run manifest.")
        commit_sha = str(run_manifest.get("git_commit_sha") or commit_sha)
        index_rows = read_csv(run_root / "run_index.csv")
        run_manifest.update({"status": "running", "resumed_at_utc": datetime.now(timezone.utc).isoformat()})
        write_json(manifest_path, run_manifest)
    else:
        if run_root.exists():
            raise FileExistsError(f"Run directory already exists; refusing reuse: {run_root}")
        (run_root / "measurements").mkdir(parents=True)
        (run_root / "logs").mkdir()
        (run_root / "inputs").mkdir()
        (run_root / "paper").mkdir()
        resolved_config_path = run_root / "inputs" / "resolved_config.json"
        write_json(resolved_config_path, config)
        config_digest = json_hash(config)
        input_rows = [
            {
                "msm_id": record["msm_id"],
                "label": record["label"],
                "input_file": str(record["input_file"].relative_to(REPO_DIR)),
                "input_sha256": sha256_file(record["input_file"]),
                "input_bytes": record["input_file"].stat().st_size,
                "requested_window_start": record.get("requested_window_start"),
                "requested_window_end": record.get("requested_window_end"),
            }
            for record in records
        ]
        write_csv(run_root / "inputs" / "input_manifest.csv", input_rows)
        reference_inputs = reference_input_descriptors(Path(args.as_precompute_file).resolve())
        write_csv(run_root / "inputs" / "reference_input_manifest.csv", reference_inputs)
        run_manifest = {
            "run_id": run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit_sha": commit_sha,
            "config_hash": config_digest,
            "config_file": str(resolved_config_path.relative_to(REPO_DIR)),
            "measurement_window": config.get("measurement_window"),
            "reference_input_manifest": str((run_root / "inputs" / "reference_input_manifest.csv").relative_to(REPO_DIR)),
            "interpretation": "measurement-observed feasible submarine corridor candidate audit; not traffic or ground-truth cable attribution",
            "status": "running",
        }
        write_json(run_root / "run_manifest.json", run_manifest)
        index_rows = []

    for record in records:
        existing_row = next((row for row in index_rows if str(row.get("msm_id")) == str(record["msm_id"])), None)
        if existing_row and existing_row.get("status") == "completed":
            print(f"Skipping completed msm_id={record['msm_id']}")
            continue
        directory_name = f"msm{record['msm_id']}_{re.sub(r'[^A-Za-z0-9]+', '-', record['label']).strip('-').lower()}"
        measurement_dir = REPO_DIR / existing_row["output_dir"] if existing_row else run_root / "measurements" / directory_name
        measurement_dir.mkdir(parents=True, exist_ok=True)
        measurement_manifest = load_json(measurement_dir / "measurement_manifest.json") or {
            "run_id": run_id,
            "git_commit_sha": commit_sha,
            "config_hash": config_digest,
            "msm_id": record["msm_id"],
            "label": record["label"],
            "input_file": str(record["input_file"].relative_to(REPO_DIR)),
            "input_sha256": sha256_file(record["input_file"]),
            "measurement_window": config.get("measurement_window"),
            "requested_window_start": record.get("requested_window_start"),
            "requested_window_end": record.get("requested_window_end"),
        }
        measurement_manifest.update({"status": "running", "error": ""})
        write_json(measurement_dir / "measurement_manifest.json", measurement_manifest)
        log_path = run_root / "logs" / f"{directory_name}.log"
        main_command = [
            sys.executable, "source/main_analysis.py", "--traceroute-input", str(record["input_file"]),
            "--output-dir", str(measurement_dir), "--as-precompute-file", str(Path(args.as_precompute_file).resolve()),
            "--run-id", run_id, "--run-config-file", str(resolved_config_path),
            "--landing-catchment-radius-km", str(config["landing_catchment_radius_km"]),
            "--landing-region-radius-km", str(config["landing_region_radius_km"]),
            "--same-city-policy", str(config["same_city_policy"]),
            "--same-city-distance-threshold-km", str(config.get("same_city_distance_threshold_km", 25.0)),
            "--timeout-gap-policy", str(config["timeout_gap_policy"]),
            "--cable-topology-policy", str(config["cable_topology_policy"]),
            "--rtt-tolerance-ms", str(config["rtt_tolerance_ms"]),
            "--candidate-support-threshold", str(config["candidate_support_threshold"]),
            "--cable-availability-mode", str(config["cable_availability_mode"]),
        ]
        requested_window = (
            f"{record['requested_window_start']}/{record['requested_window_end']}"
            if record.get("requested_window_start") and record.get("requested_window_end")
            else config.get("measurement_window")
        )
        if requested_window:
            main_command += ["--measurement-window", str(requested_window)]
        postprocess_command = [
            sys.executable, "source/postprocess_candidate_output.py", "--input",
            str(measurement_dir / "cable_matching_output.json"), "--output", str(measurement_dir),
        ]
        robustness_command = [
            sys.executable, "source/robustness_compare.py", "--input",
            str(measurement_dir / "trace_candidate_support.csv"), "--output", str(measurement_dir),
        ]
        status = "completed"
        error = ""
        try:
            stage_one_ready = all((measurement_dir / filename).exists() for filename in (
                "cable_matching_output.json", "cable_matching_stats_5051.json", "trace_denominator_audit.csv",
            ))
            postprocess_ready = all((measurement_dir / filename).exists() for filename in (
                "trace_candidate_support.csv", "dataset_summary.csv", "framework_alignment_report.json",
            ))
            robustness_ready = (measurement_dir / "robustness_conservative_candidate_audit.csv").exists()
            if not stage_one_ready:
                run_command(main_command, log_path, args.dry_run)
            if not postprocess_ready:
                run_command(postprocess_command, log_path, args.dry_run)
            if not args.skip_robustness and not robustness_ready:
                run_command(robustness_command, log_path, args.dry_run)
        except Exception as exc:
            status = "failed"
            error = str(exc)
        measurement_manifest.update({"status": status, "error": error, "completed_at_utc": datetime.now(timezone.utc).isoformat()})
        write_json(measurement_dir / "measurement_manifest.json", measurement_manifest)
        stage_stats = load_json(measurement_dir / "cable_matching_stats_5051.json")
        trace_audit_path = measurement_dir / "trace_denominator_audit.csv"
        indexed_unique_traces = trace_audit_value(trace_audit_path, "unique_traces_total")
        if status == "completed" and indexed_unique_traces and str(stage_stats.get("unique_traces_total", "")) != indexed_unique_traces:
            raise RuntimeError("Run index trace denominator does not match Stage 1 trace denominator audit.")
        index_rows = upsert_index_row(index_rows, {
            "run_id": run_id, "msm_id": record["msm_id"], "label": record["label"], "status": status,
            "output_dir": str(measurement_dir.relative_to(REPO_DIR)), "input_sha256": measurement_manifest["input_sha256"],
            "raw_results_total": stage_stats.get("raw_results_total", ""),
            "unique_traces_total": indexed_unique_traces,
            "duplicate_results_removed": stage_stats.get("duplicate_results_removed", ""),
            "atomic_segments_total": stage_stats.get("atomic_segments_total", ""),
            "error": error,
        })
        write_csv(run_root / "run_index.csv", index_rows)
        if status != "completed":
            run_manifest["status"] = "failed"
            write_json(run_root / "run_manifest.json", run_manifest)
            raise RuntimeError(error)

    run_manifest["status"] = "completed"
    run_manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    run_manifest["measurement_count"] = len(index_rows)
    write_json(run_root / "run_manifest.json", run_manifest)
    print(f"Completed isolated run: {run_root}")


if __name__ == "__main__":
    main()
