#!/usr/bin/env python3
"""Compatibility wrapper for the run-isolated paper result packager.

Historical output-tree scanning is intentionally removed.  Use the current run
index through ``python -m pipeline.package_paper_results --run-id <run_id>``.
"""

from __future__ import annotations

from pipeline.package_paper_results import main


if __name__ == "__main__":
    main()
