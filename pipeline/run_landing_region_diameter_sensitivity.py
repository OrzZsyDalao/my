"""Reaggregate A-Root results for a dedicated landing-region diameter study.

This script does not repeat traceroute-to-candidate matching. It reuses the
stable exact candidates from an existing A-Root result and writes every
10/20/30/40/50 km remapping into a new directory, leaving the historical
27-setting sensitivity outputs untouched.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.run_a_root_sensitivity import (  # noqa: E402
    compare_auditable_units,
    compare_projection_diagnostics,
    compare_shared_cohort,
    load_projection_diagnostics,
    load_setting_summary,
)
from source.result_provenance import (  # noqa: E402
    file_manifest,
    git_generation_state,
    inherited_commit,
    read_json,
    source_hashes,
)


DIAMETERS_KM = (10, 20, 30, 40, 50)
BASELINE_DIAMETER_KM = 30
LANDING_CATCHMENT_RADIUS_KM = 50
RTT_TOLERANCE_MS = 5
SCHEMA_VERSION = "landing_region_diameter_sensitivity_v1"
DEFAULT_SOURCE_RESULT = (
    REPO_ROOT
    / "output"
    / "sensitivity_a_root"
    / "catchment50_diameter50_rtt5"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT
    / "output"
    / "sensitivity_landing_region_diameter_30km_baseline"
)
DEFAULT_PUBLICATION_OUTPUT = (
    REPO_ROOT
    / "results"
    / "july1_public_atlas_20260701"
    / "sensitivity_landing_region_diameter_30km_baseline"
)
RUNTIME_INPUT_FILES = (
    "atomic_segment_inventory.csv.gz",
    "atomic_segment_inventory_manifest.json",
    "cable_matching_manifest.json",
    "cable_matching_stats_5051.json",
    "trace_observation_summary.csv",
    "trace_denominator_audit.csv",
)


def parse_args() -> argparse.Namespace:
    """Parse source, isolated output, and execution controls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-result-dir",
        type=Path,
        default=DEFAULT_SOURCE_RESULT,
        help="Existing A-Root result containing exact feasible candidates.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="New runtime directory; historical sensitivity outputs are not modified.",
    )
    parser.add_argument(
        "--publication-output",
        type=Path,
        default=DEFAULT_PUBLICATION_OUTPUT,
        help="Compact summary directory suitable for GitHub.",
    )
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setting_directory(output_root: Path, diameter_km: int) -> Path:
    """Return the isolated directory for one maximum-diameter setting."""
    return output_root / f"diameter{diameter_km}km"


def prepare_runtime_inputs(source_dir: Path, target_dir: Path) -> None:
    """Copy only the Stage 1 accounting inputs required by post-processing."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in RUNTIME_INPUT_FILES:
        source = source_dir / filename
        if not source.exists():
            raise FileNotFoundError(
                f"Required sensitivity source input is missing: {source}"
            )
        target = target_dir / filename
        if not target.exists() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)


def run_postprocess(
    source_dir: Path,
    target_dir: Path,
    diameter_km: int,
    dry_run: bool,
) -> None:
    """Reaggregate one diameter without repeating candidate matching."""
    command = [
        sys.executable,
        "source/postprocess_candidate_output.py",
        "--input",
        str(source_dir / "cable_matching_output.json"),
        "--output",
        str(target_dir),
        "--landing-region-maximum-diameter-km",
        str(diameter_km),
    ]
    print("Running:", " ".join(command))
    if not dry_run:
        subprocess.run(command, cwd=REPO_ROOT, check=True)


def validate_summary(frame: pd.DataFrame) -> None:
    """Assert complete settings, accounting identities, and bounded metrics."""
    observed = set(
        pd.to_numeric(
            frame["landing_region_maximum_diameter_km"],
            errors="raise",
        ).astype(int)
    )
    if len(frame) != len(DIAMETERS_KM) or observed != set(DIAMETERS_KM):
        raise AssertionError(
            f"Expected diameter settings {DIAMETERS_KM}, found {sorted(observed)}"
        )
    if frame["setting"].nunique() != len(DIAMETERS_KM):
        raise AssertionError("Diameter sensitivity setting labels are not unique.")
    if not (
        frame["single_corridor_segment_count"]
        + frame["bounded_multi_corridor_segment_count"]
        == frame["candidate_bearing_segment_count"]
    ).all():
        raise AssertionError("Candidate-bearing resolution accounting failed.")
    candidate_rows = frame["candidate_bearing_segment_count"].gt(0)
    share_sum = (
        frame.loc[
            candidate_rows,
            "single_corridor_share_among_candidate_bearing_segments",
        ]
        + frame.loc[
            candidate_rows,
            "bounded_multi_corridor_share_among_candidate_bearing_segments",
        ]
    )
    if not np.allclose(share_sum, 1.0, atol=1e-9):
        raise AssertionError("Candidate-bearing shares do not sum to one.")
    for column in frame:
        if (
            "jaccard" not in column
            and not column.endswith("_share")
            and not column.endswith("_rate")
        ):
            continue
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if not values.between(0, 1).all():
            raise AssertionError(f"{column} contains values outside [0, 1].")
    baseline_rows = frame[
        frame["landing_region_maximum_diameter_km"].eq(BASELINE_DIAMETER_KM)
    ]
    if len(baseline_rows) != 1:
        raise AssertionError("Exactly one 30 km baseline row is required.")


def build_manifest(
    source_dir: Path,
    output_root: Path,
    publication_output: Path,
    generated_outputs: list[Path],
) -> dict[str, Any]:
    """Build explicit provenance for the isolated diameter sensitivity."""
    source_manifests = [
        read_json(source_dir / "method_manifest.json"),
        read_json(source_dir / "cable_matching_manifest.json"),
        read_json(source_dir / "atomic_segment_inventory_manifest.json"),
    ]
    generated_method_manifests = [
        read_json(setting_directory(output_root, diameter) / "method_manifest.json")
        for diameter in DIAMETERS_KM
    ]
    identity_versions = {
        str(item.get("identity_schema_version"))
        for item in generated_method_manifests
        if item.get("identity_schema_version")
    }
    postprocess_versions = {
        str(item.get("postprocess_schema_version"))
        for item in generated_method_manifests
        if item.get("postprocess_schema_version")
    }
    generation = git_generation_state(REPO_ROOT)
    source_inputs = [
        source_dir / "cable_matching_output.json",
        *(source_dir / filename for filename in RUNTIME_INPUT_FILES),
    ]
    return {
        "sensitivity_schema_version": SCHEMA_VERSION,
        "analysis_type": "landing_region_maximum_diameter_sensitivity",
        "core_analysis_commit": inherited_commit(
            source_manifests,
            ["core_analysis_commit", "git_commit", "git_commit_sha"],
        ),
        "sensitivity_analysis_commit": (
            "unknown"
            if generation["generation_worktree_dirty"]
            else generation["generation_git_head"]
        ),
        "identity_schema_version": (
            next(iter(identity_versions))
            if len(identity_versions) == 1
            else "unknown"
        ),
        "postprocess_schema_version": (
            next(iter(postprocess_versions))
            if len(postprocess_versions) == 1
            else "unknown"
        ),
        **generation,
        "source_result_directory": str(source_dir),
        "runtime_output_directory": str(output_root),
        "publication_output_directory": str(publication_output),
        "source_file_sha256": source_hashes(
            [
                REPO_ROOT
                / "pipeline"
                / "run_landing_region_diameter_sensitivity.py",
                REPO_ROOT / "pipeline" / "run_a_root_sensitivity.py",
                REPO_ROOT / "source" / "postprocess_candidate_output.py",
                REPO_ROOT / "source" / "physical_corridor_model.py",
            ],
            REPO_ROOT,
        ),
        "input_files": [
            file_manifest(path, REPO_ROOT)
            for path in source_inputs
            if path.exists()
        ],
        "generated_outputs": [
            file_manifest(path, REPO_ROOT) for path in generated_outputs
        ],
        "settings": [
            {
                "landing_catchment_radius_km": LANDING_CATCHMENT_RADIUS_KM,
                "landing_region_maximum_diameter_km": diameter,
                "rtt_tolerance_ms": RTT_TOLERANCE_MS,
                "is_baseline": diameter == BASELINE_DIAMETER_KM,
            }
            for diameter in DIAMETERS_KM
        ],
        "baseline": {
            "landing_catchment_radius_km": LANDING_CATCHMENT_RADIUS_KM,
            "landing_region_maximum_diameter_km": BASELINE_DIAMETER_KM,
            "rtt_tolerance_ms": RTT_TOLERANCE_MS,
        },
        "historical_result_protection": {
            "historical_output_directory": str(
                REPO_ROOT / "output" / "sensitivity_a_root"
            ),
            "historical_outputs_modified": False,
        },
        "interpretation": (
            "This analysis varies only landing-region maximum diameter. "
            "Stable exact cable/landing-pair candidates are reused, while "
            "corridor remapping and paper statistics are recomputed. Candidate "
            "relations remain feasible hypotheses, not ground-truth cable use."
        ),
    }


def publish_compact_outputs(
    output_root: Path,
    publication_output: Path,
    filenames: list[str],
) -> None:
    """Copy compact sensitivity summaries without copying runtime tables."""
    publication_output.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        shutil.copy2(output_root / filename, publication_output / filename)


def main() -> None:
    """Run isolated diameter remapping and write baseline-shared summaries."""
    args = parse_args()
    source_dir = args.source_result_dir.resolve()
    output_root = args.output_root.resolve()
    publication_output = args.publication_output.resolve()
    candidate_input = source_dir / "cable_matching_output.json"
    if not candidate_input.exists():
        raise FileNotFoundError(f"Candidate source is missing: {candidate_input}")
    if output_root == (REPO_ROOT / "output" / "sensitivity_a_root").resolve():
        raise ValueError("The historical sensitivity directory cannot be overwritten.")
    output_root.mkdir(parents=True, exist_ok=True)

    for diameter in DIAMETERS_KM:
        target_dir = setting_directory(output_root, diameter)
        completion_file = target_dir / "cross_layer_normalized_entropy_audit.csv"
        if (
            args.skip_existing
            and completion_file.exists()
            and completion_file.stat().st_size > 0
        ):
            print(f"Skipping completed diameter={diameter} km")
            continue
        if not args.dry_run:
            prepare_runtime_inputs(source_dir, target_dir)
        run_postprocess(source_dir, target_dir, diameter, args.dry_run)

    if args.dry_run:
        return

    rows: list[dict[str, Any]] = []
    units_by_diameter: dict[int, pd.DataFrame] = {}
    diagnostics_by_diameter: dict[int, dict[str, Any]] = {}
    for diameter in DIAMETERS_KM:
        target_dir = setting_directory(output_root, diameter)
        row, units = load_setting_summary(
            target_dir,
            LANDING_CATCHMENT_RADIUS_KM,
            diameter,
            RTT_TOLERANCE_MS,
        )
        diagnostics = load_projection_diagnostics(target_dir)
        row["analysis_type"] = "landing_region_maximum_diameter_sensitivity"
        row["is_baseline"] = diameter == BASELINE_DIAMETER_KM
        for column in [
            "global_landing_region_count",
            "observed_landing_region_count",
            "global_corridor_count",
            "observed_corridor_count",
        ]:
            row[column] = diagnostics[column]
        rows.append(row)
        units_by_diameter[diameter] = units
        diagnostics_by_diameter[diameter] = diagnostics

    baseline_units = units_by_diameter[BASELINE_DIAMETER_KM]
    baseline_diagnostics = diagnostics_by_diameter[BASELINE_DIAMETER_KM]
    shared_frames: list[pd.DataFrame] = []
    for row in rows:
        diameter = int(row["landing_region_maximum_diameter_km"])
        row.update(
            compare_auditable_units(
                units_by_diameter[diameter],
                baseline_units,
            )
        )
        shared_metrics, shared_frame = compare_shared_cohort(
            units_by_diameter[diameter],
            baseline_units,
            str(row["setting"]),
        )
        row.update(shared_metrics)
        row.update(
            compare_projection_diagnostics(
                diagnostics_by_diameter[diameter],
                baseline_diagnostics,
                same_diameter=diameter == BASELINE_DIAMETER_KM,
            )
        )
        shared_frames.append(shared_frame)

    summary = pd.DataFrame(rows).sort_values(
        "landing_region_maximum_diameter_km"
    )
    validate_summary(summary)
    summary_path = (
        output_root / "landing_region_diameter_sensitivity_summary.csv"
    )
    shared_path = (
        output_root
        / "landing_region_diameter_sensitivity_shared_unit_comparison.csv"
    )
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.concat(shared_frames, ignore_index=True, sort=False).to_csv(
        shared_path,
        index=False,
        encoding="utf-8-sig",
    )
    manifest_path = (
        output_root / "landing_region_diameter_sensitivity_manifest.json"
    )
    generated_outputs = [summary_path, shared_path]
    manifest = build_manifest(
        source_dir,
        output_root,
        publication_output,
        generated_outputs,
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    publish_compact_outputs(
        output_root,
        publication_output,
        [
            summary_path.name,
            shared_path.name,
            manifest_path.name,
        ],
    )
    print(
        "Saved isolated 10/20/30/40/50 km diameter sensitivity to "
        f"{output_root}"
    )


if __name__ == "__main__":
    main()
