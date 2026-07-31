#!/usr/bin/env python3
"""Package compact July 1 reaggregation outputs for repository publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from source.result_provenance import (
    file_manifest,
    git_generation_state,
    inherited_commit,
    read_json,
    source_hashes,
)

DEFAULT_SOURCE = REPO_ROOT / "output" / "public_traceroute_by_msmid"
DEFAULT_DESTINATION = REPO_ROOT / "results" / "july1_public_atlas_20260701"

MEASUREMENT_FILES = (
    "candidate_space_profile.csv",
    "country_corridor_concentration_summary.csv",
    "country_corridor_observation_distribution.csv",
    "country_cross_layer_distribution_audit.csv",
    "country_network_transition_concentration_summary.csv",
    "country_physical_exposure_summary.csv",
    "dataset_summary.csv",
    "filtering_breakdown.csv",
    "framework_alignment_report.json",
    "paper_broad_corridor_distribution_cases.csv",
    "paper_corridor_observation_concentration_cases.csv",
    "paper_network_broad_physical_concentrated_cases.csv",
    "paper_physical_exposure_cases.csv",
    "service_country_corridor_concentration_summary.csv",
    "service_country_corridor_observation_distribution.csv",
    "service_country_cross_layer_distribution_audit.csv",
    "service_country_network_transition_concentration_summary.csv",
    "physical_mapping_resolution_summary.csv",
    "service_country_physical_mapping_resolution.csv",
    "bounded_candidate_set_size_distribution.csv",
    "uniquely_resolved_service_country_cross_layer_distribution.csv",
    "paper_uniquely_resolved_service_country_cross_layer_distribution.csv",
    "pipeline_accounting.csv",
    "cross_layer_normalized_entropy_audit.csv",
    "network_corridor_normalized_entropy_paired.svg",
    "network_corridor_normalized_entropy_cdf.svg",
    "atomic_segment_inventory_manifest.json",
    "candidate_row_deduplication_report.json",
    "method_manifest.json",
    "country_geography_candidate_dependency.csv",
    "service_country_geography_candidate_dependency.csv",
    "geography_type_candidate_dependency_summary.csv",
    "country_geography_catalog_resolved.csv",
    "country_geography_dependency_manifest.json",
)

STRUCTURE_FILES = (
    "landing_region_catalog.csv",
    "landing_region_summary.csv",
    "exact_landing_pair_catalog.csv",
    "corridor_catalog.csv",
    "corridor_parallel_relationship_summary.csv",
    "physical_corridor_structure_report.json",
)

AGGREGATE_FILES = (
    "physical_mapping_resolution_summary.csv",
    "service_country_physical_mapping_resolution.csv",
    "bounded_candidate_set_size_distribution.csv",
    "pipeline_accounting.csv",
    "cross_layer_normalized_entropy_audit.csv",
    "uniquely_resolved_service_country_cross_layer_distribution.csv",
    "paper_uniquely_resolved_service_country_cross_layer_distribution.csv",
    "country_geography_candidate_dependency.csv",
    "service_country_geography_candidate_dependency.csv",
    "geography_type_candidate_dependency_summary.csv",
)

ENTROPY_COMPACT_COLUMNS = (
    "msm_id",
    "probe_country",
    "service_id",
    "path_scope_stratum",
    "total_mappable_segments",
    "network_transition_normalized_entropy",
    "corridor_normalized_entropy",
    "normalized_entropy_reduction",
    "network_transition_concentration_tier",
    "corridor_concentration_tier",
    "cross_layer_distribution_class",
    "country_fallback_share",
    "auditable_paper_case",
    "unique_probes",
    "unique_probe_asns",
)


def parse_args() -> argparse.Namespace:
    """Parse source, destination, and file-size guard options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--destination", default=str(DEFAULT_DESTINATION))
    parser.add_argument("--max-file-mb", type=float, default=95.0)
    parser.add_argument("--expected-measurements", type=int, default=18)
    return parser.parse_args()


def measurement_id(path: Path) -> str:
    """Extract the measurement ID from a standard result-directory name."""
    match = re.match(r"msm(\d+)_", path.name)
    return match.group(1) if match else "NA"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a packaged artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_measurements(source: Path) -> List[Path]:
    """Return result directories that contain a completed Stage 1 candidate file."""
    return sorted(
        path
        for path in source.glob("msm*")
        if path.is_dir() and (path / "cable_matching_output.json").exists()
    )


def copy_if_compact(
    source: Path,
    destination: Path,
    max_bytes: int,
    copied: List[Dict[str, Any]],
    skipped: List[Dict[str, Any]],
) -> None:
    """Copy one artifact when it exists and is below the repository size limit."""
    if not source.exists():
        skipped.append({"source": str(source), "reason": "missing"})
        return
    if source.stat().st_size > max_bytes:
        skipped.append(
            {
                "source": str(source),
                "reason": "size_limit",
                "bytes": source.stat().st_size,
            }
        )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    copied.append(
        {
            "path": str(destination.relative_to(REPO_ROOT)),
            "bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
        }
    )


def combine_csvs(
    measurements: Iterable[Path],
    filename: str,
    destination: Path,
    *,
    require_all_nonempty: bool = False,
) -> Dict[str, int]:
    """Combine one compact per-measurement CSV with explicit measurement columns."""
    frames: List[pd.DataFrame] = []
    source_file_count = 0
    source_row_count = 0
    for measurement_dir in measurements:
        source = measurement_dir / filename
        if not source.exists():
            if require_all_nonempty:
                raise RuntimeError(f"Required source file is missing: {source}")
            continue
        frame = pd.read_csv(source, low_memory=False)
        if require_all_nonempty and frame.empty:
            raise RuntimeError(f"Required source file is empty: {source}")
        source_file_count += 1
        source_row_count += int(len(frame))
        source_msm_id = measurement_id(measurement_dir)
        if "msm_id" in frame:
            frame["msm_id"] = frame["msm_id"].fillna(source_msm_id)
        else:
            frame.insert(0, "msm_id", source_msm_id)
        frame.insert(0, "measurement_label", measurement_dir.name)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    if require_all_nonempty and combined.empty:
        raise RuntimeError(f"Aggregate output would be empty: {destination}")
    combined.to_csv(destination, index=False, encoding="utf-8-sig")
    return {
        "source_file_count": source_file_count,
        "source_row_count": source_row_count,
        "aggregate_row_count": int(len(combined)),
    }


def write_compact_entropy_aggregate(
    full_source: Path,
    compact_destination: Path,
) -> Dict[str, int]:
    """Write an API-readable entropy table while preserving the full aggregate."""
    full_frame = pd.read_csv(full_source, low_memory=False)
    missing = [
        column for column in ENTROPY_COMPACT_COLUMNS if column not in full_frame
    ]
    if missing:
        raise RuntimeError(
            "Cannot build compact normalized-entropy aggregate; missing columns: "
            + ", ".join(missing)
        )
    compact = full_frame.loc[:, ENTROPY_COMPACT_COLUMNS].copy()
    msm_ids = pd.to_numeric(compact["msm_id"], errors="coerce")
    if msm_ids.notna().sum() == compact["msm_id"].notna().sum():
        compact["msm_id"] = msm_ids.astype("Int64")
    compact.to_csv(
        compact_destination,
        index=False,
        encoding="utf-8-sig",
        float_format="%.8g",
        lineterminator="\n",
    )
    if len(compact) != len(full_frame):
        raise RuntimeError("Compact entropy aggregate changed the aggregate row count.")
    api_inline_limit = 1024 * 1024
    compact_bytes = compact_destination.stat().st_size
    if compact_bytes >= api_inline_limit:
        raise RuntimeError(
            "Compact entropy aggregate still exceeds the GitHub Contents API "
            f"inline limit: {compact_bytes} bytes."
        )
    return {
        "full_aggregate_row_count": int(len(full_frame)),
        "compact_aggregate_row_count": int(len(compact)),
        "compact_column_count": int(len(compact.columns)),
        "compact_bytes": int(compact_bytes),
        "github_contents_api_inline_limit_bytes": api_inline_limit,
    }


def current_git_commit() -> str:
    """Return the source commit used to generate the packaged artifacts."""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def combine_candidate_deduplication_reports(
    measurements: Iterable[Path],
    destination: Path,
) -> None:
    """Flatten per-measurement candidate-row deduplication diagnostics."""
    rows: List[Dict[str, Any]] = []
    for measurement_dir in measurements:
        source = measurement_dir / "candidate_row_deduplication_report.json"
        if not source.exists():
            continue
        report = json.loads(source.read_text(encoding="utf-8"))
        for view in report.get("candidate_views", []):
            rows.append(
                {
                    "measurement_label": measurement_dir.name,
                    "msm_id": measurement_id(measurement_dir),
                    **view,
                }
            )
    pd.DataFrame(rows).to_csv(destination, index=False, encoding="utf-8-sig")


def write_aggregate_entropy_cdf(frame: pd.DataFrame, output: Path) -> None:
    """Write a dependency-free CDF comparing normalized network/corridor entropy."""
    width, height = 900, 560
    left, right, top, bottom = 90, 40, 55, 75
    plot_width = width - left - right
    plot_height = height - top - bottom
    series = [
        (
            "Network transition normalized entropy",
            "#165d78",
            pd.to_numeric(
                frame.get("network_transition_normalized_entropy"),
                errors="coerce",
            ).dropna(),
        ),
        (
            "Corridor normalized entropy",
            "#c2542d",
            pd.to_numeric(
                frame.get("corridor_normalized_entropy"),
                errors="coerce",
            ).dropna(),
        ),
    ]
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#fbf7ef"/>',
        '<text x="90" y="30" font-family="Georgia" font-size="22" fill="#202520">Cross-measurement normalized entropy CDF</text>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#333"/>',
    ]
    for tick in range(6):
        value = tick / 5
        x = left + value * plot_width
        y = top + (1 - value) * plot_height
        svg.extend(
            [
                f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_height}" stroke="#ddd4c5"/>',
                f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" stroke="#ddd4c5"/>',
                f'<text x="{x:.1f}" y="{top + plot_height + 25}" text-anchor="middle" font-family="Georgia" font-size="13">{value:.1f}</text>',
                f'<text x="{left - 15}" y="{y + 5:.1f}" text-anchor="end" font-family="Georgia" font-size="13">{value:.1f}</text>',
            ]
        )
    for index, (label, color, values) in enumerate(series):
        ordered = sorted(float(value) for value in values if 0 <= float(value) <= 1)
        if ordered:
            points = []
            count = len(ordered)
            for position, value in enumerate(ordered, start=1):
                x = left + value * plot_width
                y = top + (1 - position / count) * plot_height
                points.append(f"{x:.1f},{y:.1f}")
            svg.append(
                f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3"/>'
            )
        legend_y = top + 24 + index * 28
        svg.append(
            f'<line x1="{left + 410}" y1="{legend_y}" x2="{left + 450}" y2="{legend_y}" stroke="{color}" stroke-width="4"/>'
        )
        svg.append(
            f'<text x="{left + 460}" y="{legend_y + 5}" font-family="Georgia" font-size="14">{label}</text>'
        )
    svg.extend(
        [
            f'<text x="{left + plot_width / 2}" y="{height - 20}" text-anchor="middle" font-family="Georgia" font-size="16">Normalized entropy H / log(K)</text>',
            f'<text x="24" y="{top + plot_height / 2}" transform="rotate(-90 24 {top + plot_height / 2})" text-anchor="middle" font-family="Georgia" font-size="16">Empirical CDF</text>',
            "</svg>",
        ]
    )
    output.write_text("\n".join(svg), encoding="utf-8")


def main() -> None:
    """Copy compact artifacts and create cross-measurement aggregate tables."""
    args = parse_args()
    source_root = Path(args.source).resolve()
    destination_root = Path(args.destination).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    max_bytes = int(args.max_file_mb * 1024 * 1024)
    measurements = discover_measurements(source_root)
    if len(measurements) != args.expected_measurements:
        raise RuntimeError(
            f"Expected {args.expected_measurements} measurements, found {len(measurements)}."
        )
    copied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    run_index_rows: List[Dict[str, Any]] = []

    for measurement_dir in measurements:
        target_dir = destination_root / measurement_dir.name
        for filename in MEASUREMENT_FILES:
            copy_if_compact(
                measurement_dir / filename,
                target_dir / filename,
                max_bytes,
                copied,
                skipped,
            )
        inventory_manifest_path = (
            measurement_dir / "atomic_segment_inventory_manifest.json"
        )
        inventory_manifest = (
            json.loads(inventory_manifest_path.read_text(encoding="utf-8"))
            if inventory_manifest_path.exists()
            else {}
        )
        resolution_path = measurement_dir / "physical_mapping_resolution_summary.csv"
        resolution = (
            pd.read_csv(resolution_path)
            if resolution_path.exists()
            else pd.DataFrame()
        )
        resolution_counts = (
            dict(
                zip(
                    resolution.get("mapping_resolution_state", []),
                    resolution.get("atomic_segment_count", []),
                )
            )
            if not resolution.empty
            else {}
        )
        critical_files = [
            "physical_mapping_resolution_summary.csv",
            "pipeline_accounting.csv",
            "cross_layer_normalized_entropy_audit.csv",
            "service_country_corridor_concentration_summary.csv",
            "service_country_cross_layer_distribution_audit.csv",
        ]
        run_index_rows.append(
            {
                "msm_id": measurement_id(measurement_dir),
                "measurement_label": measurement_dir.name,
                "status": (
                    "completed"
                    if all((measurement_dir / item).exists() for item in critical_files)
                    else "incomplete"
                ),
                "raw_traceroutes": inventory_manifest.get("raw_results_total"),
                "valid_traceroutes": inventory_manifest.get("valid_traces_total"),
                "observable_atomic_segments": inventory_manifest.get(
                    "observable_atomic_segments_total"
                ),
                "mappable_atomic_segments": inventory_manifest.get(
                    "mappable_atomic_segments_total"
                ),
                "uniquely_resolved_segments": resolution_counts.get(
                    "uniquely_resolved", 0
                ),
                "bounded_candidate_set_segments": resolution_counts.get(
                    "bounded_candidate_set", 0
                ),
                "no_matched_corridor_segments": resolution_counts.get(
                    "no_matched_corridor", 0
                ),
                "insufficiently_resolved_segments": resolution_counts.get(
                    "insufficiently_resolved", 0
                ),
            }
        )
    incomplete = [
        row["measurement_label"]
        for row in run_index_rows
        if row["status"] != "completed"
    ]
    if incomplete:
        raise RuntimeError(
            "Cannot package incomplete measurements: " + ", ".join(incomplete)
        )

    if measurements:
        structure_dir = destination_root / "physical_structure"
        for filename in STRUCTURE_FILES:
            copy_if_compact(
                measurements[0] / filename,
                structure_dir / filename,
                max_bytes,
                copied,
                skipped,
            )

    aggregate_dir = destination_root / "aggregate"
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    aggregate_source_accounting: Dict[str, Dict[str, int]] = {}
    for filename in AGGREGATE_FILES:
        is_entropy_aggregate = (
            filename == "cross_layer_normalized_entropy_audit.csv"
        )
        output_name = (
            "all_measurements_cross_layer_normalized_entropy_audit_full.csv"
            if is_entropy_aggregate
            else f"all_measurements_{filename}"
        )
        output = aggregate_dir / output_name
        aggregate_source_accounting[filename] = combine_csvs(
            measurements,
            filename,
            output,
            require_all_nonempty=is_entropy_aggregate,
        )
        copied.append(
            {
                "path": str(output.relative_to(REPO_ROOT)),
                "bytes": output.stat().st_size,
                "sha256": sha256_file(output),
            }
        )
        if is_entropy_aggregate:
            compact_output = (
                aggregate_dir
                / "all_measurements_cross_layer_normalized_entropy_audit.csv"
            )
            aggregate_source_accounting[filename].update(
                write_compact_entropy_aggregate(output, compact_output)
            )
            copied.append(
                {
                    "path": str(compact_output.relative_to(REPO_ROOT)),
                    "bytes": compact_output.stat().st_size,
                    "sha256": sha256_file(compact_output),
                }
            )
    deduplication_aggregate = (
        aggregate_dir
        / "all_measurements_candidate_row_deduplication_summary.csv"
    )
    combine_candidate_deduplication_reports(
        measurements,
        deduplication_aggregate,
    )
    copied.append(
        {
            "path": str(deduplication_aggregate.relative_to(REPO_ROOT)),
            "bytes": deduplication_aggregate.stat().st_size,
            "sha256": sha256_file(deduplication_aggregate),
        }
    )
    entropy_aggregate = (
        aggregate_dir
        / "all_measurements_cross_layer_normalized_entropy_audit_full.csv"
    )
    entropy_cdf = (
        aggregate_dir
        / "all_measurements_network_corridor_normalized_entropy_cdf.svg"
    )
    write_aggregate_entropy_cdf(
        pd.read_csv(entropy_aggregate, low_memory=False),
        entropy_cdf,
    )
    copied.append(
        {
            "path": str(entropy_cdf.relative_to(REPO_ROOT)),
            "bytes": entropy_cdf.stat().st_size,
            "sha256": sha256_file(entropy_cdf),
        }
    )
    run_index_path = destination_root / "per_msmid_run_index.csv"
    pd.DataFrame(run_index_rows).to_csv(
        run_index_path,
        index=False,
        encoding="utf-8-sig",
    )
    copied.append(
        {
            "path": str(run_index_path.relative_to(REPO_ROOT)),
            "bytes": run_index_path.stat().st_size,
            "sha256": sha256_file(run_index_path),
        }
    )
    sensitivity_root = REPO_ROOT / "output" / "sensitivity_a_root"
    sensitivity_source = sensitivity_root / "a_root_sensitivity_summary.csv"
    sensitivity_accounting: Dict[str, Any] = {
        "included": False,
        "setting_count": 0,
    }
    if sensitivity_source.exists() and sensitivity_source.stat().st_size > 0:
        sensitivity_frame = pd.read_csv(sensitivity_source)
        if len(sensitivity_frame) != 27:
            raise RuntimeError(
                "Expected 27 A-Root sensitivity settings, found "
                f"{len(sensitivity_frame)}."
            )
        sensitivity_target = (
            destination_root / "sensitivity" / "a_root_sensitivity_summary.csv"
        )
        copy_if_compact(
            sensitivity_source,
            sensitivity_target,
            max_bytes,
            copied,
            skipped,
        )
        for sensitivity_filename in [
            "a_root_sensitivity_shared_unit_comparison.csv",
            "a_root_sensitivity_manifest.json",
        ]:
            copy_if_compact(
                sensitivity_root / sensitivity_filename,
                destination_root / "sensitivity" / sensitivity_filename,
                max_bytes,
                copied,
                skipped,
            )
        sensitivity_accounting = {
            "included": True,
            "setting_count": int(len(sensitivity_frame)),
            "baseline_setting": "catchment50_diameter50_rtt5",
        }

    paper_primary_command = [
        sys.executable,
        str(REPO_ROOT / "source" / "build_paper_primary_summary.py"),
        "--entropy-input",
        str(
            aggregate_dir
            / "all_measurements_cross_layer_normalized_entropy_audit_full.csv"
        ),
        "--resolution-input",
        str(
            aggregate_dir
            / "all_measurements_service_country_physical_mapping_resolution.csv"
        ),
        "--output",
        str(destination_root / "paper_primary"),
    ]
    subprocess.run(paper_primary_command, cwd=REPO_ROOT, check=True)

    generation = git_generation_state(REPO_ROOT)
    sensitivity_manifest = read_json(
        destination_root / "sensitivity" / "a_root_sensitivity_manifest.json"
    )
    aggregate_inputs = [
        file_manifest(measurement / filename, REPO_ROOT)
        for measurement in measurements
        for filename in AGGREGATE_FILES
        if (measurement / filename).exists()
    ]
    manifest = {
        **generation,
        # Deprecated alias: this is the generation checkout, not historical core provenance.
        "git_commit": generation["generation_git_head"],
        "git_commit_deprecated_alias": True,
        "packaging_commit": (
            "unknown"
            if generation["generation_worktree_dirty"]
            else generation["generation_git_head"]
        ),
        "sensitivity_analysis_commit": sensitivity_manifest.get(
            "sensitivity_analysis_commit",
            "unknown",
        ),
        "measurement_count": len(measurements),
        "source": str(source_root.relative_to(REPO_ROOT)),
        "interpretation": (
            "Corrected diameter-limited corridor reaggregation and physical mapping "
            "resolution audit; candidate relations are not ground-truth cable use."
        ),
        "copied": copied,
        "skipped": skipped,
        "aggregate_source_accounting": aggregate_source_accounting,
        "input_files": aggregate_inputs,
        "input_file_sha256": {
            item["path"]: item["sha256"] for item in aggregate_inputs
        },
        "source_file_sha256": source_hashes(
            [
                REPO_ROOT
                / "ripe_atlas_public_download"
                / "package_reaggregated_paper_results.py",
                REPO_ROOT / "source" / "build_paper_primary_summary.py",
                REPO_ROOT / "source" / "result_provenance.py",
            ],
            REPO_ROOT,
        ),
        "a_root_sensitivity": sensitivity_accounting,
        "large_runtime_outputs_not_packaged": [
            "cable_matching_output.json",
            "trace_candidate_support.csv",
            "trace_feasible_candidate_space.csv",
            "atomic_segment_inventory.csv.gz",
            "atomic_segment_mapping_resolution.csv.gz",
        ],
    }
    method_manifests = [
        json.loads(
            (measurement / "method_manifest.json").read_text(encoding="utf-8")
        )
        for measurement in measurements
    ]
    postprocess_versions = {
        item.get("postprocess_schema_version") for item in method_manifests
    }
    identity_versions = {
        item.get("identity_schema_version") for item in method_manifests
    }
    if len(postprocess_versions) != 1 or None in postprocess_versions:
        raise RuntimeError(
            f"Inconsistent postprocess schema versions: {postprocess_versions}"
        )
    if len(identity_versions) != 1 or None in identity_versions:
        raise RuntimeError(
            f"Inconsistent identity schema versions: {identity_versions}"
        )
    manifest["postprocess_schema_version"] = next(iter(postprocess_versions))
    manifest["identity_schema_version"] = next(iter(identity_versions))
    manifest["core_analysis_commit"] = inherited_commit(
        method_manifests,
        ["core_analysis_commit", "git_commit", "git_commit_sha"],
    )
    (destination_root / "bundle_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"Packaged {len(measurements)} measurements with {len(copied)} compact "
        f"artifacts; skipped {len(skipped)}."
    )


if __name__ == "__main__":
    main()
