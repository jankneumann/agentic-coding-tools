#!/usr/bin/env python3
"""Parallel auto-fix executor: run ruff --fix on non-overlapping file groups concurrently."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from execute_auto import execute_auto_fixes  # noqa: E402
from fix_models import ClassifiedFinding, FixGroup  # noqa: E402


def execute_auto_fixes_parallel(
    auto_groups: list[FixGroup],
    project_dir: str,
    max_workers: int = 4,
) -> tuple[list[ClassifiedFinding], list[ClassifiedFinding]]:
    """Run ruff --fix on non-overlapping file groups concurrently.

    Each FixGroup is dispatched to a thread that calls the sequential
    execute_auto_fixes with a single-element list.  The caller MUST
    ensure no file appears in more than one group (use
    assert_no_file_overlap from plan_fixes before calling).

    Args:
        auto_groups: Non-overlapping groups of auto-tier findings.
        project_dir: Project root directory.
        max_workers: Maximum concurrent threads.

    Returns:
        Tuple of (all resolved findings, all persisting findings).
    """
    if not auto_groups:
        return [], []

    all_resolved: list[ClassifiedFinding] = []
    all_persisting: list[ClassifiedFinding] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(execute_auto_fixes, [group], project_dir)
            for group in auto_groups
        ]

        for future in futures:
            resolved, persisting = future.result()
            all_resolved.extend(resolved)
            all_persisting.extend(persisting)

    return all_resolved, all_persisting
