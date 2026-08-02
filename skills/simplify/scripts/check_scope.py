#!/usr/bin/env python3
"""Enforce simplify Rule of 500 / 5-file limit on a git diff range.

Usage:
    python3 check_scope.py --base <sha> [--head HEAD] [--allow-codemod]
    python3 check_scope.py --base <sha> --json

Exit codes:
    0 — within limits (or --allow-codemod with oversized diff)
    2 — over limit without --allow-codemod
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


def measure_scope(repo: Path, base: str, head: str) -> tuple[int, int, list[str]]:
    """Return (files_changed, lines_changed, file_list) for base...head."""
    name_out = _run_git(["diff", "--name-only", f"{base}...{head}"], repo)
    files = [line for line in name_out.splitlines() if line.strip()]
    numstat = _run_git(["diff", "--numstat", f"{base}...{head}"], repo)
    lines = 0
    for row in numstat.splitlines():
        if not row.strip():
            continue
        parts = row.split("\t")
        if len(parts) < 3:
            continue
        added, removed = parts[0], parts[1]
        if added == "-" or removed == "-":
            lines += 1
            continue
        lines += int(added) + int(removed)
    return len(files), lines, files


def evaluate(
    repo: Path,
    base: str,
    head: str,
    allow_codemod: bool,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> ScopeResult:
    files_n, lines_n, files = measure_scope(repo, base, head)
    within = files_n <= max_files and lines_n <= max_lines
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
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        status = "OK" if result.within_limit else "OVER LIMIT"
        print(
            f"Rule of 500 check: {status}\n"
            f"  range:  {result.base}...{result.head}\n"
            f"  files:  {result.files_changed} (max {result.max_files})\n"
            f"  lines:  {result.lines_changed} (max {result.max_lines})"
        )
        if not result.within_limit:
            print(
                "  action: split the PR, use a codemod, or re-run with --allow-codemod "
                "and name the automation in the simplify report.",
                file=sys.stderr,
            )

    if result.within_limit:
        return 0
    if args.allow_codemod:
        if not args.json:
            print("  note: --allow-codemod set; treating oversized diff as permitted.")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
