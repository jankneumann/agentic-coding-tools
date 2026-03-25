#!/usr/bin/env python3
"""Merge protocol for integrating per-package worktree branches.

Merges one or more package branches into a feature branch, detecting
conflicts and reporting results as structured JSON or human-readable text.

Usage:
    python3 scripts/merge_worktrees.py <change-id> <package-id> [<package-id>...] [--dry-run] [--json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def run_git(
    *args: str,
    cwd: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the CompletedProcess result."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def git_stdout(*args: str, cwd: str | None = None, check: bool = True) -> str:
    """Run a git command and return stripped stdout."""
    return run_git(*args, cwd=cwd, check=check).stdout.strip()


def resolve_repo_root(cwd: str | None = None) -> str:
    """Resolve the top-level directory of the current git repository."""
    return git_stdout("rev-parse", "--show-toplevel", cwd=cwd)


# ---------------------------------------------------------------------------
# Branch name computation
# ---------------------------------------------------------------------------

def feature_branch(change_id: str) -> str:
    """Compute the feature branch name for a change-id."""
    return f"openspec/{change_id}"


def package_branch(change_id: str, package_id: str) -> str:
    """Compute the package branch name for a change-id and package-id.

    Uses '--' separator instead of '/' to avoid git ref conflicts:
    git cannot have both refs/heads/openspec/foo and refs/heads/openspec/foo/bar.
    """
    return f"openspec/{change_id}--{package_id}"


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def _get_conflict_files(cwd: str) -> list[str]:
    """Return list of files with merge conflicts."""
    result = run_git(
        "diff", "--name-only", "--diff-filter=U",
        cwd=cwd, check=False,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f]


def merge_packages(
    change_id: str,
    package_ids: list[str],
    *,
    cwd: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Merge package branches into the feature branch.

    Args:
        change_id: The OpenSpec change identifier.
        package_ids: Ordered list of package identifiers to merge.
        cwd: Working directory (must be inside the git repo).
        dry_run: If True, test merges without persisting them.

    Returns:
        Result dict with success status, merged list, and conflicts.
    """
    feat_branch = feature_branch(change_id)
    merged: list[str] = []
    conflicts: list[dict[str, Any]] = []

    # Ensure we're on the feature branch
    current = git_stdout("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    if current != feat_branch:
        run_git("checkout", feat_branch, cwd=cwd)

    for pkg_id in package_ids:
        branch = package_branch(change_id, pkg_id)

        # Verify branch exists
        ref_check = run_git(
            "show-ref", "--verify", "--quiet", f"refs/heads/{branch}",
            cwd=cwd, check=False,
        )
        if ref_check.returncode != 0:
            conflicts.append({
                "package": pkg_id,
                "branch": branch,
                "files": [],
                "error": f"Branch {branch} does not exist",
            })
            continue

        if dry_run:
            # Test merge without committing
            result = run_git(
                "merge", "--no-commit", "--no-ff", branch,
                cwd=cwd, check=False,
            )
            if result.returncode != 0:
                conflict_files = _get_conflict_files(cwd)
                error_msg = result.stderr.strip() or result.stdout.strip()
                conflicts.append({
                    "package": pkg_id,
                    "branch": branch,
                    "files": conflict_files,
                    "error": error_msg,
                })
            else:
                merged.append(pkg_id)
            # Always abort in dry-run mode to restore state
            run_git("merge", "--abort", cwd=cwd, check=False)
        else:
            # Real merge
            result = run_git(
                "merge", "--no-ff", branch,
                "-m", f"merge: {pkg_id} into feature branch",
                cwd=cwd, check=False,
            )
            if result.returncode != 0:
                conflict_files = _get_conflict_files(cwd)
                error_msg = result.stderr.strip() or result.stdout.strip()
                conflicts.append({
                    "package": pkg_id,
                    "branch": branch,
                    "files": conflict_files,
                    "error": error_msg,
                })
                # Abort the failed merge
                run_git("merge", "--abort", cwd=cwd, check=False)
            else:
                merged.append(pkg_id)

    success = len(conflicts) == 0
    return {
        "success": success,
        "change_id": change_id,
        "feature_branch": feat_branch,
        "merged": merged,
        "conflicts": conflicts,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_human(result: dict[str, Any]) -> str:
    """Format merge result as human-readable text."""
    lines: list[str] = []
    status = "SUCCESS" if result["success"] else "FAILED"
    lines.append(f"Merge {status} for {result['change_id']}")
    lines.append(f"Feature branch: {result['feature_branch']}")
    lines.append("")

    if result["merged"]:
        lines.append("Merged:")
        for pkg in result["merged"]:
            lines.append(f"  + {pkg}")

    if result["conflicts"]:
        lines.append("Conflicts:")
        for conflict in result["conflicts"]:
            lines.append(f"  ! {conflict['package']} ({conflict['branch']})")
            lines.append(f"    Error: {conflict['error']}")
            if conflict["files"]:
                for f in conflict["files"]:
                    lines.append(f"      - {f}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge per-package branches into a feature branch",
    )
    parser.add_argument("change_id", help="OpenSpec change identifier")
    parser.add_argument(
        "package_ids", nargs="+", metavar="package-id",
        help="Package identifiers to merge (in order)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Test merges without persisting them",
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args(argv)

    cwd = resolve_repo_root()

    result = merge_packages(
        change_id=args.change_id,
        package_ids=args.package_ids,
        cwd=cwd,
        dry_run=args.dry_run,
    )

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(format_human(result))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
