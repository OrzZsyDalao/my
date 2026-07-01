import argparse
import gzip
import ipaddress
import json
import math
import os
import pickle
from statistics import median
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

import maxminddb
import numpy as np
import pandas as pd
try:
    import pytricia
except ImportError:
    pytricia = None
from geopy.distance import geodesic
from sklearn.neighbors import BallTree
from tqdm import tqdm


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else "."
BASE_DIR = os.path.dirname(SOURCE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "result")
PREPROCESSED_DIR = os.path.join(BASE_DIR, "output", "preprocessed")

CABLE_DIR = os.path.join(DATA_DIR, "cable")
TRACE_DIR = os.path.join(DATA_DIR, "traceroute_rundnsroot")
IPINFO_DIR = os.path.join(DATA_DIR, "ipinfo")
ASREL_DIR = os.path.join(DATA_DIR, "asrelationship")
PFX2AS_DIR = os.path.join(DATA_DIR, "pfx2as")
OWNER2ASN_DIR = os.path.join(DATA_DIR, "owner2asn")

LS_GEO_PATH = os.path.join(CABLE_DIR, "landing-point-geo.json")
MMDB_PATH = os.path.join(IPINFO_DIR, "ipinfo_location.mmdb")
ASREL_PATH = os.path.join(ASREL_DIR, "20250901.as-rel2.txt")
PFX2AS_PATH = os.path.join(PFX2AS_DIR, "202512.pfx2as")
OWNER2ASN_PATH = os.path.join(OWNER2ASN_DIR, "owner_to_asn.csv")

CABLE_DEBUG_OUTPUT_PATH = os.path.join(BASE_DIR, "cable_loading_debug.json")
OUTPUT_RESULTS_PATH = os.path.join(OUTPUT_DIR, "cable_matching_output.json")
MATCH_STATS_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "cable_matching_stats_5051.json")
MATCH_MANIFEST_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "cable_matching_manifest.json")
AS_GRAPH_PRECOMPUTE_PATH = os.path.join(PREPROCESSED_DIR, "as_graph_owner_reachability.pkl.gz")

TRACEROUTE_EXCLUSIONS = ("_result.json", "_geo.json", "_analysis.json")
CABLE_EXCLUSION_FILE = "landing-point-geo.json"


class IPv4PrefixLookup:
    """Fallback longest-prefix matcher used when pytricia is unavailable."""

    def __init__(self, max_bits: int = 32):
        self.max_bits = max_bits
        self._prefix_maps: Dict[int, Dict[int, str]] = {}
        self._masks = {
            prefix_len: ((0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF) if prefix_len > 0 else 0
            for prefix_len in range(max_bits + 1)
        }

    def __setitem__(self, cidr: str, value: str) -> None:
        network = ipaddress.ip_network(cidr, strict=False)
        if network.version != 4:
            return
        prefix_len = network.prefixlen
        network_int = int(network.network_address)
        self._prefix_maps.setdefault(prefix_len, {})[network_int] = value

    def get(self, ip_address: str) -> Optional[str]:
        try:
            ip_obj = ipaddress.ip_address(ip_address)
        except ValueError:
            return None

        if ip_obj.version != 4:
            return None

        ip_int = int(ip_obj)
        for prefix_len in range(self.max_bits, -1, -1):
            mask = self._masks[prefix_len]
            network_int = ip_int & mask
            prefix_bucket = self._prefix_maps.get(prefix_len)
            if prefix_bucket and network_int in prefix_bucket:
                return prefix_bucket[network_int]
        return None


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


def owner_group_signature(owner_asns: Set[str]) -> str:
    """Build a stable signature for a normalized owner-ASN set."""
    normalized = sorted(
        {
            normalize_asn_value(asn)
            for asn in owner_asns
            if normalize_asn_value(asn) != "-1"
        }
    )
    return "|".join(normalized)


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


def load_ls_coordinates(path: str) -> Dict[str, Tuple[float, float]]:
    """Load landing-station coordinates from GeoJSON."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            landing_points = json.load(handle)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing landing-point-geo.json at {path}") from exc

    ls_coordinates: Dict[str, Tuple[float, float]] = {}
    for feature in landing_points.get("features", []):
        ls_id = feature["properties"]["id"]
        lon, lat = feature["geometry"]["coordinates"]
        ls_coordinates[ls_id] = (lat, lon)
    return ls_coordinates


def load_all_cables(directory: str) -> List[Dict[str, Any]]:
    """Load submarine cable metadata files."""
    all_cables: List[Dict[str, Any]] = []
    try:
        for filename in os.listdir(directory):
            if not filename.endswith(".json") or filename == CABLE_EXCLUSION_FILE:
                continue
            file_path = os.path.join(directory, filename)
            with open(file_path, "r", encoding="utf-8") as handle:
                try:
                    cable_data = json.load(handle)
                except json.JSONDecodeError:
                    continue

            cable_id = cable_data.get("id", "Unknown")
            cable_name = cable_data.get("name", cable_id)
            owners = normalize_owners_field(cable_data.get("owners", []))
            ls_points = [
                point["id"]
                for point in cable_data.get("landing_points", [])
                if isinstance(point, dict) and point.get("id")
            ]
            all_cables.append(
                {
                    "id": cable_id,
                    "name": cable_name,
                    "owners": owners,
                    "ls_points": ls_points,
                }
            )
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing cable directory {directory}") from exc

    return all_cables


def load_as_relationship(path: str) -> Dict[Tuple[str, str], int]:
    """Load CAIDA AS relationship data."""
    as_relations: Dict[Tuple[str, str], int] = {}
    try:
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
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing AS relationship file at {path}") from exc
    return as_relations


def load_pfx2as_mapping(path: str) -> Any:
    """Load pfx2as prefixes into PyTricia or fallback longest-prefix lookup."""
    trie = pytricia.PyTricia(32) if pytricia is not None else IPv4PrefixLookup(32)
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                prefix, length, asn = line.split()
            except ValueError:
                continue
            if ":" in prefix:
                continue
            trie[f"{prefix}/{length}"] = normalize_asn_value(asn.strip("{}").split("_")[0])
    return trie


def load_owner2asn_mapping(path: str) -> Dict[str, Set[str]]:
    """Load owner -> ASN mappings."""
    owner2asn: Dict[str, Set[str]] = {}
    try:
        frame = pd.read_csv(
            path,
            dtype={"owner": str, "asn": str},
            usecols=["owner", "asn"],
            keep_default_na=False,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing owner_to_asn.csv at {path}") from exc

    frame["owner"] = frame["owner"].str.strip()
    frame["asn"] = frame["asn"].str.strip()

    for _, row in frame.iterrows():
        owner = row["owner"]
        asn = normalize_asn_value(row["asn"])
        if not owner or asn == "-1":
            continue
        owner2asn.setdefault(owner, set()).add(asn)
    return owner2asn


def load_as_graph_precompute(path: str) -> Optional[Dict[str, Any]]:
    """Load precomputed AS-graph owner reachability state if available."""
    if not path:
        return None
    if not os.path.exists(path):
        print(f"Warning: AS-graph precompute file not found, falling back to legacy AS-economic scoring: {path}")
        return None

    with gzip.open(path, "rb") as handle:
        payload = pickle.load(handle)

    required_keys = {
        "asn_to_id",
        "owner_group_signatures",
        "owner_group_reachability",
        "config",
    }
    missing_keys = sorted(required_keys.difference(payload.keys()))
    if missing_keys:
        raise ValueError(f"AS precompute file is missing required keys: {missing_keys}")
    return payload


def stream_json_array(path: str) -> Generator[Dict[str, Any], None, None]:
    """Fallback streaming reader for large JSON arrays."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line in {"[", "]"} or not line:
                continue
            if line.endswith(","):
                line = line[:-1]
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iter_traceroute_results(path: str) -> Generator[Dict[str, Any], None, None]:
    """Yield traceroute records from a JSON object, array, or streaming fallback."""
    if not os.path.exists(path):
        return

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    yield item
        elif isinstance(payload, dict):
            yield payload
        return
    except Exception:
        pass

    for item in stream_json_array(path):
        if isinstance(item, dict):
            yield item


def is_private_or_special_ip(ip_address: str) -> bool:
    """Return whether an IP is private, reserved, or otherwise not Internet-routable."""
    try:
        ip_obj = ipaddress.ip_address(ip_address)
    except ValueError:
        return True
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def get_geo_info(ip_address: str, mmdb_reader: maxminddb.Reader) -> Dict[str, Any]:
    """Query IP geolocation data from the mmdb reader."""
    geo_data = {"lat": None, "lon": None, "asn": None, "country": None, "city": None}
    if not ip_address or is_private_or_special_ip(ip_address):
        return geo_data

    try:
        record = mmdb_reader.get(ip_address)
        if record:
            geo_data["lat"] = record.get("latitude")
            geo_data["lon"] = record.get("longitude")
            geo_data["country"] = record.get("country_code")
            geo_data["city"] = record.get("city")
            if "traits" in record and "autonomous_system_number" in record["traits"]:
                geo_data["asn"] = f"AS{record['traits']['autonomous_system_number']}"
    except Exception:
        pass
    return geo_data


def parse_hops_to_links(
    hops: List[Dict[str, Any]],
    msm_id: str,
    prb_id: str,
    timestamp: str,
    file_name: str,
    mmdb_reader: maxminddb.Reader,
) -> List[Dict[str, Any]]:
    """Convert consecutive traceroute hops into adjacent hop-pair links."""
    parsed_links: List[Dict[str, Any]] = []
    previous_rtt = 0.0
    previous_hop_info: Optional[Dict[str, Any]] = None

    for hop_data in hops:
        rtt_results = [entry.get("rtt") for entry in hop_data.get("result", []) if entry.get("rtt") is not None]
        ip = hop_data.get("result", [{}])[0].get("from")

        if not ip or not rtt_results:
            previous_hop_info = None
            continue

        rtt = min(rtt_results)
        current_hop_info = {
            "ip": ip,
            "rtt": rtt,
            "geo": get_geo_info(ip, mmdb_reader),
            "hop_num": hop_data["hop"],
        }

        is_previous_geolocated = previous_hop_info and previous_hop_info["geo"]["lat"] is not None
        is_current_geolocated = current_hop_info["geo"]["lat"] is not None

        if is_previous_geolocated and is_current_geolocated:
            rtt_delta = rtt - previous_rtt
            parsed_links.append(
                {
                    "source": previous_hop_info,
                    "destination": current_hop_info,
                    "rtt_delta": rtt_delta,
                    "ips": (previous_hop_info["ip"], current_hop_info["ip"]),
                    "is_oceanic": rtt_delta > 15.0,
                    "measurement_id": msm_id,
                    "probe_id": prb_id,
                    "timestamp": timestamp,
                    "file_name": file_name,
                }
            )

        previous_rtt = rtt
        previous_hop_info = current_hop_info

    return parsed_links


def process_single_traceroute_file(path: str, mmdb_reader: maxminddb.Reader) -> List[Dict[str, Any]]:
    """Retained helper for file-level link extraction experiments."""
    all_links: List[Dict[str, Any]] = []
    file_name = os.path.basename(path)

    for result_data in iter_traceroute_results(path):
        if not result_data.get("result"):
            continue
        links_from_run = parse_hops_to_links(
            hops=result_data["result"],
            msm_id=result_data.get("msm_id", "N/A"),
            prb_id=result_data.get("prb_id", "N/A"),
            timestamp=result_data.get("timestamp", "N/A"),
            file_name=file_name,
            mmdb_reader=mmdb_reader,
        )
        all_links.extend(links_from_run)

    return all_links


class CableMatcher:
    """Cross-layer candidate matcher with uncertainty-aware evidence fusion."""

    SOL_FIBER_KM_MS = 200.0
    SLACK_FACTOR = 1.2
    LS_CATCHMENT_RADIUS_KM = 100.0
    R_EARTH = 6371.0

    MATCH_THRESHOLD = 0.5
    HIGH_CONF_THRESHOLD = 0.7
    MEDIUM_CONF_THRESHOLD = 0.5
    HIGH_GAP_THRESHOLD = 0.2
    MEDIUM_GAP_THRESHOLD = 0.1

    GEO_DECAY_CUTOFF_KM = 100.0
    GEO_DECAY_STEEPNESS = 2.0
    LAMBDA_AS = 0.35
    FUSION_ALPHA = 1.0
    FUSION_BETA = 1.0
    FUSION_GAMMA = 1.0
    CORE_STRONG_THRESHOLD = 0.7
    CORE_WEAK_THRESHOLD = 0.5
    MANY_CANDIDATES_THRESHOLD = 5
    LARGE_LANDING_RADIUS_KM = 80.0
    RTT_INCONCLUSIVE_MARGIN_MS = 2.0
    SHORT_PATH_RTT_MS = 5.0
    HIGH_INFLATION_RATIO = 20.0
    SHORT_PATH_INFLATION_PENALTY = 0.5
    MULTI_SEGMENT_GCD_THRESHOLD_KM = 3000.0
    MULTI_SEGMENT_MARGIN_THRESHOLD_MS = 10.0
    AS_GRAPH_MAX_HOPS_UNKNOWN = 4
    AS_GRAPH_SEARCH_MAX_HOPS = 4
    AS_GRAPH_ONE_SIDED_PENALTY = 1.0
    AS_GRAPH_UNKNOWN_COST = 4.0

    def __init__(
        self,
        processed_cables: List[Dict[str, Any]],
        ls_coordinates: Dict[str, Tuple[float, float]],
        as_relationship: Dict[Tuple[str, str], int],
        pfx2as_trie: Any,
        owner2asn: Dict[str, Set[str]],
        as_graph_precompute: Optional[Dict[str, Any]] = None,
    ):
        self.all_cables = processed_cables
        self.ls_geo = ls_coordinates
        self.as_relationship = as_relationship
        self.pfx2as_trie = pfx2as_trie
        self.owner2asn = owner2asn
        self.as_graph_precompute = as_graph_precompute or {}
        self.candidate_count_per_matched_link: List[int] = []
        self.owner_group_signatures: Dict[str, int] = self.as_graph_precompute.get("owner_group_signatures", {})
        self.owner_group_reachability: Dict[int, Dict[int, Tuple[float, int]]] = self.as_graph_precompute.get(
            "owner_group_reachability",
            {},
        )
        self.as_precompute_asn_to_id: Dict[str, int] = self.as_graph_precompute.get("asn_to_id", {})
        as_graph_config = self.as_graph_precompute.get("config", {})
        self.as_graph_precompute_loaded = bool(self.as_graph_precompute)
        self.as_graph_max_hops_unknown = int(as_graph_config.get("max_hops_unknown", self.AS_GRAPH_MAX_HOPS_UNKNOWN))
        self.as_graph_search_max_hops = int(as_graph_config.get("search_max_hops", self.AS_GRAPH_SEARCH_MAX_HOPS))

        self.stats: Dict[str, Any] = {
            "total_links_seen": 0,
            "same_city_filtered": 0,
            "links_with_ls_candidates": 0,
            "links_with_geo_candidates": 0,
            "candidate_segments_considered": 0,
            "rtt_infeasible_filtered": 0,
            "links_below_threshold": 0,
            "candidates_above_threshold": 0,
            "links_with_any_match": 0,
            "links_with_filtered_candidates": 0,
            "links_with_no_feasible_rtt_candidate": 0,
            "total_candidates_generated": 0,
            "total_candidates_after_threshold": 0,
            "links_with_dual_core_agreement": 0,
            "links_with_geo_dominant_as_weak": 0,
            "links_with_as_dominant_geo_ambiguous": 0,
            "links_with_parallel_ambiguity": 0,
            "links_with_many_candidates": 0,
            "links_with_domestic_candidates": 0,
            "as_precompute_enabled": self.as_graph_precompute_loaded,
            "candidate_count_list": self.candidate_count_per_matched_link,
        }

        ls_ids = list(self.ls_geo.keys())
        ls_coords_rad = np.radians([self.ls_geo[ls_id] for ls_id in ls_ids])
        self.ls_tree = BallTree(ls_coords_rad, metric="haversine")
        self.ls_id_map = {index: ls_id for index, ls_id in enumerate(ls_ids)}
        self.ls_coord_map = {ls_id: self.ls_geo[ls_id] for ls_id in ls_ids}

        self.segment_to_cables: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        self.gcd_cache: Dict[Tuple[str, str], float] = {}

        for cable in self.all_cables:
            points = cable["ls_points"]
            cable_owner_asns: Set[str] = set()
            for owner in cable["owners"]:
                cable_owner_asns.update(self.owner2asn.get(owner, set()))
            owner_signature = owner_group_signature(cable_owner_asns)
            owner_group_id = self.owner_group_signatures.get(owner_signature) if owner_signature else None
            for i in range(len(points)):
                for j in range(i + 1, len(points)):
                    ls_a = points[i]
                    ls_b = points[j]
                    if ls_a == ls_b or ls_a not in self.ls_geo or ls_b not in self.ls_geo:
                        continue
                    segment = tuple(sorted((ls_a, ls_b)))
                    if segment not in self.gcd_cache:
                        self.gcd_cache[segment] = geodesic(self.ls_geo[ls_a], self.ls_geo[ls_b]).km
                    self.segment_to_cables.setdefault(segment, []).append(
                        {
                            "cable_id": cable["id"],
                            "cable_name": cable["name"],
                            "cable_owners": cable["owners"],
                            "cable_owner_asns": cable_owner_asns,
                            "owner_group_signature": owner_signature,
                            "owner_group_id": owner_group_id,
                            "gcd_dist": self.gcd_cache[segment],
                        }
                    )

    def finalize_stats(self) -> Dict[str, Any]:
        """Return stats with aggregate metrics computed from per-link counts."""
        finalized = dict(self.stats)
        candidate_counts = list(self.candidate_count_per_matched_link)
        finalized["mean_candidate_count_per_matched_link"] = (
            float(sum(candidate_counts) / len(candidate_counts)) if candidate_counts else 0.0
        )
        finalized["median_candidate_count_per_matched_link"] = (
            float(median(candidate_counts)) if candidate_counts else 0.0
        )
        finalized["candidate_count_list"] = candidate_counts
        return finalized

    def IP2ASN(self, ip: str) -> str:
        """Map an IP address to an origin ASN using pfx2as."""
        try:
            asn = self.pfx2as_trie.get(ip)
        except Exception:
            return "-1"
        return normalize_asn_value(asn)

    def compute_geo_spatial_score(self, d_in: float, d_out: float) -> Dict[str, float]:
        """Geo-spatial Core: score landing-station proximity at both link endpoints."""
        prob_in = 1.0 / (1.0 + (d_in / self.GEO_DECAY_CUTOFF_KM) ** self.GEO_DECAY_STEEPNESS)
        prob_out = 1.0 / (1.0 + (d_out / self.GEO_DECAY_CUTOFF_KM) ** self.GEO_DECAY_STEEPNESS)
        geo_spatial_score = math.sqrt(prob_in * prob_out)
        return {
            "geo_spatial_score": float(geo_spatial_score),
            "geo_entry_score": float(prob_in),
            "geo_exit_score": float(prob_out),
            "prob_in": float(prob_in),
            "prob_out": float(prob_out),
        }

    def compute_rtt_feasibility_score(self, measured_rtt_delta: float, min_rtt: float) -> Dict[str, Any]:
        """RTT/Physical Feasibility Core: assess whether a candidate is latency-feasible."""
        if min_rtt <= 0:
            return {
                "rtt_feasible": False,
                "rtt_score": 0.0,
                "rtt_margin_ms": float(measured_rtt_delta),
                "latency_penalty": 0.0,
            }

        rtt_margin_ms = measured_rtt_delta - min_rtt
        if measured_rtt_delta < min_rtt:
            return {
                "rtt_feasible": False,
                "rtt_score": 0.0,
                "rtt_margin_ms": float(rtt_margin_ms),
                "latency_penalty": 0.0,
            }

        inflation_ratio = measured_rtt_delta / min_rtt if min_rtt > 0 else float("inf")
        rtt_score = min(1.0, 1.0 / inflation_ratio) if math.isfinite(inflation_ratio) and inflation_ratio > 0 else 0.0

        latency_penalty = 1.0
        if min_rtt < self.SHORT_PATH_RTT_MS and inflation_ratio > self.HIGH_INFLATION_RATIO:
            latency_penalty = self.SHORT_PATH_INFLATION_PENALTY

        return {
            "rtt_feasible": True,
            "rtt_score": float(rtt_score),
            "rtt_margin_ms": float(rtt_margin_ms),
            "latency_penalty": float(latency_penalty),
        }

    def _lookup_relationship(self, asn_a: str, asn_b: str) -> Optional[int]:
        return self.as_relationship.get((asn_a, asn_b))

    def _owner_neighbor_exists(self, endpoint_asn: str, cable_owner_asns: Set[str]) -> bool:
        for owner_asn in cable_owner_asns:
            if self._lookup_relationship(endpoint_asn, owner_asn) is not None:
                return True
        return False

    def _lookup_precomputed_owner_path(self, endpoint_asn: str, owner_group_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Lookup precomputed endpoint-to-owner-group reachability."""
        if owner_group_id is None:
            return None

        node_id = self.as_precompute_asn_to_id.get(normalize_asn_value(endpoint_asn))
        if node_id is None:
            return None

        reachability = self.owner_group_reachability.get(owner_group_id)
        if not reachability:
            return None

        path_info = reachability.get(node_id)
        if path_info is None:
            return None

        path_cost, path_hops = path_info
        return {
            "path_cost": float(path_cost),
            "path_hops": int(path_hops),
        }

    def _legacy_as_economic_support(
        self,
        src: str,
        dst: str,
        owner_asns: Set[str],
    ) -> Dict[str, Any]:
        """Fallback relationship-cost model used when no precompute lookup is available."""
        if src == "-1" or dst == "-1":
            cost = self.AS_GRAPH_UNKNOWN_COST
            reason = "unknown"
        elif src in owner_asns and dst in owner_asns:
            cost = 0.0
            reason = "self_or_both_owner"
        elif src in owner_asns or dst in owner_asns:
            cost = 0.25
            reason = "one_endpoint_owner"
        else:
            rel_type = self._lookup_relationship(src, dst)
            if rel_type == 0:
                cost = 1.0
                reason = "peer_relationship"
            elif rel_type in {1, -1}:
                cost = 2.0
                reason = "provider_customer_relationship"
            elif self._owner_neighbor_exists(src, owner_asns) or self._owner_neighbor_exists(dst, owner_asns):
                cost = 3.0
                reason = "owner_neighbor_relationship"
            else:
                cost = self.AS_GRAPH_UNKNOWN_COST
                reason = "unknown"

        return {
            "as_economic_score": float(math.exp(-self.LAMBDA_AS * cost)),
            "as_economic_cost": float(cost),
            "as_economic_reason": reason,
            "as_economic_src_owner_hops": None,
            "as_economic_dst_owner_hops": None,
            "as_economic_src_owner_path_cost": None,
            "as_economic_dst_owner_path_cost": None,
            "as_economic_path_found": False,
            "as_economic_owner_group_id": None,
        }

    def compute_as_economic_support(
        self,
        src_asn: str,
        dst_asn: str,
        cable_owner_asns: Set[str],
    ) -> Dict[str, Any]:
        """AS-economic Core using precomputed owner-group reachability when available."""
        src = normalize_asn_value(src_asn)
        dst = normalize_asn_value(dst_asn)
        owner_asns = {normalize_asn_value(asn) for asn in cable_owner_asns if normalize_asn_value(asn) != "-1"}
        owner_signature = owner_group_signature(owner_asns)
        owner_group_id = self.owner_group_signatures.get(owner_signature) if owner_signature else None

        if not owner_asns:
            return self._legacy_as_economic_support(src, dst, owner_asns)

        if src in owner_asns and dst in owner_asns:
            cost = 0.0
            reason = "self_or_both_owner"
            src_path = {"path_cost": 0.0, "path_hops": 0}
            dst_path = {"path_cost": 0.0, "path_hops": 0}
        elif src in owner_asns or dst in owner_asns:
            cost = 0.25
            reason = "one_endpoint_owner"
            src_path = {"path_cost": 0.0, "path_hops": 0} if src in owner_asns else None
            dst_path = {"path_cost": 0.0, "path_hops": 0} if dst in owner_asns else None
        elif self.as_graph_precompute_loaded and owner_group_id is not None:
            src_path = self._lookup_precomputed_owner_path(src, owner_group_id)
            dst_path = self._lookup_precomputed_owner_path(dst, owner_group_id)
            valid_paths = [
                path_info
                for path_info in (src_path, dst_path)
                if path_info is not None and path_info["path_hops"] <= self.as_graph_max_hops_unknown
            ]

            if len(valid_paths) == 2:
                cost = (valid_paths[0]["path_cost"] + valid_paths[1]["path_cost"]) / 2.0
                reason = "owner_group_path_both_endpoints"
            elif len(valid_paths) == 1:
                cost = valid_paths[0]["path_cost"] + self.AS_GRAPH_ONE_SIDED_PENALTY
                reason = "owner_group_path_one_endpoint"
            elif (src_path is not None and src_path["path_hops"] > self.as_graph_max_hops_unknown) or (
                dst_path is not None and dst_path["path_hops"] > self.as_graph_max_hops_unknown
            ):
                cost = self.AS_GRAPH_UNKNOWN_COST
                reason = "owner_group_path_exceeds_max_hops"
            else:
                cost = self.AS_GRAPH_UNKNOWN_COST
                reason = "unknown"
        else:
            return self._legacy_as_economic_support(src, dst, owner_asns)

        as_economic_score = math.exp(-self.LAMBDA_AS * cost)
        return {
            "as_economic_score": float(as_economic_score),
            "as_economic_cost": float(cost),
            "as_economic_reason": reason,
            "as_economic_src_owner_hops": None if src_path is None else int(src_path["path_hops"]),
            "as_economic_dst_owner_hops": None if dst_path is None else int(dst_path["path_hops"]),
            "as_economic_src_owner_path_cost": None if src_path is None else float(src_path["path_cost"]),
            "as_economic_dst_owner_path_cost": None if dst_path is None else float(dst_path["path_cost"]),
            "as_economic_path_found": bool(
                (src_path is not None and src_path["path_hops"] <= self.as_graph_max_hops_unknown)
                or (dst_path is not None and dst_path["path_hops"] <= self.as_graph_max_hops_unknown)
            ),
            "as_economic_owner_group_id": owner_group_id,
        }

    def asRelationship_prob_calculation(self, asn1: str, asn2: str, cable_owners: Set[str]) -> float:
        """Deprecated compatibility wrapper around the AS-economic Core."""
        return self.compute_as_economic_support(asn1, asn2, cable_owners)["as_economic_score"]

    def fuse_candidate_support(
        self,
        geo_score: float,
        as_score: float,
        rtt_score: float,
        latency_penalty: float,
    ) -> float:
        """Dual-core Evidence Fusion via a product-of-experts style combination."""
        geo_term = max(geo_score, 0.0) ** self.FUSION_ALPHA
        as_term = max(as_score, 0.0) ** self.FUSION_BETA
        rtt_term = max(rtt_score, 0.0) ** self.FUSION_GAMMA
        return float(geo_term * as_term * rtt_term * max(latency_penalty, 0.0))

    def classify_core_agreement(self, geo_score: float, as_score: float) -> str:
        """Classify whether the Geo-spatial Core and AS-economic Core agree."""
        if geo_score >= self.CORE_STRONG_THRESHOLD and as_score >= self.CORE_STRONG_THRESHOLD:
            return "dual_core_agreement"
        if geo_score >= self.CORE_STRONG_THRESHOLD and as_score < self.CORE_WEAK_THRESHOLD:
            return "geo_dominant_as_weak"
        if as_score >= self.CORE_STRONG_THRESHOLD and geo_score < self.CORE_WEAK_THRESHOLD:
            return "as_dominant_geo_ambiguous"
        if abs(geo_score - as_score) <= 0.15 and min(geo_score, as_score) >= 0.45:
            return "dual_core_agreement"
        return "weak_dual_evidence"

    def build_ambiguity_tags(
        self,
        candidate: Dict[str, Any],
        filtered_candidate_count: int,
        segment_candidate_count: int,
    ) -> List[str]:
        """Attach lightweight ambiguity tags to a candidate."""
        tags: List[str] = []
        if segment_candidate_count > 1:
            tags.append("parallel_candidate_corridor")
        if filtered_candidate_count > self.MANY_CANDIDATES_THRESHOLD:
            tags.append("many_candidates")
        if candidate["d_in"] > self.LARGE_LANDING_RADIUS_KM or candidate["d_out"] > self.LARGE_LANDING_RADIUS_KM:
            tags.append("large_landing_radius")
        if candidate["rtt_margin_ms"] < self.RTT_INCONCLUSIVE_MARGIN_MS:
            tags.append("rtt_inconclusive")
        if candidate["core_agreement"] in {"geo_dominant_as_weak", "as_dominant_geo_ambiguous"}:
            tags.append(candidate["core_agreement"])
        if candidate["country_a"] and candidate["country_a"] == candidate["country_b"]:
            tags.append("domestic_submarine_candidate")
        if (
            candidate["ls_entry_to_ls_exit_gcd_km"] > self.MULTI_SEGMENT_GCD_THRESHOLD_KM
            and candidate["rtt_margin_ms"] > self.MULTI_SEGMENT_MARGIN_THRESHOLD_MS
        ):
            tags.append("multi_segment_possible")
        return tags

    def normalize_candidate_supports(self, candidates: List[Dict[str, Any]]) -> float:
        """Normalize candidate support inside a single link."""
        support_sum = sum(max(candidate["candidate_support"], 0.0) for candidate in candidates)
        if support_sum <= 0:
            for candidate in candidates:
                candidate["normalized_candidate_support"] = 0.0
            return 0.0

        for candidate in candidates:
            candidate["normalized_candidate_support"] = float(candidate["candidate_support"] / support_sum)
        return float(support_sum)

    def _assign_rank(self, candidates: List[Dict[str, Any]], key: str, target_key: str) -> None:
        ranking = sorted(
            enumerate(candidates),
            key=lambda item: item[1].get(key, 0.0),
            reverse=True,
        )
        for rank, (index, _) in enumerate(ranking, start=1):
            candidates[index][target_key] = rank

    def assign_candidate_ranks(self, candidates: List[Dict[str, Any]]) -> None:
        """Assign fused, geo-only, as-only, and dual-core ranks."""
        self._assign_rank(candidates, "fused_candidate_support", "candidate_rank_by_fused_support")
        self._assign_rank(candidates, "geo_spatial_score", "geo_only_rank")
        self._assign_rank(candidates, "as_economic_score", "as_only_rank")

        agreement_priority = {
            "dual_core_agreement": 3,
            "geo_dominant_as_weak": 2,
            "as_dominant_geo_ambiguous": 1,
            "weak_dual_evidence": 0,
        }
        ranking = sorted(
            enumerate(candidates),
            key=lambda item: (
                agreement_priority.get(item[1].get("core_agreement", "weak_dual_evidence"), 0),
                item[1].get("fused_candidate_support", 0.0),
            ),
            reverse=True,
        )
        for rank, (index, _) in enumerate(ranking, start=1):
            candidates[index]["dual_core_rank"] = rank

        top_support = candidates[0]["candidate_support"] if candidates else 0.0
        for candidate in candidates:
            candidate["candidate_rank"] = candidate["candidate_rank_by_fused_support"]  # deprecated compatibility
            candidate["score_gap_to_top1"] = float(top_support - candidate["candidate_support"])

    def build_core_agreement_summary(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize core agreement categories across filtered candidates."""
        counts = {
            "dual_core_agreement": 0,
            "geo_dominant_as_weak": 0,
            "as_dominant_geo_ambiguous": 0,
            "weak_dual_evidence": 0,
        }
        for candidate in candidates:
            counts[candidate["core_agreement"]] = counts.get(candidate["core_agreement"], 0) + 1
        dominant = candidates[0]["core_agreement"] if candidates else "none"
        counts["dominant_core_agreement"] = dominant
        return counts

    def build_ambiguity_summary(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize ambiguity tags across filtered candidates."""
        tag_counts: Dict[str, int] = {}
        for candidate in candidates:
            for tag in candidate.get("ambiguity_tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return {
            "tags_present": sorted(tag_counts.keys()),
            "tag_counts": tag_counts,
            "num_ambiguous_candidates": sum(1 for candidate in candidates if candidate.get("ambiguity_tags")),
        }

    def _link_info_summary(self, filtered_candidates: List[Dict[str, Any]]) -> None:
        if not filtered_candidates:
            return
        self.candidate_count_per_matched_link.append(len(filtered_candidates))
        if any(candidate["core_agreement"] == "dual_core_agreement" for candidate in filtered_candidates):
            self.stats["links_with_dual_core_agreement"] += 1
        if any(candidate["core_agreement"] == "geo_dominant_as_weak" for candidate in filtered_candidates):
            self.stats["links_with_geo_dominant_as_weak"] += 1
        if any(candidate["core_agreement"] == "as_dominant_geo_ambiguous" for candidate in filtered_candidates):
            self.stats["links_with_as_dominant_geo_ambiguous"] += 1
        if any("parallel_candidate_corridor" in candidate["ambiguity_tags"] for candidate in filtered_candidates):
            self.stats["links_with_parallel_ambiguity"] += 1
        if any("many_candidates" in candidate["ambiguity_tags"] for candidate in filtered_candidates):
            self.stats["links_with_many_candidates"] += 1
        if any("domestic_submarine_candidate" in candidate["ambiguity_tags"] for candidate in filtered_candidates):
            self.stats["links_with_domestic_candidates"] += 1

    def match_link_to_cable(self, link: Dict[str, Any]) -> Dict[str, Any]:
        """Match a single hop-pair link to a candidate physical-support distribution."""
        self.stats["total_links_seen"] += 1

        hop_a = link["source"]
        hop_b = link["destination"]
        measured_rtt_delta = link["rtt_delta"]

        city_a = hop_a["geo"].get("city")
        city_b = hop_b["geo"].get("city")
        country_a = hop_a["geo"].get("country")
        country_b = hop_b["geo"].get("country")

        if city_a and city_b and country_a and country_b and city_a == city_b and country_a == country_b:
            self.stats["same_city_filtered"] += 1
            return {
                "all_segments": [],
                "match_summary": {
                    "filtered_reason": "same_city",
                    "num_candidates_total": 0,
                    "num_candidates_above_threshold": 0,
                    "support_sum": 0.0,
                    "top1_candidate_support": 0.0,
                    "top2_candidate_support": 0.0,
                    "top1_top2_gap": 0.0,
                    "confidence_bucket": "none",
                    "core_agreement_summary": {"dominant_core_agreement": "none"},
                    "ambiguity_summary": {"tags_present": [], "tag_counts": {}, "num_ambiguous_candidates": 0},
                    "top1_score": 0.0,
                    "top2_score": 0.0,
                },
            }

        candidates: List[Dict[str, Any]] = []
        had_segment_candidates = False
        rtt_feasible_candidate_found = False
        radius_rad = self.LS_CATCHMENT_RADIUS_KM / self.R_EARTH
        hop_a_loc = (np.radians(hop_a["geo"]["lat"]), np.radians(hop_a["geo"]["lon"]))
        hop_b_loc = (np.radians(hop_b["geo"]["lat"]), np.radians(hop_b["geo"]["lon"]))

        idx_a_list = self.ls_tree.query_radius([hop_a_loc], r=radius_rad)[0]
        idx_b_list = self.ls_tree.query_radius([hop_b_loc], r=radius_rad)[0]

        if len(idx_a_list) > 0 and len(idx_b_list) > 0:
            self.stats["links_with_ls_candidates"] += 1
            self.stats["links_with_geo_candidates"] += 1

        entries_a = []
        for index in idx_a_list:
            ls_id = self.ls_id_map[index]
            d_in = geodesic((hop_a["geo"]["lat"], hop_a["geo"]["lon"]), self.ls_coord_map[ls_id]).km
            entries_a.append((ls_id, d_in))

        entries_b = []
        for index in idx_b_list:
            ls_id = self.ls_id_map[index]
            d_out = geodesic((hop_b["geo"]["lat"], hop_b["geo"]["lon"]), self.ls_coord_map[ls_id]).km
            entries_b.append((ls_id, d_out))

        asn_a = self.IP2ASN(link["ips"][0])
        asn_b = self.IP2ASN(link["ips"][1])

        for ls_a_id, d_in in entries_a:
            for ls_b_id, d_out in entries_b:
                if ls_a_id == ls_b_id:
                    continue

                segment_key = tuple(sorted((ls_a_id, ls_b_id)))
                segment_cables = self.segment_to_cables.get(segment_key)
                if not segment_cables:
                    continue
                had_segment_candidates = True

                geo_score_info = self.compute_geo_spatial_score(d_in=d_in, d_out=d_out)

                for cable_info in segment_cables:
                    self.stats["candidate_segments_considered"] += 1

                    gcd_dist = cable_info["gcd_dist"]
                    est_fiber_len = gcd_dist * self.SLACK_FACTOR
                    min_rtt = (est_fiber_len * 2) / self.SOL_FIBER_KM_MS
                    rtt_score_info = self.compute_rtt_feasibility_score(measured_rtt_delta=measured_rtt_delta, min_rtt=min_rtt)
                    if not rtt_score_info["rtt_feasible"]:
                        self.stats["rtt_infeasible_filtered"] += 1
                        continue
                    rtt_feasible_candidate_found = True

                    cable_owner_asns: Set[str] = set(cable_info.get("cable_owner_asns", set()))

                    as_support_info = self.compute_as_economic_support(
                        src_asn=asn_a,
                        dst_asn=asn_b,
                        cable_owner_asns=cable_owner_asns,
                    )

                    if min(geo_score_info["geo_entry_score"], geo_score_info["geo_exit_score"]) >= 0.9:
                        as_support_info["as_economic_score"] = max(as_support_info["as_economic_score"], 0.8)

                    fused_candidate_support = self.fuse_candidate_support(
                        geo_score=geo_score_info["geo_spatial_score"],
                        as_score=as_support_info["as_economic_score"],
                        rtt_score=rtt_score_info["rtt_score"],
                        latency_penalty=rtt_score_info["latency_penalty"],
                    )
                    core_agreement = self.classify_core_agreement(
                        geo_score=geo_score_info["geo_spatial_score"],
                        as_score=as_support_info["as_economic_score"],
                    )

                    candidate = {
                        "cable_name": cable_info["cable_name"],
                        "cable_id": cable_info["cable_id"],
                        "segment": f"{ls_a_id} -> {ls_b_id}",
                        "landing_pair": f"{ls_a_id} -> {ls_b_id}",
                        "candidate_support": float(fused_candidate_support),
                        "fused_candidate_support": float(fused_candidate_support),
                        "normalized_candidate_support": 0.0,
                        "geo_spatial_score": float(geo_score_info["geo_spatial_score"]),
                        "geo_entry_score": float(geo_score_info["geo_entry_score"]),
                        "geo_exit_score": float(geo_score_info["geo_exit_score"]),
                        "prob_in": float(geo_score_info["prob_in"]),
                        "prob_out": float(geo_score_info["prob_out"]),
                        "d_in": float(d_in),
                        "d_out": float(d_out),
                        "ls_entry_to_ls_exit_gcd_km": float(gcd_dist),
                        "as_economic_score": float(as_support_info["as_economic_score"]),
                        "as_economic_cost": float(as_support_info["as_economic_cost"]),
                        "as_economic_reason": as_support_info["as_economic_reason"],
                        "as_economic_support": float(as_support_info["as_economic_score"]),
                        "as_economic_src_owner_hops": as_support_info.get("as_economic_src_owner_hops"),
                        "as_economic_dst_owner_hops": as_support_info.get("as_economic_dst_owner_hops"),
                        "as_economic_src_owner_path_cost": as_support_info.get("as_economic_src_owner_path_cost"),
                        "as_economic_dst_owner_path_cost": as_support_info.get("as_economic_dst_owner_path_cost"),
                        "as_economic_path_found": bool(as_support_info.get("as_economic_path_found", False)),
                        "as_economic_owner_group_id": as_support_info.get("as_economic_owner_group_id"),
                        "src_asn": asn_a,
                        "dst_asn": asn_b,
                        "owner_asn_count": len(cable_owner_asns),
                        "rtt_feasible": True,
                        "rtt_score": float(rtt_score_info["rtt_score"]),
                        "min_rtt_ms": float(min_rtt),
                        "measured_rtt_ms": float(measured_rtt_delta),
                        "rtt_margin_ms": float(rtt_score_info["rtt_margin_ms"]),
                        "latency_penalty": float(rtt_score_info["latency_penalty"]),
                        "core_agreement": core_agreement,
                        "candidate_rank_by_fused_support": 0,
                        "geo_only_rank": 0,
                        "as_only_rank": 0,
                        "dual_core_rank": 0,
                        "ambiguity_tags": [],
                        "city_a": city_a,
                        "city_b": city_b,
                        "country_a": country_a,
                        "country_b": country_b,
                        "geo-a": (
                            float(f"{hop_a['geo']['lat']:.4f}"),
                            float(f"{hop_a['geo']['lon']:.4f}"),
                        ),
                        "geo-b": (
                            float(f"{hop_b['geo']['lat']:.4f}"),
                            float(f"{hop_b['geo']['lon']:.4f}"),
                        ),
                        "parallel_segment_candidate_count": len(segment_cables),
                        "dual_core_agreement": core_agreement == "dual_core_agreement",
                        "deprecated_fields": [
                            "segment_probability",
                            "geo_score",
                            "ownership_score",
                        ],
                    }

                    # Deprecated compatibility fields retained for downstream readers.
                    candidate["segment_probability"] = candidate["candidate_support"]
                    candidate["geo_score"] = candidate["geo_spatial_score"]
                    candidate["ownership_score"] = candidate["as_economic_score"]

                    candidates.append(candidate)

        self.stats["total_candidates_generated"] += len(candidates)
        if had_segment_candidates and not rtt_feasible_candidate_found:
            self.stats["links_with_no_feasible_rtt_candidate"] += 1

        if not candidates:
            return {
                "all_segments": [],
                "match_summary": {
                    "filtered_reason": "no_candidate",
                    "num_candidates_total": 0,
                    "num_candidates_above_threshold": 0,
                    "support_sum": 0.0,
                    "top1_candidate_support": 0.0,
                    "top2_candidate_support": 0.0,
                    "top1_top2_gap": 0.0,
                    "confidence_bucket": "none",
                    "core_agreement_summary": {"dominant_core_agreement": "none"},
                    "ambiguity_summary": {"tags_present": [], "tag_counts": {}, "num_ambiguous_candidates": 0},
                    "top1_score": 0.0,
                    "top2_score": 0.0,
                },
            }

        sorted_candidates = sorted(candidates, key=lambda item: item.get("candidate_support", 0.0), reverse=True)
        deduplicated_candidates: Dict[str, Dict[str, Any]] = {}
        unique_candidates: List[Dict[str, Any]] = []
        for candidate in sorted_candidates:
            cable_id = candidate["cable_id"]
            if cable_id not in deduplicated_candidates:
                deduplicated_candidates[cable_id] = candidate
                unique_candidates.append(candidate)

        filtered_candidates = [
            candidate for candidate in unique_candidates if candidate.get("candidate_support", 0.0) >= self.MATCH_THRESHOLD
        ]
        if unique_candidates and not filtered_candidates:
            self.stats["links_below_threshold"] += 1

        self.stats["candidates_above_threshold"] += len(filtered_candidates)
        self.stats["total_candidates_after_threshold"] += len(filtered_candidates)
        if filtered_candidates:
            self.stats["links_with_any_match"] += 1
            self.stats["links_with_filtered_candidates"] += 1

        support_sum = self.normalize_candidate_supports(filtered_candidates)
        self.assign_candidate_ranks(filtered_candidates)

        for candidate in filtered_candidates:
            candidate["ambiguity_tags"] = self.build_ambiguity_tags(
                candidate=candidate,
                filtered_candidate_count=len(filtered_candidates),
                segment_candidate_count=candidate["parallel_segment_candidate_count"],
            )

        self._link_info_summary(filtered_candidates)

        top1 = filtered_candidates[0]["candidate_support"] if filtered_candidates else 0.0
        top2 = filtered_candidates[1]["candidate_support"] if len(filtered_candidates) > 1 else 0.0
        gap = top1 - top2

        if top1 >= self.HIGH_CONF_THRESHOLD and gap >= self.HIGH_GAP_THRESHOLD:
            bucket = "high"
        elif top1 >= self.MEDIUM_CONF_THRESHOLD and gap >= self.MEDIUM_GAP_THRESHOLD:
            bucket = "medium"
        elif filtered_candidates:
            bucket = "ambiguous"
        else:
            bucket = "none"

        core_agreement_summary = self.build_core_agreement_summary(filtered_candidates)
        ambiguity_summary = self.build_ambiguity_summary(filtered_candidates)

        return {
            "all_segments": filtered_candidates,
            "match_summary": {
                "filtered_reason": None if filtered_candidates else "below_threshold",
                "num_candidates_total": len(unique_candidates),
                "num_candidates_above_threshold": len(filtered_candidates),
                "support_sum": float(support_sum),
                "top1_candidate_support": float(top1),
                "top2_candidate_support": float(top2),
                "top1_top2_gap": float(gap),
                "confidence_bucket": bucket,
                "core_agreement_summary": core_agreement_summary,
                "ambiguity_summary": ambiguity_summary,
                "top1_score": float(top1),  # deprecated compatibility
                "top2_score": float(top2),  # deprecated compatibility
            },
        }


def output_debug_cable_info(ls_coords: Dict[str, Tuple[float, float]], cables: List[Dict[str, Any]], path: str) -> None:
    """Write landing-station and cable metadata to a debug file."""
    debug_data = {
        "landing_station_count": len(ls_coords),
        "submarine_cable_count": len(cables),
        "landing_station_sample": {key: value for index, (key, value) in enumerate(ls_coords.items()) if index < 5},
        "submarine_cable_sample": cables[:2],
        "all_cables": cables,
    }

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(debug_data, handle, ensure_ascii=False, indent=4)
        print(f"Saved cable/landing-station debug info to: {path}")
    except Exception as exc:
        print(f"Failed to write debug file: {exc}")


def to_repo_relative_path(path: str) -> str:
    try:
        return os.path.relpath(path, BASE_DIR)
    except Exception:
        return path


def write_match_manifest(
    traceroute_file_paths: List[str],
    total_files_processed: int,
    total_traces_processed: int,
    empty_trace_count: int,
    valid_link_count: int,
    as_precompute_file: Optional[str],
    path: str,
) -> None:
    """Write a manifest describing the processed traceroute inputs and outputs."""
    manifest = {
        "traceroute_file_paths": [to_repo_relative_path(path_item) for path_item in traceroute_file_paths],
        "total_files_processed": total_files_processed,
        "total_traces_processed": total_traces_processed,
        "empty_trace_count": empty_trace_count,
        "matched_links_above_threshold": valid_link_count,
        "match_output_file": to_repo_relative_path(OUTPUT_RESULTS_PATH),
        "match_stats_file": to_repo_relative_path(MATCH_STATS_OUTPUT_PATH),
        "as_precompute_file": to_repo_relative_path(as_precompute_file) if as_precompute_file else None,
        "method_profile": "dual_core_cross_layer_evidence_fusion",
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def load_all_traceroute_files(directory: str) -> List[str]:
    """Walk the traceroute directory and return eligible JSON files."""
    traceroute_files: List[str] = []
    if not os.path.exists(directory):
        print(f"Warning: traceroute directory does not exist: {directory}")
        return []

    for root, _, files in os.walk(directory):
        for filename in files:
            if not filename.endswith(".json"):
                continue
            if any(filename.endswith(suffix) for suffix in TRACEROUTE_EXCLUSIONS):
                continue
            traceroute_files.append(os.path.join(root, filename))

    user_uploaded_files = [
        "ripe_atlas_msm_104851959_traceroute_A-Root.json",
        "2africa.json",
    ]
    existing_basenames = {os.path.basename(path) for path in traceroute_files}
    for filename in user_uploaded_files:
        candidate_path = os.path.join(BASE_DIR, filename)
        if os.path.exists(candidate_path) and filename not in existing_basenames:
            traceroute_files.append(candidate_path)
    return traceroute_files


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the main candidate-support analysis stage."""
    parser = argparse.ArgumentParser(
        description="Run the cable candidate-support analysis with optional AS-graph precompute input."
    )
    parser.add_argument(
        "--as-precompute-file",
        default=AS_GRAPH_PRECOMPUTE_PATH,
        help="Optional precomputed AS-graph owner reachability file produced by precompute_as_graph.py.",
    )
    return parser.parse_args()


def main() -> None:
    """Process traceroute links and emit candidate-support outputs."""
    args = parse_args()

    try:
        ls_coordinates = load_ls_coordinates(LS_GEO_PATH)
        all_cables = load_all_cables(CABLE_DIR)
        as_relationship = load_as_relationship(ASREL_PATH)
        pfx2as_trie = load_pfx2as_mapping(PFX2AS_PATH)
        owner2asn = load_owner2asn_mapping(OWNER2ASN_PATH)
        as_graph_precompute = load_as_graph_precompute(args.as_precompute_file)
    except (FileNotFoundError, ValueError) as exc:
        print("--- Critical error: failed to load required input files ---")
        print(str(exc))
        return

    output_debug_cable_info(ls_coordinates, all_cables, CABLE_DEBUG_OUTPUT_PATH)
    matcher = CableMatcher(
        all_cables,
        ls_coordinates,
        as_relationship,
        pfx2as_trie,
        owner2asn,
        as_graph_precompute=as_graph_precompute,
    )
    traceroute_file_paths = load_all_traceroute_files(TRACE_DIR)

    print("\n--- Candidate-support matching task started ---")
    print(f"Identified {len(traceroute_file_paths)} traceroute files.")
    print(f"Incremental output will be written to: {OUTPUT_RESULTS_PATH}")
    if matcher.as_graph_precompute_loaded:
        print(f"Using AS-graph precompute file: {args.as_precompute_file}")
    else:
        print("Using legacy AS-economic fallback because no AS-graph precompute file was loaded.")
    print("---------------------------------------------")

    valid_link_count = 0
    total_files_processed = 0
    total_traces_processed = 0
    empty_trace_count = 0
    is_first_entry = True

    try:
        os.makedirs(os.path.dirname(OUTPUT_RESULTS_PATH), exist_ok=True)

        with maxminddb.open_database(MMDB_PATH) as mmdb_reader:
            with open(OUTPUT_RESULTS_PATH, "w", encoding="utf-8") as output_file:
                output_file.write("[\n")

                with tqdm(
                    desc="Processing traceroute records",
                    unit=" trace",
                    dynamic_ncols=True,
                    mininterval=10.0,
                    miniters=5000,
                ) as progress:
                    for traceroute_path in traceroute_file_paths:
                        total_files_processed += 1
                        file_name = os.path.basename(traceroute_path)

                        for raw_result in iter_traceroute_results(traceroute_path):
                            total_traces_processed += 1
                            progress.update(1)

                            hops = raw_result.get("result", [])
                            if not hops:
                                empty_trace_count += 1
                                continue

                            traceroute_links = parse_hops_to_links(
                                hops=hops,
                                msm_id=raw_result.get("msm_id", "N/A"),
                                prb_id=raw_result.get("prb_id", "N/A"),
                                timestamp=raw_result.get("endtime", raw_result.get("timestamp", "N/A")),
                                file_name=file_name,
                                mmdb_reader=mmdb_reader,
                            )

                            for link in traceroute_links:
                                match_output = matcher.match_link_to_cable(link)
                                all_segments = match_output["all_segments"]
                                match_summary = match_output["match_summary"]

                                if not all_segments:
                                    continue

                                valid_link_count += 1
                                link_info = {
                                    "msm_id": link.get("measurement_id", "N/A"),
                                    "probe_id": link.get("probe_id", "N/A"),
                                    "file_name": link.get("file_name", file_name),
                                    "timestamp": link.get("timestamp", "N/A"),
                                    "hop_range": f"Hop {link['source']['hop_num']} -> {link['destination']['hop_num']}",
                                    "src_ip": link["source"]["ip"],
                                    "dst_ip": link["destination"]["ip"],
                                    "src_city": link["source"]["geo"].get("city"),
                                    "dst_city": link["destination"]["geo"].get("city"),
                                    "src_country": link["source"]["geo"]["country"],
                                    "dst_country": link["destination"]["geo"]["country"],
                                    "rtt_delta_ms": link["rtt_delta"],
                                    "is_potential_oceanic": link["is_oceanic"],
                                }
                                match_result = {
                                    "link_info": link_info,
                                    "match_summary": match_summary,
                                    "all_segments": all_segments,
                                }

                                if not is_first_entry:
                                    output_file.write(",\n")
                                json.dump(match_result, output_file, ensure_ascii=False, indent=4)
                                is_first_entry = False

                output_file.write("\n]\n")

        finalized_stats = matcher.finalize_stats()
        with open(MATCH_STATS_OUTPUT_PATH, "w", encoding="utf-8") as stats_file:
            json.dump(finalized_stats, stats_file, ensure_ascii=False, indent=4)

        write_match_manifest(
            traceroute_file_paths=traceroute_file_paths,
            total_files_processed=total_files_processed,
            total_traces_processed=total_traces_processed,
            empty_trace_count=empty_trace_count,
            valid_link_count=valid_link_count,
            as_precompute_file=args.as_precompute_file if matcher.as_graph_precompute_loaded else None,
            path=MATCH_MANIFEST_OUTPUT_PATH,
        )
    except Exception as exc:
        print(f"\nFailed while writing result files: {exc}")
        return

    print(f"\nCompleted matching across {total_files_processed} traceroute files.")
    print(f"Processed {total_traces_processed} traceroute records.")
    print(f"Empty/invalid traceroute records: {empty_trace_count}")
    print(f"Matched {valid_link_count} links above threshold (>= {matcher.MATCH_THRESHOLD}).")
    print(f"Results saved to: {OUTPUT_RESULTS_PATH}")
    print(f"Stats saved to: {MATCH_STATS_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
