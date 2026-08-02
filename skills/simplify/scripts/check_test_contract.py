#!/usr/bin/env python3
"""Fail when a git diff mutates assertion / expect lines in test paths.

Simplification commits must not change what tests assert. Point ``--base`` at
the tip **after** any characterization commits (``test(...): pin behavior…``).
Within that range, any added/removed assertion-like line is a contract break —
including pure ``+assert`` additions and deleted test files.

When ``--head`` is the live tip and the working tree is dirty, uncommitted
tracked changes are included in the scan so expectation edits cannot pass by
remaining uncommitted.

Usage:
    python3 check_test_contract.py --base <post-characterization-sha> [--head HEAD]
    python3 check_test_contract.py --base <sha> --json

Exit codes:
    0 — no assertion-line mutations detected
    2 — assertion/expect lines changed (or test file deleted with asserts)
    1 — usage / git error
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec)(/|$)|"
    r"(_test\.py$|\.test\.[jt]sx?$|\.spec\.[jt]sx?$|test_[^/]+\.py$|"
    r"_test\.go$|_spec\.rb$|_test\.rs$)",
    re.IGNORECASE,
)

# Multi-language assertion / matcher heuristics (not fully language-agnostic).
ASSERT_LINE_RE = re.compile(
    r"""(?x)
    ^[+\-]\s*
    (?:
        assert_eq!\s*\(                         # Rust
        | assert_ne!\s*\(
        | assert_ok!\s*\(
        | assert_err!\s*\(
        | assert(?:equal|Equals|True|False|In|Is|IsNone|Raises|AlmostEqual)?\b
        | expect\s*\(
        | expect\w*\s*\(
        | self\.assert\w+\s*\(
        | pytest\.raises\s*\(
        | should\s*\(
        | assertThat\s*\(
        | EXPECT_\w+\s*\(
        | ASSERT_\w+\s*\(
        | t\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow|Logf)\s*\(
        | \.to(?:Be|Equal|Equal|StrictEqual|Match|Contain|Throw|HaveBeenCalled)\s*\(
        | \.to_(?:eq|equal|be|match|include)\b
    )
    """,
)


@dataclass
class Finding:
    path: str
    line: str


@dataclass
class ContractResult:
    base: str
    head: str
    clean: bool
    findings: list[Finding] = field(default_factory=list)
    test_files_touched: list[str] = field(default_factory=list)
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


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH_RE.search(path.replace("\\", "/")))


def _strip_diff_path(path: str) -> str | None:
    path = path.strip().strip('"').strip("'")
    if path == "/dev/null":
        return None
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    return path or None


def scan_unified_diff(diff_text: str) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    test_files: list[str] = []
    current_path: str | None = None
    in_test_file = False
    pending_old_path: str | None = None

    for raw in diff_text.splitlines():
        if raw.startswith("--- "):
            _, _, rest = raw.partition(" ")
            pending_old_path = _strip_diff_path(rest)
            continue

        if raw.startswith("+++ "):
            _, _, rest = raw.partition(" ")
            new_path = _strip_diff_path(rest)
            current_path = new_path if new_path is not None else pending_old_path
            in_test_file = bool(current_path and is_test_path(current_path))
            if in_test_file and current_path and current_path not in test_files:
                test_files.append(current_path)
            pending_old_path = None
            continue

        if not in_test_file or current_path is None:
            continue
        if raw.startswith("@@"):
            continue
        if not (raw.startswith("+") or raw.startswith("-")):
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if ASSERT_LINE_RE.match(raw):
            findings.append(Finding(path=current_path, line=raw[:200]))

    return findings, test_files


def evaluate(repo: Path, base: str, head: str) -> ContractResult:
    dirty = bool(_run_git(["status", "--porcelain"], repo).strip())
    head_sha = _run_git(["rev-parse", head], repo).strip()
    live_sha = _run_git(["rev-parse", "HEAD"], repo).strip()
    head_is_live = head_sha == live_sha
    include_wt = head_is_live and dirty

    if include_wt:
        # Working tree vs base (tracked changes).
        diff_text = _run_git(["diff", base, "--unified=0"], repo)
        staged = _run_git(["diff", "--cached", base, "--unified=0"], repo)
        if staged.strip():
            diff_text = f"{diff_text}\n{staged}"
    else:
        diff_text = _run_git(["diff", f"{base}...{head}", "--unified=0"], repo)

    findings, test_files = scan_unified_diff(diff_text)
    return ContractResult(
        base=base,
        head=head,
        clean=len(findings) == 0,
        findings=findings,
        test_files_touched=test_files,
        dirty_working_tree=dirty,
        included_working_tree=include_wt,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect assertion/expect body changes in test files (simplify contract)"
    )
    parser.add_argument("--base", required=True, help="Baseline git ref (after characterization)")
    parser.add_argument("--head", default="HEAD", help="End ref (default HEAD)")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    args = parser.parse_args(argv)

    try:
        result = evaluate(args.repo.resolve(), args.base, args.head)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        if result.clean:
            print(
                f"Test contract: OK\n"
                f"  range: {result.base}...{result.head}\n"
                f"  test files touched: {len(result.test_files_touched)}\n"
                f"  assertion-line mutations: 0\n"
                f"  dirty working tree: {result.dirty_working_tree} "
                f"(included: {result.included_working_tree})"
            )
        else:
            print(
                f"Test contract: BROKEN — assertion/expect lines changed\n"
                f"  range: {result.base}...{result.head}\n"
                f"  findings: {len(result.findings)}\n"
                f"  dirty working tree: {result.dirty_working_tree} "
                f"(included: {result.included_working_tree})",
                file=sys.stderr,
            )
            for f in result.findings[:30]:
                print(f"  {f.path}: {f.line}", file=sys.stderr)
            if len(result.findings) > 30:
                print(f"  ... and {len(result.findings) - 30} more", file=sys.stderr)
            print(
                "  action: set --base to the tip AFTER characterization commits; "
                "do not change assertion bodies in the simplify range. "
                "If behavior must change, use a feature/fix workflow — not /simplify.",
                file=sys.stderr,
            )

    return 0 if result.clean else 2


if __name__ == "__main__":
    sys.exit(main())
