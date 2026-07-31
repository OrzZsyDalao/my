"""Build fixed-scope paper-primary tables from existing July 1 aggregates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from .result_provenance import (
        file_manifest,
        git_generation_state,
        inherited_commit,
        read_json,
        source_hashes,
    )
except ImportError:
    from result_provenance import (
        file_manifest,
        git_generation_state,
        inherited_commit,
        read_json,
        source_hashes,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AGGREGATE_DIR = (
    REPO_ROOT / "results" / "july1_public_atlas_20260701" / "aggregate"
)
DEFAULT_ENTROPY_INPUT = (
    DEFAULT_AGGREGATE_DIR
    / "all_measurements_cross_layer_normalized_entropy_audit_full.csv"
)
DEFAULT_RESOLUTION_INPUT = (
    DEFAULT_AGGREGATE_DIR
    / "all_measurements_service_country_physical_mapping_resolution.csv"
)
DEFAULT_OUTPUT = (
    REPO_ROOT / "results" / "july1_public_atlas_20260701" / "paper_primary"
)
PAPER_PRIMARY_SCHEMA_VERSION = "paper_primary_summary_v1"
PAPER_FILTER = {
    "path_scope_stratum": "all_publicly_visible",
    "analysis_scope": "probe_country_service",
    "auditable_paper_case": True,
}
DNS_ROOT_MEASUREMENTS = {
    5009,
    5010,
    5011,
    5012,
    5013,
    5004,
    5014,
    5015,
    5005,
    5016,
    5001,
    5008,
    5006,
}
APPLICATION_MEASUREMENTS = {86710103, 176906957, 176517335}
TOPOLOGY_MEASUREMENTS = {5151, 5051}
EXPECTED_MEASUREMENTS = (
    DNS_ROOT_MEASUREMENTS | APPLICATION_MEASUREMENTS | TOPOLOGY_MEASUREMENTS
)
TARGET_CLASS = "network_broad_physical_concentrated"
CASE_IDENTITIES = [
    ("Singapore - H-Root", 5015, "SG"),
    ("Singapore - Netflix", 176517335, "SG"),
    ("New Zealand - Netflix", 176517335, "NZ"),
]
UNIT_COLUMNS = [
    "msm_id",
    "measurement_label",
    "service_id",
    "dataset_family",
    "probe_country",
    "stable_unit_id",
    "path_scope_stratum",
    "analysis_scope",
    "valid_atomic_segment_count",
    "candidate_bearing_segment_count",
    "single_corridor_segment_count",
    "bounded_multi_corridor_segment_count",
    "top2_network_transition_share",
    "top2_corridor_share",
    "top2_corridor_minus_network_shift",
    "network_transition_normalized_entropy",
    "corridor_normalized_entropy",
    "normalized_entropy_reduction",
    "effective_network_transition_count",
    "effective_corridor_count",
    "cross_layer_distribution_class",
    "country_fallback_share",
    "unique_probes",
    "unique_probe_asns",
    "auditable_paper_case",
    "auditable_cross_layer_case",
    "observation_sufficiency_reason",
    "failed_thresholds",
]
MEDIAN_COLUMNS = [
    "top2_network_transition_share",
    "top2_corridor_share",
    "top2_corridor_minus_network_shift",
    "network_transition_normalized_entropy",
    "corridor_normalized_entropy",
    "normalized_entropy_reduction",
    "effective_network_transition_count",
    "effective_corridor_count",
]


def parse_args() -> argparse.Namespace:
    """Parse aggregate inputs and paper-summary destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entropy-input", type=Path, default=DEFAULT_ENTROPY_INPUT)
    parser.add_argument(
        "--resolution-input",
        type=Path,
        default=DEFAULT_RESOLUTION_INPUT,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def normalize_msm_id(values: pd.Series) -> pd.Series:
    """Normalize measurement identifiers to nullable integers."""
    return pd.to_numeric(values, errors="coerce").astype("Int64")


def dataset_family(msm_id: Any) -> str:
    """Map one measurement explicitly to its paper dataset family."""
    if pd.isna(msm_id):
        raise ValueError("Paper-primary row has no measurement ID.")
    value = int(msm_id)
    if value in DNS_ROOT_MEASUREMENTS:
        return "DNS Roots"
    if value in APPLICATION_MEASUREMENTS:
        return "Applications"
    if value in TOPOLOGY_MEASUREMENTS:
        return "Topology references"
    raise ValueError(f"Uncatalogued paper measurement ID: {value}")


def stable_unit_id(row: pd.Series) -> str:
    """Build a deterministic country-measurement identity."""
    return (
        f"paper_primary_unit_v1|{int(row['msm_id'])}|"
        f"{row['probe_country']}|{row['service_id']}|"
        f"{row['path_scope_stratum']}"
    )


def fixed_paper_filter(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the non-configurable paper-primary scope and audit filter."""
    required = list(PAPER_FILTER)
    missing = [column for column in required if column not in frame]
    if missing:
        raise RuntimeError(
            "Paper-primary aggregate is missing filter columns: "
            + ", ".join(missing)
        )
    audit_values = frame["auditable_paper_case"]
    audit_mask = (
        audit_values.fillna(False)
        if audit_values.dtype == bool
        else audit_values.astype(str).str.strip().str.lower().eq("true")
    )
    mask = (
        frame["path_scope_stratum"].astype(str).eq(
            PAPER_FILTER["path_scope_stratum"]
        )
        & frame["analysis_scope"].astype(str).eq(PAPER_FILTER["analysis_scope"])
        & audit_mask
    )
    return frame.loc[mask].copy()


def build_paper_primary_units(
    entropy: pd.DataFrame,
    resolution: pd.DataFrame,
) -> pd.DataFrame:
    """Join fixed-scope distribution and mapping-resolution unit metrics."""
    filtered = fixed_paper_filter(entropy)
    filtered["msm_id"] = normalize_msm_id(filtered["msm_id"])
    observed_ids = set(filtered["msm_id"].dropna().astype(int))
    unexpected = observed_ids - EXPECTED_MEASUREMENTS
    if unexpected:
        raise RuntimeError(f"Unexpected measurement IDs: {sorted(unexpected)}")
    filtered["dataset_family"] = filtered["msm_id"].apply(dataset_family)
    filtered["stable_unit_id"] = filtered.apply(stable_unit_id, axis=1)
    if filtered["stable_unit_id"].duplicated().any():
        duplicates = filtered.loc[
            filtered["stable_unit_id"].duplicated(False),
            "stable_unit_id",
        ].tolist()
        raise RuntimeError(f"Duplicate paper-primary unit IDs: {duplicates[:5]}")

    resolution = resolution.copy()
    resolution["msm_id"] = normalize_msm_id(resolution["msm_id"])
    join_keys = [
        "msm_id",
        "probe_country",
        "service_id",
        "path_scope_stratum",
    ]
    resolution_columns = [
        *join_keys,
        "total_atomic_segments",
        "uniquely_resolved_segments",
        "bounded_candidate_set_segments",
    ]
    missing_resolution = [
        column for column in resolution_columns if column not in resolution
    ]
    if missing_resolution:
        raise RuntimeError(
            "Resolution aggregate is missing columns: "
            + ", ".join(missing_resolution)
        )
    resolution_view = resolution.loc[:, resolution_columns]
    if resolution_view.duplicated(join_keys).any():
        raise RuntimeError("Resolution aggregate contains duplicate paper unit keys.")
    units = filtered.merge(
        resolution_view,
        on=join_keys,
        how="left",
        validate="one_to_one",
    )
    if units["total_atomic_segments"].isna().any():
        missing_units = units.loc[
            units["total_atomic_segments"].isna(),
            "stable_unit_id",
        ].tolist()
        raise RuntimeError(
            "Paper-primary units missing resolution accounting: "
            + ", ".join(missing_units[:5])
        )
    units["valid_atomic_segment_count"] = pd.to_numeric(
        units["total_atomic_segments"], errors="coerce"
    ).astype("Int64")
    units["single_corridor_segment_count"] = pd.to_numeric(
        units["uniquely_resolved_segments"], errors="coerce"
    ).fillna(0).astype("Int64")
    units["bounded_multi_corridor_segment_count"] = pd.to_numeric(
        units["bounded_candidate_set_segments"], errors="coerce"
    ).fillna(0).astype("Int64")
    units["candidate_bearing_segment_count"] = (
        units["single_corridor_segment_count"]
        + units["bounded_multi_corridor_segment_count"]
    )
    units["top2_corridor_minus_network_shift"] = (
        pd.to_numeric(units["top2_corridor_share"], errors="coerce")
        - pd.to_numeric(
            units["top2_network_transition_share"],
            errors="coerce",
        )
    )
    units["normalized_entropy_reduction"] = (
        pd.to_numeric(
            units["network_transition_normalized_entropy"],
            errors="coerce",
        )
        - pd.to_numeric(
            units["corridor_normalized_entropy"],
            errors="coerce",
        )
    )
    for column in UNIT_COLUMNS:
        if column not in units:
            units[column] = np.nan
    return units.loc[:, UNIT_COLUMNS].sort_values(
        ["dataset_family", "msm_id", "probe_country"]
    ).reset_index(drop=True)


def build_group_summary(units: pd.DataFrame) -> pd.DataFrame:
    """Summarize paper metrics by the three explicit dataset families."""
    rows: list[dict[str, Any]] = []
    for family in ["DNS Roots", "Applications", "Topology references"]:
        group = units.loc[units["dataset_family"].eq(family)]
        row: dict[str, Any] = {
            "dataset_family": family,
            "unit_count": int(len(group)),
        }
        for column in MEDIAN_COLUMNS:
            row[f"median_{column}"] = float(
                pd.to_numeric(group[column], errors="coerce").median()
            )
        rows.append(row)
    return pd.DataFrame(rows)


def build_classification_summary(units: pd.DataFrame) -> pd.DataFrame:
    """Count cross-layer classes by family and paper comparison family."""
    groups = {
        "DNS Roots": units.loc[units["dataset_family"].eq("DNS Roots")],
        "Applications": units.loc[units["dataset_family"].eq("Applications")],
        "Topology references": units.loc[
            units["dataset_family"].eq("Topology references")
        ],
        "Service-facing combined": units.loc[
            units["dataset_family"].isin(["DNS Roots", "Applications"])
        ],
    }
    rows: list[dict[str, Any]] = []
    for label, group in groups.items():
        counts = group["cross_layer_distribution_class"].fillna("unknown").value_counts()
        for classification, count in counts.items():
            rows.append(
                {
                    "summary_group": label,
                    "cross_layer_distribution_class": classification,
                    "unit_count": int(count),
                    "unit_share": float(count / len(group)) if len(group) else np.nan,
                    "total_group_units": int(len(group)),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["summary_group", "cross_layer_distribution_class"]
    ).reset_index(drop=True)


def build_case_table(units: pd.DataFrame) -> pd.DataFrame:
    """Select the three explicitly catalogued paper candidate cases."""
    rows: list[pd.DataFrame] = []
    for case_label, msm_id, country in CASE_IDENTITIES:
        match = units.loc[
            units["msm_id"].eq(msm_id)
            & units["probe_country"].astype(str).eq(country)
        ].copy()
        if len(match) != 1:
            raise RuntimeError(
                f"Expected one row for {case_label}, found {len(match)}."
            )
        match.insert(0, "paper_case", case_label)
        rows.append(match)
    return pd.concat(rows, ignore_index=True, sort=False)


def build_summary_json(
    units: pd.DataFrame,
    groups: pd.DataFrame,
    classifications: pd.DataFrame,
) -> dict[str, Any]:
    """Build concise regression facts from calculated unit rows."""
    service_units = units.loc[
        units["dataset_family"].isin(["DNS Roots", "Applications"])
    ]
    topology_units = units.loc[
        units["dataset_family"].eq("Topology references")
    ]
    service_target = int(
        service_units["cross_layer_distribution_class"].eq(TARGET_CLASS).sum()
    )
    topology_target = int(
        topology_units["cross_layer_distribution_class"].eq(TARGET_CLASS).sum()
    )
    family_counts = {
        row["dataset_family"]: int(row["unit_count"])
        for _, row in groups.iterrows()
    }
    return {
        "paper_primary_schema_version": PAPER_PRIMARY_SCHEMA_VERSION,
        "fixed_filter": PAPER_FILTER,
        "total_units": int(len(units)),
        "dataset_family_unit_counts": family_counts,
        "service_facing_combined": {
            "target_class": TARGET_CLASS,
            "target_units": service_target,
            "total_units": int(len(service_units)),
            "target_share": (
                float(service_target / len(service_units))
                if len(service_units)
                else np.nan
            ),
        },
        "topology_references": {
            "target_class": TARGET_CLASS,
            "target_units": topology_target,
            "total_units": int(len(topology_units)),
            "target_share": (
                float(topology_target / len(topology_units))
                if len(topology_units)
                else np.nan
            ),
        },
        "classification_row_count": int(len(classifications)),
    }


def write_manifest(
    output_dir: Path,
    entropy_path: Path,
    resolution_path: Path,
    generated_paths: list[Path],
) -> None:
    """Write complete paper-summary provenance without fabricating commits."""
    bundle_manifest = read_json(
        entropy_path.resolve().parents[1] / "bundle_manifest.json"
    )
    measurement_manifests = [
        read_json(path)
        for path in entropy_path.resolve().parents[1].glob(
            "msm*/method_manifest.json"
        )
    ]
    generation = git_generation_state(REPO_ROOT)
    postprocess_versions = sorted(
        {
            str(item.get("postprocess_schema_version"))
            for item in measurement_manifests
            if item.get("postprocess_schema_version")
        }
    )
    identity_versions = sorted(
        {
            str(item.get("identity_schema_version"))
            for item in measurement_manifests
            if item.get("identity_schema_version")
        }
    )
    manifest = {
        "paper_primary_schema_version": PAPER_PRIMARY_SCHEMA_VERSION,
        "core_analysis_commit": inherited_commit(
            measurement_manifests,
            ["core_analysis_commit", "git_commit", "git_commit_sha"],
        ),
        "packaging_commit": bundle_manifest.get("packaging_commit", "unknown"),
        "sensitivity_analysis_commit": bundle_manifest.get(
            "sensitivity_analysis_commit",
            "unknown",
        ),
        "identity_schema_version": (
            identity_versions[0] if len(identity_versions) == 1 else "unknown"
        ),
        "postprocess_schema_version": (
            postprocess_versions[0] if len(postprocess_versions) == 1 else "unknown"
        ),
        **generation,
        "source_file_sha256": source_hashes(
            [
                REPO_ROOT / "source" / "build_paper_primary_summary.py",
                REPO_ROOT / "source" / "result_provenance.py",
            ],
            REPO_ROOT,
        ),
        "input_file_sha256": {
            str(entropy_path.resolve()): file_manifest(
                entropy_path, REPO_ROOT
            )["sha256"],
            str(resolution_path.resolve()): file_manifest(
                resolution_path, REPO_ROOT
            )["sha256"],
        },
        "input_files": [
            file_manifest(entropy_path, REPO_ROOT),
            file_manifest(resolution_path, REPO_ROOT),
        ],
        "generated_outputs": [
            file_manifest(path, REPO_ROOT) for path in generated_paths
        ],
        "fixed_filter": PAPER_FILTER,
        "dataset_family_measurement_ids": {
            "DNS Roots": sorted(DNS_ROOT_MEASUREMENTS),
            "Applications": sorted(APPLICATION_MEASUREMENTS),
            "Topology references": sorted(TOPOLOGY_MEASUREMENTS),
        },
        "interpretation": (
            "Paper-primary country-measurement units use the fixed "
            "all_publicly_visible, probe_country_service, auditable filter. "
            "Top-2 and normalized-entropy summaries describe measurement-observed "
            "network-transition and feasible-corridor distributions, not traffic "
            "volume or ground-truth cable use."
        ),
        "warnings": [
            "Historical core-analysis commit remains unknown when stage manifests do not record it.",
            "A dirty generation worktree is recorded explicitly rather than attributed to generation_git_head.",
        ],
    }
    (output_dir / "paper_primary_summary_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    """Generate all fixed-scope paper-primary outputs."""
    args = parse_args()
    entropy_path = args.entropy_input.resolve()
    resolution_path = args.resolution_input.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    entropy = pd.read_csv(entropy_path, low_memory=False)
    resolution = pd.read_csv(resolution_path, low_memory=False)
    units = build_paper_primary_units(entropy, resolution)
    groups = build_group_summary(units)
    classifications = build_classification_summary(units)
    cases = build_case_table(units)
    summary = build_summary_json(units, groups, classifications)

    outputs = {
        "paper_primary_units.csv": units,
        "paper_primary_group_summary.csv": groups,
        "paper_primary_classification_summary.csv": classifications,
        "paper_primary_case_table.csv": cases,
    }
    generated_paths: list[Path] = []
    for filename, frame in outputs.items():
        path = output_dir / filename
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        if frame.empty:
            raise RuntimeError(f"Paper-primary output is empty: {path}")
        if not frame.columns.is_unique:
            raise RuntimeError(f"Paper-primary output has duplicate columns: {path}")
        generated_paths.append(path)
    summary_path = output_dir / "paper_primary_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    generated_paths.append(summary_path)
    write_manifest(
        output_dir,
        entropy_path,
        resolution_path,
        generated_paths,
    )
    print(
        f"Saved {len(units)} fixed-scope paper-primary units to {output_dir}"
    )


if __name__ == "__main__":
    main()
