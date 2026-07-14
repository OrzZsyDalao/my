"""Shared measurement and service metadata for paper-facing analysis.

This catalog is intentionally small and explicit. Unknown measurements fall
back to stable `msm_<id>` service identities so downstream code never has to
guess service names from filenames.
"""

from __future__ import annotations

from typing import Any, Dict


MEASUREMENT_CATALOG: Dict[int, Dict[str, str]] = {
    5009: {"service_id": "A-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5010: {"service_id": "B-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5011: {"service_id": "C-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5012: {"service_id": "D-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5013: {"service_id": "E-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5004: {"service_id": "F-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5014: {"service_id": "G-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5015: {"service_id": "H-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5005: {"service_id": "I-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5016: {"service_id": "J-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5001: {"service_id": "K-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5008: {"service_id": "L-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    5006: {"service_id": "M-Root", "service_class": "dns_root", "deployment_type": "anycast", "role": "primary_critical_service"},
    86710103: {"service_id": "Wikipedia", "service_class": "popular_web", "deployment_type": "distributed", "role": "primary_application"},
    176906957: {"service_id": "Reddit", "service_class": "popular_web", "deployment_type": "distributed", "role": "primary_application"},
    176517335: {"service_id": "Netflix-Assets", "service_class": "edge_localized_application", "deployment_type": "distributed", "role": "extension"},
    5151: {"service_id": "Topology-IPv4-ICMP", "service_class": "topology_baseline", "deployment_type": "dynamic_multi_target", "role": "primary_baseline"},
    5051: {"service_id": "Topology-IPv4-UDP", "service_class": "topology_baseline", "deployment_type": "dynamic_multi_target", "role": "historical_baseline"},
}


def normalize_msm_id(msm_id: Any) -> int | None:
    """Normalize a RIPE Atlas measurement id to int when possible."""
    try:
        if msm_id is None:
            return None
        text = str(msm_id).strip()
        if not text or text.upper() == "N/A":
            return None
        return int(float(text))
    except (TypeError, ValueError):
        return None


def lookup_measurement(msm_id: Any) -> Dict[str, str]:
    """Return service metadata for a measurement id with an explicit unknown fallback."""
    normalized = normalize_msm_id(msm_id)
    if normalized is not None and normalized in MEASUREMENT_CATALOG:
        result = dict(MEASUREMENT_CATALOG[normalized])
        result["msm_id"] = str(normalized)
        return result
    service_id = f"msm_{msm_id}" if msm_id not in (None, "") else "msm_unknown"
    return {
        "msm_id": "" if msm_id is None else str(msm_id),
        "service_id": service_id,
        "service_class": "unknown",
        "deployment_type": "unknown",
        "role": "unknown",
    }

