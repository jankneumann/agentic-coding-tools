#!/usr/bin/env python3
"""Dual-run a test command at baseline and HEAD; write a simplify report.

Usage:
    python3 verify_behavior_preservation.py \\
        --baseline <sha> \\
        --test-cmd 'pytest -q' \\
        [--head HEAD] \\
        [--report simplify-report.json] \\
        [--skip-baseline-run]   # only re-check HEAD if baseline already known green
        [--timeout SECONDS]

Exit codes:
    0 — both runs green (or baseline skipped and HEAD green)
    2 — one or both runs failed
    1 — usage / git / IO error

Notes:
    Both baseline and HEAD runs use ``git worktree add --detach`` into temporary
    directories so uncommitted working-tree dirt does not affect results.

    Common local toolchains (``.venv``, ``node_modules``) are **symlinked** from
    the main repo into each worktree when present, so commands like
    ``.venv/bin/python -m pytest -q`` still resolve.

    ``--test-cmd`` is executed with the shell (trusted operator command). Prefer
    project-local interpreter paths. Do not pass untrusted strings.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Toolchain dirs commonly gitignored but required to run tests.
_TOOLCHAIN_LINKS = (".venv", "node_modules", "skills/.venv", ".tox")


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
    dual_run_complete: bool = True


def _run(
    cmd: list[str] | str,
    cwd: Path,
    shell: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        shell=shell,
        timeout=timeout,
    )


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_tests(
    command: str,
    cwd: Path,
    ref_label: str,
    *,
    timeout: float | None = None,
) -> RunResult:
    try:
        proc = _run(command, cwd=cwd, shell=True, timeout=timeout)
        code = proc.returncode
        out, err = proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        code = 124
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        err = f"TIMEOUT after {timeout}s\n" + (
            (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        )
    return RunResult(
        ref=ref_label,
        command=command,
        exit_code=code,
        passed=code == 0,
        cwd=str(cwd),
        stdout_tail=_tail(out),
        stderr_tail=_tail(err),
    )


def resolve_sha(repo: Path, ref: str) -> str:
    proc = _run(["git", "rev-parse", ref], cwd=repo)
    if proc.returncode != 0:
        raise RuntimeError(f"Cannot resolve ref {ref!r}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _link_toolchains(repo: Path, worktree: Path) -> list[str]:
    """Symlink common ignored toolchain dirs from repo into worktree."""
    linked: list[str] = []
    for rel in _TOOLCHAIN_LINKS:
        src = repo / rel
        dst = worktree / rel
        if not src.exists():
            continue
        if dst.exists() or dst.is_symlink():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(src, dst, target_is_directory=src.is_dir())
            linked.append(rel)
        except OSError:
            continue
    return linked


def _run_in_detached_worktree(
    repo: Path,
    sha: str,
    test_cmd: str,
    *,
    timeout: float | None = None,
) -> tuple[RunResult, list[str]]:
    """Add a temporary detached worktree at sha, run tests, remove worktree."""
    tmp = Path(tempfile.mkdtemp(prefix="simplify-dual-run-"))
    notes: list[str] = []
    try:
        add = _run(
            ["git", "worktree", "add", "--detach", str(tmp), sha],
            cwd=repo,
        )
        if add.returncode != 0:
            raise RuntimeError(
                f"git worktree add failed for {sha[:12]}: "
                f"{add.stderr.strip() or add.stdout.strip()}"
            )
        linked = _link_toolchains(repo, tmp)
        if linked:
            notes.append(f"symlinked toolchain dirs for {sha[:12]}: {', '.join(linked)}")
        result = run_tests(test_cmd, tmp, sha, timeout=timeout)
        return result, notes
    finally:
        rm = _run(["git", "worktree", "remove", "--force", str(tmp)], cwd=repo)
        if rm.returncode != 0:
            _run(["git", "worktree", "prune"], cwd=repo)
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def dual_run(
    repo: Path,
    baseline: str,
    head: str,
    test_cmd: str,
    *,
    skip_baseline: bool = False,
    timeout: float | None = None,
) -> DualRunReport:
    baseline_sha = resolve_sha(repo, baseline)
    head_sha = resolve_sha(repo, head)
    notes: list[str] = [
        "runs use detached git worktrees so dirty working trees do not affect results",
        "test-cmd is shell-executed; treat as trusted operator input",
        "prefer project-local interpreter paths (e.g. .venv/bin/python -m pytest)",
    ]

    baseline_result: RunResult | None = None
    dual_complete = True
    if not skip_baseline:
        baseline_result, n1 = _run_in_detached_worktree(
            repo, baseline_sha, test_cmd, timeout=timeout
        )
        notes.extend(n1)
    else:
        dual_complete = False
        notes.append(
            "baseline run skipped (--skip-baseline-run); dual-run is incomplete "
            "— only HEAD was proven green"
        )

    head_result, n2 = _run_in_detached_worktree(
        repo, head_sha, test_cmd, timeout=timeout
    )
    notes.extend(n2)

    both = head_result.passed and (baseline_result is None or baseline_result.passed)
    if baseline_result is not None and not baseline_result.passed:
        notes.append(
            "baseline suite failed in detached worktree — confirm test-cmd uses an "
            "absolute interpreter / that .venv was symlinked; do not assume the "
            "suite is broken without checking the report tails"
        )
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
        dual_run_complete=dual_complete,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dual-run tests for /simplify-implementation behavior preservation")
    parser.add_argument("--baseline", required=True, help="Baseline git ref (pre-simplify production tip)")
    parser.add_argument("--head", default="HEAD", help="End ref (default HEAD)")
    parser.add_argument(
        "--test-cmd",
        required=True,
        help="Trusted shell command to run tests (prefer absolute venv path)",
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
        help="Only run tests at HEAD (dual-run incomplete; still exit 0 if HEAD green)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Optional per-run timeout in seconds (exit 124 on timeout)",
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
            timeout=args.timeout,
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
        f"  dual_run_complete: {report.dual_run_complete}\n"
        f"  report:   {report_path}"
    )
    for note in report.notes:
        print(f"  note: {note}")

    if args.json_stdout:
        print(json.dumps(asdict(report), indent=2))

    return 0 if report.both_passed else 2


if __name__ == "__main__":
    sys.exit(main())
