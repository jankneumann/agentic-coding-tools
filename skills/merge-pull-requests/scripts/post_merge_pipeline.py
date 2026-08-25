"""Post-merge pipeline: composable hooks that run after each successful merge.

Hooks run independently — a failure in one doesn't block the others:
  1. auto_cascade_rebase() — refresh overlapping PRs
  2. monitor_ci_for_rollback() — revert if CI breaks

Both reach outside this repository — one updates other people's PRs, the other
can open and auto-merge a revert — so this pipeline is rightly opt-in behind
``--pipeline``.

Metrics emission used to be hook 1 here and is now in ``merge_pr()``. Recording
a merge is a local file append with none of that blast radius, and gating it
behind the same flag as these two meant it never ran: as of 2026-08-25 the
metrics log held zero ``merge`` events. An always-on record and an opt-in
mutation do not belong behind one switch.

Design decisions: D2 (composable post-merge hooks)
"""

from __future__ import annotations

import sys
from typing import Any

from auto_rebase import auto_cascade_rebase
from auto_rollback import monitor_ci_for_rollback


def post_merge_pipeline(
    *,
    pr_number: int,
    merge_sha: str | None = None,
    pr_title: str = "",
    merged_files: list[str] | None = None,
    enable_rebase: bool = True,
    enable_rollback: bool = True,
    rollback_poll_interval: int = 60,
    rollback_max_polls: int = 15,
) -> dict[str, Any]:
    result: dict[str, Any] = {"pr_number": pr_number}

    # Hook 1: Auto cascading rebase
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

    # Hook 2: CI monitoring for rollback
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
