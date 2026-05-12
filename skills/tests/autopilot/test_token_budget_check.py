"""Tests for the per-phase token-budget CI gate.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Scenario: "Joined prompt token budget is enforced"
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import token_budget_check


_GATE = Path(__file__).resolve().parents[2] / "autopilot" / "scripts" / "token_budget_check.py"


def test_gate_passes_silently_under_60pct(capsys: pytest.CaptureFixture[str]) -> None:
    """All 7 phases under 60% of a 200K window (default state) → exit 0."""
    rc = token_budget_check.run(context_window_override=None)
    assert rc == 0
    captured = capsys.readouterr()
    # Every phase emits a line on stdout.
    for phase in token_budget_check._DISPATCHING_PHASES:
        assert phase in captured.out
    # No failure or warning lines on stderr.
    assert "FAILED" not in captured.err
    assert "WARN" not in captured.err


def test_gate_fails_when_window_below_threshold(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Force tiny window → all phases report fail → exit 1."""
    rc = token_budget_check.run(context_window_override=100)  # 100 tokens
    assert rc == 1
    captured = capsys.readouterr()
    assert "FAILED" in captured.err
    # Failure message identifies phase name + token count.
    assert any(phase in captured.err for phase in token_budget_check._DISPATCHING_PHASES)


def test_gate_warns_in_60_to_75_band(capsys: pytest.CaptureFixture[str]) -> None:
    """Force a window that puts at least one phase in 60-75% range → exit 0 + warn."""
    # Compute a window such that the largest phase lands in 60-75%.
    reports_baseline = [
        token_budget_check._evaluate_phase(p, context_window_override=200_000)
        for p in token_budget_check._DISPATCHING_PHASES
    ]
    max_tokens = max(r.estimated_tokens for r in reports_baseline)
    # Target ~70% by setting context = max_tokens / 0.70.
    window = int(max_tokens / 0.70)

    rc = token_budget_check.run(context_window_override=window)
    captured = capsys.readouterr()
    assert rc == 0
    assert "WARN" in captured.err


def test_gate_iterates_exactly_seven_phases(capsys: pytest.CaptureFixture[str]) -> None:
    token_budget_check.run(context_window_override=200_000)
    captured = capsys.readouterr()
    assert len(token_budget_check._DISPATCHING_PHASES) == 7
    # 7 phases ⇒ 7 stdout lines (one per phase).
    phase_lines = [ln for ln in captured.out.splitlines() if ln.startswith("phase=")]
    assert len(phase_lines) == 7


def test_gate_cli_runs(tmp_path: Path) -> None:
    """Sanity-check the script runs as a top-level CLI."""
    extra_path = ":".join(
        str(_GATE.parents[2] / sub) for sub in (
            "autopilot/scripts", "coordination-bridge/scripts", "session-log/scripts",
        )
    )
    import os
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = extra_path + (":" + existing if existing else "")

    proc = subprocess.run(
        [sys.executable, str(_GATE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "phase=" in proc.stdout


def test_gate_cli_failure_on_low_window(tmp_path: Path) -> None:
    extra_path = ":".join(
        str(_GATE.parents[2] / sub) for sub in (
            "autopilot/scripts", "coordination-bridge/scripts", "session-log/scripts",
        )
    )
    import os
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = extra_path + (":" + existing if existing else "")

    proc = subprocess.run(
        [sys.executable, str(_GATE), "--context-window", "100"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 1
    assert "FAILED" in proc.stderr
