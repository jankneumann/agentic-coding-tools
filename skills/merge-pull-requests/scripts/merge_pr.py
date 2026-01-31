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


def run_gh(args: list[str], check: bool = True) -> str:
    result = subprocess.run(
        ["gh"] + args, capture_output=True, text=True, check=check
    )
    return result.stdout.strip()


def get_pr_status(pr_number: int) -> dict:
    raw = run_gh([
        "pr", "view", str(pr_number), "--json",
        "state,mergeable,statusCheckRollup,reviewDecision,headRefName,title",
    ])
    return json.loads(raw)


def validate_pr(pr_number: int) -> dict:
    """Pre-merge validation: CI status, approval, mergeability."""
    status = get_pr_status(pr_number)

    checks_ok = True
    check_details = []
    for check in status.get("statusCheckRollup", []) or []:
        state = check.get("conclusion") or check.get("state", "")
        name = check.get("name") or check.get("context", "unknown")
        check_details.append({"name": name, "state": state})
        if state not in ("SUCCESS", "success", "NEUTRAL", "neutral", "SKIPPED", "skipped"):
            checks_ok = False

    review_decision = status.get("reviewDecision", "")
    approved = review_decision == "APPROVED"

    mergeable = status.get("mergeable", "UNKNOWN")

    return {
        "pr_number": pr_number,
        "title": status.get("title", ""),
        "branch": status.get("headRefName", ""),
        "mergeable": mergeable,
        "checks_passing": checks_ok,
        "check_details": check_details,
        "review_decision": review_decision,
        "approved": approved,
        "can_merge": mergeable == "MERGEABLE" and checks_ok,
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
        run_gh([
            "pr", "merge", str(pr_number), strategy_flag, "--delete-branch",
        ])
        return {
            "action": "merge",
            "success": True,
            "pr_number": pr_number,
            "strategy": strategy,
        }
    except subprocess.CalledProcessError as e:
        return {
            "action": "merge",
            "success": False,
            "pr_number": pr_number,
            "error": str(e),
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

    try:
        run_gh([
            "pr", "comment", str(pr_number), "--body", reason,
        ])
        run_gh([
            "pr", "close", str(pr_number),
        ])
        return {
            "action": "close",
            "success": True,
            "pr_number": pr_number,
            "reason": reason,
        }
    except subprocess.CalledProcessError as e:
        return {
            "action": "close",
            "success": False,
            "pr_number": pr_number,
            "error": str(e),
        }


def batch_close(pr_numbers: list[int], reason: str,
                dry_run: bool = False) -> dict:
    results = []
    for num in pr_numbers:
        results.append(close_pr(num, reason, dry_run))
    return {
        "action": "batch-close",
        "dry_run": dry_run,
        "count": len(pr_numbers),
        "results": results,
    }


def main():
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
        pr_number = int(sys.argv[2])
        strategy = "squash"
        if "--strategy" in flags:
            idx = flags.index("--strategy")
            if idx + 1 < len(flags):
                strategy = flags[idx + 1]
        result = merge_pr(pr_number, strategy, dry_run)

    elif action == "close":
        pr_number = int(sys.argv[2])
        reason = "Closed by merge-pull-requests skill."
        if "--reason" in flags:
            idx = flags.index("--reason")
            if idx + 1 < len(flags):
                reason = flags[idx + 1]
        result = close_pr(pr_number, reason, dry_run)

    elif action == "batch-close":
        pr_numbers = [int(n) for n in sys.argv[2].split(",")]
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
