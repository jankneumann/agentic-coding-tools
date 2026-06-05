"""Auto cascading rebase after merge.

After a PR merges, automatically refreshes queued PRs whose files overlap
with the merged PR's changed files. Rate-limited to prevent CI storms.

Design decisions: D3 (auto-rebase rate limiting)
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from _helpers import GH_TIMEOUT, run_gh, run_gh_unchecked
from merge_events import MergeEvent, emit_event

MAX_AUTO_REBASE_PER_MERGE = int(
    os.environ.get("MERGE_AUTO_REBASE_LIMIT", "5"),
)


def find_overlapping_prs(
    merged_files: list[str],
    queued_prs: list[dict],
) -> list[dict]:
    if not merged_files or not queued_prs:
        return []
    merged_set = set(merged_files)
    return [
        pr for pr in queued_prs
        if set(pr.get("files", [])) & merged_set
    ]


def _get_queued_prs_with_files() -> list[dict]:
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


def _refresh_pr_branch(pr_number: int) -> dict:
    try:
        raw = run_gh([
            "pr", "view", str(pr_number),
            "--json", "headRefOid,baseRefName",
        ], timeout=GH_TIMEOUT)
        pr_data = json.loads(raw)
        head_sha = pr_data.get("headRefOid", "")

        result = run_gh_unchecked(
            [
                "api", f"repos/:owner/:repo/pulls/{pr_number}/update-branch",
                "-X", "PUT",
                "-f", f"expected_head_sha={head_sha}",
            ],
            timeout=GH_TIMEOUT,
        )

        if result.returncode == 0:
            return {"success": True, "pr_number": pr_number}

        error = result.stderr.strip().lower()
        if "already up-to-date" in error or "not behind" in error:
            return {"success": True, "pr_number": pr_number, "already_fresh": True}

        return {
            "success": False,
            "pr_number": pr_number,
            "reason": result.stderr.strip(),
        }
    except Exception as exc:
        return {
            "success": False,
            "pr_number": pr_number,
            "reason": str(exc),
        }


def auto_cascade_rebase(
    *,
    merged_pr_number: int,
    merged_files: list[str],
    max_rebase: int | None = None,
) -> dict[str, Any]:
    if max_rebase is None:
        max_rebase = MAX_AUTO_REBASE_PER_MERGE

    queued_prs = _get_queued_prs_with_files()
    overlapping = find_overlapping_prs(merged_files, queued_prs)

    if max_rebase == 0:
        return {
            "merged_pr": merged_pr_number,
            "refreshed": [],
            "conflicting": [],
            "remaining": len(overlapping),
        }

    to_refresh = overlapping[:max_rebase]
    remaining_count = max(0, len(overlapping) - max_rebase)

    refreshed = []
    conflicting = []

    for pr in to_refresh:
        result = _refresh_pr_branch(pr["number"])
        if result.get("success"):
            refreshed.append(result)
            emit_event(MergeEvent(
                event_type="rebase",
                pr_number=pr["number"],
                backend="direct",
                success=True,
            ))
        else:
            conflicting.append(result)

    return {
        "merged_pr": merged_pr_number,
        "refreshed": refreshed,
        "conflicting": conflicting,
        "remaining": remaining_count,
    }
