from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://www.submarinecablemap.com"
SEARCH_PATH = "/api/v3/search.json"
CABLE_GEO_PATH = "/api/v3/cable/cable-geo.json"
LANDING_POINT_GEO_PATH = "/api/v3/landing-point/landing-point-geo.json"
CONFIG_PATH = "/api/v3/config.json"

CABLE_FIELD_ORDER = [
    "id",
    "name",
    "length",
    "landing_points",
    "owners",
    "suppliers",
    "rfs",
    "rfs_year",
    "is_planned",
    "url",
    "notes",
]
LANDING_POINT_FIELD_ORDER = ["id", "name", "country", "is_tbd"]
USER_AGENT = "Mozilla/5.0 (compatible; CodexSubmarineCableMapBot/1.0)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the latest submarine cable JSON files from submarinecablemap.com "
            "and compare them with the local data/cable directory."
        )
    )
    parser.add_argument(
        "--output-root",
        default="submarinecablemap",
        help="Directory where downloaded files and reports will be written.",
    )
    parser.add_argument(
        "--compare-root",
        default="data/cable",
        help="Existing local cable directory to compare against.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Maximum number of concurrent cable detail requests.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-request timeout in seconds.",
    )
    return parser.parse_args()


def build_url(path: str) -> str:
    return f"{BASE_URL}{path}"


def fetch_json(path: str, timeout: int) -> Any:
    request = Request(
        build_url(path),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ordered_landing_point(item: dict[str, Any]) -> dict[str, Any]:
    ordered = {key: item.get(key) for key in LANDING_POINT_FIELD_ORDER}
    for key in sorted(item.keys()):
        if key not in ordered:
            ordered[key] = item[key]
    return ordered


def ordered_cable(item: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for key in CABLE_FIELD_ORDER:
        value = item.get(key)
        if key == "landing_points":
            value = [ordered_landing_point(point) for point in (value or [])]
        ordered[key] = value
    for key in sorted(item.keys()):
        if key not in ordered:
            ordered[key] = item[key]
    return ordered


def write_json_file(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_pretty_json_file(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def extract_cable_ids(search_entries: list[dict[str, Any]], cable_geo: dict[str, Any]) -> list[str]:
    ids: set[str] = set()
    prefix = "/submarine-cable/"

    for entry in search_entries:
        url = entry.get("url")
        if isinstance(url, str) and url.startswith(prefix):
            ids.add(url[len(prefix) :])

    for feature in cable_geo.get("features", []):
        cable_id = feature.get("properties", {}).get("id")
        if isinstance(cable_id, str) and cable_id:
            ids.add(cable_id)

    return sorted(ids)


def fetch_one_cable(cable_id: str, timeout: int) -> dict[str, Any]:
    payload = fetch_json(f"/api/v3/cable/{cable_id}.json", timeout=timeout)
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected payload type for cable {cable_id}: {type(payload)!r}")
    return ordered_cable(payload)


def normalize_landing_points(points: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = [ordered_landing_point(point) for point in (points or [])]
    return sorted(
        normalized,
        key=lambda point: (
            str(point.get("id") or ""),
            str(point.get("name") or ""),
            str(point.get("country") or ""),
            str(point.get("is_tbd")),
        ),
    )


def load_local_cables(path: Path) -> dict[str, dict[str, Any]]:
    cables: dict[str, dict[str, Any]] = {}
    for file_path in sorted(path.glob("*.json")):
        if file_path.name == "landing-point-geo.json":
            continue
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected JSON structure in {file_path}")
        cable_id = data.get("id") or file_path.stem
        cables[str(cable_id)] = ordered_cable(data)
    return cables


def load_landing_point_geo(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected landing-point geo payload in {path}")
    return payload


def landing_point_feature_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    feature_map: dict[str, dict[str, Any]] = {}
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        feature_id = properties.get("id")
        if isinstance(feature_id, str) and feature_id:
            feature_map[feature_id] = feature
    return feature_map


def compare_landing_point_geo(remote: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    remote_map = landing_point_feature_map(remote)
    local_map = landing_point_feature_map(local)
    remote_ids = set(remote_map)
    local_ids = set(local_map)
    shared_ids = sorted(remote_ids & local_ids)

    changed_ids = [feature_id for feature_id in shared_ids if remote_map[feature_id] != local_map[feature_id]]

    return {
        "remote_feature_count": len(remote_map),
        "local_feature_count": len(local_map),
        "remote_only_count": len(remote_ids - local_ids),
        "local_only_count": len(local_ids - remote_ids),
        "changed_feature_count": len(changed_ids),
        "remote_only_ids": sorted(remote_ids - local_ids),
        "local_only_ids": sorted(local_ids - remote_ids),
        "changed_feature_ids": changed_ids,
    }


def validate_replacement_dataset(cable_dir: Path) -> dict[str, Any]:
    landing_point_geo_path = cable_dir / "landing-point-geo.json"
    landing_point_geo = load_landing_point_geo(landing_point_geo_path)
    landing_point_ids = set(landing_point_feature_map(landing_point_geo))

    cable_files = sorted(path for path in cable_dir.glob("*.json") if path.name != "landing-point-geo.json")
    missing_required_fields: list[dict[str, Any]] = []
    malformed_landing_points: list[dict[str, Any]] = []
    missing_geo_refs: dict[str, list[str]] = {}

    required_fields = {"id", "name", "length", "landing_points", "owners", "suppliers", "rfs", "rfs_year", "is_planned", "url", "notes"}

    for file_path in cable_files:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            missing_required_fields.append({"file": file_path.name, "reason": "not_an_object"})
            continue

        missing_fields = sorted(required_fields - set(payload))
        if missing_fields:
            missing_required_fields.append({"file": file_path.name, "missing_fields": missing_fields})

        landing_points = payload.get("landing_points")
        if not isinstance(landing_points, list):
            malformed_landing_points.append({"file": file_path.name, "reason": "landing_points_not_a_list"})
            continue

        file_missing_geo_refs: list[str] = []
        for point in landing_points:
            if not isinstance(point, dict) or not point.get("id"):
                malformed_landing_points.append({"file": file_path.name, "reason": "landing_point_missing_id"})
                continue
            if point["id"] not in landing_point_ids and not point.get("is_tbd"):
                file_missing_geo_refs.append(point["id"])

        if file_missing_geo_refs:
            missing_geo_refs[file_path.name] = sorted(set(file_missing_geo_refs))

    return {
        "replacement_ready": not missing_required_fields and not malformed_landing_points,
        "cable_file_count": len(cable_files),
        "landing_point_feature_count": len(landing_point_ids),
        "missing_required_fields": missing_required_fields,
        "malformed_landing_points": malformed_landing_points,
        "files_with_missing_geo_refs_count": len(missing_geo_refs),
        "files_with_missing_geo_refs": missing_geo_refs,
    }


def compare_cable(remote: dict[str, Any], local: dict[str, Any]) -> dict[str, Any] | None:
    changes: dict[str, Any] = {}
    keys = set(remote.keys()) | set(local.keys())

    for key in sorted(keys):
        if key == "landing_points":
            remote_points = normalize_landing_points(remote.get("landing_points"))
            local_points = normalize_landing_points(local.get("landing_points"))
            if remote_points != local_points:
                remote_map = {point["id"]: point for point in remote_points}
                local_map = {point["id"]: point for point in local_points}
                shared_ids = sorted(set(remote_map) & set(local_map))
                changes[key] = {
                    "added": sorted(set(remote_map) - set(local_map)),
                    "removed": sorted(set(local_map) - set(remote_map)),
                    "updated": [
                        point_id for point_id in shared_ids if remote_map[point_id] != local_map[point_id]
                    ],
                    "remote_count": len(remote_points),
                    "local_count": len(local_points),
                }
            continue

        remote_value = remote.get(key)
        local_value = local.get(key)
        if remote_value != local_value:
            changes[key] = {
                "remote": remote_value,
                "local": local_value,
            }

    if not changes:
        return None

    return {
        "id": remote.get("id") or local.get("id"),
        "name": remote.get("name") or local.get("name"),
        "changed_fields": sorted(changes.keys()),
        "changes": changes,
    }


def main() -> int:
    args = parse_args()

    output_root = Path(args.output_root).resolve()
    cable_output_dir = ensure_dir(output_root / "cable")
    reports_dir = ensure_dir(output_root / "reports")
    compare_root = Path(args.compare_root).resolve()

    started_at = time.time()
    compared_at_utc = datetime.now(timezone.utc).isoformat()

    print("Fetching public API indexes...")
    search_entries = fetch_json(SEARCH_PATH, timeout=args.timeout)
    cable_geo = fetch_json(CABLE_GEO_PATH, timeout=args.timeout)
    landing_point_geo = fetch_json(LANDING_POINT_GEO_PATH, timeout=args.timeout)
    config = fetch_json(CONFIG_PATH, timeout=args.timeout)

    if not isinstance(search_entries, list):
        raise ValueError("search.json did not return a list")
    if not isinstance(cable_geo, dict):
        raise ValueError("cable-geo.json did not return an object")
    if not isinstance(landing_point_geo, dict):
        raise ValueError("landing-point-geo.json did not return an object")
    if not isinstance(config, dict):
        raise ValueError("config.json did not return an object")

    write_json_file(cable_output_dir / "landing-point-geo.json", landing_point_geo)

    cable_ids = extract_cable_ids(search_entries, cable_geo)
    print(f"Discovered {len(cable_ids)} cable ids.")

    remote_cables: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []

    print("Downloading per-cable JSON files...")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        future_map = {
            executor.submit(fetch_one_cable, cable_id, args.timeout): cable_id for cable_id in cable_ids
        }
        for index, future in enumerate(as_completed(future_map), start=1):
            cable_id = future_map[future]
            try:
                payload = future.result()
                remote_cables[cable_id] = payload
                write_json_file(cable_output_dir / f"{cable_id}.json", payload)
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                failures.append({"id": cable_id, "error": str(exc)})

            if index % 50 == 0 or index == len(future_map):
                print(f"Processed {index}/{len(future_map)} cables...")

    local_cables = load_local_cables(compare_root)
    remote_landing_point_geo = load_landing_point_geo(cable_output_dir / "landing-point-geo.json")
    local_landing_point_geo = load_landing_point_geo(compare_root / "landing-point-geo.json")

    remote_ids = set(remote_cables)
    local_ids = set(local_cables)
    remote_only = sorted(remote_ids - local_ids)
    local_only = sorted(local_ids - remote_ids)
    shared_ids = sorted(remote_ids & local_ids)

    changed: list[dict[str, Any]] = []
    unchanged_count = 0

    for cable_id in shared_ids:
        diff = compare_cable(remote_cables[cable_id], local_cables[cable_id])
        if diff is None:
            unchanged_count += 1
        else:
            changed.append(diff)

    changed.sort(key=lambda item: item["id"])
    landing_point_geo_comparison = compare_landing_point_geo(remote_landing_point_geo, local_landing_point_geo)
    validation = validate_replacement_dataset(cable_output_dir)

    summary = {
        "source_site": BASE_URL,
        "source_endpoints": {
            "search": build_url(SEARCH_PATH),
            "cable_geo": build_url(CABLE_GEO_PATH),
            "landing_point_geo": build_url(LANDING_POINT_GEO_PATH),
            "config": build_url(CONFIG_PATH),
            "detail_template": build_url("/api/v3/cable/{id}.json"),
        },
        "robots_txt": build_url("/robots.txt"),
        "remote_dataset_creation_time": config.get("creation_time"),
        "compared_at_utc": compared_at_utc,
        "download_seconds": round(time.time() - started_at, 3),
        "remote_cable_count": len(remote_cables),
        "local_cable_count": len(local_cables),
        "shared_cable_count": len(shared_ids),
        "remote_only_count": len(remote_only),
        "local_only_count": len(local_only),
        "changed_count": len(changed),
        "unchanged_count": unchanged_count,
        "failed_download_count": len(failures),
        "landing_point_geo_comparison": landing_point_geo_comparison,
        "replacement_validation": validation,
    }

    write_pretty_json_file(output_root / "search_index.json", search_entries)
    write_pretty_json_file(output_root / "config.json", config)
    write_pretty_json_file(output_root / "comparison_summary.json", summary)
    write_pretty_json_file(output_root / "comparison_remote_only.json", remote_only)
    write_pretty_json_file(output_root / "comparison_local_only.json", local_only)
    write_pretty_json_file(output_root / "comparison_changed.json", changed)
    write_pretty_json_file(output_root / "comparison_landing_point_geo.json", landing_point_geo_comparison)
    write_pretty_json_file(output_root / "replacement_validation.json", validation)
    write_pretty_json_file(output_root / "download_failures.json", failures)

    manifest = {
        "generated_at_utc": compared_at_utc,
        "output_root": str(output_root),
        "compare_root": str(compare_root),
        "workers": args.workers,
        "timeout": args.timeout,
        "downloaded_cable_files": len(remote_cables),
        "failed_downloads": failures,
        "reports": {
            "summary": str((output_root / "comparison_summary.json").resolve()),
            "remote_only": str((output_root / "comparison_remote_only.json").resolve()),
            "local_only": str((output_root / "comparison_local_only.json").resolve()),
            "changed": str((output_root / "comparison_changed.json").resolve()),
            "landing_point_geo": str((output_root / "comparison_landing_point_geo.json").resolve()),
            "replacement_validation": str((output_root / "replacement_validation.json").resolve()),
            "failures": str((output_root / "download_failures.json").resolve()),
        },
    }
    write_pretty_json_file(output_root / "manifest.json", manifest)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        print("Download failures detected:", file=sys.stderr)
        print(json.dumps(failures[:10], ensure_ascii=False, indent=2), file=sys.stderr)

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
