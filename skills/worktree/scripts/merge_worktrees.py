#!/usr/bin/env python3
"""Merge protocol for integrating per-package worktree branches.

Merges one or more package branches into a feature branch, detecting
conflicts and reporting results as structured JSON or human-readable text.

Branch names are resolved via ``worktree.py``'s registry and
``OPENSPEC_BRANCH_OVERRIDE`` environment variable so this script picks the
same branches that the work-package agents actually committed to — see the
``resolve_branch`` helper below for the precedence chain.

Usage:
    python3 scripts/merge_worktrees.py <change-id> <package-id> [<package-id>...] [--dry-run] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Share branch resolution logic with worktree.py so both scripts always
# agree on what branch a given (change-id, agent-id) pair resolves to.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from worktree import (  # noqa: E402
    find_entry,
    load_registry,
    resolve_branch as _resolve_branch,
    resolve_main_repo,
    resolve_parent_branch as _resolve_parent_branch,
)


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

def feature_branch(change_id: str, cwd: str | None = None) -> str:
    """Resolve the feature branch name for a change-id.

    Precedence:
      1. Registry entry (change_id, agent_id=None) — records what setup used
      2. ``OPENSPEC_BRANCH_OVERRIDE`` environment variable
      3. Default ``openspec/<change-id>``
    """
    try:
        main_repo = resolve_main_repo(cwd)
        registry = load_registry(main_repo)
        entry = find_entry(registry, change_id, None)
        if entry and entry.get("branch"):
            return str(entry["branch"])
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # Fall through to env/default resolution if we can't reach the registry
        pass
    return _resolve_parent_branch(change_id, env=os.environ)


def package_branch(change_id: str, package_id: str, cwd: str | None = None) -> str:
    """Resolve the package branch name for a (change-id, package-id) pair.

    Uses the same precedence as ``feature_branch`` plus the ``--<package-id>``
    agent suffix. The ``--`` separator (not ``/``) avoids the git ref storage
    collision where ``refs/heads/a/b`` and ``refs/heads/a/b/c`` cannot coexist.

    When ``OPENSPEC_BRANCH_OVERRIDE=claude/op-9P9o1`` is set, the work packages
    land on branches like ``claude/op-9P9o1--wp-backend`` — this function
    returns that exact name, matching what ``worktree.py setup`` created.
    """
    try:
        main_repo = resolve_main_repo(cwd)
        registry = load_registry(main_repo)
        entry = find_entry(registry, change_id, package_id)
        if entry and entry.get("branch"):
            return str(entry["branch"])
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return _resolve_branch(change_id, agent_id=package_id, env=os.environ)


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
    feat_branch = feature_branch(change_id, cwd=cwd)
    merged: list[str] = []
    conflicts: list[dict[str, Any]] = []

    # Ensure we're on the feature branch
    current = git_stdout("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    if current != feat_branch:
        run_git("checkout", feat_branch, cwd=cwd)

    for pkg_id in package_ids:
        branch = package_branch(change_id, pkg_id, cwd=cwd)

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
