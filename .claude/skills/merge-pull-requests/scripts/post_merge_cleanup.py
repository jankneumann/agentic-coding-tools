#!/usr/bin/env python3
"""Plan post-merge OpenSpec cleanup handoffs.

This helper is intentionally non-mutating. The merge-pull-requests skill uses
it after a merge pass to turn the list of PRs merged in that pass into an
operator approval prompt for `/cleanup-feature <change-id> --post-merge`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run_git(args: list[str], repo_dir: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _repo_root(repo_dir: Path | None = None) -> Path:
    cwd = repo_dir or Path.cwd()
    output = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if output:
        return Path(output)
    return cwd


def _load_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("merged", "merged_prs", "prs"):
            value = data.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    raise ValueError(
        "Expected a JSON list, or an object with merged/merged_prs/prs list.",
    )


def _load_registry(repo_dir: Path) -> list[dict[str, Any]]:
    registry_path = repo_dir / ".git-worktrees" / ".registry.json"
    if not registry_path.is_file():
        return []
    try:
        data = json.loads(registry_path.read_text())
    except json.JSONDecodeError:
        return []
    entries = data.get("entries", [])
    return entries if isinstance(entries, list) else []


def _local_branches(repo_dir: Path) -> list[str]:
    output = _run_git(
        ["for-each-ref", "--format=%(refname:short)", "refs/heads"],
        repo_dir,
    )
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _record_was_merged(record: dict[str, Any]) -> bool:
    if record.get("success") is True:
        return True
    status = str(record.get("status", "")).lower()
    action = str(record.get("action", "")).lower()
    return status == "merged" or action == "merged"


def _record_branch(record: dict[str, Any]) -> str:
    branch = record.get("branch")
    if isinstance(branch, str) and branch:
        return branch
    validation = record.get("validation")
    if isinstance(validation, dict):
        branch = validation.get("branch")
        if isinstance(branch, str):
            return branch
    return ""


def _matching_branches(
    branches: list[str], change_id: str, head_branch: str,
) -> list[str]:
    candidates = {f"openspec/{change_id}"}
    if head_branch:
        candidates.add(head_branch)
    prefixes = [f"openspec/{change_id}--"]
    if head_branch:
        prefixes.append(f"{head_branch}--")
    return sorted(
        branch for branch in branches
        if branch in candidates or any(branch.startswith(p) for p in prefixes)
    )


def plan_cleanup(
    records: list[dict[str, Any]], repo_dir: Path | None = None,
) -> list[dict[str, Any]]:
    root = _repo_root(repo_dir)
    registry = _load_registry(root)
    branches = _local_branches(root)
    candidates: list[dict[str, Any]] = []

    seen: set[str] = set()
    for record in records:
        if not _record_was_merged(record):
            continue
        if record.get("origin") != "openspec":
            continue
        change_id = record.get("change_id")
        if not isinstance(change_id, str) or not change_id.strip():
            continue
        change_id = change_id.strip()
        if change_id in seen:
            continue

        change_dir = root / "openspec" / "changes" / change_id
        if not change_dir.is_dir():
            continue

        head_branch = _record_branch(record)
        registry_entries = [
            entry for entry in registry
            if entry.get("change_id") == change_id
        ]
        local_branches = _matching_branches(branches, change_id, head_branch)
        pr_number = record.get("pr_number") or record.get("number")

        candidates.append({
            "pr_number": pr_number,
            "change_id": change_id,
            "head_branch": head_branch,
            "change_dir": str(change_dir.relative_to(root)),
            "registry_entries": registry_entries,
            "local_branches": local_branches,
            "command": (
                f"/cleanup-feature {change_id} --post-merge"
                + (f" --pr {pr_number}" if pr_number else "")
            ),
        })
        seen.add(change_id)

    return candidates


def render_prompt(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "No merged local OpenSpec PRs need post-merge cleanup."

    lines = [
        "Merged local OpenSpec PRs eligible for post-merge cleanup:",
        "",
        "| PR | Change ID | Branch | Local remnants | Command |",
        "|----|-----------|--------|----------------|---------|",
    ]
    for candidate in candidates:
        remnants: list[str] = []
        registry_count = len(candidate["registry_entries"])
        branch_count = len(candidate["local_branches"])
        if registry_count:
            noun = "entry" if registry_count == 1 else "entries"
            remnants.append(f"{registry_count} worktree registry {noun}")
        if branch_count:
            noun = "branch" if branch_count == 1 else "branches"
            remnants.append(f"{branch_count} local {noun}")
        if not remnants:
            remnants.append("OpenSpec change dir only")
        lines.append(
            "| #{pr} | {change} | {branch} | {remnants} | `{command}` |".format(
                pr=candidate.get("pr_number") or "-",
                change=candidate["change_id"],
                branch=candidate.get("head_branch") or "-",
                remnants=", ".join(remnants),
                command=candidate["command"],
            ),
        )
    lines.extend([
        "",
        "Ask the operator: Proceed with post-merge cleanup for these changes?",
        "Only run the listed cleanup commands after explicit approval.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan post-merge cleanup for merged OpenSpec PRs.",
    )
    parser.add_argument(
        "--merged-json",
        required=True,
        help="JSON file containing PRs merged during this merge-pull-requests pass.",
    )
    parser.add_argument(
        "--repo-dir",
        default=None,
        help="Repository root or working directory. Defaults to current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable cleanup candidates.",
    )
    args = parser.parse_args()

    try:
        records = _load_records(Path(args.merged_json))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error loading merged PR records: {exc}", file=sys.stderr)
        return 1

    candidates = plan_cleanup(
        records,
        repo_dir=Path(args.repo_dir) if args.repo_dir else None,
    )
    if args.json:
        print(json.dumps(candidates, indent=2))
    else:
        print(render_prompt(candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
