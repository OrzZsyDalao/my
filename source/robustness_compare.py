import argparse
import os
from typing import Dict, List, Set

import numpy as np
import pandas as pd

try:
    from source.postprocess_candidate_output import (
        TARGET_MISMATCH_CATEGORY,
        NETWORK_DEFINITION_COLUMNS,
        build_quadrant_summary,
        build_unit_network_layer_diversity,
        build_unit_network_physical_mismatch,
        build_unit_physical_candidate_diversity,
        ensure_corridor_columns,
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
        build_quadrant_summary,
        build_unit_network_layer_diversity,
        build_unit_network_physical_mismatch,
        build_unit_physical_candidate_diversity,
        ensure_corridor_columns,
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
    return "custom"


def infer_physical_projection_setting(setting: str, physical_level: str) -> str:
    """Map a setting to a paper-facing physical projection label."""
    if str(physical_level) == "corridor" or setting.endswith("_corridor"):
        return "corridor_grouped_candidates"
    return "cable_candidates"


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


def main() -> None:
    """Compare evidence settings and their network-physical mismatch stability."""
    args = parse_args()
    os.makedirs(args.output, exist_ok=True)

    frame = pd.read_csv(args.input)
    if frame.empty:
        raise ValueError("Input trace_candidate_support.csv is empty.")

    frame["geo_spatial_score"] = frame["geo_spatial_score"].fillna(0.0)
    frame["as_economic_score"] = frame["as_economic_score"].fillna(0.0)
    frame["normalized_candidate_support"] = frame["normalized_candidate_support"].fillna(0.0)
    frame = ensure_corridor_columns(frame)
    corridor_candidate_col = resolve_corridor_candidate_column(frame)

    network_frame = build_unit_network_layer_diversity(frame)
    geo_frame = normalize_within_links(frame, "geo_spatial_score", "geo_only_support")
    as_frame = normalize_within_links(frame, "as_economic_score", "as_only_support")
    high_conf_frame = frame[
        (frame["confidence_bucket"] == "high") | (frame["core_agreement"] == "dual_core_agreement")
    ].copy()

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

    robustness_summary.to_csv(robustness_summary_path, index=False, encoding="utf-8-sig")
    mismatch_stability.to_csv(mismatch_stability_path, index=False, encoding="utf-8-sig")
    quadrant_summary_frame.to_csv(quadrant_summary_path, index=False, encoding="utf-8-sig")
    robustness_profile_table.to_csv(robustness_profile_path, index=False, encoding="utf-8-sig")

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


if __name__ == "__main__":
    main()
