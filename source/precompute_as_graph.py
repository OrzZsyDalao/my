import argparse
import gzip
import heapq
import json
import os
import pickle
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else "."
BASE_DIR = os.path.dirname(SOURCE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "preprocessed")

ASREL_DIR = os.path.join(DATA_DIR, "asrelationship")
OWNER2ASN_DIR = os.path.join(DATA_DIR, "owner2asn")
CABLE_DIR = os.path.join(DATA_DIR, "cable")

DEFAULT_ASREL_PATH = os.path.join(ASREL_DIR, "20250901.as-rel2.txt")
DEFAULT_OWNER2ASN_PATH = os.path.join(OWNER2ASN_DIR, "owner_to_asn.csv")
DEFAULT_CABLE_DIR = CABLE_DIR
DEFAULT_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "as_graph_owner_reachability.pkl.gz")

CABLE_EXCLUSION_FILE = "landing-point-geo.json"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for AS-graph precomputation."""
    parser = argparse.ArgumentParser(
        description="Precompute bounded AS-graph reachability from cable owner groups."
    )
    parser.add_argument("--asrel-file", default=DEFAULT_ASREL_PATH, help="CAIDA AS relationship file path.")
    parser.add_argument("--owner2asn-file", default=DEFAULT_OWNER2ASN_PATH, help="owner_to_asn CSV file path.")
    parser.add_argument("--cable-dir", default=DEFAULT_CABLE_DIR, help="Cable metadata directory.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="Output pickle.gz file path.")
    parser.add_argument(
        "--max-hops-unknown",
        type=int,
        default=4,
        help="Online threshold: paths with more hops than this are treated as unknown.",
    )
    parser.add_argument(
        "--search-max-hops",
        type=int,
        default=4,
        help="Offline search depth used when expanding owner groups across the AS graph.",
    )
    parser.add_argument("--peer-cost", type=float, default=1.0, help="Traversal cost assigned to peer edges.")
    parser.add_argument(
        "--provider-customer-cost",
        type=float,
        default=2.0,
        help="Traversal cost assigned to provider-customer edges.",
    )
    parser.add_argument(
        "--limit-owner-groups",
        type=int,
        default=None,
        help="Optional limit for smoke tests; only precompute the first N owner groups.",
    )
    return parser.parse_args()


def normalize_owners_field(raw_owners: Any) -> List[str]:
    """Normalize cable owner metadata into a flat string list."""
    if raw_owners is None:
        return []
    if isinstance(raw_owners, str):
        return [owner.strip() for owner in raw_owners.split(",") if owner.strip()]
    if isinstance(raw_owners, list):
        owners = []
        for item in raw_owners:
            if item is None:
                continue
            owner = str(item).strip()
            if owner:
                owners.append(owner)
        return owners
    owner = str(raw_owners).strip()
    return [owner] if owner else []


def normalize_asn_value(raw_asn: Any) -> str:
    """Normalize ASN-like values to a comparable plain string."""
    if raw_asn is None:
        return "-1"
    asn = str(raw_asn).strip()
    if not asn:
        return "-1"
    if asn.upper().startswith("AS"):
        asn = asn[2:]
    return asn if asn else "-1"


def owner_group_signature(owner_asns: Iterable[str]) -> str:
    """Build a stable signature for an owner-ASN set."""
    normalized = sorted(
        {
            normalize_asn_value(asn)
            for asn in owner_asns
            if normalize_asn_value(asn) != "-1"
        }
    )
    return "|".join(normalized)


def load_as_relationship(path: str) -> Dict[Tuple[str, str], int]:
    """Load CAIDA AS relationship data."""
    as_relations: Dict[Tuple[str, str], int] = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("|")
            if len(parts) < 3:
                continue
            as_a = normalize_asn_value(parts[0])
            as_b = normalize_asn_value(parts[1])
            rel_type = int(parts[2])
            as_relations[(as_a, as_b)] = rel_type
            as_relations[(as_b, as_a)] = -rel_type
    return as_relations


def load_owner2asn_mapping(path: str) -> Dict[str, Set[str]]:
    """Load owner -> ASN mappings."""
    owner2asn: Dict[str, Set[str]] = {}
    frame = pd.read_csv(
        path,
        dtype={"owner": str, "asn": str},
        usecols=["owner", "asn"],
        keep_default_na=False,
        encoding="utf-8",
    )
    frame["owner"] = frame["owner"].str.strip()
    frame["asn"] = frame["asn"].str.strip()

    for _, row in frame.iterrows():
        owner = row["owner"]
        asn = normalize_asn_value(row["asn"])
        if not owner or asn == "-1":
            continue
        owner2asn.setdefault(owner, set()).add(asn)
    return owner2asn


def load_all_cables(directory: str) -> List[Dict[str, Any]]:
    """Load submarine cable metadata files."""
    cables: List[Dict[str, Any]] = []
    for filename in os.listdir(directory):
        if not filename.endswith(".json") or filename == CABLE_EXCLUSION_FILE:
            continue
        path = os.path.join(directory, filename)
        with open(path, "r", encoding="utf-8") as handle:
            try:
                cable_data = json.load(handle)
            except json.JSONDecodeError:
                continue
        cables.append(
            {
                "id": cable_data.get("id", "Unknown"),
                "name": cable_data.get("name", "Unknown"),
                "owners": normalize_owners_field(cable_data.get("owners", [])),
            }
        )
    return cables


def relationship_edge_cost(rel_type: int, peer_cost: float, provider_customer_cost: float) -> float:
    """Map CAIDA relationship type to graph traversal cost."""
    if rel_type == 0:
        return float(peer_cost)
    if rel_type in {1, -1}:
        return float(provider_customer_cost)
    return float(provider_customer_cost)


def build_as_graph(
    as_relationship: Dict[Tuple[str, str], int],
    peer_cost: float,
    provider_customer_cost: float,
) -> Tuple[Dict[str, int], Dict[int, str], Dict[int, List[Tuple[int, float, int]]]]:
    """Build an integer-indexed adjacency graph from AS relationship data."""
    asn_to_id: Dict[str, int] = {}
    id_to_asn: Dict[int, str] = {}
    adjacency: Dict[int, List[Tuple[int, float, int]]] = {}

    def ensure_node(asn: str) -> int:
        if asn not in asn_to_id:
            node_id = len(asn_to_id)
            asn_to_id[asn] = node_id
            id_to_asn[node_id] = asn
        return asn_to_id[asn]

    for (asn_a, asn_b), rel_type in as_relationship.items():
        node_a = ensure_node(asn_a)
        node_b = ensure_node(asn_b)
        adjacency.setdefault(node_a, []).append(
            (node_b, relationship_edge_cost(rel_type, peer_cost, provider_customer_cost), rel_type)
        )
    return asn_to_id, id_to_asn, adjacency


def collect_owner_groups(cables: List[Dict[str, Any]], owner2asn: Dict[str, Set[str]]) -> Dict[str, List[str]]:
    """Extract unique cable owner-ASN groups from cable metadata."""
    groups: Dict[str, List[str]] = {}
    for cable in cables:
        cable_owner_asns: Set[str] = set()
        for owner in cable["owners"]:
            cable_owner_asns.update(owner2asn.get(owner, set()))
        signature = owner_group_signature(cable_owner_asns)
        if not signature:
            continue
        groups.setdefault(signature, signature.split("|"))
    return groups


def bounded_multisource_shortest_paths(
    adjacency: Dict[int, List[Tuple[int, float, int]]],
    source_nodes: List[int],
    max_hops: int,
) -> Dict[int, Tuple[float, int]]:
    """Compute best weighted paths from a source set up to a bounded hop count."""
    best_state: Dict[Tuple[int, int], float] = {}
    best_result: Dict[int, Tuple[float, int]] = {}
    heap: List[Tuple[float, int, int]] = []

    for node_id in source_nodes:
        best_state[(node_id, 0)] = 0.0
        best_result[node_id] = (0.0, 0)
        heapq.heappush(heap, (0.0, 0, node_id))

    while heap:
        path_cost, path_hops, node_id = heapq.heappop(heap)
        if path_cost > best_state.get((node_id, path_hops), float("inf")):
            continue
        if path_hops >= max_hops:
            continue

        for neighbor_id, edge_cost, _rel_type in adjacency.get(node_id, []):
            next_hops = path_hops + 1
            next_cost = path_cost + edge_cost
            state_key = (neighbor_id, next_hops)
            if next_cost >= best_state.get(state_key, float("inf")):
                continue

            best_state[state_key] = next_cost
            heapq.heappush(heap, (next_cost, next_hops, neighbor_id))

            previous = best_result.get(neighbor_id)
            if previous is None or next_cost < previous[0] or (next_cost == previous[0] and next_hops < previous[1]):
                best_result[neighbor_id] = (float(next_cost), int(next_hops))

    return best_result


def fingerprint_file(path: str) -> Dict[str, Any]:
    """Collect lightweight file metadata for reproducibility."""
    stat = os.stat(path)
    return {
        "path": os.path.relpath(path, BASE_DIR),
        "size_bytes": int(stat.st_size),
        "mtime_epoch": float(stat.st_mtime),
    }


def main() -> None:
    """Precompute cable-owner-group reachability over the AS relationship graph."""
    args = parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    print("Loading AS relationship data...")
    as_relationship = load_as_relationship(args.asrel_file)
    print("Loading owner-to-ASN mappings...")
    owner2asn = load_owner2asn_mapping(args.owner2asn_file)
    print("Loading cable metadata...")
    cables = load_all_cables(args.cable_dir)

    print("Building AS relationship graph...")
    asn_to_id, id_to_asn, adjacency = build_as_graph(
        as_relationship=as_relationship,
        peer_cost=args.peer_cost,
        provider_customer_cost=args.provider_customer_cost,
    )

    print("Collecting unique owner groups from cable metadata...")
    owner_groups = collect_owner_groups(cables, owner2asn)
    owner_group_signatures = {signature: index for index, signature in enumerate(sorted(owner_groups.keys()))}
    owner_group_definitions = {
        owner_group_signatures[signature]: owner_asns
        for signature, owner_asns in owner_groups.items()
    }

    owner_group_reachability: Dict[int, Dict[int, Tuple[float, int]]] = {}
    total_reachable_entries = 0

    ordered_signatures = sorted(owner_group_signatures.keys())
    if args.limit_owner_groups is not None:
        ordered_signatures = ordered_signatures[: max(args.limit_owner_groups, 0)]
    print(f"Precomputing reachability for {len(ordered_signatures)} owner groups...")
    for index, signature in enumerate(ordered_signatures, start=1):
        group_id = owner_group_signatures[signature]
        source_nodes = [asn_to_id[asn] for asn in owner_groups[signature] if asn in asn_to_id]
        if not source_nodes:
            owner_group_reachability[group_id] = {}
            continue
        reachability = bounded_multisource_shortest_paths(
            adjacency=adjacency,
            source_nodes=source_nodes,
            max_hops=args.search_max_hops,
        )
        owner_group_reachability[group_id] = reachability
        total_reachable_entries += len(reachability)
        if index % 10 == 0 or index == len(ordered_signatures):
            print(
                f"  processed {index}/{len(ordered_signatures)} owner groups "
                f"(reachable entries so far: {total_reachable_entries})"
            )

    payload = {
        "version": 1,
        "config": {
            "max_hops_unknown": int(args.max_hops_unknown),
            "search_max_hops": int(args.search_max_hops),
            "peer_cost": float(args.peer_cost),
            "provider_customer_cost": float(args.provider_customer_cost),
            "limit_owner_groups": None if args.limit_owner_groups is None else int(args.limit_owner_groups),
        },
        "asn_to_id": asn_to_id,
        "id_to_asn": id_to_asn,
        "owner_group_signatures": owner_group_signatures,
        "owner_group_definitions": owner_group_definitions,
        "owner_group_reachability": owner_group_reachability,
        "source_files": {
            "asrel_file": fingerprint_file(args.asrel_file),
            "owner2asn_file": fingerprint_file(args.owner2asn_file),
            "cable_dir": os.path.relpath(args.cable_dir, BASE_DIR),
        },
    }

    with gzip.open(args.output, "wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)

    manifest_path = f"{args.output}.manifest.json"
    manifest = {
        "output_file": os.path.relpath(args.output, BASE_DIR),
        "owner_group_count": len(ordered_signatures),
        "graph_node_count": len(asn_to_id),
        "graph_edge_count": int(sum(len(edges) for edges in adjacency.values())),
        "reachable_entries": int(total_reachable_entries),
        "config": payload["config"],
        "source_files": payload["source_files"],
    }
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    print(f"Saved AS-graph precompute file to {args.output}")
    print(f"Saved manifest to {manifest_path}")


if __name__ == "__main__":
    main()
