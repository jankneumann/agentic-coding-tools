#!/usr/bin/env python3
"""Fast-forward submodule main branches after a parent merge.

After a parent PR is merged to main, submodules whose gitlink SHA changed
need their own ``main`` branch fast-forwarded to the SHA the parent records,
then pushed to the submodule remote. This prevents silent divergence where
the parent records a new SHA but the submodule's own main lags behind.

Usage:
    python3 sync_submodules.py [--repo-dir <path>]

The script must run AFTER ``git fetch origin main`` so that the local main
ref reflects the post-merge state. It is designed to be called from the
cleanup-feature SKILL.md between step 4 (update local repository) and
step 5 (migrate open tasks).

Exit codes:
    0 — all changed submodules synced (or none changed)
    1 — at least one submodule failed to sync (details on stderr)

The script never aborts on individual submodule failures — it processes
all changed submodules and reports a summary at the end.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def run_git(
    *args: str,
    cwd: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the CompletedProcess."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        msg = f"git {' '.join(args)} failed (exit {result.returncode})"
        if result.stderr.strip():
            msg += f": {result.stderr.strip()}"
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr,
        )
    return result


# ---------------------------------------------------------------------------
# Submodule detection
# ---------------------------------------------------------------------------

@dataclass
class SubmoduleChange:
    """A submodule whose gitlink SHA changed in the merge."""

    path: str
    new_sha: str
    remote_url: str = ""


def detect_changed_submodules(repo_dir: str) -> list[SubmoduleChange]:
    """Detect submodules whose SHA changed between main@{1} and main.

    Uses ``git diff main@{1} main`` on gitlink entries (mode 160000) to
    find submodules that were bumped in the merge. Falls back to an empty
    list if main@{1} doesn't exist (first commit on main, or reflog expired).
    """
    try:
        diff_output = run_git(
            "diff", "--raw", "--abbrev=40", "main@{1}", "main",
            cwd=repo_dir, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        print("Could not diff main@{1}..main (reflog may be empty); "
              "skipping submodule sync.", file=sys.stderr)
        return []

    changes: list[SubmoduleChange] = []
    for line in diff_output.strip().splitlines():
        if not line:
            continue
        # Raw diff format: :old_mode new_mode old_sha new_sha status\tpath
        # Gitlinks (submodules) have mode 160000
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta, path = parts
        fields = meta.split()
        if len(fields) < 5:
            continue
        new_mode = fields[1]
        new_sha = fields[3]
        if new_mode == "160000":
            changes.append(SubmoduleChange(path=path, new_sha=new_sha))

    # Resolve remote URLs for each changed submodule
    for change in changes:
        try:
            url = run_git(
                "config", "--file", ".gitmodules",
                f"submodule.{change.path}.url",
                cwd=repo_dir, check=True,
            ).stdout.strip()
            change.remote_url = url
        except subprocess.CalledProcessError:
            # Try the path as the submodule name
            pass

    return changes


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

@dataclass
class SyncResult:
    """Result of syncing one submodule."""

    path: str
    success: bool
    ff_done: bool = False
    pushed: bool = False
    branch_deleted: bool = False
    error: str = ""
    handoff_commands: list[str] = field(default_factory=list)


def detect_submodule_feature_branch(
    sub_abs: str,
    target_sha: str,
    parent_feature_branch: str,
) -> str | None:
    """Find the submodule's feature branch that contains target_sha.

    Looks for branches matching the parent feature branch name pattern
    (e.g., ``openspec/<change-id>``). Returns the branch name or None.
    """
    try:
        branches_output = run_git(
            "branch", "-r", "--contains", target_sha,
            cwd=sub_abs, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None

    # Also check local branches
    try:
        local_branches = run_git(
            "branch", "--contains", target_sha,
            cwd=sub_abs, check=True,
        ).stdout
        branches_output += "\n" + local_branches
    except subprocess.CalledProcessError:
        pass

    # Extract the feature branch name from parent (e.g., "openspec/my-feature")
    # and look for it in submodule branches
    for line in branches_output.strip().splitlines():
        branch = line.strip().lstrip("* ")
        # Strip remote prefix (origin/)
        if branch.startswith("origin/"):
            branch = branch[len("origin/"):]
        if branch == parent_feature_branch:
            return branch

    return None


def sync_submodule(
    change: SubmoduleChange,
    repo_dir: str,
    feature_branch: str | None = None,
) -> SyncResult:
    """Fast-forward a submodule's main to the SHA the parent records, push, and clean up.

    Steps:
    1. Fetch origin main inside the submodule
    2. Switch to main
    3. Fast-forward (--ff-only) to the parent-recorded SHA
    4. Push main to origin
    5. Delete the feature branch (local + remote)

    On auth/push failure, logs operator handoff commands instead of aborting.
    """
    result = SyncResult(path=change.path, success=False)
    sub_abs = str(Path(repo_dir) / change.path)

    # 1. Fetch
    try:
        run_git("fetch", "origin", "main", cwd=sub_abs, check=True)
    except subprocess.CalledProcessError as exc:
        result.error = f"fetch failed: {exc.stderr or str(exc)}"
        result.handoff_commands.append(
            f"cd {change.path} && git fetch origin main"
        )
        return result

    # 2. Switch to main
    try:
        run_git("switch", "main", cwd=sub_abs, check=True)
    except subprocess.CalledProcessError:
        try:
            run_git("checkout", "main", cwd=sub_abs, check=True)
        except subprocess.CalledProcessError as exc:
            result.error = f"checkout main failed: {exc.stderr or str(exc)}"
            return result

    # 3. Fast-forward only
    try:
        run_git(
            "merge", "--ff-only", change.new_sha,
            cwd=sub_abs, check=True,
        )
        result.ff_done = True
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        result.error = (
            f"fast-forward failed (non-FF changes on submodule main?): {stderr}"
        )
        result.handoff_commands.append(
            f"cd {change.path} && git merge --ff-only {change.new_sha}"
        )
        return result

    # 4. Push main
    try:
        run_git("push", "origin", "main", cwd=sub_abs, check=True)
        result.pushed = True
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        remote_url = change.remote_url or "(unknown)"
        result.error = (
            f"push failed for submodule {change.path} "
            f"(remote: {remote_url}): {stderr}"
        )
        result.handoff_commands.append(
            f"cd {change.path} && git push origin main"
        )
        # Continue to branch cleanup even if push failed — the ff is local

    # 5. Delete feature branch (best-effort)
    if feature_branch:
        sub_feature = detect_submodule_feature_branch(
            sub_abs, change.new_sha, feature_branch,
        )
        if sub_feature and sub_feature != "main":
            # Delete local
            try:
                run_git(
                    "branch", "-d", sub_feature,
                    cwd=sub_abs, check=True,
                )
                result.branch_deleted = True
            except subprocess.CalledProcessError:
                pass

            # Delete remote (best-effort)
            try:
                run_git(
                    "push", "origin", "--delete", sub_feature,
                    cwd=sub_abs, check=True,
                )
            except subprocess.CalledProcessError:
                result.handoff_commands.append(
                    f"cd {change.path} && git push origin --delete {sub_feature}"
                )

    result.success = result.ff_done and result.pushed
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(repo_dir: str | None = None, feature_branch: str | None = None) -> int:
    """Sync all changed submodules. Returns 0 on full success, 1 on any failure."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fast-forward submodule main branches after parent merge",
    )
    parser.add_argument(
        "--repo-dir", default=repo_dir or ".",
        help="Path to the repository (default: current directory)",
    )
    parser.add_argument(
        "--feature-branch", default=feature_branch,
        help="Parent feature branch name (for submodule feature branch cleanup)",
    )
    args = parser.parse_args()

    repo = args.repo_dir
    changes = detect_changed_submodules(repo)

    if not changes:
        print("No submodule SHA changes detected; nothing to sync.")
        return 0

    print(f"Detected {len(changes)} changed submodule(s):", file=sys.stderr)
    for c in changes:
        print(f"  {c.path} → {c.new_sha[:12]}", file=sys.stderr)

    results: list[SyncResult] = []
    for change in changes:
        print(f"\nSyncing submodule: {change.path}", file=sys.stderr)
        r = sync_submodule(change, repo, args.feature_branch)
        results.append(r)

        if r.success:
            parts = [f"  ✓ {r.path}: ff={r.ff_done} pushed={r.pushed}"]
            if r.branch_deleted:
                parts.append("branch-deleted=true")
            print(" ".join(parts), file=sys.stderr)
        else:
            print(f"  ✗ {r.path}: {r.error}", file=sys.stderr)
            if r.handoff_commands:
                print("    Operator handoff — run manually:", file=sys.stderr)
                for cmd in r.handoff_commands:
                    print(f"      {cmd}", file=sys.stderr)

    failed = [r for r in results if not r.success]
    if failed:
        print(
            f"\n{len(failed)}/{len(results)} submodule(s) failed to sync fully.",
            file=sys.stderr,
        )
        return 1

    print(f"\nAll {len(results)} submodule(s) synced successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
