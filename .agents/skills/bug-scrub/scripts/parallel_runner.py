#!/usr/bin/env python3
"""Parallel collector execution using ThreadPoolExecutor.

Runs signal collectors concurrently while preserving submission order
and isolating failures to individual collectors.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError

from models import SourceResult


def run_collectors_parallel(
    collectors: dict[str, Callable[[str], SourceResult]],
    project_dir: str,
    max_workers: int = 8,
    timeout_per_collector: int = 300,
) -> list[SourceResult]:
    """Run signal collectors concurrently via ThreadPoolExecutor.

    Returns results in submission order (same order as *collectors* dict keys).
    Failed collectors return ``SourceResult(status="error")`` instead of
    raising, so one broken collector never blocks the others.

    Args:
        collectors: Mapping of source name to collector callable.
            Each callable accepts a project_dir string and returns a
            SourceResult.
        project_dir: Root directory of the project being scanned.
        max_workers: Maximum concurrent threads (default 8).
        timeout_per_collector: Per-collector timeout in seconds (default 300).

    Returns:
        List of SourceResult in the same order as *collectors* keys.
    """
    if not collectors:
        return []

    names = list(collectors.keys())
    futures: dict[str, tuple[Future[SourceResult], float]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for name, func in collectors.items():
            start = time.monotonic()
            future = executor.submit(_run_one, name, func, project_dir)
            futures[name] = (future, start)

        results: list[SourceResult] = []
        for name in names:
            future, start = futures[name]
            try:
                result = future.result(timeout=timeout_per_collector)
            except TimeoutError:
                duration_ms = int((time.monotonic() - start) * 1000)
                result = SourceResult(
                    source=name,
                    status="error",
                    duration_ms=duration_ms,
                    messages=[
                        f"Collector '{name}' timed out after "
                        f"{timeout_per_collector}s"
                    ],
                )
            except Exception as exc:  # noqa: BLE001
                duration_ms = int((time.monotonic() - start) * 1000)
                result = SourceResult(
                    source=name,
                    status="error",
                    duration_ms=duration_ms,
                    messages=[f"Collector '{name}' failed: {exc}"],
                )
            results.append(result)

    return results


def _run_one(
    name: str, func: Callable[[str], SourceResult], project_dir: str
) -> SourceResult:
    """Execute a single collector, timing it and wrapping exceptions."""
    start = time.monotonic()
    try:
        result = func(project_dir)
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        return SourceResult(
            source=name,
            status="error",
            duration_ms=duration_ms,
            messages=[str(exc)],
        )
    # Patch duration_ms if the collector didn't set it
    if result.duration_ms == 0:
        result.duration_ms = int((time.monotonic() - start) * 1000)
    return result
