#!/usr/bin/env python3
"""Create one-off RIPE Atlas traceroute measurements from a local JSON config.

This helper is intentionally separate from the main analysis pipeline. It
creates Atlas measurements and stores the measurement IDs / submission receipts
for later experiment supplementation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DEFAULT_CONFIG_CANDIDATES = [
    SCRIPT_DIR / "atlas_traceroute_config.local.json",
    SCRIPT_DIR / "atlas_traceroute_config.json",
    SCRIPT_DIR / "atlas_traceroute_config.example.json",
]
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "results"
ATLAS_API_BASE = "https://atlas.ripe.net/api/v2"
PROBE_LIST_ENDPOINT = f"{ATLAS_API_BASE}/probes/"
MEASUREMENT_CREATE_ENDPOINT = f"{ATLAS_API_BASE}/measurements/"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the RIPE Atlas measurement helper."""
    parser = argparse.ArgumentParser(
        description=(
            "Create RIPE Atlas one-off traceroute measurements from a local JSON "
            "config. The script fetches active public probes, chunks them into "
            "batches, and submits one traceroute measurement per target per batch."
        )
    )
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Path to the JSON config file. If omitted, the script tries "
            "atlas_traceroute_config.local.json, then atlas_traceroute_config.json, "
            "then atlas_traceroute_config.example.json inside the probe directory."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where submission receipts will be written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the probe selection and measurement payloads without submitting.",
    )
    parser.add_argument(
        "--limit-probes",
        type=int,
        default=None,
        help="Optional CLI override limiting the number of selected probes.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list the selected probes; do not create measurements.",
    )
    return parser.parse_args()


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def utc_timestamp_slug() -> str:
    """Return a filesystem-friendly UTC timestamp."""
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> Dict[str, Any]:
    """Load a JSON object from disk."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Config file must contain a JSON object: {path}")
    return payload


def resolve_config_path(explicit_path: Optional[str]) -> Path:
    """Resolve the config path from CLI input or default candidates."""
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        return path

    for candidate in DEFAULT_CONFIG_CANDIDATES:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "No RIPE Atlas config file found. Expected one of: "
        + ", ".join(str(candidate) for candidate in DEFAULT_CONFIG_CANDIDATES)
    )


def build_query_url(base_url: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Append encoded query parameters to a base URL."""
    if not params:
        return base_url
    normalized = {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }
    if not normalized:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(normalized)}"


def http_json_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a JSON HTTP request and return the decoded object."""
    request_data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        request_data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url, data=request_data, headers=headers, method=method)
    with urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
    decoded = json.loads(body) if body else {}
    if not isinstance(decoded, dict):
        return {"raw_response": decoded}
    return decoded


def normalize_country_set(values: Sequence[Any]) -> Optional[set]:
    """Normalize a country allowlist / blocklist into uppercase strings."""
    normalized = {
        str(value).strip().upper()
        for value in values
        if str(value).strip()
    }
    return normalized or None


def normalize_asn_set(values: Sequence[Any]) -> Optional[set]:
    """Normalize an ASN allowlist into plain integer strings."""
    normalized = {
        str(value).strip().upper().removeprefix("AS")
        for value in values
        if str(value).strip()
    }
    return normalized or None


def select_probe_country(probe: Dict[str, Any]) -> str:
    """Extract the probe country code from the API payload."""
    country = str(probe.get("country_code", "")).strip().upper()
    if country:
        return country
    geometry = probe.get("geometry") or {}
    return str(geometry.get("country_code", "")).strip().upper()


def select_probe_asn(probe: Dict[str, Any]) -> str:
    """Extract the probe ASN from the API payload."""
    for field in ("asn_v4", "asn_v6", "asn"):
        value = probe.get(field)
        if value in (None, "", "NA"):
            continue
        return str(value).strip().upper().removeprefix("AS")
    return ""


def filter_probe_records(
    probes: Iterable[Dict[str, Any]],
    selection_cfg: Dict[str, Any],
    limit_override: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Apply optional local filters to probe records after the API fetch."""
    include_anchors = bool(selection_cfg.get("include_anchors", False))
    country_allowlist = normalize_country_set(selection_cfg.get("country_allowlist", []))
    asn_allowlist = normalize_asn_set(selection_cfg.get("asn_allowlist", []))
    filtered: List[Dict[str, Any]] = []

    for probe in probes:
        if not include_anchors and bool(probe.get("is_anchor", False)):
            continue
        if country_allowlist:
            country = select_probe_country(probe)
            if country not in country_allowlist:
                continue
        if asn_allowlist:
            asn = select_probe_asn(probe)
            if asn not in asn_allowlist:
                continue
        filtered.append(probe)

    effective_limit = limit_override
    if effective_limit is None:
        raw_limit = selection_cfg.get("limit")
        if raw_limit not in (None, "", 0):
            effective_limit = int(raw_limit)
    if effective_limit and effective_limit > 0:
        return filtered[:effective_limit]
    return filtered


def fetch_probe_records(selection_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch matching probe records from the RIPE Atlas public probes endpoint."""
    page_size = int(selection_cfg.get("page_size", 500) or 500)
    params = {
        "status": int(selection_cfg.get("status", 1) or 1),
        "is_public": "true" if bool(selection_cfg.get("is_public", True)) else "false",
        "page_size": page_size,
    }
    url = build_query_url(PROBE_LIST_ENDPOINT, params)
    probes: List[Dict[str, Any]] = []

    while url:
        response = http_json_request(url, method="GET")
        results = response.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Unexpected RIPE Atlas probe list response format.")
        probes.extend(item for item in results if isinstance(item, dict))
        next_url = response.get("next")
        url = str(next_url).strip() if next_url else ""

    return probes


def chunked(values: Sequence[Any], chunk_size: int) -> Iterable[Sequence[Any]]:
    """Yield fixed-size chunks from a sequence."""
    if chunk_size <= 0:
        raise ValueError("batch_size must be positive.")
    for index in range(0, len(values), chunk_size):
        yield values[index:index + chunk_size]


def build_measurement_definition(
    target_cfg: Dict[str, Any],
    defaults: Dict[str, Any],
    request_name: str,
    batch_index: int,
) -> Dict[str, Any]:
    """Build one RIPE Atlas traceroute measurement definition."""
    target = str(target_cfg.get("target", "")).strip()
    if not target:
        raise ValueError("Each target entry must define a non-empty 'target'.")

    description = str(target_cfg.get("description", "")).strip()
    if not description:
        description = f"{request_name}-{target}-batch-{batch_index:03d}"

    tags = target_cfg.get("tags", defaults.get("tags", []))
    if not isinstance(tags, list):
        tags = [str(tags)]

    definition = {
        "target": target,
        "description": description,
        "type": "traceroute",
        "af": int(target_cfg.get("af", defaults.get("af", 4))),
        "protocol": str(target_cfg.get("protocol", defaults.get("protocol", "ICMP"))).upper(),
        "packets": int(target_cfg.get("packets", defaults.get("packets", 3))),
        "paris": int(target_cfg.get("paris", defaults.get("paris", 16))),
        "size": int(target_cfg.get("size", defaults.get("size", 48))),
        "timeout": int(target_cfg.get("timeout", defaults.get("timeout", 4000))),
        "resolve_on_probe": bool(target_cfg.get("resolve_on_probe", defaults.get("resolve_on_probe", True))),
        "include_probe_id": bool(target_cfg.get("include_probe_id", defaults.get("include_probe_id", True))),
        "skip_dns_check": bool(target_cfg.get("skip_dns_check", defaults.get("skip_dns_check", False))),
        "spread": int(target_cfg.get("spread", defaults.get("spread", 0))),
        "is_public": bool(target_cfg.get("is_public", defaults.get("is_public", False))),
        "tags": [str(tag) for tag in tags if str(tag).strip()],
    }
    if target_cfg.get("port") is not None:
        definition["port"] = int(target_cfg["port"])
    return definition


def build_measurement_payload(
    bill_to: str,
    probe_ids: Sequence[int],
    target_cfg: Dict[str, Any],
    defaults: Dict[str, Any],
    request_name: str,
    batch_index: int,
) -> Dict[str, Any]:
    """Build the POST payload for one target / probe-batch pair."""
    if not probe_ids:
        raise ValueError("Cannot create a measurement with an empty probe list.")

    definition = build_measurement_definition(target_cfg, defaults, request_name, batch_index)
    payload: Dict[str, Any] = {
        "definitions": [definition],
        "probes": [
            {
                "requested": len(probe_ids),
                "type": "probes",
                "value": ",".join(str(probe_id) for probe_id in probe_ids),
            }
        ],
        "is_oneoff": bool(defaults.get("is_oneoff", True)),
    }
    if bill_to:
        payload["bill_to"] = bill_to
    return payload


def submit_measurement(payload: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """Submit a measurement-creation request to RIPE Atlas."""
    url = build_query_url(MEASUREMENT_CREATE_ENDPOINT, {"key": api_key})
    return http_json_request(url, method="POST", payload=payload)


def choose_probe_id_value(probe: Dict[str, Any]) -> int:
    """Return the probe ID as an integer."""
    value = probe.get("id")
    if value is None:
        raise ValueError(f"Probe record is missing 'id': {probe}")
    return int(value)


def build_probe_snapshot(probes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw probe records into a compact snapshot for receipts."""
    snapshot: List[Dict[str, Any]] = []
    for probe in probes:
        snapshot.append(
            {
                "id": choose_probe_id_value(probe),
                "country_code": select_probe_country(probe) or "NA",
                "asn": select_probe_asn(probe) or "NA",
                "is_anchor": bool(probe.get("is_anchor", False)),
                "status_name": str(probe.get("status_name", "")).strip() or "NA",
            }
        )
    return snapshot


def validate_config(config: Dict[str, Any]) -> None:
    """Validate the minimal required config structure."""
    if not isinstance(config.get("targets"), list) or not config["targets"]:
        raise ValueError("Config must define a non-empty 'targets' list.")
    if not isinstance(config.get("probe_selection", {}), dict):
        raise ValueError("Config field 'probe_selection' must be a JSON object.")
    if not isinstance(config.get("measurement_defaults", {}), dict):
        raise ValueError("Config field 'measurement_defaults' must be a JSON object.")


def main() -> None:
    """Entry point for creating RIPE Atlas traceroute measurements."""
    args = parse_args()
    config_path = resolve_config_path(args.config)
    config = load_json(config_path)
    validate_config(config)

    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    request_name = str(config.get("request_name", "infocom26-ripe-atlas-traceroute")).strip()
    api_key = str(config.get("api_key", "")).strip()
    bill_to = str(config.get("bill_to", "")).strip()
    config_dry_run = bool(config.get("dry_run", False))
    effective_dry_run = bool(args.dry_run or config_dry_run or args.list_only)
    selection_cfg = dict(config.get("probe_selection", {}))
    defaults = dict(config.get("measurement_defaults", {}))
    batch_size = int(selection_cfg.get("batch_size", 500) or 500)

    if not effective_dry_run and not api_key:
        raise ValueError(
            "A non-empty api_key is required for real submission. "
            "Use dry_run/list_only or set api_key in the local config file."
        )

    print(f"Loading config: {config_path}")
    print("Fetching RIPE Atlas probe inventory ...")
    probe_records = fetch_probe_records(selection_cfg)
    filtered_probes = filter_probe_records(
        probe_records,
        selection_cfg=selection_cfg,
        limit_override=args.limit_probes,
    )
    probe_ids = [choose_probe_id_value(probe) for probe in filtered_probes]
    probe_batches = list(chunked(probe_ids, batch_size)) if probe_ids else []

    print(
        "Selected probes: "
        f"{len(probe_ids)} total, "
        f"{len(probe_batches)} batches, "
        f"batch_size={batch_size}"
    )
    if args.list_only:
        preview = build_probe_snapshot(filtered_probes[: min(20, len(filtered_probes))])
        print(json.dumps({"probe_preview": preview}, indent=2, ensure_ascii=False))
        return

    targets = config["targets"]
    receipt: Dict[str, Any] = {
        "request_name": request_name,
        "config_path": str(config_path),
        "submitted_at_utc": utc_now().isoformat(),
        "dry_run": effective_dry_run,
        "probe_selection_summary": {
            "requested_mode": selection_cfg.get("mode", "all_public_active"),
            "status": selection_cfg.get("status", 1),
            "is_public": bool(selection_cfg.get("is_public", True)),
            "include_anchors": bool(selection_cfg.get("include_anchors", False)),
            "selected_probe_count": len(probe_ids),
            "batch_size": batch_size,
            "batch_count": len(probe_batches),
        },
        "targets": targets,
        "probe_preview": build_probe_snapshot(filtered_probes[: min(20, len(filtered_probes))]),
        "submissions": [],
    }

    if not probe_ids:
        print("No probes matched the current selection filters. Writing an empty receipt.")
    else:
        for target_cfg in targets:
            for batch_index, probe_batch in enumerate(probe_batches, start=1):
                payload = build_measurement_payload(
                    bill_to=bill_to,
                    probe_ids=probe_batch,
                    target_cfg=target_cfg,
                    defaults=defaults,
                    request_name=request_name,
                    batch_index=batch_index,
                )
                submission_record: Dict[str, Any] = {
                    "target": target_cfg.get("target"),
                    "description": payload["definitions"][0].get("description"),
                    "batch_index": batch_index,
                    "probe_count": len(probe_batch),
                    "probe_id_min": min(probe_batch),
                    "probe_id_max": max(probe_batch),
                    "payload_preview": payload,
                }
                if effective_dry_run:
                    submission_record["status"] = "dry_run_only"
                else:
                    response = submit_measurement(payload, api_key=api_key)
                    submission_record["status"] = "submitted"
                    submission_record["api_response"] = response
                    measurement_ids = response.get("measurements") or response.get("measurement_ids") or []
                    if measurement_ids:
                        submission_record["measurement_ids"] = measurement_ids
                    print(
                        "Submitted measurement batch: "
                        f"target={submission_record['target']} "
                        f"batch={batch_index}/{len(probe_batches)} "
                        f"probe_count={len(probe_batch)}"
                    )
                receipt["submissions"].append(submission_record)

    output_path = output_dir / f"ripe_atlas_traceroute_request_{utc_timestamp_slug()}.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, ensure_ascii=False)

    target_count = len(targets)
    print(
        "Saved RIPE Atlas request receipt: "
        f"{output_path} "
        f"(targets={target_count}, probes={len(probe_ids)}, dry_run={effective_dry_run})"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
