#!/usr/bin/env python3
"""Enforce simplify Rule of 500 / 5-file limit on a git diff range.

Usage:
    python3 check_scope.py --base <sha> [--head HEAD] [--allow-codemod]
    python3 check_scope.py --base <sha> --json

Exit codes:
    0 — within limits (or --allow-codemod with oversized diff)
    2 — over limit without --allow-codemod, or dirty tree with no measured diff
    1 — usage / git error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_MAX_LINES = 500
DEFAULT_MAX_FILES = 5


@dataclass
class ScopeResult:
    base: str
    head: str
    files_changed: int
    lines_changed: int
    max_files: int
    max_lines: int
    within_limit: bool
    allow_codemod: bool
    files: list[str]
    dirty_working_tree: bool = False
    included_working_tree: bool = False


def _run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed"
        )
    return proc.stdout


def working_tree_dirty(repo: Path) -> bool:
    return bool(_run_git(["status", "--porcelain"], repo).strip())


def _parse_numstat(numstat: str) -> tuple[int, list[str]]:
    files: list[str] = []
    lines = 0
    for row in numstat.splitlines():
        if not row.strip():
            continue
        parts = row.split("\t")
        if len(parts) < 3:
            continue
        added, removed, path = parts[0], parts[1], parts[2]
        # rename format: old => new — take last component after tab path field
        files.append(path)
        if added == "-" or removed == "-":
            lines += 1
            continue
        lines += int(added) + int(removed)
    return lines, files


def measure_scope(
    repo: Path,
    base: str,
    head: str,
    *,
    include_working_tree: bool,
) -> tuple[int, int, list[str]]:
    """Return (files_changed, lines_changed, file_list)."""
    if include_working_tree:
        # Working tree + index vs base tree (includes uncommitted tracked changes).
        name_out = _run_git(["diff", "--name-only", base], repo)
        numstat = _run_git(["diff", "--numstat", base], repo)
        # Untracked files (not in diff) still count toward surface area.
        untracked = _run_git(
            ["ls-files", "--others", "--exclude-standard"],
            repo,
        )
        files = [line for line in name_out.splitlines() if line.strip()]
        lines, _ = _parse_numstat(numstat)
        for path in untracked.splitlines():
            path = path.strip()
            if not path:
                continue
            if path not in files:
                files.append(path)
            # Count untracked file as at least 1 line of churn
            try:
                content = (repo / path).read_text(encoding="utf-8", errors="replace")
                lines += max(1, content.count("\n") + (0 if content.endswith("\n") else 1 if content else 1))
            except OSError:
                lines += 1
        return len(files), lines, files

    name_out = _run_git(["diff", "--name-only", f"{base}...{head}"], repo)
    files = [line for line in name_out.splitlines() if line.strip()]
    numstat = _run_git(["diff", "--numstat", f"{base}...{head}"], repo)
    lines, _ = _parse_numstat(numstat)
    return len(files), lines, files


def evaluate(
    repo: Path,
    base: str,
    head: str,
    allow_codemod: bool,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_lines: int = DEFAULT_MAX_LINES,
    allow_dirty: bool = False,
) -> ScopeResult:
    dirty = working_tree_dirty(repo)
    head_sha = _run_git(["rev-parse", head], repo).strip()
    live_sha = _run_git(["rev-parse", "HEAD"], repo).strip()
    head_is_live = head_sha == live_sha
    include_wt = head_is_live and dirty

    files_n, lines_n, files = measure_scope(
        repo, base, head, include_working_tree=include_wt
    )
    within = files_n <= max_files and lines_n <= max_lines

    # Silent-pass guard: dirty tree but zero measured churn is still a problem
    # (e.g. only ignored files) unless allow_dirty.
    if dirty and head_is_live and files_n == 0 and lines_n == 0 and not allow_dirty:
        within = False

    return ScopeResult(
        base=base,
        head=head,
        files_changed=files_n,
        lines_changed=lines_n,
        max_files=max_files,
        max_lines=max_lines,
        within_limit=within,
        allow_codemod=allow_codemod,
        files=files,
        dirty_working_tree=dirty,
        included_working_tree=include_wt,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rule of 500 / 5-file scope check for /simplify")
    parser.add_argument("--base", required=True, help="Baseline git ref (before simplify production edits)")
    parser.add_argument("--head", default="HEAD", help="End ref (default HEAD)")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument(
        "--allow-codemod",
        action="store_true",
        help="Permit oversized diffs when produced by a codemod / automation",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Do not treat dirty-with-zero-measured-churn as a failure",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON result on stdout")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Line budget (default {DEFAULT_MAX_LINES})",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_MAX_FILES,
        help=f"File budget (default {DEFAULT_MAX_FILES})",
    )
    args = parser.parse_args(argv)

    try:
        result = evaluate(
            args.repo.resolve(),
            args.base,
            args.head,
            args.allow_codemod,
            max_files=args.max_files,
            max_lines=args.max_lines,
            allow_dirty=args.allow_dirty,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        status = "OK" if result.within_limit else "OVER LIMIT / UNSAFE"
        print(
            f"Rule of 500 check: {status}\n"
            f"  range:  {result.base}...{result.head}\n"
            f"  files:  {result.files_changed} (max {result.max_files})\n"
            f"  lines:  {result.lines_changed} (max {result.max_lines})\n"
            f"  dirty:  {result.dirty_working_tree} "
            f"(included working tree: {result.included_working_tree})"
        )
        if not result.within_limit:
            print(
                "  action: split the PR, use a codemod, commit pending work, "
                "or re-run with --allow-codemod / --allow-dirty as appropriate.",
                file=sys.stderr,
            )

    if result.within_limit:
        return 0
    if args.allow_codemod and result.files_changed > 0:
        if not args.json:
            print("  note: --allow-codemod set; treating oversized diff as permitted.")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
