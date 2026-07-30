"""Shared exact identities for RIPE Atlas traceroute observations.

Identity construction is deliberately independent of transport filenames and
never uses fuzzy timestamp matching. The target address remains part of trace
identity because multi-target measurements can observe different destinations
for the same probe and timestamp.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Optional, Tuple


IDENTITY_SCHEMA_VERSION = "observation_identity_v1"
TRACE_IDENTITY_FIELDS = ("msm_id", "probe_id", "timestamp", "target_ip")
ATOMIC_SEGMENT_IDENTITY_FIELDS = (
    *TRACE_IDENTITY_FIELDS,
    "source_ttl",
    "destination_ttl",
    "src_ip",
    "dst_ip",
)

_MISSING_TOKENS = {"", "na", "n/a", "nan", "none", "null"}
_HOP_RANGE_PATTERN = re.compile(
    r"Hop\s+(?P<source>\d+)\s*->\s*(?P<destination>\d+)",
    re.IGNORECASE,
)


def normalize_identity_value(value: Any) -> str:
    """Normalize one identity component without weakening exact semantics."""
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    if text.lower() in _MISSING_TOKENS:
        return ""
    if re.fullmatch(r"-?\d+\.0", text):
        return text[:-2]
    return text


def parse_hop_range(value: Any) -> Optional[Tuple[str, str]]:
    """Parse explicit source and destination TTLs from ``Hop X -> Y``."""
    match = _HOP_RANGE_PATTERN.search(normalize_identity_value(value))
    if not match:
        return None
    return match.group("source"), match.group("destination")


def resolve_ttls(values: Mapping[str, Any]) -> Tuple[str, str]:
    """Resolve TTL fields, using an explicit hop-range string only as fallback."""
    source_ttl = normalize_identity_value(values.get("source_ttl"))
    destination_ttl = normalize_identity_value(values.get("destination_ttl"))
    if source_ttl and destination_ttl:
        return source_ttl, destination_ttl
    parsed = parse_hop_range(values.get("hop_range"))
    if parsed:
        return source_ttl or parsed[0], destination_ttl or parsed[1]
    return source_ttl, destination_ttl


def canonical_trace_id(
    msm_id: Any,
    probe_id: Any,
    exact_timestamp: Any,
    target_ip: Any,
) -> str:
    """Return an exact, transport-file-independent traceroute identity."""
    components = [
        normalize_identity_value(msm_id),
        normalize_identity_value(probe_id),
        normalize_identity_value(exact_timestamp),
        normalize_identity_value(target_ip),
    ]
    if not all(components):
        raise ValueError(
            "Canonical trace identity requires msm_id, probe_id, exact timestamp, "
            "and target_ip."
        )
    return "|".join([IDENTITY_SCHEMA_VERSION, "trace", *components])


def canonical_trace_id_from_mapping(values: Mapping[str, Any]) -> str:
    """Build canonical trace identity from a row-like mapping."""
    return canonical_trace_id(
        values.get("msm_id"),
        values.get("probe_id"),
        values.get("timestamp"),
        values.get("target_ip"),
    )


def canonical_atomic_segment_id(
    msm_id: Any,
    probe_id: Any,
    exact_timestamp: Any,
    target_ip: Any,
    source_ttl: Any,
    destination_ttl: Any,
    src_ip: Any,
    dst_ip: Any,
) -> str:
    """Return an exact identity for one observable hop-pair segment."""
    trace_id = canonical_trace_id(
        msm_id,
        probe_id,
        exact_timestamp,
        target_ip,
    )
    segment_components = [
        normalize_identity_value(source_ttl),
        normalize_identity_value(destination_ttl),
        normalize_identity_value(src_ip),
        normalize_identity_value(dst_ip),
    ]
    if not all(segment_components):
        raise ValueError(
            "Canonical atomic segment identity requires source/destination TTL "
            "and source/destination hop IP."
        )
    return "|".join([trace_id, "segment", *segment_components])


def canonical_atomic_segment_id_from_mapping(values: Mapping[str, Any]) -> str:
    """Build canonical atomic segment identity from a row-like mapping."""
    source_ttl, destination_ttl = resolve_ttls(values)
    return canonical_atomic_segment_id(
        values.get("msm_id"),
        values.get("probe_id"),
        values.get("timestamp"),
        values.get("target_ip"),
        source_ttl,
        destination_ttl,
        values.get("src_ip"),
        values.get("dst_ip"),
    )


def try_canonical_trace_id(values: Mapping[str, Any]) -> Optional[str]:
    """Return a canonical trace ID, or ``None`` when required fields are absent."""
    try:
        return canonical_trace_id_from_mapping(values)
    except ValueError:
        return None


def try_canonical_atomic_segment_id(values: Mapping[str, Any]) -> Optional[str]:
    """Return a canonical segment ID, or ``None`` for legacy incomplete rows."""
    try:
        return canonical_atomic_segment_id_from_mapping(values)
    except ValueError:
        return None
