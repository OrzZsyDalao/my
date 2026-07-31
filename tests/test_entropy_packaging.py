from pathlib import Path

import pandas as pd
import pytest

from ripe_atlas_public_download.package_reaggregated_paper_results import (
    ENTROPY_COMPACT_COLUMNS,
    write_compact_entropy_aggregate,
)


def test_compact_entropy_aggregate_preserves_rows_and_stays_api_readable(
    tmp_path: Path,
) -> None:
    """The paper-facing aggregate must remain readable through GitHub Contents API."""
    full_path = tmp_path / "entropy_full.csv"
    compact_path = tmp_path / "entropy.csv"
    rows = []
    for index in range(7000):
        rows.append(
            {
                column: (
                    176517335
                    if column == "msm_id"
                    else float(index % 10) / 10
                    if "entropy" in column or "share" in column
                    else f"value_{index % 7}"
                )
                for column in ENTROPY_COMPACT_COLUMNS
            }
        )
    pd.DataFrame(rows).to_csv(full_path, index=False)

    accounting = write_compact_entropy_aggregate(full_path, compact_path)
    compact = pd.read_csv(compact_path)

    assert len(compact) == len(rows)
    assert list(compact.columns) == list(ENTROPY_COMPACT_COLUMNS)
    assert compact["msm_id"].astype(str).eq("176517335").all()
    assert "1.765" not in compact_path.read_text(encoding="utf-8")
    assert compact_path.stat().st_size < 1024 * 1024
    assert accounting["compact_aggregate_row_count"] == len(rows)


def test_compact_entropy_aggregate_rejects_missing_columns(tmp_path: Path) -> None:
    """A truncated input must not silently produce a misleading aggregate."""
    full_path = tmp_path / "entropy_full.csv"
    compact_path = tmp_path / "entropy.csv"
    pd.DataFrame({"msm_id": [5009]}).to_csv(full_path, index=False)

    with pytest.raises(RuntimeError, match="missing columns"):
        write_compact_entropy_aggregate(full_path, compact_path)
