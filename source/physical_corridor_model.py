"""Deterministic landing-region and physical-corridor metadata helpers.

The model groups nearby landing stations without single-linkage chaining:
every automatically generated region has a diameter no greater than the
configured maximum diameter. Corridors remain candidate groupings between landing
regions; they do not assert route-level cable parallelism or shared risk.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

import pandas as pd


EARTH_RADIUS_KM = 6371.0


def haversine_km(point_a: Tuple[float, float], point_b: Tuple[float, float]) -> float:
    """Return the great-circle distance between latitude/longitude points."""
    lat_a, lon_a = math.radians(point_a[0]), math.radians(point_a[1])
    lat_b, lon_b = math.radians(point_b[0]), math.radians(point_b[1])
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    term = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return float(2.0 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(term))))


@dataclass(frozen=True)
class LandingRegionModel:
    """Resolved landing-region membership and labels."""

    station_to_region: Dict[str, str]
    region_labels: Dict[str, str]
    assignment_methods: Dict[str, str]
    coordinates: Dict[str, Tuple[float, float]]
    station_names: Dict[str, str]
    maximum_diameter_km: float
    clustering_method: str = "diameter_limited_complete_link_greedy"

    @property
    def radius_km(self) -> float:
        """Return the deprecated maximum-diameter compatibility alias."""
        return self.maximum_diameter_km


def load_landing_station_geo(path: str | Path) -> Tuple[Dict[str, Tuple[float, float]], Dict[str, str]]:
    """Load landing-station coordinates and human-readable names from GeoJSON."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    coordinates: Dict[str, Tuple[float, float]] = {}
    names: Dict[str, str] = {}
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        station_id = str(properties.get("id") or "").strip()
        geometry = feature.get("geometry", {})
        raw_coordinates = geometry.get("coordinates") or []
        if not station_id or len(raw_coordinates) < 2:
            continue
        lon, lat = raw_coordinates[:2]
        coordinates[station_id] = (float(lat), float(lon))
        names[station_id] = str(properties.get("name") or station_id)
    return coordinates, names


def _content_region_id(members: Sequence[str]) -> str:
    digest = hashlib.sha1("|".join(sorted(members)).encode("utf-8")).hexdigest()[:12]
    return f"landing_region_{digest}"


def _representative_station(
    members: Sequence[str],
    coordinates: Mapping[str, Tuple[float, float]],
) -> str:
    """Choose the member nearest the cluster centroid for a readable label."""
    mean_lat = sum(coordinates[item][0] for item in members) / len(members)
    mean_lon = sum(coordinates[item][1] for item in members) / len(members)
    return min(
        members,
        key=lambda item: (
            haversine_km(coordinates[item], (mean_lat, mean_lon)),
            item,
        ),
    )


def build_diameter_limited_landing_regions(
    coordinates: Mapping[str, Tuple[float, float]],
    station_names: Mapping[str, str],
    maximum_diameter_km: float | None = None,
    overrides: Mapping[str, Mapping[str, str]] | None = None,
    *,
    radius_km: float | None = None,
) -> LandingRegionModel:
    """Build deterministic landing regions with a hard maximum diameter.

    Stations are processed in geographic order and assigned to the closest
    existing cluster only when they remain within ``maximum_diameter_km`` of
    every member.
    This prevents the unbounded chain effect of single-linkage connected
    components while keeping the implementation dependency-light.
    """
    if (
        maximum_diameter_km is not None
        and radius_km is not None
        and not math.isclose(maximum_diameter_km, radius_km)
    ):
        raise ValueError(
            "maximum_diameter_km conflicts with deprecated radius_km"
        )
    maximum_diameter_km = (
        maximum_diameter_km
        if maximum_diameter_km is not None
        else radius_km
    )
    if maximum_diameter_km is None:
        raise ValueError("maximum_diameter_km is required")
    overrides = overrides or {}
    automatic_stations = [
        station_id for station_id in coordinates if station_id not in overrides
    ]
    automatic_stations.sort(
        key=lambda station_id: (
            coordinates[station_id][0],
            coordinates[station_id][1],
            station_id,
        )
    )
    clusters: List[List[str]] = []
    for station_id in automatic_stations:
        eligible: List[Tuple[float, str, int]] = []
        for cluster_index, members in enumerate(clusters):
            distances = [
                haversine_km(coordinates[station_id], coordinates[member])
                for member in members
            ]
            maximum_distance = max(distances)
            if maximum_distance <= float(maximum_diameter_km) + 1e-9:
                eligible.append((maximum_distance, min(members), cluster_index))
        if eligible:
            _, _, selected_index = min(eligible)
            clusters[selected_index].append(station_id)
        else:
            clusters.append([station_id])

    station_to_region: Dict[str, str] = {}
    region_labels: Dict[str, str] = {}
    assignment_methods: Dict[str, str] = {}
    for members in clusters:
        region_id = _content_region_id(members)
        representative = _representative_station(members, coordinates)
        region_labels[region_id] = station_names.get(representative, representative)
        for station_id in members:
            station_to_region[station_id] = region_id
            assignment_methods[station_id] = "diameter_limited_complete_link_greedy"

    for station_id, override in sorted(overrides.items()):
        if station_id not in coordinates:
            continue
        region_id = str(
            override.get("landing_region_id") or override.get("region_id") or ""
        ).strip()
        if not region_id:
            continue
        station_to_region[station_id] = region_id
        region_labels[region_id] = str(
            override.get("landing_region_name")
            or override.get("region_name")
            or region_id
        )
        assignment_methods[station_id] = "manual_override"

    return LandingRegionModel(
        station_to_region=station_to_region,
        region_labels=region_labels,
        assignment_methods=assignment_methods,
        coordinates=dict(coordinates),
        station_names=dict(station_names),
        maximum_diameter_km=float(maximum_diameter_km),
    )


def region_diameter_km(
    members: Sequence[str],
    coordinates: Mapping[str, Tuple[float, float]],
) -> float:
    """Return the maximum pairwise distance within one landing region."""
    if len(members) < 2:
        return 0.0
    return max(
        haversine_km(coordinates[left], coordinates[right])
        for left, right in itertools.combinations(members, 2)
    )


def build_landing_region_summary(model: LandingRegionModel) -> pd.DataFrame:
    """Build one diagnostic row per landing region."""
    members_by_region: Dict[str, List[str]] = {}
    for station_id, region_id in model.station_to_region.items():
        members_by_region.setdefault(region_id, []).append(station_id)
    rows: List[Dict[str, Any]] = []
    for region_id, members in sorted(members_by_region.items()):
        members = sorted(members)
        diameter = region_diameter_km(members, model.coordinates)
        methods = sorted({model.assignment_methods.get(item, "unknown") for item in members})
        rows.append(
            {
                "landing_region_id": region_id,
                "landing_region_label": model.region_labels.get(region_id, region_id),
                "landing_station_count": len(members),
                "region_diameter_km": diameter,
                "configured_maximum_diameter_km": model.maximum_diameter_km,
                "diameter_within_configured_maximum": bool(
                    diameter <= model.maximum_diameter_km + 1e-9
                    or "manual_override" in methods
                ),
                # Deprecated compatibility aliases.
                "configured_radius_km": model.maximum_diameter_km,
                "diameter_within_configured_radius": bool(
                    diameter <= model.maximum_diameter_km + 1e-9
                    or "manual_override" in methods
                ),
                "region_assignment_methods": json.dumps(methods),
                "landing_station_ids": json.dumps(members),
            }
        )
    return pd.DataFrame(rows)


def load_cable_exact_pairs(
    cable_dir: str | Path,
) -> Tuple[Dict[Tuple[str, str], set[str]], Dict[str, str]]:
    """Load metadata-level cable membership for each unordered exact landing pair."""
    pair_to_cables: Dict[Tuple[str, str], set[str]] = {}
    cable_names: Dict[str, str] = {}
    for path in sorted(Path(cable_dir).glob("*.json")):
        if path.name == "landing-point-geo.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        cable_id = str(payload.get("id") or path.stem).strip()
        points = sorted(
            {
                str(item.get("id")).strip()
                for item in payload.get("landing_points", [])
                if item.get("id")
            }
        )
        if len(points) < 2:
            continue
        cable_names[cable_id] = str(payload.get("name") or cable_id)
        for left, right in itertools.combinations(points, 2):
            pair_to_cables.setdefault((left, right), set()).add(cable_id)
    return pair_to_cables, cable_names


def _cable_pair_relationships(cable_ids: Iterable[str]) -> set[Tuple[str, str]]:
    return {
        tuple(sorted((left, right)))
        for left, right in itertools.combinations(sorted(set(cable_ids)), 2)
    }


def build_corridor_structure_tables(
    model: LandingRegionModel,
    cable_dir: str | Path,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Build exact-pair, corridor, and strict-vs-co-group diagnostics."""
    pair_to_cables, cable_names = load_cable_exact_pairs(cable_dir)
    exact_rows: List[Dict[str, Any]] = []
    corridor_exact_pairs: Dict[str, set[str]] = {}
    corridor_cables: Dict[str, set[str]] = {}
    corridor_labels: Dict[str, str] = {}
    strict_relationships: set[Tuple[str, str]] = set()

    for (left, right), cable_ids in sorted(pair_to_cables.items()):
        if left not in model.station_to_region or right not in model.station_to_region:
            continue
        region_left = model.station_to_region[left]
        region_right = model.station_to_region[right]
        region_pair = tuple(sorted((region_left, region_right)))
        corridor_id = "::".join(region_pair)
        exact_pair_id = "::".join(sorted((left, right)))
        if region_pair[0] == region_pair[1]:
            corridor_label = f"{model.region_labels.get(region_pair[0], region_pair[0])} intra-region"
            candidate_scope = "intra_landing_region"
        else:
            corridor_label = " <-> ".join(
                model.region_labels.get(region_id, region_id) for region_id in region_pair
            )
            candidate_scope = "inter_region"
        strict_pairs = _cable_pair_relationships(cable_ids)
        strict_relationships.update(strict_pairs)
        corridor_exact_pairs.setdefault(corridor_id, set()).add(exact_pair_id)
        corridor_cables.setdefault(corridor_id, set()).update(cable_ids)
        corridor_labels[corridor_id] = corridor_label
        exact_rows.append(
            {
                "exact_landing_pair_id": exact_pair_id,
                "landing_station_a_id": left,
                "landing_station_a_name": model.station_names.get(left, left),
                "landing_station_b_id": right,
                "landing_station_b_name": model.station_names.get(right, right),
                "corridor_id": corridor_id,
                "corridor_label": corridor_label,
                "candidate_scope": candidate_scope,
                "cable_count": len(cable_ids),
                "cable_ids": json.dumps(sorted(cable_ids)),
                "cable_names": json.dumps(
                    sorted(cable_names.get(item, item) for item in cable_ids)
                ),
                "strict_parallel_candidate": len(cable_ids) > 1,
                "strict_parallel_cable_pair_relationships": len(strict_pairs),
            }
        )

    corridor_rows: List[Dict[str, Any]] = []
    corridor_relationships: set[Tuple[str, str]] = set()
    for corridor_id, cable_ids in sorted(corridor_cables.items()):
        co_group_pairs = _cable_pair_relationships(cable_ids)
        corridor_relationships.update(co_group_pairs)
        exact_ids = corridor_exact_pairs[corridor_id]
        strict_in_corridor: set[Tuple[str, str]] = set()
        for exact_id in exact_ids:
            pair = tuple(exact_id.split("::", 1))
            strict_in_corridor.update(_cable_pair_relationships(pair_to_cables[pair]))
        corridor_rows.append(
            {
                "corridor_id": corridor_id,
                "corridor_label": corridor_labels[corridor_id],
                "corridor_type": "landing_region_pair",
                "exact_landing_pair_count": len(exact_ids),
                "cable_count": len(cable_ids),
                "cable_ids": json.dumps(sorted(cable_ids)),
                "corridor_cogroup_cable_pair_relationships": len(co_group_pairs),
                "strict_parallel_cable_pair_relationships": len(strict_in_corridor),
                "strict_share_of_corridor_cogroup_relationships": (
                    len(strict_in_corridor) / len(co_group_pairs)
                    if co_group_pairs
                    else 0.0
                ),
                "interpretation": (
                    "landing-region corridor candidate group; not confirmed route-level parallelism"
                ),
            }
        )

    overlap = strict_relationships & corridor_relationships
    union = strict_relationships | corridor_relationships
    relationship_rows = [
        {
            "strict_parallel_candidate_relationships": len(strict_relationships),
            "corridor_cogroup_relationships": len(corridor_relationships),
            "overlap_relationships": len(overlap),
            "strict_relationship_covered_by_corridor_share": (
                len(overlap) / len(strict_relationships)
                if strict_relationships
                else math.nan
            ),
            "corridor_cogroup_relationship_strict_share": (
                len(overlap) / len(corridor_relationships)
                if corridor_relationships
                else math.nan
            ),
            "relationship_jaccard": len(overlap) / len(union) if union else math.nan,
            "strict_definition": (
                "two distinct cable IDs share an exact unordered landing-station pair"
            ),
            "corridor_cogroup_definition": (
                "two distinct cable IDs occur in the same unordered landing-region pair"
            ),
            "interpretation_boundary": (
                "both are metadata-level candidate relationships, not route-geometry proof"
            ),
        }
    ]

    region_summary = build_landing_region_summary(model)
    report = {
        "clustering_method": model.clustering_method,
        "configured_maximum_diameter_km": model.maximum_diameter_km,
        "configured_radius_km": model.maximum_diameter_km,
        "landing_station_count": len(model.station_to_region),
        "landing_region_count": int(region_summary["landing_region_id"].nunique()),
        "region_size_distribution": describe_numeric(
            region_summary["landing_station_count"].tolist()
        ),
        "region_diameter_km_distribution": describe_numeric(
            region_summary["region_diameter_km"].tolist()
        ),
        "exact_landing_pair_count": len(exact_rows),
        "corridor_count": len(corridor_rows),
        "cables_per_corridor_distribution": describe_numeric(
            [row["cable_count"] for row in corridor_rows]
        ),
        "strict_parallel_vs_corridor_cogroup": relationship_rows[0],
        "interpretation": (
            "Corridors are diameter-limited landing-region-pair candidate groups. "
            "They are not confirmed physical parallel-cable routes."
        ),
    }
    return (
        pd.DataFrame(exact_rows),
        pd.DataFrame(corridor_rows),
        pd.DataFrame(relationship_rows),
        report,
    )


def describe_numeric(values: Sequence[float]) -> Dict[str, float]:
    """Return a compact numeric distribution summary."""
    series = pd.to_numeric(pd.Series(list(values), dtype=float), errors="coerce").dropna()
    if series.empty:
        return {
            "count": 0,
            "min": math.nan,
            "p25": math.nan,
            "median": math.nan,
            "p75": math.nan,
            "p95": math.nan,
            "max": math.nan,
            "mean": math.nan,
        }
    return {
        "count": int(len(series)),
        "min": float(series.min()),
        "p25": float(series.quantile(0.25)),
        "median": float(series.median()),
        "p75": float(series.quantile(0.75)),
        "p95": float(series.quantile(0.95)),
        "max": float(series.max()),
        "mean": float(series.mean()),
    }


def write_corridor_structure_outputs(
    output_dir: str | Path,
    model: LandingRegionModel,
    cable_dir: str | Path,
) -> Dict[str, Any]:
    """Write corrected landing-region and corridor diagnostics."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    region_summary = build_landing_region_summary(model)
    exact_pairs, corridors, overlap, report = build_corridor_structure_tables(
        model,
        cable_dir,
    )
    station_rows = [
        {
            "landing_station_id": station_id,
            "landing_station_name": model.station_names.get(station_id, station_id),
            "landing_region_id": region_id,
            "landing_region_label": model.region_labels.get(region_id, region_id),
            "latitude": model.coordinates[station_id][0],
            "longitude": model.coordinates[station_id][1],
            "region_assignment_method": model.assignment_methods.get(
                station_id,
                "unknown",
            ),
        }
        for station_id, region_id in sorted(model.station_to_region.items())
    ]
    pd.DataFrame(station_rows).to_csv(
        output_path / "landing_region_catalog.csv",
        index=False,
        encoding="utf-8-sig",
    )
    region_summary.to_csv(
        output_path / "landing_region_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    exact_pairs.to_csv(
        output_path / "exact_landing_pair_catalog.csv",
        index=False,
        encoding="utf-8-sig",
    )
    corridors.to_csv(
        output_path / "corridor_catalog.csv",
        index=False,
        encoding="utf-8-sig",
    )
    overlap.to_csv(
        output_path / "corridor_parallel_relationship_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (output_path / "physical_corridor_structure_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report
