"""Deterministic goal-gate scorer — the core, LLM-free score.

Given a post-run :class:`WorkspaceState`, evaluate each :class:`GoalGate` to
pass/fail without any model in the loop. This is what makes a scenario result
reproducible and what the parity matrix is built on; the LLM judge is strictly
additive on top.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from .models import GateVerdict, GoalGate, GoalGatesBlock, WorkspaceState


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )


def _condition_met(gate: GoalGate, state: WorkspaceState) -> tuple[bool, str]:
    """Return (condition_holds, detail) for a gate, independent of mode.

    ``condition_holds`` is the raw truth of the outcome (e.g. "the file
    exists"); the caller applies verify/prohibit polarity.
    """
    root = Path(state.root)

    if gate.check == "file":
        target = root / gate.path if gate.path else None
        if target is None or not target.is_file():
            return False, f"file not found: {gate.path}"
        if gate.contains:
            body = target.read_text(encoding="utf-8", errors="replace")
            if re.search(gate.contains, body):
                return True, f"file {gate.path} matches /{gate.contains}/"
            return False, f"file {gate.path} present but does not match /{gate.contains}/"
        return True, f"file present: {gate.path}"

    if gate.check == "artifact":
        if gate.artifact_key:
            if gate.artifact_key in state.artifacts:
                return True, f"artifact present: {gate.artifact_key}"
            return False, f"artifact missing: {gate.artifact_key}"
        target = root / gate.path if gate.path else None
        if target is not None and target.exists():
            return True, f"artifact file present: {gate.path}"
        return False, f"artifact file missing: {gate.path}"

    if gate.check == "branch":
        proc = _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{gate.branch}")
        if proc.returncode == 0:
            return True, f"branch exists: {gate.branch}"
        return False, f"branch missing: {gate.branch}"

    if gate.check == "commit":
        # Count only commits created *after* the fixture's initial commit, so the
        # fixture's own "initial state" commit never satisfies a `min_count` gate
        # (a scenario with min_count=1 must require a real agent commit).
        rev_range = f"{state.base_sha}..HEAD" if state.base_sha else "HEAD"
        log = _git(root, "log", "--format=%H%x00%s", rev_range)
        if log.returncode != 0:
            return False, f"git log failed: {log.stderr.strip()}"
        lines = [ln for ln in log.stdout.split("\n") if ln]
        if gate.message_contains:
            matched = [
                ln for ln in lines if re.search(gate.message_contains, ln.split("\x00", 1)[-1])
            ]
            if matched:
                return True, f"{len(matched)} commit(s) match /{gate.message_contains}/"
            return False, f"no commit message matches /{gate.message_contains}/"
        if gate.min_count is not None:
            if len(lines) >= gate.min_count:
                return True, f"{len(lines)} commit(s) >= {gate.min_count}"
            return False, f"only {len(lines)} commit(s) < {gate.min_count}"
        if lines:
            return True, f"{len(lines)} commit(s) present"
        return False, "no commits present"

    if gate.check == "pr":
        pr = state.created_pr
        if pr is None:
            return False, "no PR created"
        if gate.pr_head and pr.head != gate.pr_head:
            return False, f"PR head {pr.head!r} != expected {gate.pr_head!r}"
        return True, f"PR created: {pr.url or pr.head or pr.number}"

    if gate.check == "command":
        assert gate.command is not None  # guarded by model validator
        proc = subprocess.run(
            _resolve_command(gate.command),
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        return _evaluate_command(gate, proc)

    return False, f"unknown check kind: {gate.check}"


def _resolve_command(command: list[str]) -> list[str]:
    """Make a command gate's interpreter deterministic.

    A leading bare ``python``/``python3`` resolves via ``PATH``, which differs
    across invocation contexts (system interpreter vs. the harness venv) and
    silently breaks the "deterministic scorer" guarantee — a correct outcome
    fails its ``test-passes`` gate only because the ambient ``python`` lacks the
    test deps. Pin such a leading token to ``sys.executable`` (the interpreter
    running the harness, which carries its dependencies) so the gate scores the
    workspace, not the caller's PATH. Non-Python commands pass through untouched.
    """
    if command and command[0] in ("python", "python3"):
        return [sys.executable, *command[1:]]
    return command


def _evaluate_command(gate: GoalGate, proc: subprocess.CompletedProcess[str]) -> tuple[bool, str]:
    """Score a ``command`` gate against its reused gen-eval ``ExpectBlock``."""
    expect = gate.expect
    combined = (proc.stdout or "") + (proc.stderr or "")
    if expect is None:
        # No assertions: success == exit code 0.
        return proc.returncode == 0, f"exit={proc.returncode}"
    if expect.exit_code is not None and proc.returncode != expect.exit_code:
        return False, f"exit {proc.returncode} != expected {expect.exit_code}"
    if expect.error_contains is not None and expect.error_contains not in combined:
        return False, f"output does not contain {expect.error_contains!r}"
    if expect.not_empty and not combined.strip():
        return False, "output was empty"
    return True, f"command ok (exit={proc.returncode})"


def score_gate(gate: GoalGate, state: WorkspaceState) -> GateVerdict:
    """Score a single goal gate against the post-run workspace state."""
    try:
        holds, detail = _condition_met(gate, state)
    except Exception as exc:  # defensive: scoring must never crash the runner
        return GateVerdict(
            gate_id=gate.id,
            check=gate.check,
            mode=gate.mode,
            status="error",
            detail=f"scorer error: {exc}",
        )

    if gate.mode == "verify":
        status = "pass" if holds else "fail"
    else:  # prohibit: pass when the (undesired) condition does NOT hold
        status = "pass" if not holds else "fail"
        detail = f"prohibited outcome {'absent' if not holds else 'PRESENT'}: {detail}"

    return GateVerdict(
        gate_id=gate.id,
        check=gate.check,
        mode=gate.mode,
        status=status,
        detail=detail,
    )


def score_gates(gates: GoalGatesBlock, state: WorkspaceState) -> list[GateVerdict]:
    """Score every gate in a scenario's goal-gate block."""
    return [score_gate(gate, state) for gate in gates.all_gates()]


def deterministic_status(verdicts: list[GateVerdict]) -> str:
    """Roll gate verdicts up to a single deterministic status.

    ``error`` if any gate errored, else ``fail`` if any gate failed, else
    ``pass``.
    """
    if any(v.status == "error" for v in verdicts):
        return "error"
    if any(v.status == "fail" for v in verdicts):
        return "fail"
    return "pass"
