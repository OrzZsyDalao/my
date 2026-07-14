import argparse
import gzip
import hashlib
import ipaddress
import json
import math
import os
import pickle
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

import maxminddb
import numpy as np
import pandas as pd
try:
    import pytricia
except ImportError:
    pytricia = None
from sklearn.neighbors import BallTree
from tqdm import tqdm

from measurement_catalog import lookup_measurement


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
PROBE_DIR = os.path.join(DATA_DIR, "probe")

LS_GEO_PATH = os.path.join(CABLE_DIR, "landing-point-geo.json")
MMDB_PATH = os.path.join(IPINFO_DIR, "ipinfo_location.mmdb")
ASN_MMDB_PATH = os.path.join(IPINFO_DIR, "ipinfo_asn.mmdb")
ASREL_PATH = os.path.join(ASREL_DIR, "20250901.as-rel2.txt")
PFX2AS_PATH = os.path.join(PFX2AS_DIR, "202512.pfx2as")
OWNER2ASN_PATH = os.path.join(OWNER2ASN_DIR, "owner_to_asn.csv")
PROBE_META_PATH = os.path.join(PROBE_DIR, "20251201.json")

CABLE_DEBUG_OUTPUT_PATH = os.path.join(BASE_DIR, "cable_loading_debug.json")
OUTPUT_RESULTS_PATH = os.path.join(OUTPUT_DIR, "cable_matching_output.json")
MATCH_STATS_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "cable_matching_stats_5051.json")
MATCH_MANIFEST_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "cable_matching_manifest.json")
AS_GRAPH_PRECOMPUTE_PATH = os.path.join(PREPROCESSED_DIR, "as_graph_owner_reachability.pkl.gz")

TRACEROUTE_EXCLUSIONS = ("_result.json", "_geo.json", "_analysis.json")
CABLE_EXCLUSION_FILE = "landing-point-geo.json"
EARTH_RADIUS_KM = 6371.0


def haversine_km(point_a: Tuple[float, float], point_b: Tuple[float, float]) -> float:
    """Return spherical great-circle distance in kilometres for pipeline filtering."""
    lat_a, lon_a = math.radians(point_a[0]), math.radians(point_a[1])
    lat_b, lon_b = math.radians(point_b[0]), math.radians(point_b[1])
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    haversine_term = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return float(2.0 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(haversine_term))))


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


def parse_loose_date(value: Any) -> Optional[datetime]:
    """Parse common cable lifecycle date/year values into a UTC datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        year = int(value)
        if 1800 <= year <= 3000:
            return datetime(year, 1, 1, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "unknown"}:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y %B", "%Y %b", "%B %Y", "%b %Y", "%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    for token in text.replace(",", " ").split():
        if token.isdigit() and len(token) == 4:
            year = int(token)
            if 1800 <= year <= 3000:
                return datetime(year, 1, 1, tzinfo=timezone.utc)
    return None


def parse_trace_datetime(value: Any) -> Optional[datetime]:
    """Parse RIPE Atlas timestamp/endtime values into UTC datetimes."""
    if value in (None, "", "N/A"):
        return None
    try:
        numeric = float(value)
        if numeric > 0:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        pass
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def is_cable_available_at(
    cable: Dict[str, Any],
    trace_timestamp: Any,
    mode: str = "confirmed_active_only",
    trace_datetime: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Evaluate cable lifecycle availability for a trace timestamp.

    Unknown lifecycle metadata is retained but explicitly marked so old cable
    datasets remain compatible.
    """
    trace_dt = trace_datetime if trace_datetime is not None else parse_trace_datetime(trace_timestamp)
    rfs_date = cable.get("rfs_date_parsed") or parse_loose_date(
        cable.get("rfs_date") or cable.get("rfs") or cable.get("rfs_year")
    )
    retired_date = cable.get("retired_date_parsed") or parse_loose_date(cable.get("retired_date"))
    is_planned = bool(cable.get("is_planned", False))
    retired = bool(cable.get("retired", False))
    status = str(cable.get("status") or "").strip().lower()
    availability_status = "active_unknown_date"
    passed = True

    if is_planned and (rfs_date is None or (trace_dt is not None and rfs_date > trace_dt)):
        availability_status = "planned_not_rfs_at_trace_time"
        passed = False
    elif rfs_date is not None and trace_dt is not None and rfs_date > trace_dt:
        availability_status = "rfs_after_trace_time"
        passed = False
    elif retired_date is not None and trace_dt is not None and retired_date <= trace_dt:
        availability_status = "retired_before_trace_time"
        passed = False
    elif retired and retired_date is None:
        availability_status = "retired_unknown_date"
        passed = False
    elif "planned" in status and (rfs_date is None or (trace_dt is not None and rfs_date > trace_dt)):
        availability_status = "planned_status_not_rfs_at_trace_time"
        passed = False
    elif "retired" in status or "decommission" in status:
        availability_status = "retired_status"
        passed = False
    elif rfs_date is None and not is_planned and not retired:
        availability_status = "unknown"
        passed = False
    else:
        availability_status = "confirmed_active_at_trace_time"
        passed = True

    if mode == "confirmed_active_plus_unknown" and availability_status == "unknown":
        passed = True
    return {
        "availability_filter_passed": bool(passed),
        "cable_availability_status": availability_status,
        "cable_rfs_date": rfs_date.date().isoformat() if rfs_date else None,
        "cable_retired_date": retired_date.date().isoformat() if retired_date else None,
        "cable_status": cable.get("status"),
    }


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
                    "rfs": cable_data.get("rfs"),
                    "rfs_year": cable_data.get("rfs_year"),
                    "rfs_date": cable_data.get("rfs_date"),
                    "is_planned": cable_data.get("is_planned", False),
                    "status": cable_data.get("status"),
                    "retired": cable_data.get("retired", False),
                    "retired_date": cable_data.get("retired_date"),
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


def load_probe_metadata(path: str) -> Dict[str, Dict[str, Any]]:
    """Load optional RIPE Atlas probe metadata keyed by probe id."""
    if not path or not os.path.exists(path):
        print(f"Warning: probe metadata file not found: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        print(f"Warning: failed to load probe metadata from {path}: {exc}")
        return {}

    objects = payload.get("objects", payload if isinstance(payload, list) else [])
    probes: Dict[str, Dict[str, Any]] = {}
    for item in objects:
        if not isinstance(item, dict):
            continue
        probe_id = item.get("id")
        if probe_id is None:
            continue
        probes[str(probe_id)] = {
            "probe_country": item.get("country_code"),
            "probe_asn": normalize_asn_value(item.get("asn_v4")),
        }
    print(f"Loaded probe metadata for {len(probes)} probes from {path}")
    return probes


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


def fingerprint_file(path: Optional[str]) -> Optional[str]:
    """Return a SHA256 hash for a local file when available."""
    if not path or not os.path.exists(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_landing_region_override(path: Optional[str]) -> Dict[str, Dict[str, str]]:
    """Load optional landing-station to landing-region manual overrides."""
    if not path:
        return {}
    if not os.path.exists(path):
        print(f"Warning: landing-region override file not found, using geographic clustering only: {path}")
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Landing-region override file must be a JSON object keyed by landing_station_id.")
    overrides: Dict[str, Dict[str, str]] = {}
    for station_id, value in payload.items():
        if isinstance(value, dict):
            region_id = str(value.get("landing_region_id") or value.get("region_id") or "").strip()
            region_name = str(value.get("landing_region_name") or value.get("region_name") or region_id).strip()
        else:
            region_id = str(value).strip()
            region_name = region_id
        if not station_id or not region_id:
            continue
        overrides[str(station_id)] = {
            "landing_region_id": region_id,
            "landing_region_name": region_name or region_id,
        }
    print(f"Loaded {len(overrides)} landing-region manual overrides from {path}")
    return overrides


def stream_json_array(path: str) -> Generator[Dict[str, Any], None, None]:
    """Fallback reader that yields complete objects from a JSON array or stream.

    RIPE Atlas result dumps are often written as one very long JSON array. Some
    interrupted downloads can end mid-object; this scanner preserves all
    complete objects before the truncation point instead of discarding the file.
    """
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as handle:
        buffer: List[str] = []
        depth = 0
        in_string = False
        escape = False
        collecting = False

        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            for char in chunk:
                if not collecting:
                    if char == "{":
                        collecting = True
                        depth = 1
                        buffer = ["{"]
                    continue

                buffer.append(char)
                if in_string:
                    if escape:
                        escape = False
                    elif char == "\\":
                        escape = True
                    elif char == '"':
                        in_string = False
                    continue

                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads("".join(buffer))
                            if isinstance(parsed, dict):
                                yield parsed
                        except json.JSONDecodeError:
                            pass
                        collecting = False
                        buffer = []


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


class IPInfoASNResolver:
    """Resolve IP addresses to ASNs using the local IPinfo ASN MMDB database."""

    def __init__(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing IPinfo ASN MMDB at {path}")
        self.path = path
        self.reader = maxminddb.open_database(path)
        self._cache: Dict[str, str] = {}

    def close(self) -> None:
        """Close the underlying MMDB reader."""
        self.reader.close()

    def get(self, ip_address: str) -> str:
        """Return a normalized ASN string from IPinfo ASN MMDB, or -1 if unavailable."""
        cached = self._cache.get(ip_address)
        if cached is not None:
            return cached
        if not ip_address or is_private_or_special_ip(ip_address):
            self._cache[ip_address] = "-1"
            return "-1"
        try:
            record = self.reader.get(ip_address)
        except Exception:
            self._cache[ip_address] = "-1"
            return "-1"
        if not record:
            self._cache[ip_address] = "-1"
            return "-1"
        resolved = normalize_asn_value(
            record.get("asn")
            or record.get("autonomous_system_number")
            or record.get("autonomous_system_organization")
        )
        self._cache[ip_address] = resolved
        return resolved


def get_geo_info(
    ip_address: str,
    mmdb_reader: maxminddb.Reader,
    asn_resolver: Optional[IPInfoASNResolver] = None,
    geo_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Query IP geolocation data and attach ASN from the IPinfo ASN MMDB when available."""
    if geo_cache is not None and ip_address in geo_cache:
        return geo_cache[ip_address]
    geo_data = {"lat": None, "lon": None, "asn": None, "country": None, "city": None}
    if not ip_address or is_private_or_special_ip(ip_address):
        if geo_cache is not None:
            geo_cache[ip_address] = geo_data
        return geo_data

    try:
        record = mmdb_reader.get(ip_address)
        if record:
            geo_data["lat"] = record.get("latitude")
            geo_data["lon"] = record.get("longitude")
            geo_data["country"] = record.get("country_code")
            geo_data["city"] = record.get("city")
            if asn_resolver is None and "traits" in record and "autonomous_system_number" in record["traits"]:
                geo_data["asn"] = f"AS{record['traits']['autonomous_system_number']}"
    except Exception:
        pass
    if asn_resolver is not None:
        asn = asn_resolver.get(ip_address)
        geo_data["asn"] = f"AS{asn}" if asn != "-1" else None
    if geo_cache is not None:
        geo_cache[ip_address] = geo_data
    return geo_data


def select_hop_reply(hop_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Select one reply IP and RTT from a hop using a consistent minimum-RTT IP group."""
    replies_by_ip: Dict[str, List[float]] = {}
    for entry in hop_data.get("result", []):
        ip = entry.get("from")
        rtt = entry.get("rtt")
        if not ip or rtt is None:
            continue
        try:
            replies_by_ip.setdefault(str(ip), []).append(float(rtt))
        except (TypeError, ValueError):
            continue
    if not replies_by_ip:
        return None
    selected_ip, selected_rtts = min(
        replies_by_ip.items(),
        key=lambda item: min(item[1]),
    )
    return {
        "ip": selected_ip,
        "rtt": min(selected_rtts),
        "hop_reply_ip_count": len(replies_by_ip),
        "hop_selected_reply_rule": "minimum_rtt_reply_ip",
    }


def build_trace_id(file_name: str, msm_id: Any, probe_id: Any, timestamp: Any, target_ip: Any) -> str:
    """Build a stable trace identifier for client-to-service observation accounting."""
    return f"{file_name}:{msm_id}:{probe_id}:{timestamp}:{target_ip}"


def parse_hops_to_links(
    hops: List[Dict[str, Any]],
    msm_id: str,
    prb_id: str,
    timestamp: str,
    file_name: str,
    mmdb_reader: maxminddb.Reader,
    asn_resolver: IPInfoASNResolver,
    trace_metadata: Optional[Dict[str, Any]] = None,
    geo_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Convert consecutive traceroute hops into adjacent hop-pair links."""
    parsed_links: List[Dict[str, Any]] = []
    trace_metadata = trace_metadata or {}
    target_asn = normalize_asn_value(trace_metadata.get("target_asn"))

    hop_infos: List[Optional[Dict[str, Any]]] = []
    for hop_data in hops:
        selected_reply = select_hop_reply(hop_data)
        if not selected_reply:
            hop_infos.append(None)
            continue
        ip = selected_reply["ip"]
        geo = get_geo_info(ip, mmdb_reader, asn_resolver, geo_cache=geo_cache)
        hop_infos.append(
            {
                "ip": ip,
                "rtt": selected_reply["rtt"],
                "geo": geo,
                "asn": normalize_asn_value(geo.get("asn")),
                "hop_num": hop_data["hop"],
                "hop_reply_ip_count": selected_reply["hop_reply_ip_count"],
                "hop_selected_reply_rule": selected_reply["hop_selected_reply_rule"],
            }
        )

    service_entry_hop: Optional[int] = None
    service_entry_asn: Optional[str] = None
    if target_asn != "-1":
        for hop_info in hop_infos:
            if hop_info and hop_info.get("asn") == target_asn:
                service_entry_hop = int(hop_info["hop_num"])
                service_entry_asn = target_asn
                break

    link_trace_metadata = dict(trace_metadata)
    if service_entry_hop is not None:
        link_trace_metadata.update(
            {
                "service_entry_hop": service_entry_hop,
                "service_entry_asn": service_entry_asn,
                "service_entry_resolved": True,
                "path_scope": "client_to_service_entry",
            }
        )

    previous_rtt = 0.0
    previous_hop_info: Optional[Dict[str, Any]] = None

    for current_hop_info in hop_infos:
        if current_hop_info is None:
            previous_hop_info = None
            continue
        if service_entry_hop is not None and int(current_hop_info["hop_num"]) > service_entry_hop:
            break
        rtt = current_hop_info["rtt"]

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
                    **link_trace_metadata,
                }
            )

        previous_rtt = rtt
        previous_hop_info = current_hop_info

    return parsed_links


def process_single_traceroute_file(
    path: str,
    mmdb_reader: maxminddb.Reader,
    asn_resolver: IPInfoASNResolver,
) -> List[Dict[str, Any]]:
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
            asn_resolver=asn_resolver,
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
    AS_GRAPH_MAX_HOPS_UNKNOWN = 2
    AS_GRAPH_SEARCH_MAX_HOPS = 2
    AS_GRAPH_ONE_SIDED_PENALTY = 1.0
    AS_GRAPH_UNKNOWN_COST = 4.0

    def build_landing_region_map(self) -> Dict[str, str]:
        """Cluster landing stations into deterministic connected landing regions."""
        station_ids = sorted(self.ls_geo.keys())
        parent = {station_id: station_id for station_id in station_ids}

        def find(item: str) -> str:
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        def union(left: str, right: str) -> None:
            root_left = find(left)
            root_right = find(right)
            if root_left == root_right:
                return
            if root_left < root_right:
                parent[root_right] = root_left
            else:
                parent[root_left] = root_right

        for index, station_a in enumerate(station_ids):
            for station_b in station_ids[index + 1:]:
                if haversine_km(self.ls_geo[station_a], self.ls_geo[station_b]) <= self.landing_region_radius_km:
                    union(station_a, station_b)

        components: Dict[str, List[str]] = {}
        for station_id in station_ids:
            components.setdefault(find(station_id), []).append(station_id)

        landing_region_map: Dict[str, str] = {}
        for component_index, (_, members) in enumerate(sorted(components.items()), start=1):
            region_id = f"landing_region_{component_index:04d}"
            for station_id in members:
                landing_region_map[station_id] = region_id
                self.landing_region_method_map[station_id] = "geographic_connected_component"
            self.landing_region_label_map.setdefault(region_id, region_id)

        for station_id, override in self.landing_region_override.items():
            if station_id not in self.ls_geo:
                continue
            region_id = override["landing_region_id"]
            landing_region_map[station_id] = region_id
            self.landing_region_label_map[region_id] = override.get("landing_region_name") or region_id
            self.landing_region_method_map[station_id] = "manual_override"
        return landing_region_map

    def __init__(
        self,
        processed_cables: List[Dict[str, Any]],
        ls_coordinates: Dict[str, Tuple[float, float]],
        as_relationship: Dict[Tuple[str, str], int],
        asn_resolver: IPInfoASNResolver,
        owner2asn: Dict[str, Set[str]],
        as_graph_precompute: Optional[Dict[str, Any]] = None,
        rtt_tolerance_ms: float = 5.0,
        landing_region_radius_km: float = 50.0,
        landing_region_override: Optional[Dict[str, Dict[str, str]]] = None,
        landing_region_override_file: Optional[str] = None,
        cable_availability_mode: str = "confirmed_active_only",
    ):
        self.all_cables = processed_cables
        self.ls_geo = ls_coordinates
        self.as_relationship = as_relationship
        self.asn_resolver = asn_resolver
        self.owner2asn = owner2asn
        self.as_graph_precompute = as_graph_precompute or {}
        self.rtt_tolerance_ms = float(rtt_tolerance_ms)
        self.landing_region_radius_km = float(landing_region_radius_km)
        self.landing_region_override = landing_region_override or {}
        self.landing_region_override_file = landing_region_override_file
        self.landing_region_label_map: Dict[str, str] = {}
        self.landing_region_method_map: Dict[str, str] = {}
        self.cable_availability_mode = cable_availability_mode
        self.landing_region_map = self.build_landing_region_map()
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
            "links_without_landing_candidates": 0,
            "links_without_segment_candidates": 0,
            "links_with_ls_candidates": 0,
            "links_with_geo_candidates": 0,
            "candidate_segments_considered": 0,
            "rtt_infeasible_filtered": 0,
            "candidates_rtt_infeasible": 0,
            "candidates_rtt_feasible": 0,
            "segments_with_valid_rtt": 0,
            "segments_with_inconclusive_rtt": 0,
            "candidates_filtered_by_valid_rtt": 0,
            "candidates_retained_due_to_inconclusive_rtt": 0,
            "links_below_threshold": 0,
            "candidates_above_threshold": 0,
            "candidates_support_above_threshold": 0,
            "candidates_support_below_threshold": 0,
            "links_with_any_match": 0,
            "links_with_filtered_candidates": 0,
            "links_with_no_feasible_rtt_candidate": 0,
            "links_with_no_feasible_candidate": 0,
            "links_with_feasible_candidates": 0,
            "links_with_only_low_support_feasible_candidates": 0,
            "total_candidates_generated": 0,
            "total_candidates_after_threshold": 0,
            "links_with_dual_core_agreement": 0,
            "links_with_geo_dominant_as_weak": 0,
            "links_with_as_dominant_geo_ambiguous": 0,
            "links_with_parallel_ambiguity": 0,
            "links_with_many_candidates": 0,
            "links_with_domestic_candidates": 0,
            "rtt_tolerance_ms": float(self.rtt_tolerance_ms),
            "landing_region_radius_km": float(self.landing_region_radius_km),
            "landing_region_count": len(set(self.landing_region_map.values())),
            "landing_region_override_file": self.landing_region_override_file,
            "landing_region_override_hash": fingerprint_file(self.landing_region_override_file),
            "landing_region_override_count": len(self.landing_region_override),
            "ip_to_asn_source": getattr(self.asn_resolver, "path", "ipinfo_asn_mmdb"),
            "cable_availability_mode": self.cable_availability_mode,
            "candidates_filtered_by_cable_lifecycle": 0,
            "segments_filtered_by_cable_lifecycle": 0,
            "candidates_with_unknown_cable_status": 0,
            "confirmed_active_candidates": 0,
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
                        self.gcd_cache[segment] = haversine_km(self.ls_geo[ls_a], self.ls_geo[ls_b])
                    self.segment_to_cables.setdefault(segment, []).append(
                        {
                            "cable_id": cable["id"],
                            "cable_name": cable["name"],
                            "cable_owners": cable["owners"],
                            "cable_owner_asns": cable_owner_asns,
                            "owner_group_signature": owner_signature,
                            "owner_group_id": owner_group_id,
                            "gcd_dist": self.gcd_cache[segment],
                            "rfs": cable.get("rfs"),
                            "rfs_year": cable.get("rfs_year"),
                            "rfs_date": cable.get("rfs_date"),
                            "rfs_date_parsed": parse_loose_date(
                                cable.get("rfs_date") or cable.get("rfs") or cable.get("rfs_year")
                            ),
                            "is_planned": cable.get("is_planned", False),
                            "status": cable.get("status"),
                            "retired": cable.get("retired", False),
                            "retired_date": cable.get("retired_date"),
                            "retired_date_parsed": parse_loose_date(cable.get("retired_date")),
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
        considered = float(finalized.get("candidate_segments_considered", 0) or 0)
        confirmed = float(finalized.get("confirmed_active_candidates", 0) or 0)
        unknown = float(finalized.get("candidates_with_unknown_cable_status", 0) or 0)
        finalized["lifecycle_known_candidate_count"] = int(max(considered - unknown, 0))
        finalized["lifecycle_metadata_known_ratio"] = float((considered - unknown) / considered) if considered > 0 else 0.0
        finalized["lifecycle_confirmed_active_ratio"] = float(confirmed / considered) if considered > 0 else 0.0
        finalized["lifecycle_metadata_warning"] = (
            "low_lifecycle_metadata_coverage"
            if considered > 0 and finalized["lifecycle_metadata_known_ratio"] < 0.5
            else ""
        )
        return finalized

    def IP2ASN(self, ip: str) -> str:
        """Map an IP address to an ASN using the local IPinfo ASN MMDB."""
        return self.asn_resolver.get(ip)

    def compute_geo_spatial_score(self, d_in: float, d_out: float) -> Dict[str, float]:
        """Geo-spatial Core: compute landing-proximity evidence support, not ground-truth cable probability."""
        prob_in = 1.0 / (1.0 + (d_in / self.GEO_DECAY_CUTOFF_KM) ** self.GEO_DECAY_STEEPNESS)
        prob_out = 1.0 / (1.0 + (d_out / self.GEO_DECAY_CUTOFF_KM) ** self.GEO_DECAY_STEEPNESS)
        geo_spatial_score = math.sqrt(prob_in * prob_out)
        return {
            "geo_spatial_score": float(geo_spatial_score),
            "geo_spatial_support": float(geo_spatial_score),
            "geo_entry_score": float(prob_in),
            "geo_exit_score": float(prob_out),
            "geo_entry_support": float(prob_in),
            "geo_exit_support": float(prob_out),
            "prob_in": float(prob_in),
            "prob_out": float(prob_out),
        }

    def compute_rtt_feasibility_score(self, measured_rtt_delta: float, min_rtt: float) -> Dict[str, Any]:
        """RTT/Physical Feasibility Core: assess whether a candidate is latency-feasible."""
        rtt_quality = "valid"
        try:
            measured = float(measured_rtt_delta)
        except (TypeError, ValueError):
            measured = float("nan")
        if not math.isfinite(measured) or measured <= 0:
            rtt_quality = "non_positive_or_noisy"
            return {
                "rtt_feasible": True,
                "rtt_feasibility_status": "inconclusive",
                "rtt_filter_applied": False,
                "rtt_score": 1.0,
                "rtt_margin_ms": None,
                "rtt_margin_with_tolerance_ms": None,
                "latency_penalty": 1.0,
                "rtt_tolerance_ms": float(self.rtt_tolerance_ms),
                "rtt_delta_quality": rtt_quality,
            }

        if min_rtt <= 0:
            return {
                "rtt_feasible": True,
                "rtt_feasibility_status": "inconclusive",
                "rtt_filter_applied": False,
                "rtt_score": 1.0,
                "rtt_margin_ms": None,
                "rtt_margin_with_tolerance_ms": None,
                "latency_penalty": 1.0,
                "rtt_tolerance_ms": float(self.rtt_tolerance_ms),
                "rtt_delta_quality": "invalid_lower_bound",
            }

        rtt_margin_ms = measured - min_rtt
        rtt_margin_with_tolerance_ms = measured + self.rtt_tolerance_ms - min_rtt
        if rtt_margin_with_tolerance_ms < 0:
            return {
                "rtt_feasible": False,
                "rtt_feasibility_status": "infeasible",
                "rtt_filter_applied": True,
                "rtt_score": 0.0,
                "rtt_margin_ms": float(rtt_margin_ms),
                "rtt_margin_with_tolerance_ms": float(rtt_margin_with_tolerance_ms),
                "latency_penalty": 0.0,
                "rtt_tolerance_ms": float(self.rtt_tolerance_ms),
                "rtt_delta_quality": rtt_quality,
            }

        inflation_ratio = measured / min_rtt if min_rtt > 0 and measured > 0 else float("inf")
        rtt_score = min(1.0, 1.0 / inflation_ratio) if math.isfinite(inflation_ratio) and inflation_ratio > 0 else 0.0

        latency_penalty = 1.0
        if min_rtt < self.SHORT_PATH_RTT_MS and inflation_ratio > self.HIGH_INFLATION_RATIO:
            latency_penalty = self.SHORT_PATH_INFLATION_PENALTY

        return {
            "rtt_feasible": True,
            "rtt_feasibility_status": "feasible",
            "rtt_filter_applied": True,
            "rtt_score": float(rtt_score),
            "rtt_margin_ms": float(rtt_margin_ms),
            "rtt_margin_with_tolerance_ms": float(rtt_margin_with_tolerance_ms),
            "latency_penalty": float(latency_penalty),
            "rtt_tolerance_ms": float(self.rtt_tolerance_ms),
            "rtt_delta_quality": rtt_quality,
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
        rtt_margin = candidate.get("rtt_margin_ms")
        if candidate.get("rtt_feasibility_status") == "inconclusive" or candidate.get("rtt_delta_quality") == "non_positive_or_noisy":
            tags.append("rtt_inconclusive")
        elif rtt_margin is not None and rtt_margin < self.RTT_INCONCLUSIVE_MARGIN_MS:
            tags.append("rtt_inconclusive")
        if candidate["core_agreement"] in {"geo_dominant_as_weak", "as_dominant_geo_ambiguous"}:
            tags.append(candidate["core_agreement"])
        if candidate["country_a"] and candidate["country_a"] == candidate["country_b"]:
            tags.append("domestic_submarine_candidate")
        if (
            candidate["ls_entry_to_ls_exit_gcd_km"] > self.MULTI_SEGMENT_GCD_THRESHOLD_KM
            and rtt_margin is not None
            and rtt_margin > self.MULTI_SEGMENT_MARGIN_THRESHOLD_MS
        ):
            tags.append("multi_segment_possible")
        return tags

    def normalize_candidate_supports(self, candidates: List[Dict[str, Any]]) -> float:
        """Normalize evidence support inside a single feasible candidate set for one link."""
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

    def classify_link_physical_projection(self, candidates: List[Dict[str, Any]]) -> str:
        """Classify the link-level physical projection pattern implied by retained candidates."""
        if not candidates:
            return "no_physical_candidate"

        corridor_ids = {
            str(candidate.get("corridor_id", "")).strip()
            for candidate in candidates
            if str(candidate.get("corridor_id", "")).strip()
        }
        cable_ids = {
            str(candidate.get("cable_id", "")).strip()
            for candidate in candidates
            if str(candidate.get("cable_id", "")).strip()
        }
        has_parallel_group = any(
            bool(candidate.get("is_parallel_ambiguous"))
            or int(candidate.get("parallel_group_size", 0) or 0) > 1
            or "parallel_candidate_corridor" in candidate.get("ambiguity_tags", [])
            for candidate in candidates
        )

        if len(corridor_ids) == 1 and len(cable_ids) == 1 and not has_parallel_group:
            return "single_cable_single_corridor"
        if len(corridor_ids) == 1 and has_parallel_group:
            return "parallel_cable_same_corridor"
        if len(corridor_ids) == 1 and len(cable_ids) > 1:
            return "multi_cable_single_corridor"
        if len(corridor_ids) > 1:
            return "multi_corridor_projection"
        return "mixed_or_unknown_projection"

    def classify_projection_quality(
        self,
        candidates: List[Dict[str, Any]],
        confidence_bucket: str,
        link_physical_projection_class: str,
        top1_top2_gap: float,
    ) -> str:
        """Classify projection quality without forcing deterministic physical attribution."""
        if not candidates:
            return "ambiguous"

        candidate_count = len(candidates)
        has_parallel = any(
            bool(candidate.get("is_parallel_ambiguous"))
            or int(candidate.get("parallel_group_size", 0) or 0) > 1
            or "parallel_candidate_corridor" in candidate.get("ambiguity_tags", [])
            for candidate in candidates
        )
        has_many_candidates = any("many_candidates" in candidate.get("ambiguity_tags", []) for candidate in candidates) or candidate_count > 4
        has_large_radius = any(
            max(float(candidate.get("d_in", 0.0) or 0.0), float(candidate.get("d_out", 0.0) or 0.0)) > 80.0
            for candidate in candidates
        )
        min_rtt_margin = min(float(candidate.get("rtt_margin_ms", 0.0) or 0.0) for candidate in candidates)
        has_dual_core = any(candidate.get("core_agreement") == "dual_core_agreement" for candidate in candidates)

        if (
            candidate_count == 1
            and confidence_bucket == "high"
            and top1_top2_gap >= self.HIGH_GAP_THRESHOLD
            and not has_parallel
            and link_physical_projection_class == "single_cable_single_corridor"
            and not has_large_radius
            and min_rtt_margin >= 5.0
            and has_dual_core
        ):
            return "strong"
        if (
            candidate_count <= 2
            and confidence_bucket in {"high", "medium"}
            and not has_many_candidates
            and link_physical_projection_class not in {"multi_corridor_projection", "mixed_or_unknown_projection"}
        ):
            return "moderate"
        if has_parallel or has_many_candidates or link_physical_projection_class == "multi_corridor_projection" or confidence_bucket == "ambiguous":
            return "ambiguous"
        return "weak"

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

    def _match_summary_stub(self, filtered_reason: str) -> Dict[str, Any]:
        """Return a backward-compatible empty match summary for links without feasible candidates."""
        return {
            "filtered_reason": filtered_reason,
            "num_candidates_total": 0,
            "num_feasible_candidates_total": 0,
            "num_feasible_corridors_total": 0,
            "num_candidates_above_threshold": 0,
            "feasible_candidate_retention_mode": "infeasibility_first",
            "support_threshold_used_for_legacy_all_segments": True,
            "support_threshold_value": float(self.MATCH_THRESHOLD),
            "support_sum": 0.0,
            "top1_candidate_support": 0.0,
            "top2_candidate_support": 0.0,
            "top1_top2_gap": 0.0,
            "confidence_bucket": "none",
            "core_agreement_summary": {"dominant_core_agreement": "none"},
            "ambiguity_summary": {"tags_present": [], "tag_counts": {}, "num_ambiguous_candidates": 0},
            "link_physical_projection_class": "no_physical_candidate",
            "projection_class": "ambiguous",
            "top1_score": 0.0,
            "top2_score": 0.0,
        }

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
                "all_feasible_segments": [],
                "all_segments": [],
                "match_summary": self._match_summary_stub("same_city"),
            }

        candidates: List[Dict[str, Any]] = []
        had_segment_candidates = False
        rtt_feasible_candidate_found = False
        radius_rad = self.LS_CATCHMENT_RADIUS_KM / self.R_EARTH
        hop_a_loc = (np.radians(hop_a["geo"]["lat"]), np.radians(hop_a["geo"]["lon"]))
        hop_b_loc = (np.radians(hop_b["geo"]["lat"]), np.radians(hop_b["geo"]["lon"]))

        idx_a_list = self.ls_tree.query_radius([hop_a_loc], r=radius_rad)[0]
        idx_b_list = self.ls_tree.query_radius([hop_b_loc], r=radius_rad)[0]

        if len(idx_a_list) == 0 or len(idx_b_list) == 0:
            self.stats["links_without_landing_candidates"] += 1
        if len(idx_a_list) > 0 and len(idx_b_list) > 0:
            self.stats["links_with_ls_candidates"] += 1
            self.stats["links_with_geo_candidates"] += 1

        entries_a = []
        for index in idx_a_list:
            ls_id = self.ls_id_map[index]
            d_in = haversine_km((hop_a["geo"]["lat"], hop_a["geo"]["lon"]), self.ls_coord_map[ls_id])
            entries_a.append((ls_id, d_in))

        entries_b = []
        for index in idx_b_list:
            ls_id = self.ls_id_map[index]
            d_out = haversine_km((hop_b["geo"]["lat"], hop_b["geo"]["lon"]), self.ls_coord_map[ls_id])
            entries_b.append((ls_id, d_out))

        asn_a = normalize_asn_value(hop_a.get("asn"))
        asn_b = normalize_asn_value(hop_b.get("asn"))
        trace_datetime = parse_trace_datetime(link.get("timestamp"))

        for ls_a_id, d_in in entries_a:
            for ls_b_id, d_out in entries_b:
                if ls_a_id == ls_b_id:
                    continue

                segment_key = tuple(sorted((ls_a_id, ls_b_id)))
                segment_cables = self.segment_to_cables.get(segment_key)
                if not segment_cables:
                    continue
                had_segment_candidates = True
                exact_corridor_id = f"{segment_key[0]}::{segment_key[1]}"
                region_a = self.landing_region_map.get(ls_a_id, ls_a_id)
                region_b = self.landing_region_map.get(ls_b_id, ls_b_id)
                landing_region_pair = tuple(sorted((region_a, region_b)))
                corridor_id = f"{landing_region_pair[0]}::{landing_region_pair[1]}"
                region_label_pair = tuple(
                    self.landing_region_label_map.get(region_id, region_id)
                    for region_id in landing_region_pair
                )
                corridor_label = f"{region_label_pair[0]} -> {region_label_pair[1]}"
                landing_region_method = (
                    "manual_override"
                    if "manual_override" in {
                        self.landing_region_method_map.get(ls_a_id),
                        self.landing_region_method_map.get(ls_b_id),
                    }
                    else "geographic_connected_component"
                )
                parallel_group_id = corridor_id

                geo_score_info = self.compute_geo_spatial_score(d_in=d_in, d_out=d_out)

                for cable_info in segment_cables:
                    self.stats["candidate_segments_considered"] += 1
                    availability_info = is_cable_available_at(
                        cable_info,
                        link.get("timestamp"),
                        mode=self.cable_availability_mode,
                        trace_datetime=trace_datetime,
                    )
                    if availability_info["cable_availability_status"] == "unknown":
                        self.stats["candidates_with_unknown_cable_status"] += 1
                    if availability_info["cable_availability_status"] == "confirmed_active_at_trace_time":
                        self.stats["confirmed_active_candidates"] += 1
                    if not availability_info["availability_filter_passed"]:
                        self.stats["candidates_filtered_by_cable_lifecycle"] += 1
                        self.stats["segments_filtered_by_cable_lifecycle"] += 1
                        continue

                    gcd_dist = cable_info["gcd_dist"]
                    legacy_slack_lower_bound_ms = ((gcd_dist * self.SLACK_FACTOR) * 2) / self.SOL_FIBER_KM_MS
                    min_rtt = (gcd_dist * 2) / self.SOL_FIBER_KM_MS
                    rtt_score_info = self.compute_rtt_feasibility_score(measured_rtt_delta=measured_rtt_delta, min_rtt=min_rtt)
                    if rtt_score_info["rtt_feasibility_status"] == "inconclusive":
                        self.stats["segments_with_inconclusive_rtt"] += 1
                        self.stats["candidates_retained_due_to_inconclusive_rtt"] += 1
                    elif rtt_score_info["rtt_feasibility_status"] in {"feasible", "infeasible"}:
                        self.stats["segments_with_valid_rtt"] += 1
                    if not rtt_score_info["rtt_feasible"]:
                        self.stats["rtt_infeasible_filtered"] += 1
                        self.stats["candidates_rtt_infeasible"] += 1
                        if rtt_score_info.get("rtt_filter_applied"):
                            self.stats["candidates_filtered_by_valid_rtt"] += 1
                        continue
                    rtt_feasible_candidate_found = True
                    self.stats["candidates_rtt_feasible"] += 1

                    cable_owner_asns: Set[str] = set(cable_info.get("cable_owner_asns", set()))

                    as_support_info = self.compute_as_economic_support(
                        src_asn=asn_a,
                        dst_asn=asn_b,
                        cable_owner_asns=cable_owner_asns,
                    )

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
                        "cable_owners": cable_info.get("cable_owners", []),
                        "cable_rfs_date": availability_info["cable_rfs_date"],
                        "cable_retired_date": availability_info["cable_retired_date"],
                        "cable_status": availability_info["cable_status"],
                        "cable_availability_status": availability_info["cable_availability_status"],
                        "availability_filter_passed": availability_info["availability_filter_passed"],
                        "segment": f"{ls_a_id} -> {ls_b_id}",
                        "landing_pair": f"{ls_a_id} -> {ls_b_id}",
                        "corridor_id": corridor_id,
                        "corridor_label": corridor_label,
                        "corridor_type": "landing_region_pair",
                        "exact_corridor_id": exact_corridor_id,
                        "exact_landing_pair_id": exact_corridor_id,
                        "exact_landing_pair_label": f"{ls_a_id} -> {ls_b_id}",
                        "landing_region_pair_id": corridor_id,
                        "landing_region_entry_id": region_a,
                        "landing_region_exit_id": region_b,
                        "landing_region_entry_label": self.landing_region_label_map.get(region_a, region_a),
                        "landing_region_exit_label": self.landing_region_label_map.get(region_b, region_b),
                        "landing_region_method": landing_region_method,
                        "landing_region_radius_km": float(self.landing_region_radius_km),
                        "parallel_group_id": parallel_group_id,
                        "parallel_group_size": len(segment_cables),
                        "is_parallel_ambiguous": len(segment_cables) > 1,
                        "physical_candidate_group_id": parallel_group_id,
                        "physical_candidate_group_type": "srlg_like_corridor_group",
                        "candidate_support": float(fused_candidate_support),
                        "fused_candidate_support": float(fused_candidate_support),
                        "normalized_candidate_support": 0.0,
                        "geo_spatial_score": float(geo_score_info["geo_spatial_score"]),
                        "geo_spatial_support": float(geo_score_info["geo_spatial_support"]),
                        "geo_entry_score": float(geo_score_info["geo_entry_score"]),
                        "geo_exit_score": float(geo_score_info["geo_exit_score"]),
                        "geo_entry_support": float(geo_score_info["geo_entry_support"]),
                        "geo_exit_support": float(geo_score_info["geo_exit_support"]),
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
                        "rtt_feasible": bool(rtt_score_info["rtt_feasible"]),
                        "rtt_feasibility_status": rtt_score_info["rtt_feasibility_status"],
                        "rtt_filter_applied": bool(rtt_score_info["rtt_filter_applied"]),
                        "rtt_score": float(rtt_score_info["rtt_score"]),
                        "min_rtt_ms": float(min_rtt),
                        "rtt_lower_bound_ms": float(min_rtt),
                        "legacy_slack_rtt_lower_bound_ms": float(legacy_slack_lower_bound_ms),
                        "measured_rtt_ms": float(measured_rtt_delta),
                        "rtt_margin_ms": rtt_score_info["rtt_margin_ms"],
                        "rtt_margin_with_tolerance_ms": rtt_score_info["rtt_margin_with_tolerance_ms"],
                        "rtt_tolerance_ms": float(rtt_score_info["rtt_tolerance_ms"]),
                        "rtt_delta_quality": rtt_score_info["rtt_delta_quality"],
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
                        "hard_feasible": True,
                        "infeasibility_filter_passed": True,
                        "support_above_threshold": False,
                        "support_filter_reason": "below_threshold_but_feasible",
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
        if len(idx_a_list) > 0 and len(idx_b_list) > 0 and not had_segment_candidates:
            self.stats["links_without_segment_candidates"] += 1
        if had_segment_candidates and not rtt_feasible_candidate_found:
            self.stats["links_with_no_feasible_rtt_candidate"] += 1

        if not candidates:
            self.stats["links_with_no_feasible_candidate"] += 1
            return {
                "all_feasible_segments": [],
                "all_segments": [],
                "match_summary": self._match_summary_stub("no_candidate"),
            }

        sorted_candidates = sorted(candidates, key=lambda item: item.get("candidate_support", 0.0), reverse=True)
        deduplicated_candidates: Dict[str, Dict[str, Any]] = {}
        unique_candidates: List[Dict[str, Any]] = []
        for candidate in sorted_candidates:
            feasible_key = f"{candidate['cable_id']}::{candidate['segment']}"
            if feasible_key not in deduplicated_candidates:
                deduplicated_candidates[feasible_key] = candidate
                unique_candidates.append(candidate)

        feasible_candidates = [dict(candidate) for candidate in unique_candidates]
        feasible_support_sum = self.normalize_candidate_supports(feasible_candidates)
        self.assign_candidate_ranks(feasible_candidates)

        for candidate in feasible_candidates:
            candidate["support_above_threshold"] = bool(candidate.get("candidate_support", 0.0) >= self.MATCH_THRESHOLD)
            candidate["support_filter_reason"] = (
                "above_threshold" if candidate["support_above_threshold"] else "below_threshold_but_feasible"
            )
            if candidate["support_above_threshold"]:
                self.stats["candidates_support_above_threshold"] += 1
            else:
                self.stats["candidates_support_below_threshold"] += 1

        filtered_candidates = [dict(candidate) for candidate in feasible_candidates if candidate["support_above_threshold"]]
        if feasible_candidates and not filtered_candidates:
            self.stats["links_below_threshold"] += 1
            self.stats["links_with_only_low_support_feasible_candidates"] += 1

        self.stats["candidates_above_threshold"] += len(filtered_candidates)
        self.stats["total_candidates_after_threshold"] += len(filtered_candidates)
        if feasible_candidates:
            self.stats["links_with_feasible_candidates"] += 1
        if filtered_candidates:
            self.stats["links_with_any_match"] += 1
            self.stats["links_with_filtered_candidates"] += 1

        support_sum = self.normalize_candidate_supports(filtered_candidates)
        self.assign_candidate_ranks(filtered_candidates)

        for candidate in feasible_candidates:
            candidate["ambiguity_tags"] = self.build_ambiguity_tags(
                candidate=candidate,
                filtered_candidate_count=len(feasible_candidates),
                segment_candidate_count=candidate["parallel_segment_candidate_count"],
            )
        for candidate in filtered_candidates:
            candidate["ambiguity_tags"] = self.build_ambiguity_tags(
                candidate=candidate,
                filtered_candidate_count=len(feasible_candidates),
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

        summary_candidates = feasible_candidates if feasible_candidates else filtered_candidates
        core_agreement_summary = self.build_core_agreement_summary(summary_candidates)
        ambiguity_summary = self.build_ambiguity_summary(summary_candidates)
        link_physical_projection_class = self.classify_link_physical_projection(summary_candidates)
        projection_class = self.classify_projection_quality(
            summary_candidates,
            confidence_bucket=bucket,
            link_physical_projection_class=link_physical_projection_class,
            top1_top2_gap=gap,
        )

        for candidate in feasible_candidates:
            candidate["link_physical_projection_class"] = link_physical_projection_class
            candidate["projection_class"] = projection_class
        for candidate in filtered_candidates:
            candidate["link_physical_projection_class"] = link_physical_projection_class
            candidate["projection_class"] = projection_class

        return {
            "all_feasible_segments": feasible_candidates,
            "all_segments": filtered_candidates,
            "match_summary": {
                "filtered_reason": None if filtered_candidates else "below_threshold",
                "num_candidates_total": len(feasible_candidates),
                "num_feasible_candidates_total": len(feasible_candidates),
                "num_feasible_corridors_total": len(
                    {
                        str(candidate.get("corridor_id", "")).strip()
                        for candidate in feasible_candidates
                        if str(candidate.get("corridor_id", "")).strip()
                    }
                ),
                "num_candidates_above_threshold": len(filtered_candidates),
                "feasible_candidate_retention_mode": "infeasibility_first",
                "support_threshold_used_for_legacy_all_segments": True,
                "support_threshold_value": float(self.MATCH_THRESHOLD),
                "support_sum": float(support_sum),
                "feasible_support_sum": float(feasible_support_sum),
                "top1_candidate_support": float(top1),
                "top2_candidate_support": float(top2),
                "top1_top2_gap": float(gap),
                "confidence_bucket": bucket,
                "core_agreement_summary": core_agreement_summary,
                "ambiguity_summary": ambiguity_summary,
                "link_physical_projection_class": link_physical_projection_class,
                "projection_class": projection_class,
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
    feasible_link_count: int,
    as_precompute_file: Optional[str],
    asn_mmdb_path: str,
    landing_region_override_file: Optional[str],
    path: str,
    match_output_file: str = OUTPUT_RESULTS_PATH,
    match_stats_file: str = MATCH_STATS_OUTPUT_PATH,
) -> None:
    """Write a manifest describing the processed traceroute inputs and outputs."""
    manifest = {
        "traceroute_file_paths": [to_repo_relative_path(path_item) for path_item in traceroute_file_paths],
        "total_files_processed": total_files_processed,
        "total_traces_processed": total_traces_processed,
        "empty_trace_count": empty_trace_count,
        "matched_links_above_threshold": valid_link_count,
        "links_with_feasible_candidates": feasible_link_count,
        "match_output_file": to_repo_relative_path(match_output_file),
        "match_stats_file": to_repo_relative_path(match_stats_file),
        "as_precompute_file": to_repo_relative_path(as_precompute_file) if as_precompute_file else None,
        "ip_to_asn_source": "ipinfo_asn_mmdb",
        "asn_mmdb_path": to_repo_relative_path(asn_mmdb_path),
        "landing_region_override_file": to_repo_relative_path(landing_region_override_file) if landing_region_override_file else None,
        "landing_region_override_hash": fingerprint_file(landing_region_override_file),
        "method_profile": "infeasibility_first_feasible_corridor_construction",
        "paper_primary_cable_availability_mode": "confirmed_active_only",
        "robustness_cable_availability_mode": "confirmed_active_plus_unknown",
        "primary_candidate_constraints": [
            "landing_proximity",
            "cable_connectivity",
            "measurement_time_availability",
            "conservative_rtt_feasibility_when_observable",
        ],
        "supplementary_support_model": "geo_as_owner_rtt_evidence_scoring",
        "supplementary_support_affects_primary_feasible_set": False,
        "interpretation": "infeasibility_first_conservative_candidate_audit",
        "support_semantics": "candidate support is evidence support, not ground-truth probability",
        "legacy_all_segments_semantics": "support-thresholded legacy candidate view",
        "all_segments_semantics": "legacy support-thresholded supplementary view",
        "all_feasible_segments_semantics": "all candidates passing hard infeasibility filters",
        "support_threshold_value": float(CableMatcher.MATCH_THRESHOLD),
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


def resolve_traceroute_input(path: str) -> List[str]:
    """Resolve a traceroute input file or directory into eligible JSON files."""
    if os.path.isfile(path):
        return [path]
    return load_all_traceroute_files(path)


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
    parser.add_argument(
        "--traceroute-input",
        default=TRACE_DIR,
        help="Traceroute input file or directory. Defaults to data/traceroute_rundnsroot/.",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Directory for cable_matching_output.json, stats, and manifest outputs.",
    )
    parser.add_argument(
        "--probe-meta-file",
        default=PROBE_META_PATH,
        help="Optional RIPE Atlas probe metadata JSON used for probe_country/probe_asn.",
    )
    parser.add_argument(
        "--asn-mmdb-path",
        default=ASN_MMDB_PATH,
        help="IPinfo ASN MMDB used for every IP-to-ASN lookup.",
    )
    parser.add_argument(
        "--rtt-tolerance-ms",
        type=float,
        default=5.0,
        help="Tolerance added to RTT lower-bound feasibility checks.",
    )
    parser.add_argument(
        "--landing-region-radius-km",
        type=float,
        default=50.0,
        help="Connected-component distance threshold for landing-region corridor grouping.",
    )
    parser.add_argument(
        "--landing-region-override-file",
        default=None,
        help="Optional JSON mapping landing_station_id to manual landing_region_id/name overrides.",
    )
    parser.add_argument(
        "--cable-availability-mode",
        choices=["confirmed_active_only", "confirmed_active_plus_unknown"],
        default="confirmed_active_only",
        help="Cable lifecycle filter mode for the main feasible candidate set; use confirmed_active_plus_unknown for robustness.",
    )
    return parser.parse_args()


def main() -> None:
    """Process traceroute links and emit candidate-support outputs."""
    args = parse_args()
    output_dir = os.path.abspath(args.output_dir)
    output_results_path = os.path.join(output_dir, "cable_matching_output.json")
    match_stats_output_path = os.path.join(output_dir, "cable_matching_stats_5051.json")
    match_manifest_output_path = os.path.join(output_dir, "cable_matching_manifest.json")

    try:
        ls_coordinates = load_ls_coordinates(LS_GEO_PATH)
        all_cables = load_all_cables(CABLE_DIR)
        as_relationship = load_as_relationship(ASREL_PATH)
        asn_resolver = IPInfoASNResolver(args.asn_mmdb_path)
        owner2asn = load_owner2asn_mapping(OWNER2ASN_PATH)
        as_graph_precompute = load_as_graph_precompute(args.as_precompute_file)
        landing_region_override = load_landing_region_override(args.landing_region_override_file)
        probe_metadata = load_probe_metadata(args.probe_meta_file)
    except (FileNotFoundError, ValueError) as exc:
        print("--- Critical error: failed to load required input files ---")
        print(str(exc))
        return

    output_debug_cable_info(ls_coordinates, all_cables, CABLE_DEBUG_OUTPUT_PATH)
    matcher = CableMatcher(
        all_cables,
        ls_coordinates,
        as_relationship,
        asn_resolver,
        owner2asn,
        as_graph_precompute=as_graph_precompute,
        rtt_tolerance_ms=args.rtt_tolerance_ms,
        landing_region_radius_km=args.landing_region_radius_km,
        landing_region_override=landing_region_override,
        landing_region_override_file=args.landing_region_override_file,
        cable_availability_mode=args.cable_availability_mode,
    )
    traceroute_file_paths = resolve_traceroute_input(args.traceroute_input)

    print("\n--- Candidate-support matching task started ---")
    print(f"Identified {len(traceroute_file_paths)} traceroute files.")
    print(f"Incremental output will be written to: {output_results_path}")
    if matcher.as_graph_precompute_loaded:
        print(f"Using AS-graph precompute file: {args.as_precompute_file}")
    else:
        print("Using legacy AS-economic fallback because no AS-graph precompute file was loaded.")
    print("---------------------------------------------")

    valid_link_count = 0
    feasible_link_count = 0
    total_files_processed = 0
    total_traces_processed = 0
    empty_trace_count = 0
    is_first_entry = True
    trace_summary_rows: List[Dict[str, Any]] = []
    geo_cache: Dict[str, Dict[str, Any]] = {}

    try:
        os.makedirs(os.path.dirname(output_results_path), exist_ok=True)

        with maxminddb.open_database(MMDB_PATH) as mmdb_reader:
            with open(output_results_path, "w", encoding="utf-8") as output_file:
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
                            raw_msm_id = raw_result.get("msm_id", "N/A")
                            raw_probe_id = raw_result.get("prb_id", "N/A")
                            raw_timestamp = raw_result.get("endtime", raw_result.get("timestamp", "N/A"))
                            target_ip = (
                                raw_result.get("dst_addr")
                                or raw_result.get("dst_ip")
                                or raw_result.get("target_ip")
                                or raw_result.get("dst_name")
                            )
                            target_hostname = raw_result.get("dst_name") or raw_result.get("target") or raw_result.get("hostname")
                            target_asn = matcher.IP2ASN(target_ip) if target_ip else "-1"
                            service_meta = lookup_measurement(raw_msm_id)
                            raw_probe_country = (
                                raw_result.get("probe_country")
                                or raw_result.get("prb_country")
                                or raw_result.get("country_code")
                            )
                            raw_probe_asn = (
                                raw_result.get("probe_asn")
                                or raw_result.get("prb_asn")
                                or raw_result.get("asn_v4")
                            )
                            probe_meta = probe_metadata.get(str(raw_probe_id), {})
                            probe_country = raw_probe_country or probe_meta.get("probe_country")
                            probe_asn = normalize_asn_value(raw_probe_asn or probe_meta.get("probe_asn"))
                            trace_id = build_trace_id(file_name, raw_msm_id, raw_probe_id, raw_timestamp, target_ip)
                            trace_metadata = {
                                "trace_id": trace_id,
                                "service_id": service_meta["service_id"],
                                "service_class": service_meta["service_class"],
                                "service_role": service_meta["role"],
                                "deployment_type": service_meta["deployment_type"],
                                "probe_country": probe_country,
                                "probe_asn": probe_asn,
                                "target_ip": target_ip,
                                "target_asn": target_asn,
                                "target_hostname": target_hostname,
                                "source_address": raw_result.get("from") or raw_result.get("src_addr"),
                                "service_entry_hop": None,
                                "service_entry_asn": None,
                                "service_entry_resolved": False,
                                "target_asn_as_service_entry": bool(target_asn and target_asn != "-1"),
                                "path_scope": "publicly_visible_path_unresolved_entry",
                            }

                            traceroute_links = parse_hops_to_links(
                                hops=hops,
                                msm_id=raw_msm_id,
                                prb_id=raw_probe_id,
                                timestamp=raw_timestamp,
                                file_name=file_name,
                                mmdb_reader=mmdb_reader,
                                asn_resolver=asn_resolver,
                                trace_metadata=trace_metadata,
                                geo_cache=geo_cache,
                            )

                            trace_mappable_links = len(traceroute_links)
                            trace_service_entry_resolved = any(
                                bool(link.get("service_entry_resolved")) for link in traceroute_links
                            )
                            if trace_service_entry_resolved:
                                first_entry_link = next(
                                    link for link in traceroute_links if bool(link.get("service_entry_resolved"))
                                )
                                trace_metadata["service_entry_hop"] = first_entry_link.get("service_entry_hop")
                                trace_metadata["service_entry_asn"] = first_entry_link.get("service_entry_asn")
                                trace_metadata["service_entry_resolved"] = True
                                trace_metadata["path_scope"] = first_entry_link.get("path_scope")
                            trace_feasible_links = 0
                            trace_legacy_matched_links = 0
                            for link in traceroute_links:
                                match_output = matcher.match_link_to_cable(link)
                                all_feasible_segments = match_output.get("all_feasible_segments", [])
                                all_segments = match_output["all_segments"]
                                match_summary = match_output["match_summary"]

                                if not all_feasible_segments:
                                    continue

                                trace_feasible_links += 1
                                feasible_link_count += 1
                                if all_segments:
                                    trace_legacy_matched_links += 1
                                    valid_link_count += 1
                                link_info = {
                                    "msm_id": link.get("measurement_id", "N/A"),
                                    "trace_id": link.get("trace_id"),
                                    "service_id": link.get("service_id"),
                                    "service_class": link.get("service_class"),
                                    "service_role": link.get("service_role"),
                                    "deployment_type": link.get("deployment_type"),
                                    "probe_id": link.get("probe_id", "N/A"),
                                    "probe_country": link.get("probe_country"),
                                    "probe_asn": link.get("probe_asn"),
                                    "file_name": link.get("file_name", file_name),
                                    "timestamp": link.get("timestamp", "N/A"),
                                    "source_address": link.get("source_address"),
                                    "target_ip": link.get("target_ip"),
                                    "target_asn": link.get("target_asn"),
                                    "target_hostname": link.get("target_hostname"),
                                    "service_entry_hop": link.get("service_entry_hop"),
                                    "service_entry_asn": link.get("service_entry_asn"),
                                    "service_entry_resolved": link.get("service_entry_resolved"),
                                    "target_asn_as_service_entry": link.get("target_asn_as_service_entry"),
                                    "path_scope": link.get("path_scope"),
                                    "hop_range": f"Hop {link['source']['hop_num']} -> {link['destination']['hop_num']}",
                                    "src_ip": link["source"]["ip"],
                                    "dst_ip": link["destination"]["ip"],
                                    "src_asn": normalize_asn_value(link["source"].get("asn")),
                                    "dst_asn": normalize_asn_value(link["destination"].get("asn")),
                                    "src_city": link["source"]["geo"].get("city"),
                                    "dst_city": link["destination"]["geo"].get("city"),
                                    "transition_near_country": link["source"]["geo"]["country"],
                                    "transition_far_country": link["destination"]["geo"]["country"],
                                    "src_country": link["source"]["geo"]["country"],
                                    "dst_country": link["destination"]["geo"]["country"],
                                    "rtt_delta_ms": link["rtt_delta"],
                                    "hop_reply_ip_count": max(
                                        link["source"].get("hop_reply_ip_count", 0),
                                        link["destination"].get("hop_reply_ip_count", 0),
                                    ),
                                    "hop_selected_reply_rule": link["destination"].get("hop_selected_reply_rule"),
                                    "is_potential_oceanic": link["is_oceanic"],
                                }
                                match_result = {
                                    "link_info": link_info,
                                    "match_summary": match_summary,
                                    "all_feasible_segments": all_feasible_segments,
                                    "all_segments": all_segments,
                                }

                                if not is_first_entry:
                                    output_file.write(",\n")
                                json.dump(match_result, output_file, ensure_ascii=False, indent=4)
                                is_first_entry = False

                            trace_summary_rows.append(
                                {
                                    **trace_metadata,
                                    "msm_id": raw_msm_id,
                                    "probe_id": raw_probe_id,
                                    "timestamp": raw_timestamp,
                                    "file_name": file_name,
                                    "total_mappable_links": trace_mappable_links,
                                    "links_with_feasible_submarine_corridor": trace_feasible_links,
                                    "links_above_legacy_support_threshold": trace_legacy_matched_links,
                                    "has_at_least_one_mappable_segment": trace_mappable_links > 0,
                                    "has_at_least_one_feasible_submarine_corridor": trace_feasible_links > 0,
                                }
                            )

                output_file.write("\n]\n")

        finalized_stats = matcher.finalize_stats()
        if finalized_stats.get("lifecycle_metadata_warning"):
            print(
                "Warning: cable lifecycle metadata coverage is low "
                f"({finalized_stats.get('lifecycle_metadata_known_ratio', 0.0):.2%} known among considered candidates)."
            )
        with open(match_stats_output_path, "w", encoding="utf-8") as stats_file:
            json.dump(finalized_stats, stats_file, ensure_ascii=False, indent=4)

        trace_summary_path = os.path.join(output_dir, "trace_observation_summary.csv")
        pd.DataFrame(trace_summary_rows).to_csv(trace_summary_path, index=False, encoding="utf-8-sig")

        write_match_manifest(
            traceroute_file_paths=traceroute_file_paths,
            total_files_processed=total_files_processed,
            total_traces_processed=total_traces_processed,
            empty_trace_count=empty_trace_count,
            valid_link_count=valid_link_count,
            feasible_link_count=feasible_link_count,
            as_precompute_file=args.as_precompute_file if matcher.as_graph_precompute_loaded else None,
            asn_mmdb_path=args.asn_mmdb_path,
            landing_region_override_file=args.landing_region_override_file,
            path=match_manifest_output_path,
            match_output_file=output_results_path,
            match_stats_file=match_stats_output_path,
        )
    except Exception as exc:
        print(f"\nFailed while writing result files: {exc}")
        return

    print(f"\nCompleted matching across {total_files_processed} traceroute files.")
    print(f"Processed {total_traces_processed} traceroute records.")
    print(f"Empty/invalid traceroute records: {empty_trace_count}")
    print(f"Retained {feasible_link_count} links with feasible candidates before thresholding.")
    print(f"Matched {valid_link_count} links above threshold (>= {matcher.MATCH_THRESHOLD}) in legacy all_segments.")
    print(f"Results saved to: {output_results_path}")
    print(f"Stats saved to: {match_stats_output_path}")


if __name__ == "__main__":
    main()
