"""Rebuild physical mapping-resolution outputs from existing flattened candidates."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import postprocess_candidate_output as post


def parse_args() -> argparse.Namespace:
    """Parse the per-measurement output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    """Rebuild resolution ledgers and the uniquely resolved cross-layer subset."""
    args = parse_args()
    output_dir = Path(args.output_dir)
    feasible_path = output_dir / "trace_feasible_candidate_space.csv"
    if not feasible_path.exists():
        raise FileNotFoundError(feasible_path)
    feasible = pd.read_csv(feasible_path, low_memory=False)
    inventory = post.load_atomic_segment_inventory(str(output_dir))
    trace_frame = post.load_trace_observation_summary(str(output_dir))
    resolution_map = post.build_legacy_resolution_id_map(inventory, feasible)
    ledger, summary, unit_summary, bounded = (
        post.build_physical_mapping_resolution_tables(
            inventory,
            feasible,
            trace_frame,
            resolution_map,
        )
    )

    prepared = post.prepare_atomic_segment_projection_frame(feasible)
    inter_region = prepared.loc[
        prepared.get(
            "candidate_scope",
            pd.Series("", index=prepared.index),
        )
        .fillna("")
        .astype(str)
        .ne("intra_landing_region")
    ].copy()
    uniquely_resolved_ids = set(
        ledger.loc[
            ledger["mapping_resolution_state"].eq("uniquely_resolved"),
            "atomic_segment_id",
        ].astype(str)
    )
    projected_resolution_ids = (
        inter_region.get(
            "atomic_segment_id",
            pd.Series("", index=inter_region.index),
        )
        .astype(str)
        .map(resolution_map)
        .apply(post.canonical_resolution_segment_id)
    )
    unique_projection = inter_region.loc[
        projected_resolution_ids.isin(uniquely_resolved_ids)
    ].copy()
    scoped_unique = post.build_service_path_scope_projections(unique_projection)
    group_fields = ["probe_country", "service_id", "path_scope_stratum"]
    unique_mass = post.build_segment_corridor_mass_frame(scoped_unique)
    unique_corridor_distribution = post.summarize_corridor_observation_distribution(
        unique_mass,
        group_fields,
    )
    unique_corridor_summary = post.build_corridor_concentration_summary(
        unique_corridor_distribution,
        group_fields,
    )
    unique_network_summary = post.summarize_network_transition_concentration(
        scoped_unique,
        group_fields,
    )
    unique_cross_layer = post.build_cross_layer_distribution_audit(
        unique_corridor_summary,
        unique_network_summary,
        group_fields,
    )
    paper_unique = post.filter_auditable_paper_rows(unique_cross_layer)

    ledger.to_csv(
        output_dir / "atomic_segment_mapping_resolution.csv.gz",
        index=False,
        encoding="utf-8-sig",
        compression="gzip",
    )
    summary.to_csv(
        output_dir / "physical_mapping_resolution_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    unit_summary.to_csv(
        output_dir / "service_country_physical_mapping_resolution.csv",
        index=False,
        encoding="utf-8-sig",
    )
    bounded.to_csv(
        output_dir / "bounded_candidate_set_size_distribution.csv",
        index=False,
        encoding="utf-8-sig",
    )
    unique_cross_layer.to_csv(
        output_dir
        / "uniquely_resolved_service_country_cross_layer_distribution.csv",
        index=False,
        encoding="utf-8-sig",
    )
    paper_unique.to_csv(
        output_dir
        / "paper_uniquely_resolved_service_country_cross_layer_distribution.csv",
        index=False,
        encoding="utf-8-sig",
    )
    print(
        f"Rebuilt mapping resolution for {len(ledger)} atomic segments: "
        f"unique={len(uniquely_resolved_ids)}, "
        f"unique_cross_layer_rows={len(unique_cross_layer)}"
    )


if __name__ == "__main__":
    main()
