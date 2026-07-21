"""Strictly package paper-facing artifacts from one completed isolated run."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pipeline.common import REPO_DIR, sha256_file, write_json


# Optional post-hoc matched-service outputs are intentionally not paper-package inputs.
PAPER_FILES = (
    "dataset_summary.csv",
    "trace_denominator_audit.csv",
    "filtering_breakdown.csv",
    "candidate_space_profile.csv",
    "paper_service_country_physical_exposure.csv",
    "paper_service_country_geography_candidate_dependency.csv",
    "paper_service_country_corridor_concentration.csv",
    "paper_service_country_cross_layer_distribution.csv",
    "service_country_network_transition_distribution.csv",
    "service_country_as_boundary_transition_distribution.csv",
    "service_country_as_boundary_transition_concentration_summary.csv",
    "network_corridor_segment_population_alignment.csv",
    "paper_corridor_observation_concentration_cases.csv",
    "paper_network_broad_physical_concentrated_cases.csv",
    "paper_broad_corridor_distribution_cases.csv",
    "robustness_conservative_candidate_audit.csv",
    "framework_alignment_report.json",
    "method_manifest.json",
    "cable_matching_manifest.json",
    "landing_region_catalog.csv",
    "corridor_catalog.csv",
)
REQUIRED_PAPER_FILES = tuple(filename for filename in PAPER_FILES if filename != "robustness_conservative_candidate_audit.csv")


def parse_args() -> argparse.Namespace:
    """Parse a strict run-ID-only packaging command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-file-mb", type=float, default=95.0)
    return parser.parse_args()


def read_index(path: Path) -> List[Dict[str, str]]:
    """Read the current run index rather than scanning historical output roots."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_readme(path: Path, run_id: str) -> None:
    """Write a compact paper-facing manifest with explicit interpretation limits."""
    sections = [
        "# Paper Results",
        f"Run ID: `{run_id}`.",
        "## 1. Scope\nThis package contains only completed measurements listed in this run's index.",
        "## 2. Observation unit\nA traceroute is decomposed into measurement-observed atomic path-transition segments.",
        "## 3. Trace denominator\nTrace IDs use measurement, probe, timestamp, and actual target IP; transport filenames are excluded.",
        "## 4. Physical projection\nCandidates are feasible submarine corridor candidates, not observed cable use.",
        "## 5. Topology\nThe default policy enumerates valid landing-station pairs on the same cable when only unordered landing metadata is available. These are reachability candidates, labelled unordered_cable_reachability, not asserted direct physical links. Explicit topology can be evaluated separately with the adjacent_only policy.",
        "## 6. Candidate exposure\nExposure means a trace contains at least one atomic segment with a feasible corridor candidate.",
        "## 7. Observation mass\nMass counts traceroute-observed transitions, not traffic volume, packets, or bytes.",
        "## 8. Corridor concentration\nConcentration is measured over feasible corridor observation distributions.",
        "## 9. Network concentration\nNetwork transition concentration is computed over the same atomic segment population.",
        "## 9.1 Network distribution\nN_u(t) counts each unique atomic segment once and q_u(t) is its normalized network-transition share. Missing endpoint ASNs remain visible as explicitly labelled country fallbacks.",
        "## 9.2 Population alignment\nThe packaged alignment audit verifies that network q_u(t) and corridor p_u(c) use exactly the same atomic segment set.",
        "## 9.3 Hop-pair AS classes\nThe complete view distinguishes cross-AS transitions, intra-AS hop pairs, and explicit country fallbacks. Separate AS-boundary-only tables audit cross-AS convergence without treating same-AS hops or unknown ASN sentinels as AS boundaries.",
        "## 10. Cross-layer audit\nThe audit compares distribution shapes, not AS and corridor counts as interchangeable units.",
        "## 11. Robustness\nSensitivity outputs retain timeout-gap, geolocation, topology, and support uncertainty where available.",
        "## 12. Candidate breadth\nUnique corridor counts are candidate-space breadth descriptors, not the primary observation-concentration metric.",
        "## 13. Interpretation boundary\nNo table establishes real traffic volume, actual cable use, or ground-truth cable attribution.",
        "## 14. Country geography stratification\nThe country-geography table reports an inter-region feasible-corridor candidate-dependency proxy. Geography type is explanatory metadata only and never changes physical candidate construction.",
    ]
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def main() -> None:
    """Validate and copy only current-run completed measurement artifacts."""
    args = parse_args()
    run_root = REPO_DIR / "runs" / args.run_id
    manifest_path = run_root / "run_manifest.json"
    index_path = run_root / "run_index.csv"
    if not manifest_path.exists() or not index_path.exists():
        raise FileNotFoundError("Run manifest or run index is missing.")
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if run_manifest.get("status") != "completed":
        raise RuntimeError("Only completed runs may be packaged.")
    max_bytes = int(args.max_file_mb * 1024 * 1024)
    destination = REPO_DIR / "paper_results" / args.run_id
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite package: {destination}")
    destination.mkdir(parents=True)
    copied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    completed = [row for row in read_index(index_path) if row.get("status") == "completed"]
    if not completed:
        raise RuntimeError("Current run index has no completed measurements.")
    for row in completed:
        measurement_dir = REPO_DIR / row["output_dir"]
        measurement_manifest_path = measurement_dir / "measurement_manifest.json"
        if not measurement_manifest_path.exists():
            raise RuntimeError(f"Missing measurement manifest: {measurement_dir}")
        measurement_manifest = json.loads(measurement_manifest_path.read_text(encoding="utf-8"))
        if measurement_manifest.get("run_id") != args.run_id or measurement_manifest.get("git_commit_sha") != run_manifest.get("git_commit_sha"):
            raise RuntimeError(f"Manifest mismatch for {measurement_dir}")
        trace_audit = measurement_dir / "trace_denominator_audit.csv"
        if not trace_audit.exists():
            raise RuntimeError(f"Trace denominator audit is missing: {measurement_dir}")
        with trace_audit.open("r", encoding="utf-8-sig", newline="") as handle:
            audit_row = next(csv.DictReader(handle), {})
        if row.get("unique_traces_total") and row["unique_traces_total"] != audit_row.get("unique_traces_total"):
            raise RuntimeError(f"Run index / trace denominator mismatch: {measurement_dir}")
        target_dir = destination / "measurements" / measurement_dir.name
        target_dir.mkdir(parents=True)
        shutil.copy2(measurement_manifest_path, target_dir / measurement_manifest_path.name)
        for filename in PAPER_FILES:
            source = measurement_dir / filename
            if not source.exists():
                if filename in REQUIRED_PAPER_FILES:
                    raise RuntimeError(f"Required paper artifact is missing for {measurement_dir}: {filename}")
                skipped.append({"measurement": measurement_dir.name, "file": filename, "reason": "missing"})
                continue
            if source.stat().st_size == 0:
                raise RuntimeError(f"Paper artifact is empty: {source}")
            if source.stat().st_size > max_bytes:
                skipped.append({"measurement": measurement_dir.name, "file": filename, "reason": "size_limit"})
                continue
            target = target_dir / filename
            shutil.copy2(source, target)
            copied.append({"path": str(target.relative_to(REPO_DIR)), "sha256": sha256_file(target), "bytes": target.stat().st_size})
    shutil.copy2(manifest_path, destination / "run_manifest.json")
    shutil.copy2(index_path, destination / "run_index.csv")
    input_destination = destination / "inputs"
    input_destination.mkdir()
    for filename in ("resolved_config.json", "input_manifest.csv", "reference_input_manifest.csv"):
        source = run_root / "inputs" / filename
        if not source.exists():
            raise RuntimeError(f"Required run input artifact is missing: {source}")
        target = input_destination / filename
        shutil.copy2(source, target)
        copied.append({"path": str(target.relative_to(REPO_DIR)), "sha256": sha256_file(target), "bytes": target.stat().st_size})
    write_readme(destination / "PAPER_RESULTS_README.md", args.run_id)
    write_json(destination / "package_manifest.json", {
        "run_id": args.run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_run": str(run_root.relative_to(REPO_DIR)),
        "copied": copied,
        "skipped": skipped,
        "interpretation": "measurement-observed feasible corridor audit; no raw traceroute data or ground-truth cable claim",
    })
    print(f"Packaged {len(copied)} current-run files to {destination}; skipped {len(skipped)} files.")


if __name__ == "__main__":
    main()
