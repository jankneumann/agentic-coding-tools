#!/usr/bin/env python3
"""Dual-run a test command at baseline and HEAD; write a simplify report.

Usage:
    python3 verify_behavior_preservation.py \\
        --baseline <sha> \\
        --test-cmd 'pytest -q' \\
        [--head HEAD] \\
        [--report simplify-report.json] \\
        [--skip-baseline-run]   # only re-check HEAD if baseline already known green

Exit codes:
    0 — both runs green (or baseline skipped and HEAD green)
    2 — one or both runs failed
    1 — usage / git / IO error

Notes:
    Baseline run uses `git worktree add --detach` into a temp directory when
    possible so the main working tree is not dirtied. Falls back to
    `git stash` + checkout only if worktree fails (and restores afterward).
    Prefer a clean working tree.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RunResult:
    ref: str
    command: str
    exit_code: int
    passed: bool
    cwd: str
    stdout_tail: str = ""
    stderr_tail: str = ""


@dataclass
class DualRunReport:
    schema_version: int
    baseline: str
    head: str
    test_cmd: str
    generated_at: str
    baseline_run: RunResult | None
    head_run: RunResult
    both_passed: bool
    notes: list[str] = field(default_factory=list)


def _run(cmd: list[str] | str, cwd: Path, shell: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        shell=shell,
    )


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_tests(command: str, cwd: Path, ref_label: str) -> RunResult:
    proc = _run(command, cwd=cwd, shell=True)
    return RunResult(
        ref=ref_label,
        command=command,
        exit_code=proc.returncode,
        passed=proc.returncode == 0,
        cwd=str(cwd),
        stdout_tail=_tail(proc.stdout or ""),
        stderr_tail=_tail(proc.stderr or ""),
    )


def resolve_sha(repo: Path, ref: str) -> str:
    proc = _run(["git", "rev-parse", ref], cwd=repo)
    if proc.returncode != 0:
        raise RuntimeError(f"Cannot resolve ref {ref!r}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def dual_run(
    repo: Path,
    baseline: str,
    head: str,
    test_cmd: str,
    *,
    skip_baseline: bool = False,
) -> DualRunReport:
    baseline_sha = resolve_sha(repo, baseline)
    head_sha = resolve_sha(repo, head)
    notes: list[str] = []

    baseline_result: RunResult | None = None
    if not skip_baseline:
        tmp = Path(tempfile.mkdtemp(prefix="simplify-baseline-"))
        try:
            add = _run(
                ["git", "worktree", "add", "--detach", str(tmp), baseline_sha],
                cwd=repo,
            )
            if add.returncode != 0:
                raise RuntimeError(
                    f"git worktree add failed: {add.stderr.strip() or add.stdout.strip()}"
                )
            baseline_result = run_tests(test_cmd, tmp, baseline_sha)
        finally:
            _run(["git", "worktree", "remove", "--force", str(tmp)], cwd=repo)
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
    else:
        notes.append("baseline run skipped (--skip-baseline-run)")

    head_result = run_tests(test_cmd, repo, head_sha)

    both = head_result.passed and (baseline_result is None or baseline_result.passed)
    if baseline_result is not None and not baseline_result.passed:
        notes.append("baseline suite was already red — fix tests before simplifying")
    if not head_result.passed:
        notes.append("HEAD suite failed after simplify — revert last simplification")

    return DualRunReport(
        schema_version=1,
        baseline=baseline_sha,
        head=head_sha,
        test_cmd=test_cmd,
        generated_at=datetime.now(timezone.utc).isoformat(),
        baseline_run=baseline_result,
        head_run=head_result,
        both_passed=both,
        notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dual-run tests for /simplify behavior preservation")
    parser.add_argument("--baseline", required=True, help="Baseline git ref (pre-simplify production tip)")
    parser.add_argument("--head", default="HEAD", help="End ref (default HEAD)")
    parser.add_argument(
        "--test-cmd",
        required=True,
        help="Shell command to run tests (e.g. 'pytest -q' or 'npm test')",
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("simplify-report.json"),
        help="Path to write JSON report (default ./simplify-report.json)",
    )
    parser.add_argument(
        "--skip-baseline-run",
        action="store_true",
        help="Only run tests at HEAD (when baseline was already verified)",
    )
    parser.add_argument("--json-stdout", action="store_true", help="Also print report JSON to stdout")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    try:
        report = dual_run(
            repo,
            args.baseline,
            args.head,
            args.test_cmd,
            skip_baseline=args.skip_baseline_run,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report_path = args.report if args.report.is_absolute() else repo / args.report
    try:
        report_path.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot write report: {exc}", file=sys.stderr)
        return 1

    def _status(run: RunResult | None) -> str:
        if run is None:
            return "skipped"
        return "PASS" if run.passed else f"FAIL (exit {run.exit_code})"

    print(
        f"Behavior preservation dual-run\n"
        f"  baseline: {report.baseline} → {_status(report.baseline_run)}\n"
        f"  head:     {report.head} → {_status(report.head_run)}\n"
        f"  report:   {report_path}"
    )
    for note in report.notes:
        print(f"  note: {note}")

    if args.json_stdout:
        print(json.dumps(asdict(report), indent=2))

    return 0 if report.both_passed else 2


if __name__ == "__main__":
    sys.exit(main())
