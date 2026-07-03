import argparse
import os
from typing import Dict, List, Set

import numpy as np
import pandas as pd

try:
    from source.postprocess_candidate_output import (
        TARGET_MISMATCH_CATEGORY,
        NETWORK_DEFINITION_COLUMNS,
        PAPER_PRIMARY_NETWORK_DEFINITION,
        build_quadrant_summary,
        build_unit_network_layer_diversity,
        build_unit_network_physical_mismatch,
        build_unit_network_physical_upper_bound_mismatch,
        build_unit_physical_feasible_set_diversity,
        build_unit_physical_candidate_diversity,
        annotate_projection_quality,
        ensure_corridor_columns,
        load_peeringdb_descriptors,
        merge_peeringdb_descriptors,
        resolve_corridor_candidate_column,
    )
except ModuleNotFoundError:
    import sys

    SOURCE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else "."
    BASE_DIR = os.path.dirname(SOURCE_DIR)
    if BASE_DIR not in sys.path:
        sys.path.append(BASE_DIR)
    from source.postprocess_candidate_output import (  # type: ignore
        TARGET_MISMATCH_CATEGORY,
        NETWORK_DEFINITION_COLUMNS,
        PAPER_PRIMARY_NETWORK_DEFINITION,
        build_quadrant_summary,
        build_unit_network_layer_diversity,
        build_unit_network_physical_mismatch,
        build_unit_network_physical_upper_bound_mismatch,
        build_unit_physical_feasible_set_diversity,
        build_unit_physical_candidate_diversity,
        annotate_projection_quality,
        ensure_corridor_columns,
        load_peeringdb_descriptors,
        merge_peeringdb_descriptors,
        resolve_corridor_candidate_column,
    )


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else "."
BASE_DIR = os.path.dirname(SOURCE_DIR)
DEFAULT_INPUT = os.path.join(BASE_DIR, "output", "result", "trace_candidate_support.csv")
DEFAULT_OUTPUT = os.path.join(BASE_DIR, "output", "result")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Compare network-physical mismatch stability across evidence settings.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input trace_candidate_support.csv file.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output directory.")
    return parser.parse_args()


def normalize_within_links(frame: pd.DataFrame, score_col: str, out_col: str) -> pd.DataFrame:
    """Normalize a score column within each link."""
    result = frame.copy()
    grouped = result.groupby("link_id")[score_col].transform("sum")
    result[out_col] = np.where(grouped > 0, result[score_col] / grouped, 0.0)
    return result


def spearman_corr(left: pd.Series, right: pd.Series) -> float:
    """Compute a Spearman correlation with graceful fallback."""
    if left.empty or right.empty:
        return 0.0
    value = left.corr(right, method="spearman")
    return 0.0 if pd.isna(value) else float(value)


def top_k_overlap(left: pd.DataFrame, right: pd.DataFrame, metric: str, top_k: int) -> float:
    """Compute overlap ratio between top-k units under a metric."""
    if left.empty or right.empty or top_k <= 0:
        return 0.0
    left_ids = set(left.nlargest(top_k, metric)["unit_id"])
    right_ids = set(right.nlargest(top_k, metric)["unit_id"])
    if not left_ids and not right_ids:
        return 1.0
    return float(len(left_ids & right_ids) / max(len(left_ids | right_ids), 1))


def write_named_bar_svg(summary_frame: pd.DataFrame, output_path: str, title: str) -> None:
    """Render a simple bar chart keyed by arbitrary mode names."""
    width = 1040
    height = 620
    if summary_frame.empty:
        svg = (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
            "<rect width='100%' height='100%' fill='white'/>"
            "<text x='24' y='36' font-size='18'>No data available.</text></svg>"
        )
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        return

    plot_left = 120
    plot_top = 80
    plot_width = 820
    plot_height = 360
    max_count = max(int(summary_frame["shared_target_units"].max()), 1)
    bar_slot = plot_width / max(len(summary_frame), 1)
    body = [
        f"<text x='24' y='34' font-size='20' font-family='Arial'>{title}</text>",
        f"<line x1='{plot_left}' y1='{plot_top + plot_height}' x2='{plot_left + plot_width}' y2='{plot_top + plot_height}' stroke='#566573'/>",
        f"<line x1='{plot_left}' y1='{plot_top}' x2='{plot_left}' y2='{plot_top + plot_height}' stroke='#566573'/>",
    ]

    for index, (_, row) in enumerate(summary_frame.iterrows()):
        x = plot_left + index * bar_slot + 18
        height_value = plot_height * (float(row["shared_target_units"]) / max_count)
        y = plot_top + plot_height - height_value
        fill = "#c0392b" if str(row["mode"]) == "fused_dual_core_cable" else "#5dade2"
        body.append(f"<rect x='{x:.2f}' y='{y:.2f}' width='72' height='{height_value:.2f}' fill='{fill}'/>")
        body.append(f"<text x='{x + 12:.2f}' y='{y - 8:.2f}' font-size='12' font-family='Arial'>{int(row['shared_target_units'])}</text>")
        body.append(f"<text x='{x - 4:.2f}' y='{plot_top + plot_height + 22:.2f}' font-size='10' font-family='Arial'>{row['mode']}</text>")
        body.append(
            f"<text x='{x - 4:.2f}' y='{plot_top + plot_height + 38:.2f}' font-size='10' font-family='Arial'>J={float(row['target_jaccard_vs_baseline']):.2f}</text>"
        )

    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        "<rect width='100%' height='100%' fill='white'/>"
        + "".join(body)
        + "</svg>"
    )
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(svg)


def build_mode_result(
    mode_name: str,
    mode_frame: pd.DataFrame,
    support_col: str,
    candidate_col: str,
    physical_level: str,
    network_frame: pd.DataFrame,
    network_definition: str,
    network_score_column: str,
) -> Dict[str, pd.DataFrame]:
    """Build physical-diversity and mismatch tables for one evidence setting."""
    if mode_frame.empty:
        physical = pd.DataFrame()
        mismatch = pd.DataFrame()
        quadrant_summary = pd.DataFrame(columns=["physical_level", "network_physical_mismatch_category", "unit_count", "unit_share"])
    else:
        physical = build_unit_physical_candidate_diversity(
            mode_frame,
            candidate_id_col=candidate_col,
            physical_level=physical_level,
            support_col=support_col,
        )
        mismatch = build_unit_network_physical_mismatch(
            network_frame,
            physical,
            physical_level,
            network_score_column=network_score_column,
            network_definition=network_definition,
        )
        mismatch["mode"] = mode_name
        quadrant_summary = build_quadrant_summary(mismatch, physical_level)
        quadrant_summary["mode"] = mode_name

    if not physical.empty:
        physical["mode"] = mode_name
    return {
        "mode": mode_name,
        "physical_level": physical_level,
        "network_definition": network_definition,
        "network_score_column": network_score_column,
        "physical": physical,
        "mismatch": mismatch,
        "quadrant_summary": quadrant_summary,
    }


def build_candidate_space_mode_result(
    mode_name: str,
    physical_frame: pd.DataFrame,
    physical_level: str,
    network_frame: pd.DataFrame,
    network_definition: str,
    network_score_column: str,
) -> Dict[str, pd.DataFrame]:
    """Build mismatch output for a precomputed weighted or uniform physical-diversity view."""
    if physical_frame.empty:
        mismatch = pd.DataFrame()
    else:
        mismatch = build_unit_network_physical_mismatch(
            network_frame,
            physical_frame,
            physical_level,
            network_score_column=network_score_column,
            network_definition=network_definition,
        )
        mismatch["mode"] = mode_name
    return {
        "mode": mode_name,
        "physical_level": physical_level,
        "network_definition": network_definition,
        "network_score_column": network_score_column,
        "physical": physical_frame.copy(),
        "mismatch": mismatch,
    }


def target_unit_set(mismatch_frame: pd.DataFrame) -> Set[str]:
    """Return the set of units in the target mismatch quadrant."""
    if mismatch_frame.empty:
        return set()
    return set(
        mismatch_frame.loc[
            mismatch_frame["network_physical_mismatch_category"].astype(str) == TARGET_MISMATCH_CATEGORY,
            "unit_id",
        ]
    )


def quadrant_agreement_rate(baseline: pd.DataFrame, candidate: pd.DataFrame) -> float:
    """Compute the fraction of units with the same quadrant label."""
    required_columns = {"unit_id", "network_physical_mismatch_category"}
    if baseline.empty or candidate.empty:
        return 0.0
    if not required_columns.issubset(baseline.columns) or not required_columns.issubset(candidate.columns):
        return 0.0
    merged = baseline[["unit_id", "network_physical_mismatch_category"]].merge(
        candidate[["unit_id", "network_physical_mismatch_category"]],
        on="unit_id",
        suffixes=("_baseline", "_mode"),
        how="inner",
    )
    if merged.empty:
        return 0.0
    return float(
        (
            merged["network_physical_mismatch_category_baseline"].astype(str)
            == merged["network_physical_mismatch_category_mode"].astype(str)
        ).mean()
    )


def infer_evidence_view(setting: str) -> str:
    """Map an internal setting name to a compact evidence-view label."""
    if setting.startswith("geo_only"):
        return "geo_only"
    if setting.startswith("as_only"):
        return "as_only"
    if setting.startswith("high_confidence_subset"):
        return "high_confidence_subset"
    if setting.startswith("fused_dual_core"):
        return "fused_dual_core"
    if setting.startswith("weighted"):
        return "weighted"
    if setting.startswith("uniform"):
        return "uniform"
    return "custom"


def infer_physical_projection_setting(setting: str, physical_level: str) -> str:
    """Map a setting to a paper-facing physical projection label."""
    if str(physical_level) == "corridor" or setting.endswith("_corridor"):
        return "corridor_grouped_candidates"
    return "cable_candidates"


def infer_projection_subset(setting: str) -> str:
    """Map a setting to an all-links vs strong-projection subset label."""
    if "_strong_" in setting or setting.endswith("_strong") or "strong_projection" in setting:
        return "strong_only"
    return "all_projections"


def normalize_upper_bound_category(label: str) -> str:
    """Normalize weighted and upper-bound quadrant labels onto a common comparison vocabulary."""
    return str(label).replace("_physical_upper_", "_physical_")


def build_conservative_audit_interpretation(
    candidate_view: str,
    physical_level: str,
    projection_subset: str,
    network_definition: str,
) -> str:
    """Generate a paper-facing interpretation for the conservative candidate-audit robustness table."""
    pieces = [f"{network_definition} network definition"]
    pieces.append("corridor-level" if physical_level == "corridor" else "cable-level")
    pieces.append("conservative feasible-set view" if candidate_view == "conservative_set" else "weighted support view")
    if projection_subset == "strong_only":
        pieces.append("strong projections only")
    elif projection_subset == "strong_or_moderate":
        pieces.append("strong/moderate projections only")
    else:
        pieces.append("all projections")
    return ", ".join(pieces)


def build_robustness_interpretation(row: pd.Series) -> str:
    """Generate the paper-facing interpretation string for one robustness setting."""
    setting = str(row.get("setting", ""))
    if setting == "fused_dual_core_cable":
        return "baseline dual-core cable-level view"
    if setting.endswith("_corridor"):
        if setting.startswith("geo_only"):
            return "tests whether network-physical mismatch is stable under geo-spatial evidence only after aggregating parallel candidates into corridors"
        if setting.startswith("as_only"):
            return "tests whether network-physical mismatch is stable under AS-economic evidence only after aggregating parallel candidates into corridors"
        if setting.startswith("high_confidence_subset"):
            return "tests whether mismatch persists under high-confidence observations after aggregating parallel candidates into corridors"
        return "tests whether mismatch persists after aggregating parallel candidates into corridors"
    if setting.startswith("geo_only"):
        return "tests whether network-physical mismatch is stable under geo-spatial evidence only"
    if setting.startswith("as_only"):
        return "tests whether network-physical mismatch is stable under AS-economic evidence only"
    if setting.startswith("high_confidence_subset"):
        return "tests whether mismatch persists under high-confidence observations"
    if setting.startswith("fused_dual_core"):
        return "baseline dual-core candidate-support view"
    return "supplementary robustness view"


def subset_by_projection(frame: pd.DataFrame, projection_subset: str) -> pd.DataFrame:
    """Filter a candidate table by projection-quality subset."""
    if frame.empty or "projection_class" not in frame.columns:
        return frame.copy()
    projection_values = frame["projection_class"].fillna("").astype(str)
    if projection_subset == "strong_only":
        return frame.loc[projection_values == "strong"].copy()
    if projection_subset == "strong_or_moderate":
        return frame.loc[projection_values.isin(["strong", "moderate"])].copy()
    return frame.copy()


def numeric_series_or_default(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    """Return a numeric Series from a DataFrame column or a constant-valued fallback series."""
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce").fillna(default)
    return pd.Series(np.full(len(frame), default, dtype=float), index=frame.index, dtype=float)


def summarize_peeringdb_context(frame: pd.DataFrame) -> Dict[str, object]:
    """Summarize optional PeeringDB descriptor coverage for an aggregate robustness slice."""
    if frame.empty or "pdb_interconnection_footprint_percentile" not in frame.columns:
        return {
            "pdb_country_coverage": 0,
            "median_pdb_interconnection_footprint_percentile": np.nan,
            "dominant_pdb_interconnection_footprint_tier": "",
        }
    percentile_series = pd.to_numeric(frame["pdb_interconnection_footprint_percentile"], errors="coerce").dropna()
    tier_series = frame.get("pdb_interconnection_footprint_tier", pd.Series(index=frame.index, dtype=object)).dropna().astype(str)
    dominant_tier = tier_series.mode().iloc[0] if not tier_series.empty else ""
    return {
        "pdb_country_coverage": int(frame["src_country"].replace("", np.nan).dropna().nunique()) if "src_country" in frame.columns else 0,
        "median_pdb_interconnection_footprint_percentile": float(percentile_series.median()) if not percentile_series.empty else np.nan,
        "dominant_pdb_interconnection_footprint_tier": dominant_tier,
    }


def main() -> None:
    """Compare evidence settings and their network-physical mismatch stability."""
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)

    frame = pd.read_csv(args.input)
    if frame.empty:
        raise ValueError("Input trace_candidate_support.csv is empty.")

    feasible_input_path = os.path.join(os.path.dirname(args.input), "trace_feasible_candidate_space.csv")
    if os.path.exists(feasible_input_path):
        feasible_frame = pd.read_csv(feasible_input_path)
    else:
        print("Warning: trace_feasible_candidate_space.csv not found; falling back to trace_candidate_support.csv.")
        feasible_frame = frame.copy()

    frame["geo_spatial_score"] = frame["geo_spatial_score"].fillna(0.0)
    frame["as_economic_score"] = frame["as_economic_score"].fillna(0.0)
    frame["normalized_candidate_support"] = frame["normalized_candidate_support"].fillna(0.0)
    frame = ensure_corridor_columns(frame)
    frame = annotate_projection_quality(frame)
    corridor_candidate_col = resolve_corridor_candidate_column(frame)

    feasible_frame["candidate_support"] = pd.to_numeric(
        feasible_frame.get("candidate_support", pd.Series(np.zeros(len(feasible_frame)), index=feasible_frame.index)),
        errors="coerce",
    ).fillna(0.0)
    feasible_frame["normalized_candidate_support"] = pd.to_numeric(
        feasible_frame.get("normalized_candidate_support", feasible_frame["candidate_support"]),
        errors="coerce",
    ).fillna(0.0)
    feasible_frame = ensure_corridor_columns(feasible_frame)
    feasible_frame = annotate_projection_quality(feasible_frame)
    feasible_corridor_candidate_col = resolve_corridor_candidate_column(feasible_frame)

    network_frame = build_unit_network_layer_diversity(feasible_frame if not feasible_frame.empty else frame)
    peeringdb_descriptors = load_peeringdb_descriptors(args.output)
    geo_frame = normalize_within_links(frame, "geo_spatial_score", "geo_only_support")
    as_frame = normalize_within_links(frame, "as_economic_score", "as_only_support")
    high_conf_frame = frame[
        (frame["confidence_bucket"] == "high") | (frame["core_agreement"] == "dual_core_agreement")
    ].copy()
    strong_projection_frame = frame[frame["projection_class"].astype(str) == "strong"].copy()

    mode_specs = [
        ("fused_dual_core_cable", frame, "normalized_candidate_support", "cable_id", "cable"),
        ("geo_only_cable", geo_frame, "geo_only_support", "cable_id", "cable"),
        ("as_only_cable", as_frame, "as_only_support", "cable_id", "cable"),
        (
            "high_confidence_subset_cable",
            high_conf_frame if not high_conf_frame.empty else frame.iloc[0:0],
            "normalized_candidate_support",
            "cable_id",
            "cable",
        ),
        ("fused_dual_core_corridor", frame, "normalized_candidate_support", corridor_candidate_col, "corridor"),
        ("geo_only_corridor", geo_frame, "geo_only_support", corridor_candidate_col, "corridor"),
        ("as_only_corridor", as_frame, "as_only_support", corridor_candidate_col, "corridor"),
        (
            "high_confidence_subset_corridor",
            high_conf_frame if not high_conf_frame.empty else frame.iloc[0:0],
            "normalized_candidate_support",
            corridor_candidate_col,
            "corridor",
        ),
    ]

    robustness_rows: List[Dict[str, float]] = []
    stability_rows: List[Dict[str, float]] = []
    quadrant_summaries: List[pd.DataFrame] = []
    candidate_space_rows: List[Dict[str, float]] = []
    for network_definition, network_score_column in NETWORK_DEFINITION_COLUMNS.items():
        mode_results = [
            build_mode_result(
                *spec,
                network_frame=network_frame,
                network_definition=network_definition,
                network_score_column=network_score_column,
            )
            for spec in mode_specs
        ]
        baseline = next(result for result in mode_results if result["mode"] == "fused_dual_core_cable")
        baseline_physical = baseline["physical"]
        baseline_mismatch = baseline["mismatch"]
        baseline_target = target_unit_set(baseline_mismatch)
        top_k = max(1, min(10, len(baseline_physical))) if not baseline_physical.empty else 1

        for result in mode_results:
            mode_name = str(result["mode"])
            physical_level = str(result["physical_level"])
            physical = result["physical"]
            mismatch = result["mismatch"]
            quadrant_summary = result["quadrant_summary"]

            if not quadrant_summary.empty:
                quadrant_summary["network_definition"] = network_definition
                quadrant_summaries.append(quadrant_summary)

            merged = baseline_physical.merge(physical, on="unit_id", suffixes=("_baseline", "_mode"), how="inner")
            if merged.empty:
                robustness_rows.append(
                    {
                        "network_definition": network_definition,
                        "mode": mode_name,
                        "physical_level": physical_level,
                        "num_units_compared": 0,
                        "spearman_dominant_candidate_support_share": 0.0,
                        "spearman_effective_num_candidates": 0.0,
                        "topk_dominant_share_overlap": 0.0,
                    }
                )
            else:
                robustness_rows.append(
                    {
                        "network_definition": network_definition,
                        "mode": mode_name,
                        "physical_level": physical_level,
                        "num_units_compared": int(len(merged)),
                        "spearman_dominant_candidate_support_share": spearman_corr(
                            merged["dominant_candidate_support_share_baseline"],
                            merged["dominant_candidate_support_share_mode"],
                        ),
                        "spearman_effective_num_candidates": spearman_corr(
                            merged["effective_num_candidates_baseline"],
                            merged["effective_num_candidates_mode"],
                        ),
                        "topk_dominant_share_overlap": top_k_overlap(
                            baseline_physical,
                            physical,
                            "dominant_candidate_support_share",
                            top_k,
                        ),
                    }
                )

            mode_target = target_unit_set(mismatch)
            intersection = baseline_target & mode_target
            union = baseline_target | mode_target
            stability_rows.append(
                {
                    "network_definition": network_definition,
                    "mode": mode_name,
                    "physical_level": physical_level,
                    "num_units_compared": int(len(mismatch)),
                    "baseline_target_units": int(len(baseline_target)),
                    "mode_target_units": int(len(mode_target)),
                    "shared_target_units": int(len(intersection)),
                    "target_jaccard_vs_baseline": float(len(intersection) / len(union)) if union else 1.0,
                    "target_precision_vs_baseline": float(len(intersection) / len(mode_target)) if mode_target else 0.0,
                    "target_recall_vs_baseline": float(len(intersection) / len(baseline_target)) if baseline_target else 0.0,
                    "quadrant_agreement_rate": quadrant_agreement_rate(baseline_mismatch, mismatch),
                }
            )

        candidate_space_specs = [
            (
                "weighted_all_cable",
                build_unit_physical_candidate_diversity(frame, "cable_id", "cable"),
                "cable",
            ),
            (
                "weighted_all_corridor",
                build_unit_physical_candidate_diversity(frame, corridor_candidate_col, "corridor"),
                "corridor",
            ),
            (
                "uniform_all_cable",
                build_unit_physical_feasible_set_diversity(frame, "cable_id", "cable"),
                "cable",
            ),
            (
                "uniform_all_corridor",
                build_unit_physical_feasible_set_diversity(frame, corridor_candidate_col, "corridor"),
                "corridor",
            ),
            (
                "weighted_strong_projection_cable",
                build_unit_physical_candidate_diversity(
                    strong_projection_frame if not strong_projection_frame.empty else frame.iloc[0:0],
                    "cable_id",
                    "cable",
                ),
                "cable",
            ),
            (
                "weighted_strong_projection_corridor",
                build_unit_physical_candidate_diversity(
                    strong_projection_frame if not strong_projection_frame.empty else frame.iloc[0:0],
                    corridor_candidate_col,
                    "corridor",
                ),
                "corridor",
            ),
            (
                "uniform_strong_projection_cable",
                build_unit_physical_feasible_set_diversity(
                    strong_projection_frame if not strong_projection_frame.empty else frame.iloc[0:0],
                    "cable_id",
                    "cable",
                ),
                "cable",
            ),
            (
                "uniform_strong_projection_corridor",
                build_unit_physical_feasible_set_diversity(
                    strong_projection_frame if not strong_projection_frame.empty else frame.iloc[0:0],
                    corridor_candidate_col,
                    "corridor",
                ),
                "corridor",
            ),
        ]
        candidate_space_results = [
            build_candidate_space_mode_result(
                mode_name=mode_name,
                physical_frame=physical_frame,
                physical_level=physical_level,
                network_frame=network_frame,
                network_definition=network_definition,
                network_score_column=network_score_column,
            )
            for mode_name, physical_frame, physical_level in candidate_space_specs
        ]
        candidate_space_baseline = next(result for result in candidate_space_results if result["mode"] == "weighted_all_corridor")
        baseline_physical_candidate_space = candidate_space_baseline["physical"]
        baseline_mismatch_candidate_space = candidate_space_baseline["mismatch"]
        baseline_target_candidate_space = target_unit_set(baseline_mismatch_candidate_space)

        for result in candidate_space_results:
            physical = result["physical"]
            mismatch = result["mismatch"]
            merged = baseline_physical_candidate_space.merge(
                physical,
                on="unit_id",
                suffixes=("_baseline", "_mode"),
                how="inner",
            )
            mode_target = target_unit_set(mismatch)
            intersection = baseline_target_candidate_space & mode_target
            union = baseline_target_candidate_space | mode_target
            if merged.empty:
                rank_corr = 0.0
            else:
                rank_corr = spearman_corr(
                    merged["physical_candidate_diversity_score_baseline"],
                    merged["physical_candidate_diversity_score_mode"],
                )
            candidate_space_rows.append(
                {
                    "network_definition": network_definition,
                    "setting": str(result["mode"]),
                    "weighting_view": "uniform" if str(result["mode"]).startswith("uniform") else "weighted",
                    "physical_level": str(result["physical_level"]),
                    "physical_projection_setting": infer_physical_projection_setting(str(result["mode"]), str(result["physical_level"])),
                    "projection_subset": infer_projection_subset(str(result["mode"])),
                    "num_units_compared": int(len(mismatch)),
                    "rank_corr_physical_diversity": rank_corr,
                    "target_quadrant_jaccard": float(len(intersection) / len(union)) if union else 1.0,
                    "target_quadrant_recall": float(len(intersection) / len(baseline_target_candidate_space)) if baseline_target_candidate_space else 0.0,
                    "quadrant_agreement_rate": quadrant_agreement_rate(baseline_mismatch_candidate_space, mismatch),
                    "baseline_setting": "weighted_all_corridor",
                }
            )

    robustness_summary = pd.DataFrame(robustness_rows).sort_values(["network_definition", "physical_level", "mode"])
    mismatch_stability = pd.DataFrame(stability_rows).sort_values(["network_definition", "physical_level", "mode"])
    quadrant_summary_frame = pd.concat(quadrant_summaries, ignore_index=True) if quadrant_summaries else pd.DataFrame()
    robustness_profile_table = (
        mismatch_stability.merge(
            robustness_summary[
                [
                    "network_definition",
                    "mode",
                    "physical_level",
                    "spearman_dominant_candidate_support_share",
                    "spearman_effective_num_candidates",
                ]
            ],
            on=["network_definition", "mode", "physical_level"],
            how="left",
        )
        .rename(
            columns={
                "mode": "setting",
                "spearman_dominant_candidate_support_share": "rank_corr_dominant_support",
                "spearman_effective_num_candidates": "rank_corr_effective_num",
                "target_jaccard_vs_baseline": "target_quadrant_jaccard",
                "target_recall_vs_baseline": "target_quadrant_recall",
            }
        )
        .assign(
            evidence_view=lambda df: df["setting"].map(infer_evidence_view),
            physical_projection_setting=lambda df: df.apply(
                lambda row: infer_physical_projection_setting(str(row["setting"]), str(row["physical_level"])),
                axis=1,
            ),
        )
    )
    robustness_profile_table["interpretation"] = robustness_profile_table.apply(build_robustness_interpretation, axis=1)
    robustness_profile_table = robustness_profile_table[
        [
            "network_definition",
            "setting",
            "evidence_view",
            "physical_level",
            "physical_projection_setting",
            "rank_corr_dominant_support",
            "rank_corr_effective_num",
            "target_quadrant_jaccard",
            "target_quadrant_recall",
            "quadrant_agreement_rate",
            "interpretation",
        ]
    ].sort_values(["network_definition", "physical_level", "setting"])

    robustness_summary_path = os.path.join(args.output, "robustness_summary.csv")
    mismatch_stability_path = os.path.join(args.output, "robustness_mismatch_stability.csv")
    quadrant_summary_path = os.path.join(args.output, "robustness_quadrant_summary.csv")
    robustness_profile_path = os.path.join(args.output, "robustness_profile_table.csv")
    candidate_space_path = os.path.join(args.output, "robustness_candidate_space.csv")
    candidate_space_frame = pd.DataFrame(candidate_space_rows).sort_values(
        ["network_definition", "projection_subset", "physical_level", "setting"]
    )

    conservative_rows: List[Dict[str, float]] = []
    projection_subsets = ["all", "strong_only", "strong_or_moderate"]
    baseline_physical = build_unit_physical_feasible_set_diversity(
        feasible_frame,
        feasible_corridor_candidate_col,
        "corridor",
    )
    baseline_upper = build_unit_network_physical_upper_bound_mismatch(
        network_frame,
        {"corridor": baseline_physical},
    )
    baseline_corridor = baseline_upper[
        (baseline_upper["network_definition"].astype(str) == PAPER_PRIMARY_NETWORK_DEFINITION)
        & (baseline_upper["physical_level"].astype(str) == "corridor")
    ].copy()
    baseline_target_units: Set[str] = set(
        baseline_corridor.loc[
            baseline_corridor.get("upper_bound_mismatch_category", pd.Series(dtype=object)).astype(str)
            == "network_high_physical_upper_low",
            "unit_id",
        ]
    )
    baseline_strict_units: Set[str] = set(
        baseline_corridor.loc[
            baseline_corridor.get("strict_upper_bound_mismatch_75_25", pd.Series(dtype=bool)).fillna(False).astype(bool),
            "unit_id",
        ]
    )
    baseline_categories = baseline_corridor[["unit_id", "upper_bound_mismatch_category"]].copy()
    if not baseline_categories.empty:
        baseline_categories["normalized_category"] = baseline_categories["upper_bound_mismatch_category"].astype(str).map(
            normalize_upper_bound_category
        )
    baseline_rank_gap = pd.Series(
        pd.to_numeric(
            baseline_corridor.get("network_physical_upper_bound_percentile_gap", pd.Series(dtype=float)),
            errors="coerce",
        ).fillna(0.0).values,
        index=baseline_corridor["unit_id"] if not baseline_corridor.empty else None,
        dtype=float,
    )

    for network_definition, network_score_column in NETWORK_DEFINITION_COLUMNS.items():
        for projection_subset in projection_subsets:
            weighted_subset = subset_by_projection(frame, projection_subset)
            feasible_subset = subset_by_projection(feasible_frame, projection_subset)

            for physical_level, candidate_col in [
                ("cable", "cable_id"),
                ("corridor", feasible_corridor_candidate_col),
            ]:
                if candidate_col not in feasible_subset.columns and physical_level == "corridor":
                    continue

                weighted_physical = build_unit_physical_candidate_diversity(
                    weighted_subset,
                    candidate_col,
                    physical_level,
                )
                weighted_mismatch = build_unit_network_physical_mismatch(
                    network_frame,
                    weighted_physical,
                    physical_level,
                    network_score_column=network_score_column,
                    network_definition=network_definition,
                )
                weighted_mismatch = merge_peeringdb_descriptors(weighted_mismatch, peeringdb_descriptors)

                conservative_physical = build_unit_physical_feasible_set_diversity(
                    feasible_subset,
                    candidate_col,
                    physical_level,
                )
                conservative_upper = build_unit_network_physical_upper_bound_mismatch(
                    network_frame,
                    {physical_level: conservative_physical},
                )
                conservative_mismatch = conservative_upper[
                    (conservative_upper["network_definition"].astype(str) == network_definition)
                    & (conservative_upper["physical_level"].astype(str) == physical_level)
                ].copy()
                conservative_mismatch = merge_peeringdb_descriptors(conservative_mismatch, peeringdb_descriptors)

                views = [
                    ("weighted_support", weighted_mismatch),
                    ("conservative_set", conservative_mismatch),
                ]
                for candidate_view, mismatch in views:
                    if candidate_view == "weighted_support":
                        target_units = set(
                            mismatch.loc[
                                mismatch.get("network_physical_mismatch_category", pd.Series(dtype=object)).astype(str)
                                == "network_high_physical_low",
                                "unit_id",
                            ]
                        )
                        network_percentile_series = numeric_series_or_default(mismatch, "network_diversity_percentile", 0.0)
                        physical_percentile_series = numeric_series_or_default(mismatch, "physical_diversity_percentile", 1.0)
                        strict_units = set(
                            mismatch.loc[
                                (network_percentile_series >= 0.75)
                                & (physical_percentile_series <= 0.25),
                                "unit_id",
                            ]
                        )
                        categories = mismatch[["unit_id", "network_physical_mismatch_category"]].copy() if not mismatch.empty else pd.DataFrame()
                        if not categories.empty:
                            categories["normalized_category"] = categories["network_physical_mismatch_category"].astype(str).map(normalize_upper_bound_category)
                        rank_gap = pd.to_numeric(
                            numeric_series_or_default(mismatch, "network_physical_percentile_gap", 0.0),
                            errors="coerce",
                        ).fillna(0.0)
                    else:
                        target_units = set(
                            mismatch.loc[
                                mismatch.get("upper_bound_mismatch_category", pd.Series(dtype=object)).astype(str)
                                == "network_high_physical_upper_low",
                                "unit_id",
                            ]
                        )
                        strict_units = set(
                            mismatch.loc[
                                mismatch.get("strict_upper_bound_mismatch_75_25", pd.Series(dtype=bool)).fillna(False).astype(bool),
                                "unit_id",
                            ]
                        )
                        categories = mismatch[["unit_id", "upper_bound_mismatch_category"]].copy() if not mismatch.empty else pd.DataFrame()
                        if not categories.empty:
                            categories["normalized_category"] = categories["upper_bound_mismatch_category"].astype(str).map(normalize_upper_bound_category)
                        rank_gap = pd.to_numeric(
                            numeric_series_or_default(mismatch, "network_physical_upper_bound_percentile_gap", 0.0),
                            errors="coerce",
                        ).fillna(0.0)

                    intersection = baseline_target_units & target_units
                    union = baseline_target_units | target_units
                    merged_categories = baseline_categories.merge(
                        categories[["unit_id", "normalized_category"]] if not categories.empty else pd.DataFrame(columns=["unit_id", "normalized_category"]),
                        on="unit_id",
                        how="inner",
                        suffixes=("_baseline", "_mode"),
                    )
                    if merged_categories.empty:
                        agreement_rate = 0.0
                    else:
                        agreement_rate = float(
                            (
                                merged_categories["normalized_category_baseline"].astype(str)
                                == merged_categories["normalized_category_mode"].astype(str)
                            ).mean()
                        )

                    if mismatch.empty or baseline_rank_gap.empty:
                        rank_gap_corr = 0.0
                    else:
                        current_gap = pd.Series(rank_gap.values, index=mismatch["unit_id"])
                        aligned = pd.DataFrame(
                            {
                                "baseline": baseline_rank_gap,
                                "current": current_gap,
                            }
                        ).dropna()
                        rank_gap_corr = spearman_corr(aligned["baseline"], aligned["current"]) if not aligned.empty else 0.0
                    peeringdb_context = summarize_peeringdb_context(mismatch)

                    conservative_rows.append(
                        {
                            "network_definition": network_definition,
                            "physical_level": physical_level,
                            "candidate_view": candidate_view,
                            "projection_subset": projection_subset,
                            "target_units": int(len(target_units)),
                            "strict_target_units": int(len(strict_units)),
                            "target_jaccard_vs_baseline": float(len(intersection) / len(union)) if union else 1.0,
                            "target_recall_vs_baseline": float(len(intersection) / len(baseline_target_units)) if baseline_target_units else 0.0,
                            "quadrant_agreement_rate": agreement_rate,
                            "rank_gap_spearman_vs_baseline": rank_gap_corr,
                            "pdb_country_coverage": peeringdb_context["pdb_country_coverage"],
                            "median_pdb_interconnection_footprint_percentile": peeringdb_context["median_pdb_interconnection_footprint_percentile"],
                            "dominant_pdb_interconnection_footprint_tier": peeringdb_context["dominant_pdb_interconnection_footprint_tier"],
                            "interpretation": build_conservative_audit_interpretation(
                                candidate_view,
                                physical_level,
                                projection_subset,
                                network_definition,
                            ),
                        }
                    )

    conservative_audit_path = os.path.join(args.output, "robustness_conservative_candidate_audit.csv")
    conservative_audit_frame = pd.DataFrame(conservative_rows).sort_values(
        ["network_definition", "physical_level", "candidate_view", "projection_subset"]
    )

    robustness_summary.to_csv(robustness_summary_path, index=False, encoding="utf-8-sig")
    mismatch_stability.to_csv(mismatch_stability_path, index=False, encoding="utf-8-sig")
    quadrant_summary_frame.to_csv(quadrant_summary_path, index=False, encoding="utf-8-sig")
    robustness_profile_table.to_csv(robustness_profile_path, index=False, encoding="utf-8-sig")
    candidate_space_frame.to_csv(candidate_space_path, index=False, encoding="utf-8-sig")
    conservative_audit_frame.to_csv(conservative_audit_path, index=False, encoding="utf-8-sig")

    chart_source = mismatch_stability[
        mismatch_stability["network_definition"] == PAPER_PRIMARY_NETWORK_DEFINITION
    ].copy()
    if chart_source.empty:
        chart_source = mismatch_stability[mismatch_stability["network_definition"] == "composite"].copy()
    if chart_source.empty:
        chart_source = mismatch_stability.copy()
    if not chart_source.empty:
        write_named_bar_svg(
            chart_source,
            os.path.join(args.output, "robustness_network_high_physical_low_stability.svg"),
            "Shared network_high_physical_low units vs fused_dual_core_cable baseline",
        )

    print(f"Saved robustness summary to {robustness_summary_path}")
    print(f"Saved mismatch stability summary to {mismatch_stability_path}")
    print(f"Saved robustness quadrant summary to {quadrant_summary_path}")
    print(f"Saved robustness profile table to {robustness_profile_path}")
    print(f"Saved candidate-space robustness table to {candidate_space_path}")
    print(f"Saved conservative candidate-audit robustness table to {conservative_audit_path}")


if __name__ == "__main__":
    main()
