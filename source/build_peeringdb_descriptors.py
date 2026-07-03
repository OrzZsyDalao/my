"""Build country-level PeeringDB interconnection footprint descriptors from local dump files."""

import argparse
import json
import math
import os
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np
import pandas as pd


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else "."
BASE_DIR = os.path.dirname(SOURCE_DIR)
DEFAULT_INPUT_DIR = os.path.join(BASE_DIR, "data", "peeringdb")
DEFAULT_OUTPUT = os.path.join(BASE_DIR, "output", "result", "country_peeringdb_descriptors.csv")
SUPPORTED_FILES = ["ix.json", "fac.json", "net.json", "netfac.json", "netixlan.json"]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Build country-level PeeringDB interconnection descriptors from local dump files.")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="Directory containing local PeeringDB JSON dump files.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output CSV path.")
    return parser.parse_args()


def shannon_entropy(values: Iterable[float]) -> float:
    """Compute Shannon entropy for a non-negative count sequence."""
    array = np.asarray([float(value) for value in values if float(value) > 0], dtype=float)
    if array.size == 0:
        return 0.0
    total = array.sum()
    if total <= 0:
        return 0.0
    probs = array / total
    return float(-(probs * np.log(probs)).sum())


def normalize_country(value: Any) -> str:
    """Normalize a country-like value to uppercase ISO-style text when possible."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text.upper()


def coerce_int(value: Any) -> int:
    """Convert a scalar-like value to integer with graceful fallback."""
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return int(numeric) if pd.notna(numeric) else -1


def first_present(row: Dict[str, Any], keys: Sequence[str], default: Any = "") -> Any:
    """Return the first non-empty key present in a JSON-like row."""
    for key in keys:
        if key in row:
            value = row.get(key)
            if value not in (None, "", []):
                return value
    return default


def extract_records(payload: Any, resource_name: str) -> List[Dict[str, Any]]:
    """Extract a flat record list from different PeeringDB dump shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return [item for item in payload["data"] if isinstance(item, dict)]
        if isinstance(payload.get(resource_name), list):
            return [item for item in payload[resource_name] if isinstance(item, dict)]
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return [item for item in value if isinstance(item, dict)]
    return []


def load_resource(input_dir: str, filename: str) -> List[Dict[str, Any]]:
    """Load one optional PeeringDB dump file into a flat record list."""
    path = os.path.join(input_dir, filename)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return extract_records(payload, os.path.splitext(filename)[0])


def build_empty_output() -> pd.DataFrame:
    """Return an empty-but-valid output frame with stable headers."""
    return pd.DataFrame(
        columns=[
            "country",
            "pdb_num_ixps",
            "pdb_num_facilities",
            "pdb_num_networks",
            "pdb_num_network_facility_presence",
            "pdb_num_ixp_participants",
            "pdb_ixp_participant_entropy",
            "pdb_facility_participant_entropy",
            "pdb_interconnection_footprint_score",
            "pdb_interconnection_footprint_percentile",
            "pdb_interconnection_footprint_tier",
        ]
    )


def build_country_descriptors(input_dir: str) -> pd.DataFrame:
    """Build country-level PeeringDB interconnection footprint descriptors from local dump files."""
    ix_rows = load_resource(input_dir, "ix.json")
    fac_rows = load_resource(input_dir, "fac.json")
    net_rows = load_resource(input_dir, "net.json")
    netfac_rows = load_resource(input_dir, "netfac.json")
    netixlan_rows = load_resource(input_dir, "netixlan.json")

    if not any([ix_rows, fac_rows, net_rows, netfac_rows, netixlan_rows]):
        return build_empty_output()

    ix_country_by_id: Dict[int, str] = {}
    ix_country_rows: Dict[str, Dict[str, set]] = {}
    for row in ix_rows:
        ix_id = coerce_int(first_present(row, ["id", "ix_id"]))
        country = normalize_country(first_present(row, ["country", "country_code", "country_alpha2"]))
        if ix_id < 0 or not country:
            continue
        ix_country_by_id[ix_id] = country
        ix_country_rows.setdefault(country, {"ix_ids": set(), "fac_ids": set(), "network_ids": set(), "ix_pairs": set(), "netfac_rows": 0})
        ix_country_rows[country]["ix_ids"].add(ix_id)

    fac_country_by_id: Dict[int, str] = {}
    for row in fac_rows:
        fac_id = coerce_int(first_present(row, ["id", "fac_id"]))
        country = normalize_country(first_present(row, ["country", "country_code", "country_alpha2"]))
        if fac_id < 0 or not country:
            continue
        fac_country_by_id[fac_id] = country
        ix_country_rows.setdefault(country, {"ix_ids": set(), "fac_ids": set(), "network_ids": set(), "ix_pairs": set(), "netfac_rows": 0})
        ix_country_rows[country]["fac_ids"].add(fac_id)

    known_network_ids = {
        coerce_int(first_present(row, ["id", "net_id"]))
        for row in net_rows
        if coerce_int(first_present(row, ["id", "net_id"])) >= 0
    }

    ix_participation_counts: Dict[str, Dict[int, int]] = {}
    facility_presence_counts: Dict[str, Dict[int, int]] = {}

    for row in netixlan_rows:
        net_id = coerce_int(first_present(row, ["net_id", "network_id", "id"]))
        ix_id = coerce_int(first_present(row, ["ix_id", "ix"]))
        if net_id < 0 or ix_id < 0:
            continue
        country = ix_country_by_id.get(ix_id, "")
        if not country:
            continue
        bucket = ix_country_rows.setdefault(country, {"ix_ids": set(), "fac_ids": set(), "network_ids": set(), "ix_pairs": set(), "netfac_rows": 0})
        bucket["ix_ids"].add(ix_id)
        bucket["network_ids"].add(net_id)
        bucket["ix_pairs"].add((net_id, ix_id))
        ix_participation_counts.setdefault(country, {})
        ix_participation_counts[country][ix_id] = ix_participation_counts[country].get(ix_id, 0) + 1

    for row in netfac_rows:
        net_id = coerce_int(first_present(row, ["net_id", "network_id", "id"]))
        fac_id = coerce_int(first_present(row, ["fac_id", "facility_id"]))
        if net_id < 0 or fac_id < 0:
            continue
        country = fac_country_by_id.get(fac_id, "")
        if not country:
            continue
        bucket = ix_country_rows.setdefault(country, {"ix_ids": set(), "fac_ids": set(), "network_ids": set(), "ix_pairs": set(), "netfac_rows": 0})
        bucket["fac_ids"].add(fac_id)
        bucket["network_ids"].add(net_id)
        bucket["netfac_rows"] += 1
        facility_presence_counts.setdefault(country, {})
        facility_presence_counts[country][fac_id] = facility_presence_counts[country].get(fac_id, 0) + 1

    rows: List[Dict[str, Any]] = []
    for country in sorted(ix_country_rows.keys()):
        bucket = ix_country_rows[country]
        network_ids = {net_id for net_id in bucket["network_ids"] if net_id >= 0}
        if known_network_ids:
            network_ids = {net_id for net_id in network_ids if net_id in known_network_ids}
        pdb_num_ixps = int(len(bucket["ix_ids"]))
        pdb_num_facilities = int(len(bucket["fac_ids"]))
        pdb_num_networks = int(len(network_ids))
        pdb_num_network_facility_presence = int(bucket["netfac_rows"])
        pdb_num_ixp_participants = int(len(bucket["ix_pairs"]))
        pdb_ixp_participant_entropy = shannon_entropy(ix_participation_counts.get(country, {}).values())
        pdb_facility_participant_entropy = shannon_entropy(facility_presence_counts.get(country, {}).values())
        footprint_score = float(
            math.log1p(pdb_num_ixps)
            + math.log1p(pdb_num_facilities)
            + math.log1p(pdb_num_networks)
            + pdb_ixp_participant_entropy
            + pdb_facility_participant_entropy
        )
        rows.append(
            {
                "country": country,
                "pdb_num_ixps": pdb_num_ixps,
                "pdb_num_facilities": pdb_num_facilities,
                "pdb_num_networks": pdb_num_networks,
                "pdb_num_network_facility_presence": pdb_num_network_facility_presence,
                "pdb_num_ixp_participants": pdb_num_ixp_participants,
                "pdb_ixp_participant_entropy": float(pdb_ixp_participant_entropy),
                "pdb_facility_participant_entropy": float(pdb_facility_participant_entropy),
                "pdb_interconnection_footprint_score": footprint_score,
            }
        )

    if not rows:
        return build_empty_output()

    frame = pd.DataFrame(rows).sort_values("country").reset_index(drop=True)
    frame["pdb_interconnection_footprint_percentile"] = frame["pdb_interconnection_footprint_score"].rank(
        method="average",
        pct=True,
        ascending=True,
    )
    low_cut = float(frame["pdb_interconnection_footprint_score"].quantile(1 / 3))
    high_cut = float(frame["pdb_interconnection_footprint_score"].quantile(2 / 3))
    frame["pdb_interconnection_footprint_tier"] = frame["pdb_interconnection_footprint_score"].apply(
        lambda value: "low" if value <= low_cut else ("medium" if value <= high_cut else "high")
    )
    return frame[build_empty_output().columns.tolist()]


def main() -> None:
    """Build and write PeeringDB country descriptors."""
    args = parse_args()
    output_frame = build_country_descriptors(args.input_dir)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    output_frame.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"Saved PeeringDB country descriptors to {args.output}")


if __name__ == "__main__":
    main()
