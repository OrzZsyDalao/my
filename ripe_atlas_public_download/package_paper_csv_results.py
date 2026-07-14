#!/usr/bin/env python3
"""Package GitHub-sized paper-facing CSV outputs from per-measurement runs.

Raw RIPE Atlas results and trace-level candidate tables remain local.  This
script copies only reproducible country/service-country audit outputs into a
version-control-friendly result bundle and records anything skipped by size.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_DIR / "output" / "public_traceroute_by_msmid"
DEFAULT_DESTINATION = REPO_DIR / "results" / "july1_public_atlas_20260701"
MAX_GITHUB_FILE_BYTES = 95 * 1024 * 1024

PAPER_CSV_FILENAMES = (
    "dataset_summary.csv",
    "filtering_breakdown.csv",
    "framework_alignment_report.csv",
    "candidate_space_profile.csv",
    "country_corridor_observation_distribution.csv",
    "service_country_corridor_observation_distribution.csv",
    "country_corridor_concentration_summary.csv",
    "service_country_corridor_concentration_summary.csv",
    "country_network_transition_concentration_summary.csv",
    "service_country_network_transition_concentration_summary.csv",
    "country_cross_layer_distribution_audit.csv",
    "service_country_cross_layer_distribution_audit.csv",
    "country_physical_exposure_summary.csv",
    "paper_corridor_observation_concentration_cases.csv",
    "paper_network_broad_physical_concentrated_cases.csv",
    "paper_broad_corridor_distribution_cases.csv",
    "paper_physical_exposure_cases.csv",
)


def parse_args() -> argparse.Namespace:
    """Parse result-bundle paths without changing pipeline CLI contracts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--destination", default=str(DEFAULT_DESTINATION))
    parser.add_argument("--max-file-mb", type=float, default=95.0)
    return parser.parse_args()


def main() -> None:
    """Create a compact, reviewable bundle of paper-facing CSV results."""
    args = parse_args()
    source = Path(args.source).resolve()
    destination = Path(args.destination).resolve()
    max_bytes = int(args.max_file_mb * 1024 * 1024)
    destination.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for measurement_dir in sorted(path for path in source.iterdir() if path.is_dir() and path.name.startswith("msm")):
        destination_dir = destination / measurement_dir.name
        for filename in PAPER_CSV_FILENAMES:
            input_path = measurement_dir / filename
            if not input_path.exists():
                continue
            size = input_path.stat().st_size
            if size > max_bytes:
                skipped.append({"path": str(input_path.relative_to(REPO_DIR)), "bytes": size, "reason": "github_file_size_limit"})
                continue
            destination_dir.mkdir(parents=True, exist_ok=True)
            output_path = destination_dir / filename
            shutil.copy2(input_path, output_path)
            copied.append({"path": str(output_path.relative_to(REPO_DIR)), "bytes": size})

        manifest = measurement_dir / "framework_alignment_report.json"
        if manifest.exists() and manifest.stat().st_size <= max_bytes:
            destination_dir.mkdir(parents=True, exist_ok=True)
            output_path = destination_dir / manifest.name
            shutil.copy2(manifest, output_path)
            copied.append({"path": str(output_path.relative_to(REPO_DIR)), "bytes": manifest.stat().st_size})

    run_index = source / "per_msmid_run_index.csv"
    if run_index.exists() and run_index.stat().st_size <= max_bytes:
        shutil.copy2(run_index, destination / run_index.name)
        copied.append({"path": str((destination / run_index.name).relative_to(REPO_DIR)), "bytes": run_index.stat().st_size})

    bundle_manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source.relative_to(REPO_DIR)),
        "interpretation": "paper-facing aggregate measurement-observed transition and feasible-corridor audit CSVs; no raw traffic-volume claim",
        "copied_files": copied,
        "skipped_files": skipped,
    }
    with (destination / "bundle_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(bundle_manifest, handle, indent=2, ensure_ascii=False)
    print(f"Packaged {len(copied)} files; skipped {len(skipped)} oversized files: {destination}")


if __name__ == "__main__":
    main()
