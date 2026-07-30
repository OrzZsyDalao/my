"""Run and summarize the 27-setting A-Root projection sensitivity grid."""

from __future__ import annotations

import argparse
import itertools
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = (
    REPO_ROOT
    / "data"
    / "traceroute_rundnsroot"
    / "ripe_atlas_public_20260701_0000_0100"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "output" / "sensitivity_a_root"
DEFAULT_AS_PRECOMPUTE = (
    REPO_ROOT / "output" / "preprocessed" / "as_graph_owner_reachability.pkl.gz"
)
BASELINE = (50, 50, 5)


def parse_args() -> argparse.Namespace:
    """Parse sensitivity input, output, and execution controls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--as-precompute-file",
        type=Path,
        default=DEFAULT_AS_PRECOMPUTE,
    )
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve_a_root_input(explicit: Path | None) -> Path:
    """Resolve the downloaded A-Root result file."""
    if explicit:
        return explicit.resolve()
    matches = sorted(DEFAULT_INPUT_ROOT.glob("*a-root*msm5009*.json"))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one A-Root msm5009 input under {DEFAULT_INPUT_ROOT}, "
            f"found {len(matches)}."
        )
    return matches[0].resolve()


def setting_name(catchment: int, diameter: int, rtt: int) -> str:
    """Return a stable directory label for one sensitivity setting."""
    return f"catchment{catchment}_diameter{diameter}_rtt{rtt}"


def run_command(command: Iterable[str], dry_run: bool) -> None:
    """Run one subprocess and fail immediately on non-zero exit."""
    printable = " ".join(str(item) for item in command)
    print(f"Running: {printable}")
    if not dry_run:
        subprocess.run(list(command), cwd=REPO_ROOT, check=True)


def median_numeric(frame: pd.DataFrame, column: str) -> float:
    """Return one robust numeric median."""
    if frame.empty or column not in frame:
        return np.nan
    return float(pd.to_numeric(frame[column], errors="coerce").median())


def auditable_scope(frame: pd.DataFrame) -> pd.DataFrame:
    """Select paper-auditable all-publicly-visible rows when columns exist."""
    result = frame.copy()
    if "path_scope_stratum" in result:
        result = result.loc[
            result["path_scope_stratum"].astype(str).eq("all_publicly_visible")
        ]
    audit_column = next(
        (
            column
            for column in ["auditable_paper_case", "auditable_cross_layer_case"]
            if column in result
        ),
        None,
    )
    if audit_column:
        result = result.loc[result[audit_column].fillna(False).astype(bool)]
    return result


def load_setting_summary(
    output_dir: Path,
    catchment: int,
    diameter: int,
    rtt: int,
) -> tuple[Dict[str, Any], pd.DataFrame]:
    """Extract paper-facing sensitivity metrics from one completed setting."""
    resolution = pd.read_csv(output_dir / "physical_mapping_resolution_summary.csv")
    resolution_counts = dict(
        zip(resolution["mapping_resolution_state"], resolution["atomic_segment_count"])
    )
    total_segments = int(pd.to_numeric(resolution["atomic_segment_count"]).sum())
    unique = int(resolution_counts.get("uniquely_resolved", 0))
    bounded = int(resolution_counts.get("bounded_candidate_set", 0))
    cross = pd.read_csv(output_dir / "service_country_cross_layer_distribution_audit.csv")
    corridor = pd.read_csv(output_dir / "service_country_corridor_concentration_summary.csv")
    entropy = pd.read_csv(output_dir / "cross_layer_normalized_entropy_audit.csv")
    audit_cross = auditable_scope(cross)
    audit_corridor = auditable_scope(corridor)
    audit_entropy = auditable_scope(entropy)
    keys = [
        column
        for column in ["probe_country", "service_id", "path_scope_stratum"]
        if column in audit_cross
    ]
    classifications = audit_cross[
        [*keys, "cross_layer_distribution_class"]
    ].drop_duplicates(keys)
    return (
        {
            "setting": setting_name(catchment, diameter, rtt),
            "landing_catchment_radius_km": catchment,
            "landing_region_maximum_diameter_km": diameter,
            "rtt_tolerance_ms": rtt,
            "inter_region_candidate_bearing_segments": unique + bounded,
            "uniquely_resolved_segments": unique,
            "bounded_candidate_set_segments": bounded,
            "uniquely_resolved_share": unique / total_segments if total_segments else np.nan,
            "bounded_candidate_set_share": bounded / total_segments if total_segments else np.nan,
            "auditable_country_service_units": int(len(audit_cross)),
            "median_corridor_top2_share": median_numeric(
                audit_corridor, "top2_corridor_share"
            ),
            "median_corridor_normalized_entropy": median_numeric(
                audit_entropy, "corridor_normalized_entropy"
            ),
            "median_normalized_entropy_reduction": median_numeric(
                audit_entropy, "normalized_entropy_reduction"
            ),
        },
        classifications,
    )


def classification_agreement(
    current: pd.DataFrame,
    baseline: pd.DataFrame,
) -> float:
    """Compute classification agreement on shared paper-auditable units."""
    if current.empty or baseline.empty:
        return np.nan
    keys = [
        column
        for column in ["probe_country", "service_id", "path_scope_stratum"]
        if column in current and column in baseline
    ]
    merged = baseline.merge(
        current,
        on=keys,
        how="inner",
        suffixes=("_baseline", "_current"),
    )
    if merged.empty:
        return np.nan
    return float(
        (
            merged["cross_layer_distribution_class_baseline"].astype(str)
            == merged["cross_layer_distribution_class_current"].astype(str)
        ).mean()
    )


def main() -> None:
    """Run missing settings and write the paper-facing sensitivity summary."""
    args = parse_args()
    input_path = resolve_a_root_input(args.input)
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    settings = list(itertools.product([30, 50, 75], [30, 50, 75], [0, 5, 10]))

    for catchment, diameter, rtt in settings:
        output_dir = output_root / setting_name(catchment, diameter, rtt)
        summary_path = output_dir / "cross_layer_normalized_entropy_audit.csv"
        if args.skip_existing and summary_path.exists() and summary_path.stat().st_size > 0:
            continue
        output_dir.mkdir(parents=True, exist_ok=True)
        run_command(
            [
                sys.executable,
                "source/main_analysis.py",
                "--traceroute-input",
                str(input_path),
                "--output-dir",
                str(output_dir),
                "--as-precompute-file",
                str(args.as_precompute_file.resolve()),
                "--landing-catchment-radius-km",
                str(catchment),
                "--landing-region-radius-km",
                str(diameter),
                "--rtt-tolerance-ms",
                str(rtt),
            ],
            args.dry_run,
        )
        run_command(
            [
                sys.executable,
                "source/build_atomic_segment_inventory.py",
                "--traceroute-input",
                str(input_path),
                "--output-dir",
                str(output_dir),
            ],
            args.dry_run,
        )
        run_command(
            [
                sys.executable,
                "source/postprocess_candidate_output.py",
                "--input",
                str(output_dir / "cable_matching_output.json"),
                "--output",
                str(output_dir),
            ],
            args.dry_run,
        )

    if args.dry_run:
        return
    rows: list[Dict[str, Any]] = []
    classifications: Dict[tuple[int, int, int], pd.DataFrame] = {}
    for catchment, diameter, rtt in settings:
        output_dir = output_root / setting_name(catchment, diameter, rtt)
        row, classification = load_setting_summary(
            output_dir,
            catchment,
            diameter,
            rtt,
        )
        rows.append(row)
        classifications[(catchment, diameter, rtt)] = classification
    baseline = classifications[BASELINE]
    for row in rows:
        key = (
            int(row["landing_catchment_radius_km"]),
            int(row["landing_region_maximum_diameter_km"]),
            int(row["rtt_tolerance_ms"]),
        )
        row["classification_agreement_with_baseline"] = classification_agreement(
            classifications[key],
            baseline,
        )
    pd.DataFrame(rows).to_csv(
        output_root / "a_root_sensitivity_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    print(f"Saved 27-setting A-Root sensitivity summary to {output_root}")


if __name__ == "__main__":
    main()
