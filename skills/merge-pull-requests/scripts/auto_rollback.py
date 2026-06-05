"""Auto rollback with CI monitoring and revert PR creation.

After a PR merges, monitors main branch CI. If CI fails and the failing
files overlap with the merged PR's changes, auto-creates a revert PR.

Design decisions: D4 (file overlap attribution)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

from _helpers import GH_TIMEOUT, run_cmd, run_gh, run_gh_unchecked
from merge_events import MergeEvent, emit_event

ROLLBACK_MONITOR_MINUTES = int(
    os.environ.get("ROLLBACK_MONITOR_MINUTES", "15"),
)

DEFAULT_POLL_INTERVAL = 60
DEFAULT_MAX_POLLS = ROLLBACK_MONITOR_MINUTES


def attribute_breakage(
    merged_files: list[str],
    failing_files: list[str],
) -> dict[str, Any]:
    if not merged_files or not failing_files:
        return {"attributed": False, "overlapping_files": []}

    overlap = sorted(set(merged_files) & set(failing_files))
    return {
        "attributed": len(overlap) > 0,
        "overlapping_files": overlap,
    }


def _run_gh(args: list[str]) -> str:
    return run_gh(args, timeout=GH_TIMEOUT)


def _run_cmd(cmd: list[str]) -> str:
    return run_cmd(cmd)


def _get_main_ci_status(base_branch: str = "main") -> dict[str, str]:
    try:
        raw = run_gh([
            "api", f"repos/:owner/:repo/commits/{base_branch}/status",
            "--jq", ".state",
        ], timeout=GH_TIMEOUT)
        state = raw.strip().lower()
        if state in ("success",):
            return {"status": "success"}
        elif state in ("failure", "error"):
            return {"status": "failure"}
        else:
            return {"status": "pending"}
    except (RuntimeError, subprocess.TimeoutExpired):
        return {"status": "unknown"}


def _get_failing_test_files(base_branch: str = "main") -> list[str]:
    try:
        raw = run_gh([
            "run", "list", "--branch", base_branch,
            "--status", "failure", "--limit", "5",
            "--json", "databaseId",
        ], timeout=GH_TIMEOUT)
        runs = json.loads(raw) if raw else []
        if not runs:
            return []

        run_id = runs[0]["databaseId"]
        log_raw = run_gh([
            "run", "view", str(run_id), "--json", "jobs",
        ], timeout=GH_TIMEOUT)
        jobs = json.loads(log_raw).get("jobs", [])

        failing_files = set()
        for job in jobs:
            if job.get("conclusion") == "failure":
                for step in job.get("steps", []):
                    name = step.get("name", "")
                    if "test" in name.lower():
                        parts = name.split()
                        for part in parts:
                            if "/" in part and "." in part:
                                failing_files.add(part)

        return sorted(failing_files)
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return []


def create_revert_pr(
    *,
    merge_sha: str,
    original_pr_number: int,
    original_pr_title: str,
    base_branch: str = "main",
) -> dict[str, Any]:
    revert_branch = f"revert/pr-{original_pr_number}"

    try:
        _run_cmd(["git", "fetch", "origin", base_branch])
        _run_cmd(["git", "checkout", "-b", revert_branch, f"origin/{base_branch}"])
        _run_cmd(["git", "revert", "--no-edit", merge_sha])
        _run_cmd(["git", "push", "-u", "origin", revert_branch])
    except RuntimeError as exc:
        return {
            "success": False,
            "original_pr_number": original_pr_number,
            "error": str(exc),
        }

    try:
        body = (
            f"Automated revert of #{original_pr_number} "
            f"({original_pr_title}).\n\n"
            f"Main branch CI failed after merge. "
            f"Failing files overlap with merged PR's changes.\n\n"
            f"Reverted commit: {merge_sha}"
        )
        raw = _run_gh([
            "pr", "create",
            "--base", base_branch,
            "--head", revert_branch,
            "--title", f"revert: {original_pr_title} (#{original_pr_number})",
            "--body", body,
        ])
        pr_data = json.loads(raw)
        revert_pr_number = pr_data.get("number", 0)

        _run_gh([
            "pr", "merge", str(revert_pr_number), "--squash", "--auto",
        ])

        return {
            "success": True,
            "original_pr_number": original_pr_number,
            "revert_pr_number": revert_pr_number,
            "revert_branch": revert_branch,
        }
    except RuntimeError as exc:
        return {
            "success": False,
            "original_pr_number": original_pr_number,
            "error": str(exc),
        }


def monitor_ci_for_rollback(
    *,
    merge_sha: str,
    pr_number: int,
    pr_title: str,
    merged_files: list[str],
    base_branch: str = "main",
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_polls: int = DEFAULT_MAX_POLLS,
) -> dict[str, Any]:
    for _ in range(max_polls):
        ci_status = _get_main_ci_status(base_branch)

        if ci_status["status"] == "success":
            return {
                "action": "stable",
                "pr_number": pr_number,
                "merge_sha": merge_sha,
            }

        if ci_status["status"] == "failure":
            failing_files = _get_failing_test_files(base_branch)
            attribution = attribute_breakage(merged_files, failing_files)

            if not attribution["attributed"]:
                return {
                    "action": "no_revert",
                    "reason": "no_file_overlap",
                    "pr_number": pr_number,
                    "merge_sha": merge_sha,
                    "failing_files": failing_files,
                }

            revert_result = create_revert_pr(
                merge_sha=merge_sha,
                original_pr_number=pr_number,
                original_pr_title=pr_title,
                base_branch=base_branch,
            )

            emit_event(MergeEvent(
                event_type="revert",
                pr_number=pr_number,
                backend="direct",
                success=revert_result.get("success", False),
                error=revert_result.get("error"),
            ))

            return {
                "action": "reverted",
                "pr_number": pr_number,
                "merge_sha": merge_sha,
                "revert_pr_number": revert_result.get("revert_pr_number"),
                "attribution": attribution,
            }

        if poll_interval > 0:
            time.sleep(poll_interval)

    return {
        "action": "timeout",
        "pr_number": pr_number,
        "merge_sha": merge_sha,
    }
