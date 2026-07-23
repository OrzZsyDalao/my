"""Draw paper-facing boxplots from merged country-geography result tables."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.common import REPO_DIR  # noqa: E402


GEOGRAPHY_ORDER = [
    "coastal_mainland_or_mixed",
    "island_or_archipelagic",
    "landlocked",
]
GEOGRAPHY_LABELS = {
    "coastal_mainland_or_mixed": "Coastal mainland / mixed",
    "island_or_archipelagic": "Island / archipelagic",
    "landlocked": "Landlocked",
}
GEOGRAPHY_COLORS = {
    "coastal_mainland_or_mixed": "#176B87",
    "island_or_archipelagic": "#D97706",
    "landlocked": "#2F855A",
}


def parse_args() -> argparse.Namespace:
    """Parse input and output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = REPO_DIR / "output" / "public_traceroute_by_msmid"
    parser.add_argument(
        "--input",
        type=Path,
        default=default_root / "all_measurements_service_country_geography_concentration.csv",
    )
    parser.add_argument(
        "--paper-input",
        type=Path,
        default=default_root / "all_measurements_paper_service_country_geography_concentration.csv",
    )
    parser.add_argument("--output", type=Path, default=default_root)
    return parser.parse_args()


def finite_values(frame: pd.DataFrame, metric: str, geography_type: str) -> np.ndarray:
    """Return finite metric values for one operational geography type."""
    if metric not in frame.columns:
        return np.array([], dtype=float)
    values = pd.to_numeric(
        frame.loc[frame["country_geography_type"].eq(geography_type), metric],
        errors="coerce",
    ).to_numpy(dtype=float)
    return values[np.isfinite(values)]


def tukey_summary(values: np.ndarray) -> Dict[str, Any]:
    """Compute a standard Tukey boxplot summary without changing metric units."""
    if values.size == 0:
        return {
            "n": 0,
            "minimum": np.nan,
            "q1": np.nan,
            "median": np.nan,
            "q3": np.nan,
            "maximum": np.nan,
            "lower_whisker": np.nan,
            "upper_whisker": np.nan,
            "outlier_count": 0,
            "outliers": np.array([], dtype=float),
        }
    q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75])
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    inliers = values[(values >= lower_fence) & (values <= upper_fence)]
    outliers = values[(values < lower_fence) | (values > upper_fence)]
    return {
        "n": int(values.size),
        "minimum": float(values.min()),
        "q1": float(q1),
        "median": float(median),
        "q3": float(q3),
        "maximum": float(values.max()),
        "lower_whisker": float(inliers.min()) if inliers.size else float(q1),
        "upper_whisker": float(inliers.max()) if inliers.size else float(q3),
        "outlier_count": int(outliers.size),
        "outliers": np.sort(outliers),
    }


def metric_transform(value: float, scale: str) -> float:
    """Transform one value for drawing while retaining raw summary statistics."""
    if scale == "log1p":
        return math.log1p(max(float(value), 0.0))
    return float(value)


def axis_ticks(scale: str, summaries: Sequence[Dict[str, Any]]) -> List[tuple[float, str]]:
    """Return transformed tick positions and human-readable raw labels."""
    if scale == "rate":
        return [(value, f"{value:.2f}") for value in [0.0, 0.25, 0.5, 0.75, 1.0]]
    maximum = max(
        [float(summary.get("maximum", 0.0)) for summary in summaries if summary.get("n", 0)]
        or [1.0]
    )
    candidates = [0, 1, 3, 10, 30, 100, 300, 1000, 3000, 10000]
    selected = [value for value in candidates if value < maximum]
    upper_tick = next((value for value in candidates if value >= maximum), maximum)
    selected.append(upper_tick)
    return [(math.log1p(value), f"{value:g}") for value in selected]


def svg_text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 16,
    anchor: str = "start",
    weight: int = 400,
    fill: str = "#17313D",
) -> str:
    """Return one escaped SVG text element."""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Georgia, Segoe UI, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}">{escape(str(value))}</text>'
    )


def draw_panel(
    frame: pd.DataFrame,
    panel: Dict[str, Any],
    x: float,
    y: float,
    width: float,
    height: float,
    statistics_rows: List[Dict[str, Any]],
) -> List[str]:
    """Draw one geography-stratified Tukey boxplot panel."""
    metric = panel["metric"]
    scale = panel["scale"]
    summaries = [
        tukey_summary(finite_values(frame, metric, geography_type))
        for geography_type in GEOGRAPHY_ORDER
    ]
    plot_left = x + 78
    plot_right = x + width - 24
    plot_top = y + 64
    plot_bottom = y + height - 92
    ticks = axis_ticks(scale, summaries)
    transformed_ticks = [position for position, _ in ticks]
    y_min = 0.0
    y_max = max(transformed_ticks or [1.0])
    if scale == "rate":
        y_max = 1.0
    if y_max <= y_min:
        y_max = 1.0

    def y_position(raw_value: float) -> float:
        transformed = metric_transform(raw_value, scale)
        fraction = (transformed - y_min) / (y_max - y_min)
        return plot_bottom - max(0.0, min(1.0, fraction)) * (plot_bottom - plot_top)

    elements = [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
        'rx="10" fill="#FFFFFF" stroke="#CAD8DD"/>',
        svg_text(x + 22, y + 31, panel["title"], size=18, weight=500),
        svg_text(x + 22, y + 52, panel["subtitle"], size=12, fill="#526A75"),
    ]
    for tick_position, tick_label in ticks:
        tick_y = plot_bottom - (tick_position - y_min) / (y_max - y_min) * (plot_bottom - plot_top)
        elements.append(
            f'<line x1="{plot_left:.1f}" y1="{tick_y:.1f}" x2="{plot_right:.1f}" '
            f'y2="{tick_y:.1f}" stroke="#E4ECEF" stroke-width="1"/>'
        )
        elements.append(svg_text(plot_left - 10, tick_y + 5, tick_label, size=12, anchor="end", fill="#526A75"))

    category_width = (plot_right - plot_left) / len(GEOGRAPHY_ORDER)
    box_width = min(74.0, category_width * 0.42)
    for index, (geography_type, summary) in enumerate(zip(GEOGRAPHY_ORDER, summaries)):
        center_x = plot_left + category_width * (index + 0.5)
        color = GEOGRAPHY_COLORS[geography_type]
        label = GEOGRAPHY_LABELS[geography_type]
        elements.append(svg_text(center_x, plot_bottom + 27, label, size=12, anchor="middle"))
        elements.append(svg_text(center_x, plot_bottom + 47, f'n={summary["n"]}', size=11, anchor="middle", fill="#526A75"))
        statistics_rows.append(
            {
                "figure": panel["figure"],
                "analysis_population": panel["population"],
                "metric": metric,
                "metric_scale_in_figure": scale,
                "rate_source": panel.get("rate_source", "not_applicable"),
                "country_geography_type": geography_type,
                **{key: value for key, value in summary.items() if key != "outliers"},
            }
        )
        if summary["n"] == 0:
            elements.append(svg_text(center_x, (plot_top + plot_bottom) / 2, "no data", size=12, anchor="middle", fill="#7A8D95"))
            continue
        q1_y = y_position(summary["q1"])
        q3_y = y_position(summary["q3"])
        median_y = y_position(summary["median"])
        lower_y = y_position(summary["lower_whisker"])
        upper_y = y_position(summary["upper_whisker"])
        elements.extend(
            [
                f'<line x1="{center_x:.1f}" y1="{upper_y:.1f}" x2="{center_x:.1f}" y2="{q3_y:.1f}" stroke="{color}" stroke-width="2"/>',
                f'<line x1="{center_x:.1f}" y1="{q1_y:.1f}" x2="{center_x:.1f}" y2="{lower_y:.1f}" stroke="{color}" stroke-width="2"/>',
                f'<line x1="{center_x - box_width / 3:.1f}" y1="{upper_y:.1f}" x2="{center_x + box_width / 3:.1f}" y2="{upper_y:.1f}" stroke="{color}" stroke-width="2"/>',
                f'<line x1="{center_x - box_width / 3:.1f}" y1="{lower_y:.1f}" x2="{center_x + box_width / 3:.1f}" y2="{lower_y:.1f}" stroke="{color}" stroke-width="2"/>',
                f'<rect x="{center_x - box_width / 2:.1f}" y="{min(q1_y, q3_y):.1f}" width="{box_width:.1f}" height="{max(abs(q1_y - q3_y), 1.0):.1f}" fill="{color}" fill-opacity="0.24" stroke="{color}" stroke-width="2"/>',
                f'<line x1="{center_x - box_width / 2:.1f}" y1="{median_y:.1f}" x2="{center_x + box_width / 2:.1f}" y2="{median_y:.1f}" stroke="#17313D" stroke-width="3"/>',
            ]
        )
        outliers = summary["outliers"]
        if outliers.size > 80:
            sampled_indices = np.linspace(0, outliers.size - 1, 80).astype(int)
            outliers = outliers[sampled_indices]
        for outlier_index, outlier in enumerate(outliers):
            jitter = ((outlier_index % 9) - 4) * 2.1
            elements.append(
                f'<circle cx="{center_x + jitter:.1f}" cy="{y_position(float(outlier)):.1f}" r="2.4" '
                f'fill="{color}" fill-opacity="0.55"/>'
            )
    return elements


def write_boxplot_figure(
    path: Path,
    frame: pd.DataFrame,
    title: str,
    subtitle: str,
    panels: Sequence[Dict[str, Any]],
    statistics_rows: List[Dict[str, Any]],
) -> None:
    """Write a responsive SVG small-multiple boxplot figure."""
    panel_width = 740
    panel_height = 470
    columns = 2
    rows = math.ceil(len(panels) / columns)
    width = 1540
    height = 118 + rows * (panel_height + 28)
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(title)}</title>',
        f'<desc id="desc">{escape(subtitle)}</desc>',
        f'<rect width="{width}" height="{height}" fill="#F5F1E8"/>',
        svg_text(34, 42, title, size=27, weight=500),
        svg_text(34, 70, subtitle, size=14, fill="#526A75"),
        svg_text(34, 95, "Boxes show Q1–Q3; center line is median; whiskers use 1.5×IQR; dots are sampled outliers.", size=12, fill="#526A75"),
    ]
    for index, panel in enumerate(panels):
        panel_x = 30 + (index % columns) * (panel_width + 30)
        panel_y = 118 + (index // columns) * (panel_height + 28)
        elements.extend(draw_panel(frame, panel, panel_x, panel_y, panel_width, panel_height, statistics_rows))
    elements.append("</svg>")
    path.write_text("\n".join(elements) + "\n", encoding="utf-8")


def main() -> None:
    """Generate exposure, concentration, and observation-scale boxplot figures."""
    args = parse_args()
    full = pd.read_csv(args.input, low_memory=False)
    paper = pd.read_csv(args.paper_input, low_memory=False)
    args.output.mkdir(parents=True, exist_ok=True)
    statistics_rows: List[Dict[str, Any]] = []

    exposure_panels = []
    for rate_source, title in [
        ("legacy_service_physical_exposure_rate", "Legacy feasible-candidate exposure"),
        ("inter_region_candidate_exposure_rate", "Inter-region candidate exposure"),
    ]:
        exposure_panels.append(
            {
                "figure": "country_geography_candidate_exposure_boxplots",
                "population": "all_existing_service_country_units",
                "metric": "analysis_candidate_dependency_rate",
                "scale": "rate",
                "rate_source": rate_source,
                "title": title,
                "subtitle": "Rate source kept separate; values are candidate exposure, not observed cable use.",
            }
        )
    exposure_path = args.output / "country_geography_candidate_exposure_boxplots.svg"
    exposure_elements: List[str] = []
    for panel in exposure_panels:
        source_frame = full.loc[
            full["analysis_candidate_dependency_rate_source"].astype(str).eq(panel["rate_source"])
        ].copy()
        panel["source_frame"] = source_frame
    # Each exposure panel uses a different rate-source population.
    width = 1540
    height = 616
    exposure_elements.extend(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            '<title id="title">Country geography and feasible-candidate exposure</title>',
            '<desc id="desc">Separate Tukey boxplots for legacy and inter-region candidate-exposure rates.</desc>',
            f'<rect width="{width}" height="{height}" fill="#F5F1E8"/>',
            svg_text(34, 42, "Country geography and feasible-candidate exposure", size=27, weight=500),
            svg_text(34, 70, "Rate sources are separated because their exposure semantics are not interchangeable.", size=14, fill="#526A75"),
            svg_text(34, 95, "Boxes show Q1–Q3; center line is median; whiskers use 1.5×IQR; dots are sampled outliers.", size=12, fill="#526A75"),
        ]
    )
    for index, panel in enumerate(exposure_panels):
        exposure_elements.extend(
            draw_panel(
                panel.pop("source_frame"),
                panel,
                30 + index * 770,
                118,
                740,
                470,
                statistics_rows,
            )
        )
    exposure_elements.append("</svg>")
    exposure_path.write_text("\n".join(exposure_elements) + "\n", encoding="utf-8")

    concentration_panels = [
        {
            "figure": "country_geography_concentration_boxplots",
            "population": "auditable_paper_service_country_units",
            "metric": "top1_corridor_share",
            "scale": "rate",
            "title": "Top-1 feasible corridor share",
            "subtitle": "Higher values indicate stronger corridor-observation concentration.",
        },
        {
            "figure": "country_geography_concentration_boxplots",
            "population": "auditable_paper_service_country_units",
            "metric": "effective_corridor_count",
            "scale": "log1p",
            "title": "Effective feasible corridor count",
            "subtitle": "Raw counts shown on a log1p axis; lower values indicate narrower concentration.",
        },
        {
            "figure": "country_geography_concentration_boxplots",
            "population": "auditable_paper_service_country_units",
            "metric": "effective_network_transition_count",
            "scale": "log1p",
            "title": "Effective network-transition count",
            "subtitle": "Network-side concentration over the comparable segment population.",
        },
        {
            "figure": "country_geography_concentration_boxplots",
            "population": "auditable_paper_service_country_units",
            "metric": "top3_corridor_share",
            "scale": "rate",
            "title": "Top-3 feasible corridor share",
            "subtitle": "Cumulative observation mass assigned to the three leading corridor candidates.",
        },
    ]
    write_boxplot_figure(
        args.output / "country_geography_concentration_boxplots.svg",
        paper,
        "Country geography and cross-layer concentration",
        "Auditable service-country units only; physical metrics describe feasible corridor candidates.",
        concentration_panels,
        statistics_rows,
    )

    sampling_panels = [
        {
            "figure": "country_geography_sampling_boxplots",
            "population": "all_existing_service_country_units",
            "metric": metric,
            "scale": "log1p",
            "title": title,
            "subtitle": subtitle,
        }
        for metric, title, subtitle in [
            ("total_valid_traces", "Valid traceroute observations", "Raw counts on a log1p axis."),
            ("mappable_traces", "Mappable traceroute observations", "Raw counts on a log1p axis."),
            ("unique_probes", "Unique RIPE Atlas probes", "Per existing service-country result row."),
            ("unique_probe_asns", "Unique probe ASNs", "Per existing service-country result row."),
        ]
    ]
    write_boxplot_figure(
        args.output / "country_geography_sampling_boxplots.svg",
        full,
        "Country geography and measurement coverage",
        "Coverage distributions contextualize concentration differences and sample-size imbalance.",
        sampling_panels,
        statistics_rows,
    )

    statistics_path = args.output / "country_geography_boxplot_statistics.csv"
    pd.DataFrame(statistics_rows).to_csv(statistics_path, index=False, encoding="utf-8-sig")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(args.input.resolve().relative_to(REPO_DIR)),
        "paper_input": str(args.paper_input.resolve().relative_to(REPO_DIR)),
        "country_geography_types_plotted": GEOGRAPHY_ORDER,
        "excluded_from_main_figures": ["unknown"],
        "boxplot_definition": "Tukey: Q1-Q3 box, median line, whiskers within 1.5 IQR",
        "rate_source_policy": "legacy and inter-region candidate-exposure rates are shown in separate panels",
        "interpretation_boundary": (
            "measurement-observed feasible-candidate statistics, not traffic volume, actual cable use, "
            "causal geography effects, or national resilience ground truth"
        ),
        "outputs": [
            exposure_path.name,
            "country_geography_concentration_boxplots.svg",
            "country_geography_sampling_boxplots.svg",
            statistics_path.name,
        ],
    }
    manifest_path = args.output / "country_geography_boxplot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"statistics_rows": len(statistics_rows), **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
