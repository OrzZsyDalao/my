"""Cluster-aware uncertainty analysis for the paper's Layer Agreement result.

The script reads the already-generated country--measurement summaries.  It does
not rerun traceroute collection or corridor projection.  Countries are the
clusters because geography is assigned at the country level and each country
can contribute multiple measurement units.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


SEED = 20260919
BOOTSTRAP_REPLICATES = 50_000
PERMUTATION_REPLICATES = 100_000
SERVICE_MEASUREMENT_IDS = {
    5001,
    5004,
    5005,
    5006,
    5008,
    5009,
    5010,
    5011,
    5012,
    5013,
    5014,
    5015,
    5016,
    86710103,
    176906957,
    176517335,
}
GROUPS = ("island_or_archipelagic", "coastal_mainland_or_mixed")


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman's rho with average ranks for ties."""

    xr = pd.Series(x).rank(method="average").to_numpy(dtype=float)
    yr = pd.Series(y).rank(method="average").to_numpy(dtype=float)
    if xr.size < 3 or np.isclose(xr.std(), 0) or np.isclose(yr.std(), 0):
        return float("nan")
    return float(np.corrcoef(xr, yr)[0, 1])


def load_units(repo_root: Path) -> pd.DataFrame:
    frozen = repo_root / "results" / "july1_public_atlas_20260701"
    result_root = repo_root / "output" / "public_traceroute_by_msmid"
    units = pd.read_csv(frozen / "paper_primary" / "paper_primary_units.csv")
    units = units.loc[units["msm_id"].isin(SERVICE_MEASUREMENT_IDS)].copy()
    units["measurement_id"] = units["msm_id"]
    geography = pd.read_csv(
        result_root / "all_measurements_country_geography_catalog_resolved.csv"
    )
    units = units.merge(geography, on="probe_country", how="left", validate="many_to_one")
    units = units.loc[units["country_geography_type"].isin(GROUPS)].copy()
    units = units[
        [
            "probe_country",
            "measurement_id",
            "service_id",
            "country_geography_type",
            "top2_network_transition_share",
            "top2_corridor_share",
        ]
    ].sort_values(["country_geography_type", "probe_country", "measurement_id"])
    units.reset_index(drop=True, inplace=True)
    return units


def group_rho(frame: pd.DataFrame) -> float:
    return spearman(
        frame["top2_network_transition_share"].to_numpy(dtype=float),
        frame["top2_corridor_share"].to_numpy(dtype=float),
    )


def resample_countries(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    country_frames = {country: rows for country, rows in frame.groupby("probe_country")}
    countries = np.array(sorted(country_frames))
    sampled = rng.choice(countries, size=len(countries), replace=True)
    return pd.concat([country_frames[country] for country in sampled], ignore_index=True)


def percentile_interval(values: list[float]) -> list[float]:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    return [float(v) for v in np.percentile(clean, [2.5, 97.5])]


def main() -> None:
    workspace = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[3]
    result_dir = workspace / "analysis" / "results"
    result_dir.mkdir(parents=True, exist_ok=True)

    units = load_units(repo_root)
    by_group = {
        group: units.loc[units["country_geography_type"] == group].copy()
        for group in GROUPS
    }
    observed = {group: group_rho(frame) for group, frame in by_group.items()}
    observed_difference = observed[GROUPS[0]] - observed[GROUPS[1]]

    rng = np.random.default_rng(SEED)
    bootstrap = {group: [] for group in GROUPS}
    bootstrap_difference: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        replicate = {
            group: group_rho(resample_countries(frame, rng))
            for group, frame in by_group.items()
        }
        for group in GROUPS:
            bootstrap[group].append(replicate[group])
        bootstrap_difference.append(replicate[GROUPS[0]] - replicate[GROUPS[1]])

    country_group = (
        units[["probe_country", "country_geography_type"]]
        .drop_duplicates()
        .set_index("probe_country")["country_geography_type"]
    )
    countries = country_group.index.to_numpy()
    island_country_count = int((country_group == GROUPS[0]).sum())
    country_rows = {
        country: units.loc[units["probe_country"] == country]
        for country in countries
    }
    at_least_as_extreme = 0
    valid_permutations = 0
    for _ in range(PERMUTATION_REPLICATES):
        shuffled = rng.permutation(countries)
        island_countries = set(shuffled[:island_country_count])
        island = pd.concat([country_rows[c] for c in island_countries], ignore_index=True)
        coastal = pd.concat(
            [country_rows[c] for c in countries if c not in island_countries],
            ignore_index=True,
        )
        difference = group_rho(island) - group_rho(coastal)
        if np.isfinite(difference):
            valid_permutations += 1
            if abs(difference) >= abs(observed_difference):
                at_least_as_extreme += 1
    permutation_p = (at_least_as_extreme + 1) / (valid_permutations + 1)

    summary = {
        "input_scope": "272 non-landlocked service-facing units; frozen equal-share 30-km outputs",
        "allocation": "equal_share",
        "cluster": "probe_country",
        "seed": SEED,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "permutation_replicates": PERMUTATION_REPLICATES,
        "groups": {
            group: {
                "units": int(len(frame)),
                "countries": int(frame["probe_country"].nunique()),
                "rho": observed[group],
                "cluster_bootstrap_95_percent_ci": percentile_interval(bootstrap[group]),
            }
            for group, frame in by_group.items()
        },
        "difference_island_minus_coastal": {
            "estimate": observed_difference,
            "cluster_bootstrap_95_percent_ci": percentile_interval(
                bootstrap_difference
            ),
            "country_label_permutation_two_sided_p": permutation_p,
            "valid_permutations": valid_permutations,
        },
        "interpretation": (
            "The resampling unit is country because geography is a country-level "
            "attribute. The permutation p-value is a descriptive randomization "
            "reference for the difference in rho, not evidence of a causal "
            "geographic mechanism."
        ),
    }

    units.to_csv(result_dir / "layer_agreement_units.csv", index=False)
    (result_dir / "layer_agreement_inference.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
