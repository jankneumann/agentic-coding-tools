#!/usr/bin/env python3
"""Fail when a git diff mutates assertion / expect expectation bodies in tests.

Simplification commits must not change what tests assert. Characterization
commits that *add* new tests are fine; this checker focuses on modified lines
inside assertion/expect calls.

Usage:
    python3 check_test_contract.py --base <sha> [--head HEAD]
    python3 check_test_contract.py --base <sha> --json

Exit codes:
    0 — no expectation-body mutations detected
    2 — expectation bodies changed
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


# Paths that look like tests (path-based; language-agnostic)
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec)(/|$)|"
    r"(_test\.py$|\.test\.[jt]sx?$|\.spec\.[jt]sx?$|test_[^/]+\.py$)",
    re.IGNORECASE,
)

# Assertion-like call sites in common languages
ASSERT_LINE_RE = re.compile(
    r"""(?x)
    ^[+\-]\s*                                   # diff line marker + content start
    (?:
        assert(?:Equal|Equals|True|False|In|Is|IsNone|Raises|AlmostEqual)?\b
        | expect\s*\(
        | self\.assert\w+\s*\(
        | pytest\.raises\s*\(
        | should\s*\(
        | assertThat\s*\(
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


def scan_unified_diff(diff_text: str) -> tuple[list[Finding], list[str]]:
    """Scan a unified diff for assertion-body changes in test paths."""
    findings: list[Finding] = []
    test_files: list[str] = []
    current_path: str | None = None
    in_test_file = False

    for raw in diff_text.splitlines():
        if raw.startswith("+++ ") or raw.startswith("--- "):
            # --- a/path or +++ b/path
            marker, _, rest = raw.partition(" ")
            path = rest.strip()
            if path == "/dev/null":
                continue
            if path.startswith("a/") or path.startswith("b/"):
                path = path[2:]
            if marker.startswith("+++"):
                current_path = path
                in_test_file = is_test_path(path)
                if in_test_file and path not in test_files:
                    test_files.append(path)
            continue

        if not in_test_file or current_path is None:
            continue
        if raw.startswith("+++") or raw.startswith("---") or raw.startswith("@@"):
            continue
        # Only added/removed content lines (not ' ' context, not '\').
        if not (raw.startswith("+") or raw.startswith("-")):
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if ASSERT_LINE_RE.match(raw):
            findings.append(Finding(path=current_path, line=raw[:200]))

    return findings, test_files


def evaluate(repo: Path, base: str, head: str) -> ContractResult:
    diff_text = _run_git(["diff", f"{base}...{head}", "--unified=0"], repo)
    findings, test_files = scan_unified_diff(diff_text)
    return ContractResult(
        base=base,
        head=head,
        clean=len(findings) == 0,
        findings=findings,
        test_files_touched=test_files,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect assertion/expect body changes in test files (simplify contract)"
    )
    parser.add_argument("--base", required=True, help="Baseline git ref")
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
        payload = asdict(result)
        print(json.dumps(payload, indent=2))
    else:
        if result.clean:
            print(
                f"Test contract: OK\n"
                f"  range: {result.base}...{result.head}\n"
                f"  test files touched: {len(result.test_files_touched)}\n"
                f"  assertion-line mutations: 0"
            )
        else:
            print(
                f"Test contract: BROKEN — assertion/expect lines changed\n"
                f"  range: {result.base}...{result.head}\n"
                f"  findings: {len(result.findings)}",
                file=sys.stderr,
            )
            for f in result.findings[:30]:
                print(f"  {f.path}: {f.line}", file=sys.stderr)
            if len(result.findings) > 30:
                print(f"  ... and {len(result.findings) - 30} more", file=sys.stderr)
            print(
                "  action: revert expectation edits; if behavior must change, "
                "use a feature/fix workflow — not /simplify.",
                file=sys.stderr,
            )

    return 0 if result.clean else 2


if __name__ == "__main__":
    sys.exit(main())
