"""Post-merge pipeline: composable hooks that run after each successful merge.

Hooks run independently — a failure in one doesn't block the others:
  1. emit_merge_event() — metrics
  2. auto_cascade_rebase() — refresh overlapping PRs
  3. monitor_ci_for_rollback() — revert if CI breaks

Design decisions: D2 (composable post-merge hooks)
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from auto_rebase import auto_cascade_rebase
from auto_rollback import monitor_ci_for_rollback
from merge_events import MergeEvent, emit_event


def post_merge_pipeline(
    *,
    pr_number: int,
    strategy: str,
    backend: str,
    merge_sha: str | None = None,
    pr_title: str = "",
    merged_files: list[str] | None = None,
    origin: str | None = None,
    duration_seconds: float | None = None,
    queue_depth: int | None = None,
    partition_count: int | None = None,
    train_id: str | None = None,
    enable_rebase: bool = True,
    enable_rollback: bool = True,
    rollback_poll_interval: int = 60,
    rollback_max_polls: int = 15,
) -> dict[str, Any]:
    result: dict[str, Any] = {"pr_number": pr_number}

    # Hook 1: Emit merge event
    try:
        event = MergeEvent(
            event_type="merge",
            pr_number=pr_number,
            origin=origin,
            strategy=strategy,
            backend=backend,
            duration_seconds=duration_seconds,
            queue_depth=queue_depth,
            partition_count=partition_count,
            train_id=train_id,
            success=True,
        )
        emit_event(event)
        result["event_emitted"] = True
    except Exception as exc:
        result["event_emitted"] = False
        result["event_error"] = str(exc)
        print(f"Warning: merge event emission failed: {exc}", file=sys.stderr)

    # Hook 2: Auto cascading rebase
    if enable_rebase and merged_files:
        try:
            rebase_result = auto_cascade_rebase(
                merged_pr_number=pr_number,
                merged_files=merged_files,
            )
            result["rebase"] = rebase_result
        except Exception as exc:
            result["rebase"] = {"error": str(exc)}
            print(f"Warning: auto-rebase failed: {exc}", file=sys.stderr)
    else:
        result["rebase"] = {"skipped": True}

    # Hook 3: CI monitoring for rollback
    if enable_rollback and merge_sha and merged_files:
        try:
            rollback_result = monitor_ci_for_rollback(
                merge_sha=merge_sha,
                pr_number=pr_number,
                pr_title=pr_title,
                merged_files=merged_files,
                poll_interval=rollback_poll_interval,
                max_polls=rollback_max_polls,
            )
            result["rollback"] = rollback_result
        except Exception as exc:
            result["rollback"] = {"error": str(exc)}
            print(f"Warning: rollback monitoring failed: {exc}", file=sys.stderr)
    else:
        result["rollback"] = {"skipped": True}

    return result
