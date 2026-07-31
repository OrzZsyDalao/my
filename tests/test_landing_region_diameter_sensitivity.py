import inspect
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from pipeline.common import DEFAULT_EXPERIMENT_CONFIG
from pipeline.run_landing_region_diameter_sensitivity import (
    BASELINE_DIAMETER_KM,
    DEFAULT_OUTPUT_ROOT,
    DIAMETERS_KM,
    validate_summary,
)
from main_analysis import CableMatcher
from postprocess_candidate_output import (
    DEFAULT_LANDING_REGION_MAXIMUM_DIAMETER_KM,
)


def test_paper_default_landing_region_diameter_is_30_km() -> None:
    """Stage 1, post-processing, and experiment config must share the default."""
    matcher_default = inspect.signature(CableMatcher).parameters[
        "landing_region_maximum_diameter_km"
    ].default
    assert matcher_default == 30.0
    assert DEFAULT_LANDING_REGION_MAXIMUM_DIAMETER_KM == 30.0
    assert (
        DEFAULT_EXPERIMENT_CONFIG["landing_region_maximum_diameter_km"]
        == 30.0
    )


def test_dedicated_diameter_grid_is_isolated_and_complete() -> None:
    """The new grid must not overlap the historical sensitivity directory."""
    assert DIAMETERS_KM == (10, 20, 30, 40, 50)
    assert BASELINE_DIAMETER_KM == 30
    assert DEFAULT_OUTPUT_ROOT.name == (
        "sensitivity_landing_region_diameter_30km_baseline"
    )


def test_diameter_summary_validation_accepts_five_consistent_rows() -> None:
    """Five unique settings with normalized shares satisfy hard assertions."""
    frame = pd.DataFrame(
        [
            {
                "setting": f"diameter{diameter}",
                "landing_region_maximum_diameter_km": diameter,
                "single_corridor_segment_count": 8,
                "bounded_multi_corridor_segment_count": 2,
                "candidate_bearing_segment_count": 10,
                "single_corridor_share_among_candidate_bearing_segments": 0.8,
                "bounded_multi_corridor_share_among_candidate_bearing_segments": 0.2,
                "exact_candidate_set_jaccard_mean": 1.0,
                "classification_agreement_rate": 1.0,
            }
            for diameter in DIAMETERS_KM
        ]
    )
    validate_summary(frame)
