"""Merge existing measurement summaries with the operational country-geography catalog."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.common import REPO_DIR


SOURCE_DIR = REPO_DIR / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

import postprocess_candidate_output as postprocess  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse paths for the existing-result merge."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result-root",
        type=Path,
        default=REPO_DIR / "output" / "public_traceroute_by_msmid",
    )
    parser.add_argument(
        "--country-geography-catalog",
        type=Path,
        default=REPO_DIR / "data" / "country_geography_types.json",
    )
    return parser.parse_args()


def numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return one numeric column or an aligned missing-value series."""
    source = frame[column] if column in frame.columns else pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(source, errors="coerce")


def select_existing_scope(frame: pd.DataFrame) -> pd.DataFrame:
    """Select all-publicly-visible rows when explicit path strata are available."""
    if "path_scope_stratum" not in frame.columns:
        return frame.copy()
    return frame.loc[
        frame["path_scope_stratum"].astype(str).eq("all_publicly_visible")
    ].copy()


def load_measurement_rows(
    measurement_dir: Path,
    catalog: Dict[str, Any],
) -> tuple[pd.DataFrame, Dict[str, Any] | None]:
    """Load and combine one measurement's existing exposure and concentration summaries."""
    required = {
        "exposure": measurement_dir / "service_country_physical_exposure_summary.csv",
        "corridor": measurement_dir / "service_country_corridor_concentration_summary.csv",
        "cross_layer": measurement_dir / "service_country_cross_layer_distribution_audit.csv",
    }
    missing = [path.name for path in required.values() if not path.exists()]
    if missing:
        return pd.DataFrame(), {"measurement_dir": measurement_dir.name, "missing_files": missing}

    exposure_raw = pd.read_csv(required["exposure"])
    if exposure_raw.empty:
        return pd.DataFrame(), {
            "measurement_dir": measurement_dir.name,
            "missing_files": ["nonempty exposure rows"],
        }
    result_scope_schema = (
        "explicit_all_publicly_visible"
        if "path_scope_stratum" in exposure_raw.columns
        else "legacy_single_scope"
    )
    exposure = select_existing_scope(exposure_raw)
    if "path_scope_stratum" not in exposure.columns:
        exposure["path_scope_stratum"] = "all_publicly_visible_legacy"
    corridor = select_existing_scope(pd.read_csv(required["corridor"]))
    cross_layer = select_existing_scope(pd.read_csv(required["cross_layer"]))

    join_keys = [
        key
        for key in ["probe_country", "service_id"]
        if key in exposure.columns and key in corridor.columns
    ]
    if not join_keys:
        return pd.DataFrame(), {
            "measurement_dir": measurement_dir.name,
            "missing_files": ["compatible country/service join keys"],
        }

    corridor_columns = join_keys + [
        column
        for column in [
            "total_mappable_segments",
            "top1_corridor_id",
            "top1_corridor_share",
            "top2_corridor_share",
            "top3_corridor_share",
            "effective_corridor_count",
            "corridor_concentration_tier",
            "is_corridor_concentrated",
            "auditable_corridor_concentration",
            "auditable_paper_case",
        ]
        if column in corridor.columns
    ]
    corridor_join = corridor[corridor_columns].drop_duplicates(subset=join_keys).rename(
        columns={"auditable_paper_case": "corridor_auditable_paper_case"}
    )
    merged = exposure.merge(corridor_join, on=join_keys, how="left", validate="many_to_one")

    if all(key in cross_layer.columns for key in join_keys):
        cross_columns = join_keys + [
            column
            for column in [
                "effective_network_transition_count",
                "network_transition_concentration_tier",
                "cross_layer_distribution_class",
                "country_fallback_share",
                "auditable_paper_case",
            ]
            if column in cross_layer.columns
        ]
        cross_join = cross_layer[cross_columns].drop_duplicates(subset=join_keys).rename(
            columns={"auditable_paper_case": "cross_layer_auditable_paper_case"}
        )
        merged = merged.merge(cross_join, on=join_keys, how="left", validate="many_to_one")

    measurement_match = re.match(r"msm(\d+)_", measurement_dir.name)
    merged["measurement_id"] = measurement_match.group(1) if measurement_match else "NA"
    merged["measurement_dir"] = measurement_dir.name
    merged["result_scope_schema"] = result_scope_schema
    classified = merged["probe_country"].apply(
        lambda value: postprocess.classify_country_geography_type(value, catalog)
    )
    merged["country_geography_type"] = classified.apply(lambda value: value[0])
    merged["country_geography_classification_source"] = classified.apply(lambda value: value[1])

    existing_rate = numeric_column(merged, "service_physical_exposure_rate")
    inter_region_rate = numeric_column(merged, "inter_region_candidate_exposure_rate")
    merged["existing_candidate_exposure_rate"] = existing_rate
    merged["analysis_candidate_dependency_rate"] = inter_region_rate.where(
        inter_region_rate.notna(), existing_rate
    )
    merged["analysis_candidate_dependency_rate_source"] = np.where(
        inter_region_rate.notna(),
        "inter_region_candidate_exposure_rate",
        "legacy_service_physical_exposure_rate",
    )
    merged["analysis_candidate_dependency_tier"] = merged[
        "analysis_candidate_dependency_rate"
    ].apply(postprocess.classify_candidate_dependency_proxy)
    merged["metric_interpretation_boundary"] = (
        "existing feasible-candidate exposure and corridor-observation concentration; "
        "not actual cable use, traffic volume, causal dependency, or resilience ground truth"
    )
    return merged, None


def build_geography_summary(combined: pd.DataFrame) -> pd.DataFrame:
    """Aggregate existing measurement rows by operational country-geography type."""
    rows: List[Dict[str, Any]] = []
    for (geography_type, rate_source), group in combined.groupby(
        ["country_geography_type", "analysis_candidate_dependency_rate_source"],
        dropna=False,
    ):
        rates = numeric_column(group, "analysis_candidate_dependency_rate")
        total_traces = numeric_column(group, "total_valid_traces").fillna(0)
        estimated_exposed = total_traces * rates.fillna(0)
        audit_column = (
            "cross_layer_auditable_paper_case"
            if "cross_layer_auditable_paper_case" in group.columns
            else "auditable_paper_case"
        )
        auditable = (
            group[audit_column].fillna(False).astype(bool)
            if audit_column in group.columns
            else pd.Series(False, index=group.index)
        )
        auditable_group = group.loc[auditable]
        concentration = auditable_group.get(
            "corridor_concentration_tier",
            pd.Series(index=auditable_group.index, dtype=object),
        ).astype(str)
        concentrated = concentration.isin(
            [
                "severe_corridor_observation_concentration",
                "moderate_corridor_observation_concentration",
            ]
        )
        cross_signal = auditable_group.get(
            "cross_layer_distribution_class",
            pd.Series(index=auditable_group.index, dtype=object),
        ).astype(str).eq("network_broad_physical_concentrated")
        rows.append(
            {
                "country_geography_type": geography_type,
                "analysis_candidate_dependency_rate_source": rate_source,
                "measurement_service_country_units": int(len(group)),
                "measurements": int(group["measurement_id"].astype(str).nunique()),
                "countries": int(group["probe_country"].astype(str).nunique()),
                "total_valid_traces_summed_across_measurements": int(total_traces.sum()),
                "estimated_candidate_exposed_traces_from_available_rate": float(estimated_exposed.sum()),
                "trace_weighted_available_candidate_dependency_rate": (
                    float(estimated_exposed.sum() / total_traces.sum())
                    if total_traces.sum()
                    else np.nan
                ),
                "median_unit_candidate_dependency_rate": float(rates.median()),
                "candidate_dependency_rate_p25": float(rates.quantile(0.25)),
                "candidate_dependency_rate_p75": float(rates.quantile(0.75)),
                "auditable_service_country_units": int(auditable.sum()),
                "auditable_severe_or_moderate_corridor_units": int(concentrated.sum()),
                "auditable_severe_or_moderate_corridor_share": (
                    float(concentrated.mean()) if len(concentrated) else np.nan
                ),
                "auditable_network_broad_physical_concentrated_units": int(cross_signal.sum()),
                "auditable_network_broad_physical_concentrated_share": (
                    float(cross_signal.mean()) if len(cross_signal) else np.nan
                ),
                "interpretation": (
                    "descriptive stratification of existing measurement outputs by operational country geography type"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["country_geography_type", "analysis_candidate_dependency_rate_source"]
    ).reset_index(drop=True)


def main() -> None:
    """Merge all compatible measurement summaries without rerunning candidate analysis."""
    args = parse_args()
    result_root = args.result_root.resolve()
    catalog_path = args.country_geography_catalog.resolve()
    catalog = postprocess.load_country_geography_catalog(str(catalog_path))
    frames: List[pd.DataFrame] = []
    skipped: List[Dict[str, Any]] = []
    for measurement_dir in sorted(result_root.glob("msm*")):
        if not measurement_dir.is_dir():
            continue
        frame, skip = load_measurement_rows(measurement_dir, catalog)
        if skip:
            skipped.append(skip)
        elif not frame.empty:
            frames.append(frame)
    combined = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    if combined.empty:
        raise RuntimeError("No compatible existing measurement summaries were found.")

    combined_path = result_root / "all_measurements_service_country_geography_concentration.csv"
    summary_path = result_root / "all_measurements_country_geography_type_summary.csv"
    tier_path = result_root / "all_measurements_geography_concentration_tier_summary.csv"
    catalog_output_path = result_root / "all_measurements_country_geography_catalog_resolved.csv"
    paper_path = result_root / "all_measurements_paper_service_country_geography_concentration.csv"
    manifest_path = result_root / "all_measurements_country_geography_merge_manifest.json"

    combined.to_csv(combined_path, index=False, encoding="utf-8-sig")
    build_geography_summary(combined).to_csv(summary_path, index=False, encoding="utf-8-sig")
    tier_summary = (
        combined.groupby(
            ["country_geography_type", "corridor_concentration_tier"], dropna=False
        )
        .agg(
            measurement_service_country_units=("probe_country", "size"),
            countries=("probe_country", pd.Series.nunique),
            measurements=("measurement_id", pd.Series.nunique),
        )
        .reset_index()
    )
    tier_summary.to_csv(tier_path, index=False, encoding="utf-8-sig")
    audit_column = (
        "cross_layer_auditable_paper_case"
        if "cross_layer_auditable_paper_case" in combined.columns
        else "auditable_paper_case"
    )
    paper_rows = (
        combined.loc[combined[audit_column].fillna(False).astype(bool)].copy()
        if audit_column in combined.columns
        else combined.iloc[0:0].copy()
    )
    paper_rows.to_csv(paper_path, index=False, encoding="utf-8-sig")
    combined[
        [
            "probe_country",
            "country_geography_type",
            "country_geography_classification_source",
        ]
    ].drop_duplicates().sort_values("probe_country").to_csv(
        catalog_output_path, index=False, encoding="utf-8-sig"
    )
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "merge_existing_measurement_results_with_operational_country_geography_type",
        "input_policy": "existing summary CSVs only; no Stage 1 or full postprocess rerun",
        "catalog": str(catalog_path.relative_to(REPO_DIR)),
        "measurements_included": sorted(combined["measurement_dir"].astype(str).unique()),
        "measurements_skipped": skipped,
        "scope_harmonization": (
            "explicit outputs use all_publicly_visible; legacy outputs retain their single existing scope"
        ),
        "rate_harmonization": (
            "prefer inter_region_candidate_exposure_rate when present; otherwise retain "
            "legacy service_physical_exposure_rate with an explicit source label"
        ),
        "generated_outputs": [
            path.name
            for path in [combined_path, summary_path, tier_path, catalog_output_path, paper_path]
        ],
        "interpretation_boundary": (
            "descriptive feasible-candidate and corridor-concentration analysis, "
            "not actual cable use or traffic dependency"
        ),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "included_measurements": len(manifest["measurements_included"]),
                "skipped_measurements": skipped,
                "combined_rows": len(combined),
                "countries": int(combined["probe_country"].astype(str).nunique()),
                "outputs": [*manifest["generated_outputs"], manifest_path.name],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
