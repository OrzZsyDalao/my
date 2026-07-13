#!/usr/bin/env python3
"""Download selected public RIPE Atlas IPv4 traceroute result windows.

The downloaded files are RIPE Atlas result JSON arrays and can be placed under
data/traceroute_rundnsroot/ for direct use by the current analysis pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from http.client import IncompleteRead
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = REPO_DIR / "data" / "traceroute_rundnsroot" / "ripe_atlas_public_20260701_0000_0100"
DEFAULT_MANIFEST_DIR = SCRIPT_DIR / "manifests"
ATLAS_API_BASE = "https://atlas.ripe.net/api/v2"
DEFAULT_START_UTC = "2026-07-01T00:00:00Z"
DEFAULT_DURATION_MINUTES = 60


ROOT_TRACEROUTE_MEASUREMENTS: Dict[str, int] = {
    "A-Root": 5009,
    "B-Root": 5010,
    "C-Root": 5011,
    "D-Root": 5012,
    "E-Root": 5013,
    "F-Root": 5004,
    "G-Root": 5014,
    "H-Root": 5015,
    "I-Root": 5005,
    "J-Root": 5016,
    "K-Root": 5001,
    "L-Root": 5008,
    "M-Root": 5006,
}


APPLICATION_TRACEROUTE_MEASUREMENTS: Dict[str, Dict[str, Any]] = {
    "Wikipedia": {
        "msm_id": 86710103,
        "target": "wikipedia.org",
        "role": "primary_application",
    },
    "Reddit": {
        "msm_id": 176906957,
        "target": "reddit.com",
        "role": "primary_application",
    },
}


EXTENSION_TRACEROUTE_MEASUREMENTS: Dict[str, Dict[str, Any]] = {
    "Netflix-Assets": {
        "msm_id": 176517335,
        "target": "assets.nflxext.com",
        "role": "edge_localization_extension",
    }
}


BASELINE_TRACEROUTE_MEASUREMENTS: Dict[str, Dict[str, Any]] = {
    "Topology-IPv4-ICMP": {
        "msm_id": 5151,
        "protocol": "ICMP",
        "role": "primary_topology_baseline",
    },
    "Topology-IPv4-UDP": {
        "msm_id": 5051,
        "protocol": "UDP",
        "role": "historical_protocol_baseline",
    },
}


def parse_args() -> argparse.Namespace:
    """Parse CLI options for the public traceroute downloader."""
    parser = argparse.ArgumentParser(
        description=(
            "Download the first-round public RIPE Atlas IPv4 traceroute datasets "
            "for a fixed UTC time window."
        )
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where pipeline-ready RIPE Atlas result JSON files are written.",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional manifest JSON path. Defaults to ripe_atlas_public_download/manifests/...",
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START_UTC,
        help="UTC start time, for example 2026-07-01T00:00:00Z.",
    )
    parser.add_argument(
        "--duration-minutes",
        type=int,
        default=DEFAULT_DURATION_MINUTES,
        help="Download window length in minutes.",
    )
    parser.add_argument(
        "--measurement-id",
        type=int,
        action="append",
        default=None,
        help="Optional measurement ID filter. Repeat to download/test only selected IDs.",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Validate measurement metadata but do not download result data.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip downloads when the target output file already exists.",
    )
    parser.add_argument(
        "--no-count-records",
        action="store_true",
        help="Skip streaming JSON record counting after download.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of HTTP retries for metadata and result downloads.",
    )
    return parser.parse_args()


def parse_utc_time(value: str) -> datetime:
    """Parse a UTC timestamp string."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def slugify(value: str) -> str:
    """Convert a label into a stable filename-safe slug."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "unnamed"


def build_measurement_catalog() -> List[Dict[str, Any]]:
    """Return the complete first-round public traceroute measurement catalog."""
    catalog: List[Dict[str, Any]] = []
    for root_name, msm_id in ROOT_TRACEROUTE_MEASUREMENTS.items():
        root_target = f"{root_name[0].lower()}.root-servers.net"
        catalog.append(
            {
                "dataset": "dns_root",
                "name": root_name,
                "msm_id": msm_id,
                "target": root_target,
                "role": "critical_infrastructure_anycast",
                "interpretation_note": "DNS Root built-in IPv4 traceroute for anycast infrastructure analysis.",
            }
        )
    for name, spec in APPLICATION_TRACEROUTE_MEASUREMENTS.items():
        catalog.append(
            {
                "dataset": "popular_application",
                "name": name,
                **spec,
                "interpretation_note": "Actual dst_addr values must be preserved because per-probe service resolution may differ.",
            }
        )
    for name, spec in EXTENSION_TRACEROUTE_MEASUREMENTS.items():
        catalog.append(
            {
                "dataset": "edge_localization_extension",
                "name": name,
                **spec,
                "interpretation_note": "This measurement represents assets.nflxext.com paths, not full Netflix video delivery.",
            }
        )
    for name, spec in BASELINE_TRACEROUTE_MEASUREMENTS.items():
        catalog.append(
            {
                "dataset": "topology_baseline",
                "name": name,
                **spec,
                "interpretation_note": "Dynamic multi-target traceroute baseline; use for aggregate baseline analysis.",
            }
        )
    return catalog


def build_query_url(base_url: str, params: Dict[str, Any]) -> str:
    """Append URL-encoded query parameters."""
    filtered = {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }
    if not filtered:
        return base_url
    return f"{base_url}?{urlencode(filtered)}"


def http_json_request(url: str, timeout: int, retries: int) -> Dict[str, Any]:
    """GET a JSON object with retry handling."""
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            request = Request(url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
            decoded = json.loads(body) if body else {}
            if not isinstance(decoded, dict):
                return {"raw_response": decoded}
            return decoded
        except (HTTPError, URLError, TimeoutError, IncompleteRead, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"Failed to fetch JSON from {url}: {last_error}") from last_error


def download_url_to_file(url: str, path: Path, timeout: int, retries: int) -> int:
    """Stream a URL response into a local file and return byte count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            request = Request(url, headers={"Accept": "application/json"})
            byte_count = 0
            with urlopen(request, timeout=timeout) as response, tmp_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    byte_count += len(chunk)
            tmp_path.replace(path)
            return byte_count
        except (HTTPError, URLError, TimeoutError, IncompleteRead, OSError) as exc:
            last_error = exc
            if tmp_path.exists():
                tmp_path.unlink()
            if attempt < retries:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"Failed to download {url}: {last_error}") from last_error


def metadata_url(msm_id: int) -> str:
    """Return the RIPE Atlas measurement metadata URL."""
    return f"{ATLAS_API_BASE}/measurements/{msm_id}/"


def results_url(msm_id: int, start_epoch: int, stop_epoch: int) -> str:
    """Return the RIPE Atlas measurement results URL for a time window."""
    return build_query_url(
        f"{ATLAS_API_BASE}/measurements/{msm_id}/results/",
        {
            "start": start_epoch,
            "stop": stop_epoch,
            "format": "json",
        },
    )


def expected_output_path(
    output_dir: Path,
    measurement: Dict[str, Any],
    start_time: datetime,
    stop_time: datetime,
) -> Path:
    """Build a pipeline-ready output filename for one measurement."""
    start_slug = start_time.strftime("%Y%m%dT%H%M%SZ")
    stop_slug = stop_time.strftime("%H%M%SZ")
    dataset = slugify(str(measurement["dataset"]))
    name = slugify(str(measurement["name"]))
    msm_id = int(measurement["msm_id"])
    return output_dir / f"{dataset}_{name}_msm{msm_id}_{start_slug}_{stop_slug}.json"


def verify_measurement_metadata(expected: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Check that a RIPE Atlas measurement looks like the expected IPv4 traceroute."""
    expected_msm_id = int(expected["msm_id"])
    metadata_id = metadata.get("id")
    measurement_type = str(metadata.get("type", "")).lower()
    af = metadata.get("af")
    target = metadata.get("target") or metadata.get("target_ip") or metadata.get("target_hostname")
    protocol = metadata.get("protocol")

    warnings: List[str] = []
    if metadata_id is not None and int(metadata_id) != expected_msm_id:
        raise ValueError(f"Metadata ID mismatch: expected {expected_msm_id}, got {metadata_id}")
    if measurement_type and measurement_type != "traceroute":
        raise ValueError(f"Measurement {expected_msm_id} is not traceroute: type={measurement_type}")
    if af is not None and int(af) != 4:
        raise ValueError(f"Measurement {expected_msm_id} is not IPv4: af={af}")

    expected_target = expected.get("target")
    if expected_target and target and str(expected_target).lower() not in str(target).lower():
        warnings.append(
            f"metadata target differs from catalog target: catalog={expected_target}, metadata={target}"
        )
    expected_protocol = expected.get("protocol")
    if expected_protocol and protocol and str(expected_protocol).upper() != str(protocol).upper():
        warnings.append(
            f"metadata protocol differs from catalog protocol: catalog={expected_protocol}, metadata={protocol}"
        )

    return {
        "id": metadata_id,
        "type": metadata.get("type"),
        "af": af,
        "target": target,
        "protocol": protocol,
        "description": metadata.get("description"),
        "is_oneoff": metadata.get("is_oneoff"),
        "status": metadata.get("status"),
        "warnings": warnings,
    }


def count_json_array_records(path: Path) -> Optional[int]:
    """Count top-level records in a JSON array without loading the whole file."""
    decoder = json.JSONDecoder()
    count = 0
    buffer = ""
    started = False
    index = 0
    with path.open("r", encoding="utf-8") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            buffer += chunk
            if not started:
                array_start = buffer.find("[")
                if array_start == -1:
                    continue
                buffer = buffer[array_start + 1:]
                started = True
                index = 0
            while True:
                while index < len(buffer) and buffer[index] in " \r\n\t,":
                    index += 1
                if index >= len(buffer):
                    buffer = ""
                    index = 0
                    break
                if buffer[index] == "]":
                    return count
                try:
                    _, next_index = decoder.raw_decode(buffer, index)
                except json.JSONDecodeError:
                    if index > 0:
                        buffer = buffer[index:]
                        index = 0
                    break
                count += 1
                index = next_index
    return count if started else None


def default_manifest_path(start_time: datetime, stop_time: datetime) -> Path:
    """Build the default manifest path for a run."""
    DEFAULT_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    start_slug = start_time.strftime("%Y%m%dT%H%M%SZ")
    stop_slug = stop_time.strftime("%H%M%SZ")
    return DEFAULT_MANIFEST_DIR / f"ripe_atlas_public_{start_slug}_{stop_slug}_manifest.json"


def write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    """Write a manifest JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def main() -> None:
    """Download the configured public traceroute measurement set."""
    args = parse_args()
    start_time = parse_utc_time(args.start)
    stop_time = start_time + timedelta(minutes=args.duration_minutes)
    start_epoch = int(start_time.timestamp())
    stop_epoch = int(stop_time.timestamp())
    output_dir = Path(args.output_dir).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else default_manifest_path(start_time, stop_time)
    selected_ids = set(args.measurement_id or [])

    catalog = build_measurement_catalog()
    if selected_ids:
        catalog = [entry for entry in catalog if int(entry["msm_id"]) in selected_ids]
    if not catalog:
        raise ValueError("No measurements selected.")

    run_manifest: Dict[str, Any] = {
        "download_profile": "ripe_atlas_public_ipv4_traceroute_first_round",
        "window_start_utc": start_time.isoformat(),
        "window_stop_utc": stop_time.isoformat(),
        "duration_minutes": args.duration_minutes,
        "output_dir": str(output_dir),
        "metadata_only": bool(args.metadata_only),
        "result_semantics": "RIPE Atlas public traceroute results; dst_addr is preserved as returned by Atlas.",
        "pipeline_use": "Files under output_dir are JSON arrays directly readable by source/main_analysis.py.",
        "measurements": [],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Selected {len(catalog)} public RIPE Atlas traceroute measurements.")
    print(f"UTC window: {start_time.isoformat()} to {stop_time.isoformat()}")
    print(f"Output directory: {output_dir}")

    for index, measurement in enumerate(catalog, start=1):
        msm_id = int(measurement["msm_id"])
        output_path = expected_output_path(output_dir, measurement, start_time, stop_time)
        print(f"[{index}/{len(catalog)}] Validating msm_id={msm_id} {measurement['name']} ...")

        metadata = http_json_request(metadata_url(msm_id), timeout=args.timeout, retries=args.retries)
        verified_metadata = verify_measurement_metadata(measurement, metadata)
        record: Dict[str, Any] = {
            **measurement,
            "metadata": verified_metadata,
            "output_file": str(output_path),
            "results_url": results_url(msm_id, start_epoch, stop_epoch),
            "status": "metadata_validated",
        }

        if args.metadata_only:
            run_manifest["measurements"].append(record)
            continue

        if args.skip_existing and output_path.exists():
            record["status"] = "skipped_existing"
            record["bytes"] = output_path.stat().st_size
            if not args.no_count_records:
                record["record_count"] = count_json_array_records(output_path)
            run_manifest["measurements"].append(record)
            print(f"  skipped existing file: {output_path}")
            continue

        print(f"  downloading results to {output_path.name} ...")
        byte_count = download_url_to_file(
            record["results_url"],
            output_path,
            timeout=args.timeout,
            retries=args.retries,
        )
        record["bytes"] = byte_count
        if not args.no_count_records:
            record["record_count"] = count_json_array_records(output_path)
        record["status"] = "downloaded"
        run_manifest["measurements"].append(record)
        write_manifest(manifest_path, run_manifest)
        print(
            f"  saved {byte_count} bytes"
            + (f", records={record.get('record_count')}" if "record_count" in record else "")
        )

    downloaded = sum(1 for item in run_manifest["measurements"] if item.get("status") == "downloaded")
    skipped = sum(1 for item in run_manifest["measurements"] if item.get("status") == "skipped_existing")
    run_manifest["summary"] = {
        "selected_measurements": len(catalog),
        "downloaded": downloaded,
        "skipped_existing": skipped,
        "metadata_validated_only": sum(
            1 for item in run_manifest["measurements"] if item.get("status") == "metadata_validated"
        ),
        "total_bytes": sum(int(item.get("bytes", 0)) for item in run_manifest["measurements"]),
        "total_records": sum(
            int(item.get("record_count", 0) or 0) for item in run_manifest["measurements"]
        ),
    }
    write_manifest(manifest_path, run_manifest)
    print(f"Manifest written to: {manifest_path}")
    print(f"Summary: {run_manifest['summary']}")


if __name__ == "__main__":
    main()
