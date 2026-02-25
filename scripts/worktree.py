#!/usr/bin/env python3
"""Git worktree lifecycle helper for OpenSpec skills.

Manages worktree creation, teardown, status, and detection.
Outputs machine-parseable KEY=VALUE lines for shell eval.

Usage:
    python3 scripts/worktree.py setup <change-id> [--branch <name>] [--prefix <prefix>]
    python3 scripts/worktree.py teardown <change-id> [--prefix <prefix>]
    python3 scripts/worktree.py status [<change-id>]
    python3 scripts/worktree.py detect
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_git(*args: str, cwd: str | None = None, check: bool = True) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def resolve_main_repo(cwd: str | None = None) -> Path:
    """Resolve the main repository path, even from inside a worktree."""
    git_common = run_git("rev-parse", "--git-common-dir", cwd=cwd)
    if git_common == ".git":
        return Path(run_git("rev-parse", "--show-toplevel", cwd=cwd))
    # In a worktree: git-common-dir returns /path/to/main/.git
    # or /path/to/main/.git/worktrees/<name>
    main_git = git_common.split("/.git")[0]
    return Path(main_git)


def worktree_path(main_repo: Path, change_id: str, prefix: str | None = None) -> Path:
    """Compute the worktree path under .git-worktrees/."""
    base = main_repo / ".git-worktrees"
    if prefix:
        return base / prefix / change_id
    return base / change_id


def legacy_worktree_path(
    main_repo: Path, change_id: str, prefix: str | None = None
) -> Path:
    """Compute the legacy worktree path at ../<repo>.worktrees/."""
    repo_name = main_repo.name
    parent = main_repo.parent / f"{repo_name}.worktrees"
    if prefix:
        return parent / prefix / change_id
    return parent / change_id


def cmd_setup(args: argparse.Namespace) -> int:
    """Create a worktree for the given change-id."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id = args.change_id
    prefix = args.prefix
    branch = args.branch or (
        f"openspec/{change_id}" if not prefix else f"{prefix}/{change_id}"
    )

    wt_path = worktree_path(main_repo, change_id, prefix)

    # Check if already in the target worktree
    try:
        current_toplevel = Path(
            run_git("rev-parse", "--show-toplevel", cwd=cwd)
        )
        if current_toplevel == wt_path:
            print(f"WORKTREE_PATH={wt_path}")
            print("ALREADY_EXISTS=true", file=sys.stderr)
            return 0
    except subprocess.CalledProcessError:
        pass

    # Create parent directory
    wt_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure we have latest main
    run_git("fetch", "origin", "main", cwd=str(main_repo), check=False)

    # Create branch if it doesn't exist
    try:
        run_git(
            "show-ref", "--verify", "--quiet", f"refs/heads/{branch}",
            cwd=str(main_repo),
        )
    except subprocess.CalledProcessError:
        run_git("branch", branch, "main", cwd=str(main_repo))
        print(f"BRANCH_CREATED={branch}", file=sys.stderr)

    # Create worktree (or reuse)
    if wt_path.is_dir():
        print("ALREADY_EXISTS=true", file=sys.stderr)
    else:
        run_git("worktree", "add", str(wt_path), branch, cwd=str(main_repo))
        print("CREATED=true", file=sys.stderr)

    print(f"WORKTREE_PATH={wt_path}")
    return 0


def cmd_teardown(args: argparse.Namespace) -> int:
    """Remove a worktree for the given change-id."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id = args.change_id
    prefix = args.prefix

    # Check new location first, then legacy
    wt_path = worktree_path(main_repo, change_id, prefix)
    legacy_path = legacy_worktree_path(main_repo, change_id, prefix)

    target = None
    is_legacy = False
    if wt_path.is_dir():
        target = wt_path
    elif legacy_path.is_dir():
        target = legacy_path
        is_legacy = True

    if target is None:
        print(f"No worktree found for {change_id}", file=sys.stderr)
        print("REMOVED=false")
        return 1

    if is_legacy:
        print(f"Using legacy location: {target}", file=sys.stderr)

    # Must run from main repo to remove worktree
    run_git("worktree", "remove", str(target), cwd=str(main_repo))
    print("REMOVED=true")
    print(f"REMOVED_PATH={target}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """List active worktrees or check a specific one."""
    cwd = os.getcwd()
    main_repo = resolve_main_repo(cwd)
    change_id = args.change_id

    if change_id:
        wt_path = worktree_path(main_repo, change_id)
        legacy_path = legacy_worktree_path(main_repo, change_id)
        if wt_path.is_dir():
            print("EXISTS=true")
            print(f"WORKTREE_PATH={wt_path}")
            print("LOCATION=new")
        elif legacy_path.is_dir():
            print("EXISTS=true")
            print(f"WORKTREE_PATH={legacy_path}")
            print("LOCATION=legacy")
        else:
            print("EXISTS=false")
            return 1
    else:
        output = run_git("worktree", "list", cwd=str(main_repo))
        print(output)
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    """Detect if running in a worktree and output context variables."""
    cwd = os.getcwd()
    try:
        git_common = run_git("rev-parse", "--git-common-dir", cwd=cwd)
    except subprocess.CalledProcessError:
        print("IN_WORKTREE=false")
        print(f"MAIN_REPO={cwd}")
        print("OPENSPEC_PATH=openspec")
        return 0

    if git_common == ".git":
        main_repo = run_git("rev-parse", "--show-toplevel", cwd=cwd)
        print("IN_WORKTREE=false")
        print(f"MAIN_REPO={main_repo}")
        print("OPENSPEC_PATH=openspec")
    else:
        main_git = git_common.split("/.git")[0]
        print("IN_WORKTREE=true")
        print(f"MAIN_REPO={main_git}")
        print(f"OPENSPEC_PATH={main_git}/openspec")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Git worktree lifecycle helper for OpenSpec skills"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup
    setup_parser = subparsers.add_parser("setup", help="Create a worktree")
    setup_parser.add_argument("change_id", help="Change ID or identifier")
    setup_parser.add_argument("--branch", help="Branch name (default: openspec/<change-id>)")
    setup_parser.add_argument("--prefix", help="Path prefix (e.g., fix-scrub)")
    setup_parser.set_defaults(func=cmd_setup)

    # teardown
    teardown_parser = subparsers.add_parser("teardown", help="Remove a worktree")
    teardown_parser.add_argument("change_id", help="Change ID or identifier")
    teardown_parser.add_argument("--prefix", help="Path prefix (e.g., fix-scrub)")
    teardown_parser.set_defaults(func=cmd_teardown)

    # status
    status_parser = subparsers.add_parser("status", help="Check worktree status")
    status_parser.add_argument("change_id", nargs="?", help="Change ID to check")
    status_parser.set_defaults(func=cmd_status)

    # detect
    detect_parser = subparsers.add_parser("detect", help="Detect worktree context")
    detect_parser.set_defaults(func=cmd_detect)

    parsed = parser.parse_args()
    return parsed.func(parsed)


if __name__ == "__main__":
    sys.exit(main())
