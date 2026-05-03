"""Prototype branch cleanup helper for /cleanup-feature.

Per D4, prototype/<change-id>/v<n> branches and their worktrees persist
from /prototype-feature through to /cleanup-feature so the synthesized
design can be traced back to the variant source material. This module
is the bookend that ends that retention period.

The /cleanup-feature SKILL.md calls into here from a step that runs
right before the standard branch + worktree cleanup, so prototype
branches are removed alongside the feature branch.

Spec scenarios:
  - CleanupIncludesPrototypeBranches.prototype-cleanup-on-merge
  - CleanupIncludesPrototypeBranches.stale-state-without-findings

The helper is intentionally narrow:
  - Enumerate local branches matching ``refs/heads/prototype/<change>/v<n>``.
  - Force-delete each (variant branches were exploratory; their commits
    are NOT expected to be merged into main, since the synthesized design
    landed on the feature branch via /iterate-on-plan, not via a merge of
    the variant branch itself).
  - Remote deletion is the SKILL workflow's responsibility (it has the
    operator's gh credentials and remote name); this helper handles only
    the local side.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Spec ties this to the prototype/<change-id>/v<n> naming convention from
# the wp-worktree --branch-prefix prototype scheme.
PROTOTYPE_BRANCH_PATTERN: str = "prototype/{change_id}/v*"

_VARIANT_SUFFIX_RE = re.compile(r"^v[1-9][0-9]*$")


def _run_git(repo_dir: Path, *args: str, check: bool = True) -> str:
    """Run a git command in the repo, returning stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout


def enumerate_prototype_branches(
    change_id: str,
    repo_dir: Path,
) -> list[str]:
    """List local prototype branches for ``change_id``.

    Returns the matching branch names (e.g. ``['prototype/add-foo/v1', ...]``).
    Empty list if none exist — callers must handle the "stale state without
    findings" case where someone invokes /cleanup-feature without ever
    having run /prototype-feature.
    """
    pattern = PROTOTYPE_BRANCH_PATTERN.format(change_id=change_id)
    raw = _run_git(repo_dir, "branch", "--list", pattern, check=False)

    branches: list[str] = []
    for line in raw.splitlines():
        # ``git branch --list`` prefixes the current branch with '* ' and
        # everything else with '  '. Strip both.
        name = line.strip().lstrip("* ").strip()
        if not name:
            continue
        # Defensive check: ensure the suffix is actually a v<n> pattern, not
        # some accidental match (the glob is permissive).
        suffix = name.rsplit("/", 1)[-1]
        if _VARIANT_SUFFIX_RE.match(suffix):
            branches.append(name)

    return sorted(branches)


def delete_prototype_branches(
    change_id: str,
    repo_dir: Path,
) -> list[str]:
    """Force-delete all local prototype branches for ``change_id``.

    Returns the list of branches that were actually deleted. Idempotent:
    if no branches match, returns an empty list with no error.

    Force is required because variant branches typically aren't merged
    into main — the chosen design landed on the feature branch via
    iterate-on-plan synthesis, not via a merge of any single variant.
    Variant branches are exploratory; deleting them at feature-close is
    expected.
    """
    targets = enumerate_prototype_branches(change_id, repo_dir=repo_dir)
    if not targets:
        return []

    deleted: list[str] = []
    for branch in targets:
        result = subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=str(repo_dir),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            deleted.append(branch)
        # If a delete fails (e.g. branch was already removed mid-loop) we
        # silently skip — cleanup MUST be idempotent and best-effort. The
        # caller (SKILL workflow) re-enumerates after to verify nothing
        # was left behind.

    return deleted


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point for the SKILL.md to shell out to.

    Usage:
        python3 cleanup_prototype.py <change_id> [--repo-dir <path>]

    Prints one deleted branch per line on stdout. Exits 0 even when no
    branches were found (cleanup must be idempotent — running twice is
    not an error).
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Delete prototype/<change>/v<n> branches for a change."
    )
    parser.add_argument("change_id", help="OpenSpec change-id")
    parser.add_argument(
        "--repo-dir",
        default=".",
        help="Git repository root (default: cwd)",
    )
    args = parser.parse_args(argv)

    deleted = delete_prototype_branches(
        args.change_id, repo_dir=Path(args.repo_dir)
    )
    for branch in deleted:
        print(f"DELETED={branch}")
    print(f"DELETED_COUNT={len(deleted)}", file=sys.stderr)
    return 0


__all__ = [
    "PROTOTYPE_BRANCH_PATTERN",
    "delete_prototype_branches",
    "enumerate_prototype_branches",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
