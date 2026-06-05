#!/usr/bin/env python3
"""Background merge watcher: single-pass tick for auto-rebase and auto-rollback.

Can be invoked as:
  python merge_watcher.py tick     -- single pass (for /loop or cron)
  python merge_watcher.py run      -- polling loop (standalone daemon)

Design decisions: D5 (merge watcher as coordinator background task)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any

from _helpers import GH_TIMEOUT, run_gh
from auto_rebase import auto_cascade_rebase
from auto_rollback import monitor_ci_for_rollback
from merge_events import MergeEvent, emit_event

DEFAULT_WATCHER_INTERVAL = 60


def _get_open_prs() -> list[dict]:
    try:
        raw = run_gh([
            "pr", "list", "--state", "open", "--json",
            "number,files,title",
            "--limit", "100",
        ], timeout=GH_TIMEOUT)
        prs = json.loads(raw) if raw else []
        return [
            {
                "number": pr["number"],
                "title": pr.get("title", ""),
                "files": [f["path"] for f in pr.get("files", [])],
            }
            for pr in prs
        ]
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return []


def _get_recent_merges() -> list[dict]:
    try:
        raw = run_gh([
            "pr", "list", "--state", "merged",
            "--json", "number,mergeCommit,files,title",
            "--limit", "5",
        ], timeout=GH_TIMEOUT)
        prs = json.loads(raw) if raw else []
        results = []
        for pr in prs:
            merge_commit = pr.get("mergeCommit") or {}
            sha = merge_commit.get("oid", "")
            if sha:
                results.append({
                    "pr_number": pr["number"],
                    "merge_sha": sha,
                    "title": pr.get("title", ""),
                    "files": [f["path"] for f in pr.get("files", [])],
                })
        return results
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return []


def merge_watcher_tick() -> dict[str, Any]:
    try:
        open_prs = _get_open_prs()
        recent_merges = _get_recent_merges()
    except Exception as exc:
        emit_event(MergeEvent(
            event_type="train_compose",
            pr_number=0,
            backend="watcher",
            success=False,
            error=str(exc),
        ))
        return {"action": "error", "error": str(exc)}

    if not open_prs and not recent_merges:
        emit_event(MergeEvent(
            event_type="train_compose",
            pr_number=0,
            backend="watcher",
            success=True,
        ))
        return {"action": "heartbeat"}

    results: dict[str, Any] = {"action": "processed", "details": []}

    for merge in recent_merges:
        try:
            rollback_result = monitor_ci_for_rollback(
                merge_sha=merge["merge_sha"],
                pr_number=merge["pr_number"],
                pr_title=merge["title"],
                merged_files=merge["files"],
                poll_interval=0,
                max_polls=1,
            )
            results["details"].append({
                "pr_number": merge["pr_number"],
                "rollback": rollback_result,
            })
        except Exception as exc:
            results["details"].append({
                "pr_number": merge["pr_number"],
                "rollback_error": str(exc),
            })

        if open_prs and merge["files"]:
            try:
                rebase_result = auto_cascade_rebase(
                    merged_pr_number=merge["pr_number"],
                    merged_files=merge["files"],
                )
                results["details"].append({
                    "pr_number": merge["pr_number"],
                    "rebase": rebase_result,
                })
            except Exception as exc:
                results["details"].append({
                    "pr_number": merge["pr_number"],
                    "rebase_error": str(exc),
                })

    emit_event(MergeEvent(
        event_type="train_compose",
        pr_number=0,
        backend="watcher",
        success=True,
    ))

    return results


def run_polling_loop(interval: int = DEFAULT_WATCHER_INTERVAL) -> None:
    print(f"Merge watcher started (interval: {interval}s)", file=sys.stderr)
    while True:
        result = merge_watcher_tick()
        print(json.dumps(result), file=sys.stderr)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Background merge watcher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("tick", help="Single-pass check")

    run_parser = subparsers.add_parser("run", help="Polling loop")
    run_parser.add_argument(
        "--interval", type=int, default=DEFAULT_WATCHER_INTERVAL,
        help=f"Poll interval in seconds (default: {DEFAULT_WATCHER_INTERVAL})",
    )

    args = parser.parse_args()

    if args.command == "tick":
        result = merge_watcher_tick()
        print(json.dumps(result, indent=2))
    elif args.command == "run":
        run_polling_loop(args.interval)


if __name__ == "__main__":
    main()
