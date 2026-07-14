"""Shared utilities for isolated experiment runs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


REPO_DIR = Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 checksum for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_hash(value: Any) -> str:
    """Return a deterministic digest for a JSON-serializable configuration."""
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def git_commit_sha() -> str:
    """Read the checked-out commit without modifying repository state."""
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_DIR, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


def make_run_id(commit_sha: str) -> str:
    """Build the collision-resistant default run identifier."""
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{now}_{commit_sha[:8]}"


def write_json(path: Path, value: Dict[str, Any]) -> None:
    """Write a UTF-8 JSON document, creating its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


DEFAULT_EXPERIMENT_CONFIG: Dict[str, Any] = {
    "measurement_window": None,
    "landing_catchment_radius_km": 50.0,
    "landing_region_radius_km": 50.0,
    "same_city_policy": "retain",
    "same_city_distance_threshold_km": 25.0,
    "timeout_gap_policy": "allow_timeout_bridged",
    "cable_topology_policy": "allow_unordered_reachability",
    "rtt_tolerance_ms": 5.0,
    "candidate_support_threshold": 0.5,
    "cable_availability_mode": "confirmed_active_only",
    "time_match_tolerance_seconds": 900,
}
