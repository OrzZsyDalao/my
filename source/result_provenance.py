"""Small provenance helpers shared by paper-result generators."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 checksum for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_generation_state(repo_root: Path) -> dict[str, Any]:
    """Return the checked-out commit and whether generation used a dirty tree."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "generation_git_head": head.stdout.strip() if head.returncode == 0 else "unknown",
        "generation_worktree_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def csv_row_count(path: Path) -> int | None:
    """Return a CSV row count without treating the header as a data row."""
    try:
        return int(len(pd.read_csv(path, low_memory=False)))
    except (pd.errors.EmptyDataError, UnicodeDecodeError, ValueError):
        return None


def file_manifest(path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    """Describe one input or source file with size, checksum, and CSV row count."""
    resolved = path.resolve()
    display_path: str
    if repo_root is not None:
        try:
            display_path = str(resolved.relative_to(repo_root.resolve()))
        except ValueError:
            display_path = str(resolved)
    else:
        display_path = str(resolved)
    return {
        "path": display_path,
        "bytes": int(resolved.stat().st_size),
        "sha256": sha256_file(resolved),
        "row_count": csv_row_count(resolved) if resolved.suffix.lower() == ".csv" else None,
    }


def source_hashes(paths: Iterable[Path], repo_root: Path) -> dict[str, str]:
    """Return path-to-SHA mappings for existing source files."""
    result: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        try:
            key = str(path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            key = str(path.resolve())
        result[key] = sha256_file(path)
    return result


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object, returning an empty object when unavailable."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def inherited_commit(
    manifests: Iterable[dict[str, Any]],
    keys: Iterable[str],
) -> str:
    """Return one consistently inherited commit or ``unknown``."""
    values = {
        str(manifest.get(key)).strip()
        for manifest in manifests
        for key in keys
        if manifest.get(key) not in (None, "", "unknown")
    }
    return next(iter(values)) if len(values) == 1 else "unknown"
