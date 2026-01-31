#!/usr/bin/env python3
"""Merge or close pull requests with pre-merge validation.

Actions:
  merge        - Merge a single PR (squash/merge/rebase)
  close        - Close a single PR with a comment
  batch-close  - Close multiple obsolete PRs with explanatory comments
  rerun-checks - Re-run failed CI workflow runs for a PR

Usage:
  python merge_pr.py merge <pr_number> [--strategy squash|merge|rebase] [--dry-run]
  python merge_pr.py close <pr_number> --reason <text> [--dry-run]
  python merge_pr.py batch-close <pr_numbers_comma_sep> --reason <text> [--dry-run]
  python merge_pr.py rerun-checks <pr_number> [--dry-run]

Output: JSON result to stdout.
"""

import argparse
import json
import subprocess
import sys

from shared import (
    GH_TIMEOUT,
    check_gh,
    parse_pr_numbers,
    run_gh,
    run_gh_unchecked,
    safe_author,
)

# Use a longer timeout for merge operations which can be slow
MERGE_TIMEOUT = 60


def get_pr_status(pr_number: int) -> dict:
    try:
        raw = run_gh([
            "pr", "view", str(pr_number), "--json",
            "state,mergeable,statusCheckRollup,reviewDecision,"
            "headRefName,title,isDraft,isCrossRepository,reviewRequests",
        ], timeout=GH_TIMEOUT)
    except RuntimeError as e:
        print(f"Error: Could not fetch PR #{pr_number}: {e}", file=sys.stderr)
        sys.exit(1)
    return json.loads(raw)


def check_approval_freshness(pr_number: int) -> dict:
    """Check if the latest commit is newer than the latest approval.

    Returns a dict with stale approval info. This is informational —
    repos with 'Dismiss stale reviews on push' enforce this server-side,
    but repos without that setting should still be warned.
    """
    try:
        raw = run_gh([
            "pr", "view", str(pr_number), "--json", "commits,reviews",
        ], timeout=GH_TIMEOUT)
    except RuntimeError as e:
        print(
            f"Warning: Could not verify approval freshness for PR #{pr_number}: {e}",
            file=sys.stderr,
        )
        return {
            "approval_may_be_stale": False,
            "reason": "could_not_check",
            "warning": "Could not verify approval freshness",
        }

    data = json.loads(raw)
    commits = data.get("commits", [])
    reviews = data.get("reviews", [])

    if not commits or not reviews:
        return {"approval_may_be_stale": False}

    # Get latest commit date
    last_commit = commits[-1]
    commit_date = last_commit.get("committedDate", "")

    # Get latest APPROVED review date
    approved_dates = [
        r.get("submittedAt", "")
        for r in reviews
        if r.get("state") == "APPROVED" and r.get("submittedAt")
    ]
    if not approved_dates:
        return {"approval_may_be_stale": False}

    latest_approval = max(approved_dates)

    # Check if any CHANGES_REQUESTED review was submitted after the latest approval
    changes_requested_dates = [
        r.get("submittedAt", "")
        for r in reviews
        if r.get("state") == "CHANGES_REQUESTED" and r.get("submittedAt")
    ]
    if changes_requested_dates and max(changes_requested_dates) > latest_approval:
        return {
            "approval_may_be_stale": True,
            "reason": "changes_requested_after_approval",
            "latest_approval": latest_approval,
            "latest_changes_requested": max(changes_requested_dates),
        }

    # ISO date strings are lexicographically comparable
    if commit_date and latest_approval and commit_date > latest_approval:
        return {
            "approval_may_be_stale": True,
            "reason": "commits_after_approval",
            "latest_commit": commit_date,
            "latest_approval": latest_approval,
        }

    return {"approval_may_be_stale": False}


def format_pending_reviewers(review_requests: list) -> list[str]:
    """Extract pending reviewer names from reviewRequests."""
    reviewers = []
    for req in review_requests or []:
        # User reviewers have 'login', team reviewers have 'name'/'slug'
        login = req.get("login")
        if login:
            reviewers.append(login)
        else:
            name = req.get("name") or req.get("slug")
            if name:
                reviewers.append(f"team:{name}")
    return reviewers


def validate_pr(pr_number: int) -> dict:
    """Pre-merge validation: CI status, approval, mergeability, and warnings."""
    status = get_pr_status(pr_number)
    is_draft = status.get("isDraft", False)
    is_fork = status.get("isCrossRepository", False)
    mergeable = status.get("mergeable", "UNKNOWN")
    has_conflicts = mergeable == "CONFLICTING"

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

    # Check for stale approval (commits pushed after last approval)
    approval_freshness = {}
    if approved:
        approval_freshness = check_approval_freshness(pr_number)

    # Extract pending reviewers (CODEOWNERS or manually requested)
    pending_reviewers = format_pending_reviewers(
        status.get("reviewRequests", []),
    )

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
        "is_fork": is_fork,
        "mergeable": mergeable,
        "has_conflicts": has_conflicts,
        "check_summary": check_summary,
        "checks_passing": checks_ok and not checks_pending,
        "checks_pending": checks_pending,
        "checks_failed": not checks_ok,
        "check_details": check_details,
        "review_decision": review_decision,
        "approved": approved,
        "approval_may_be_stale": approval_freshness.get(
            "approval_may_be_stale", False,
        ),
        "pending_reviewers": pending_reviewers,
        "can_merge": (
            mergeable == "MERGEABLE"
            and checks_ok
            and not checks_pending
            and not is_draft
            and approved
        ),
    }


def _try_merge(pr_number: int, strategy: str, is_fork: bool) -> dict:
    """Attempt the actual gh pr merge command, handling edge cases."""
    strategy_flag = f"--{strategy}"
    merge_args = ["pr", "merge", str(pr_number), strategy_flag]

    # Fork PRs: can't delete the remote branch (no push access to fork)
    if not is_fork:
        merge_args.append("--delete-branch")

    try:
        result = run_gh_unchecked(merge_args, timeout=MERGE_TIMEOUT)
    except subprocess.TimeoutExpired:
        resp = {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "error": "Merge command timed out",
        }
        if is_fork:
            resp["note"] = "Fork PR — remote branch not deleted"
        return resp

    if result.returncode == 0:
        resp = {
            "action": "merge",
            "success": True,
            "status": "merged",
            "pr_number": pr_number,
            "strategy": strategy,
        }
        if is_fork:
            resp["note"] = "Fork PR — remote branch not deleted"
        return resp

    stderr = result.stderr.strip()

    # Detect merge queue requirement and retry
    stderr_lower = stderr.lower()
    if "merge queue" in stderr_lower or "enqueue" in stderr_lower:
        return _try_merge_queue(pr_number, strategy, is_fork)

    # Merge may have succeeded but branch deletion failed
    post_status = get_pr_status(pr_number)
    if post_status.get("state") == "MERGED":
        resp = {
            "action": "merge",
            "success": True,
            "status": "merged",
            "pr_number": pr_number,
            "strategy": strategy,
            "warning": "PR merged but branch deletion may have failed",
            "stderr": stderr,
        }
        if is_fork:
            resp["note"] = "Fork PR — remote branch not deleted"
        return resp

    resp = {
        "action": "merge",
        "success": False,
        "pr_number": pr_number,
        "error": stderr or "Merge command failed",
    }
    if is_fork:
        resp["note"] = "Fork PR — remote branch not deleted"
    return resp


def _try_merge_queue(pr_number: int, strategy: str, is_fork: bool) -> dict:
    """Retry merge using --merge-queue for repos that require it."""
    strategy_flag = f"--{strategy}"
    merge_args = ["pr", "merge", str(pr_number), strategy_flag, "--merge-queue"]
    if not is_fork:
        merge_args.append("--delete-branch")

    try:
        result = run_gh_unchecked(merge_args, timeout=MERGE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "error": "Merge queue command timed out",
        }

    if result.returncode == 0:
        resp = {
            "action": "merge",
            "success": True,
            "status": "enqueued",
            "pr_number": pr_number,
            "strategy": strategy,
            "merge_queue": True,
            "note": "PR added to merge queue — will merge automatically when ready",
        }
        if is_fork:
            resp["note"] += "; fork PR — remote branch not deleted"
        return resp

    return {
        "action": "merge",
        "success": False,
        "pr_number": pr_number,
        "error": result.stderr.strip() or "Merge queue command failed",
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

    if validation["has_conflicts"]:
        return {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "reason": (
                "PR has merge conflicts — rebase onto the base branch "
                "or merge the base branch into the PR branch to resolve"
            ),
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
        reason = "Review approval required before merging"
        if validation["pending_reviewers"]:
            reviewers = ", ".join(validation["pending_reviewers"])
            reason += f" (pending: {reviewers})"
        return {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "reason": reason,
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

    result = _try_merge(
        pr_number, strategy, validation.get("is_fork", False),
    )

    # Include stale approval warning on successful merges
    if result.get("success") and validation.get("approval_may_be_stale"):
        result["warning"] = result.get("warning", "")
        if result["warning"]:
            result["warning"] += "; "
        result["warning"] += (
            "Approval may be stale — commits were pushed after the last approval"
        )

    return result


def rerun_failed_checks(pr_number: int, dry_run: bool = False) -> dict:
    """Re-run failed CI workflow runs for a PR."""
    # Get PR branch
    try:
        raw = run_gh([
            "pr", "view", str(pr_number), "--json", "headRefName",
        ], timeout=GH_TIMEOUT)
    except RuntimeError as e:
        return {
            "action": "rerun-checks",
            "success": False,
            "pr_number": pr_number,
            "error": f"Could not fetch PR: {e}",
        }

    branch = json.loads(raw).get("headRefName", "")
    if not branch:
        return {
            "action": "rerun-checks",
            "success": False,
            "pr_number": pr_number,
            "error": "Could not determine PR branch",
        }

    # Find failed workflow runs on this branch
    try:
        raw = run_gh([
            "run", "list", "--branch", branch, "--status", "failure",
            "--limit", "10", "--json", "databaseId,name,conclusion",
        ], timeout=GH_TIMEOUT)
    except RuntimeError as e:
        return {
            "action": "rerun-checks",
            "success": False,
            "pr_number": pr_number,
            "error": f"Could not list runs: {e}",
        }

    runs = json.loads(raw) if raw else []
    if not runs:
        return {
            "action": "rerun-checks",
            "success": True,
            "pr_number": pr_number,
            "message": "No failed workflow runs found",
            "rerun_count": 0,
        }

    if dry_run:
        return {
            "action": "rerun-checks",
            "dry_run": True,
            "pr_number": pr_number,
            "failed_runs": [
                {"id": r["databaseId"], "name": r["name"]} for r in runs
            ],
        }

    rerun_results = []
    for run in runs:
        run_id = run["databaseId"]
        try:
            rr = run_gh_unchecked(
                ["run", "rerun", str(run_id), "--failed"], timeout=GH_TIMEOUT,
            )
            rerun_results.append({
                "id": run_id,
                "name": run["name"],
                "rerun": rr.returncode == 0,
                "error": rr.stderr.strip() if rr.returncode != 0 else None,
            })
        except subprocess.TimeoutExpired:
            rerun_results.append({
                "id": run_id,
                "name": run["name"],
                "rerun": False,
                "error": "timeout",
            })

    return {
        "action": "rerun-checks",
        "success": True,
        "pr_number": pr_number,
        "rerun_count": sum(1 for r in rerun_results if r["rerun"]),
        "results": rerun_results,
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
    remaining = []
    for i, num in enumerate(pr_numbers):
        result = close_pr(num, reason, dry_run)
        results.append(result)
        # Stop on first real failure (not dry-run)
        if not dry_run and not result.get("success"):
            remaining = pr_numbers[i + 1:]
            break

    succeeded = sum(1 for r in results if r.get("success") or r.get("dry_run"))
    failed = sum(1 for r in results if not r.get("success") and not r.get("dry_run"))

    resp = {
        "action": "batch-close",
        "dry_run": dry_run,
        "count": len(pr_numbers),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
    if remaining:
        resp["partial"] = True
        resp["remaining"] = remaining
    return resp


def main():
    parser = argparse.ArgumentParser(
        description="Merge or close pull requests with pre-merge validation.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    # merge subcommand
    merge_parser = subparsers.add_parser("merge", help="Merge a single PR")
    merge_parser.add_argument("pr_number", type=int, help="PR number to merge")
    merge_parser.add_argument(
        "--strategy", default="squash", choices=["squash", "merge", "rebase"],
        help="Merge strategy (default: squash)",
    )
    merge_parser.add_argument("--dry-run", action="store_true")

    # close subcommand
    close_parser = subparsers.add_parser("close", help="Close a single PR")
    close_parser.add_argument("pr_number", type=int, help="PR number to close")
    close_parser.add_argument(
        "--reason", default="Closed by merge-pull-requests skill.",
        help="Reason for closing",
    )
    close_parser.add_argument("--dry-run", action="store_true")

    # batch-close subcommand
    batch_parser = subparsers.add_parser("batch-close", help="Close multiple PRs")
    batch_parser.add_argument(
        "pr_numbers", help="Comma-separated PR numbers (e.g. 1,2,3)",
    )
    batch_parser.add_argument(
        "--reason", default="Closed as obsolete by merge-pull-requests skill.",
        help="Reason for closing",
    )
    batch_parser.add_argument("--dry-run", action="store_true")

    # rerun-checks subcommand
    rerun_parser = subparsers.add_parser("rerun-checks", help="Re-run failed CI checks")
    rerun_parser.add_argument("pr_number", type=int, help="PR number")
    rerun_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    check_gh()

    if args.action == "merge":
        result = merge_pr(args.pr_number, args.strategy, args.dry_run)
    elif args.action == "close":
        result = close_pr(args.pr_number, args.reason, args.dry_run)
    elif args.action == "batch-close":
        pr_numbers = parse_pr_numbers(args.pr_numbers)
        result = batch_close(pr_numbers, args.reason, args.dry_run)
    elif args.action == "rerun-checks":
        result = rerun_failed_checks(args.pr_number, args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
