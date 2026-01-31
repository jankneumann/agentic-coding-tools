#!/usr/bin/env python3
"""Merge or close pull requests with pre-merge validation.

Actions:
  merge   - Merge a single PR (squash/merge/rebase)
  close   - Close a single PR with a comment
  batch-close - Close multiple obsolete PRs with explanatory comments

Usage:
  python merge_pr.py merge <pr_number> [--strategy squash|merge|rebase] [--dry-run]
  python merge_pr.py close <pr_number> --reason <text> [--dry-run]
  python merge_pr.py batch-close <pr_numbers_comma_sep> --reason <text> [--dry-run]

Output: JSON result to stdout.
"""

import json
import subprocess
import sys

from shared import (
    GH_TIMEOUT,
    check_gh,
    parse_pr_number,
    parse_pr_numbers,
    run_gh,
    run_gh_unchecked,
)


def get_pr_status(pr_number: int) -> dict:
    try:
        raw = run_gh([
            "pr", "view", str(pr_number), "--json",
            "state,mergeable,statusCheckRollup,reviewDecision,headRefName,title,isDraft",
        ], timeout=GH_TIMEOUT)
    except RuntimeError as e:
        print(f"Error: Could not fetch PR #{pr_number}: {e}", file=sys.stderr)
        sys.exit(1)
    return json.loads(raw)


def validate_pr(pr_number: int) -> dict:
    """Pre-merge validation: CI status, approval, mergeability."""
    status = get_pr_status(pr_number)
    is_draft = status.get("isDraft", False)

    checks_ok = True
    checks_pending = False
    check_details = []
    for check in status.get("statusCheckRollup", []) or []:
        conclusion = check.get("conclusion") or ""
        state = check.get("state") or check.get("status") or ""
        name = check.get("name") or check.get("context", "unknown")

        # Determine effective status
        if conclusion:
            effective = conclusion.upper()
        elif state:
            effective = state.upper()
        else:
            effective = "UNKNOWN"

        check_details.append({"name": name, "state": effective})

        passed_states = {"SUCCESS", "NEUTRAL", "SKIPPED"}
        pending_states = {"PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED"}

        if effective in passed_states:
            continue
        elif effective in pending_states:
            checks_pending = True
        elif effective == "UNKNOWN":
            # Treat truly unknown checks as pending rather than failed
            checks_pending = True
        else:
            checks_ok = False

    review_decision = status.get("reviewDecision", "")
    approved = review_decision == "APPROVED"

    mergeable = status.get("mergeable", "UNKNOWN")

    # Build a clear status summary
    if not checks_ok:
        check_summary = "failed"
    elif checks_pending:
        check_summary = "pending"
    else:
        check_summary = "passing"

    return {
        "pr_number": pr_number,
        "title": status.get("title", ""),
        "branch": status.get("headRefName", ""),
        "is_draft": is_draft,
        "mergeable": mergeable,
        "check_summary": check_summary,
        "checks_passing": checks_ok and not checks_pending,
        "checks_pending": checks_pending,
        "checks_failed": not checks_ok,
        "check_details": check_details,
        "review_decision": review_decision,
        "approved": approved,
        "can_merge": (
            mergeable == "MERGEABLE"
            and checks_ok
            and not checks_pending
            and not is_draft
            and approved
        ),
    }


def merge_pr(pr_number: int, strategy: str = "squash",
             dry_run: bool = False) -> dict:
    validation = validate_pr(pr_number)

    if dry_run:
        return {
            "action": "merge",
            "dry_run": True,
            "pr_number": pr_number,
            "strategy": strategy,
            "validation": validation,
            "would_merge": validation["can_merge"],
        }

    if validation["is_draft"]:
        return {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "reason": "PR is a draft — mark as ready before merging",
            "validation": validation,
        }

    if validation["checks_pending"]:
        return {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "reason": "CI checks still running — wait for completion",
            "validation": validation,
        }

    if not validation["approved"]:
        return {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "reason": "Review approval required before merging",
            "validation": validation,
        }

    if not validation["can_merge"]:
        return {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "reason": "Pre-merge validation failed",
            "validation": validation,
        }

    strategy_flag = f"--{strategy}"
    try:
        result = run_gh_unchecked([
            "pr", "merge", str(pr_number), strategy_flag, "--delete-branch",
        ], timeout=GH_TIMEOUT)

        if result.returncode != 0:
            # Merge may have succeeded but branch deletion failed
            # Check if the PR is actually merged now
            post_status = get_pr_status(pr_number)
            if post_status.get("state") == "MERGED":
                return {
                    "action": "merge",
                    "success": True,
                    "pr_number": pr_number,
                    "strategy": strategy,
                    "warning": "PR merged but branch deletion may have failed",
                    "stderr": result.stderr.strip(),
                }
            return {
                "action": "merge",
                "success": False,
                "pr_number": pr_number,
                "error": result.stderr.strip() or "Merge command failed",
            }

        return {
            "action": "merge",
            "success": True,
            "pr_number": pr_number,
            "strategy": strategy,
        }
    except subprocess.TimeoutExpired:
        return {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "error": "Merge command timed out",
        }


def close_pr(pr_number: int, reason: str,
             dry_run: bool = False) -> dict:
    if dry_run:
        return {
            "action": "close",
            "dry_run": True,
            "pr_number": pr_number,
            "reason": reason,
        }

    # Close first, then comment. If close fails we don't leave orphan comments.
    try:
        close_result = run_gh_unchecked(["pr", "close", str(pr_number)],
                                        timeout=GH_TIMEOUT)
        if close_result.returncode != 0:
            return {
                "action": "close",
                "success": False,
                "pr_number": pr_number,
                "error": close_result.stderr.strip() or "Close command failed",
            }
    except subprocess.TimeoutExpired:
        return {
            "action": "close",
            "success": False,
            "pr_number": pr_number,
            "error": "Close command timed out",
        }

    # Post the comment after successful close — failure here is non-fatal
    comment_warning = None
    try:
        comment_result = run_gh_unchecked([
            "pr", "comment", str(pr_number), "--body", reason,
        ], timeout=GH_TIMEOUT)
        if comment_result.returncode != 0:
            comment_warning = (
                f"PR closed but comment failed: {comment_result.stderr.strip()}"
            )
    except subprocess.TimeoutExpired:
        comment_warning = "PR closed but comment timed out"

    result = {
        "action": "close",
        "success": True,
        "pr_number": pr_number,
        "reason": reason,
    }
    if comment_warning:
        result["warning"] = comment_warning
    return result


def batch_close(pr_numbers: list[int], reason: str,
                dry_run: bool = False) -> dict:
    results = []
    for num in pr_numbers:
        results.append(close_pr(num, reason, dry_run))

    succeeded = sum(1 for r in results if r.get("success") or r.get("dry_run"))
    failed = sum(1 for r in results if not r.get("success") and not r.get("dry_run"))

    return {
        "action": "batch-close",
        "dry_run": dry_run,
        "count": len(pr_numbers),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


def main():
    check_gh()

    if len(sys.argv) < 3:
        print(
            "Usage:\n"
            "  merge_pr.py merge <pr> [--strategy squash|merge|rebase] [--dry-run]\n"
            "  merge_pr.py close <pr> --reason <text> [--dry-run]\n"
            "  merge_pr.py batch-close <pr,pr,...> --reason <text> [--dry-run]",
            file=sys.stderr,
        )
        sys.exit(1)

    action = sys.argv[1]
    flags = sys.argv[2:]
    dry_run = "--dry-run" in flags

    if action == "merge":
        pr_number = parse_pr_number(sys.argv[2])
        strategy = "squash"
        if "--strategy" in flags:
            idx = flags.index("--strategy")
            if idx + 1 < len(flags):
                strategy = flags[idx + 1]
        result = merge_pr(pr_number, strategy, dry_run)

    elif action == "close":
        pr_number = parse_pr_number(sys.argv[2])
        reason = "Closed by merge-pull-requests skill."
        if "--reason" in flags:
            idx = flags.index("--reason")
            if idx + 1 < len(flags):
                reason = flags[idx + 1]
        result = close_pr(pr_number, reason, dry_run)

    elif action == "batch-close":
        pr_numbers = parse_pr_numbers(sys.argv[2])
        reason = "Closed as obsolete by merge-pull-requests skill."
        if "--reason" in flags:
            idx = flags.index("--reason")
            if idx + 1 < len(flags):
                reason = flags[idx + 1]
        result = batch_close(pr_numbers, reason, dry_run)

    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
