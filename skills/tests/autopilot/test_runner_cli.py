"""CLI integration tests for `skills/autopilot/scripts/runner.py`.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Requirement: Sub-Agent Dispatch Protocol Helpers
      Scenario: build_phase_dispatch_kwargs returns dispatch-ready dict
Design decisions: D3 (CLI surface).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


_RUNNER = Path(__file__).resolve().parents[2] / "autopilot" / "scripts" / "runner.py"


def _seed_state(repo_root: Path, change_id: str, **overrides: Any) -> Path:
    change_dir = repo_root / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "schema_version": 3,
        "change_id": change_id,
        "current_phase": "IMPLEMENT",
        "iteration": 0,
        "total_iterations": 0,
        "max_phase_iterations": 3,
        "findings_trend": [],
        "blocking_findings": [],
        "vendor_availability": {},
        "packages_status": {},
        "package_authors": {},
        "implementation_strategy": {},
        "memory_ids": [],
        "handoff_ids": [],
        "last_handoff_id": None,
        "started_at": "2026-05-05T00:00:00+00:00",
        "phase_started_at": "2026-05-05T00:00:00+00:00",
        "previous_phase": None,
        "escalation_reason": None,
        "val_review_enabled": False,
        "cli_review_enabled": True,
        "error": None,
        "phase_archetype": None,
    }
    state.update(overrides)
    state_path = change_dir / "loop-state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    return state_path


def _run_cli(cwd: Path, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    # Make sibling skill scripts importable inside the subprocess (mirrors
    # conftest.py's sys.path injection for in-process tests).
    extra_path = ":".join(
        str(_RUNNER.parents[2] / sub) for sub in (
            "autopilot/scripts", "coordination-bridge/scripts", "session-log/scripts",
        )
    )
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = extra_path + (":" + existing if existing else "")
    return subprocess.run(
        [sys.executable, str(_RUNNER), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path


def test_runner_build_dispatch_emits_json(workspace: Path) -> None:
    _seed_state(workspace, "demo")

    # Force the bridge into "no coordinator" mode — null model/system_prompt.
    result = _run_cli(
        workspace, "build-dispatch", "--phase", "IMPLEMENT", "--change-id", "demo",
        env_extra={
            "COORDINATION_API_URL": "",  # disable bridge
            "AUTOPILOT_PHASE_MODEL_OVERRIDE": "",
        },
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout.strip())
    assert set(payload.keys()) >= {"prompt", "model", "system_prompt", "isolation", "archetype"}
    # IMPLEMENT phase enforces worktree isolation regardless of bridge.
    assert payload["isolation"] == "worktree"
    # No bridge → no model/system_prompt.
    assert payload["model"] is None
    assert payload["system_prompt"] is None
    assert payload["archetype"] is None


def test_runner_apply_outcome_updates_state(workspace: Path) -> None:
    state_path = _seed_state(workspace, "demo")
    # Pre-write a valid cache so apply-outcome propagates the archetype.
    cache = workspace / "openspec" / "changes" / "demo" / ".phase-resolution-cache.json"
    archetype = "implementer"
    checksum = hashlib.sha256(
        b"demo" + b"IMPLEMENT" + archetype.encode("utf-8")
    ).hexdigest()
    cache.write_text(json.dumps({
        "schema_version": 1,
        "change_id": "demo",
        "phase": "IMPLEMENT",
        "archetype": archetype,
        "checksum": checksum,
    }))

    result = _run_cli(
        workspace, "apply-outcome",
        "--change-id", "demo", "--phase", "IMPLEMENT",
        "--outcome", "continue", "--handoff-id", "h-cli",
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    state = json.loads(state_path.read_text())
    assert state["last_handoff_id"] == "h-cli"
    assert state["phase_archetype"] == "implementer"
    # Cache deleted.
    assert not cache.exists()


def test_runner_apply_then_invalid_transition_escalates_and_can_project(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The executable host path parks malformed phase outcomes durably."""
    state_path = _seed_state(
        workspace,
        "demo",
        current_phase="PLAN_REVIEW",
        total_iterations=6,
    )

    applied = _run_cli(
        workspace,
        "apply-outcome",
        "--change-id",
        "demo",
        "--phase",
        "PLAN_REVIEW",
        "--outcome",
        "not-a-review-outcome",
        "--handoff-id",
        "h-invalid-edge",
    )
    assert applied.returncode == 0, applied.stderr

    transitioned = _run_cli(
        workspace,
        "transition",
        "--change-id",
        "demo",
        "--outcome",
        "not-a-review-outcome",
    )
    assert transitioned.returncode == 0, transitioned.stderr
    assert "run parked in ESCALATE" in transitioned.stderr

    state = json.loads(state_path.read_text())
    assert state["current_phase"] == "ESCALATE"
    assert state["previous_phase"] == "PLAN_REVIEW"
    assert state["total_iterations"] == 7
    assert "not-a-review-outcome" in state["escalation_reason"]
    assert state["phase_history"][-1]["outcome"] == "transition_failed"

    # Exit zero makes the ordinary coordinated-host projection step executable;
    # prove that project-state reads the just-persisted ESCALATE generation.
    monkeypatch.chdir(workspace)
    import queue_projection
    import runner

    projected: list[tuple[str, int, str]] = []

    class _Adapter:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def __call__(self, state: Any, *, mode: str) -> dict[str, str]:
            projected.append((state.current_phase, state.total_iterations, mode))
            return {"status": "ok"}

    monkeypatch.setattr(queue_projection, "QueueProjectionAdapter", _Adapter)
    assert runner.main(
        [
            "project-state",
            "--change-id",
            "demo",
            "--mode",
            "submit",
            "--coordinator-url",
            "https://coordinator.test",
        ]
    ) == 0
    assert projected == [("ESCALATE", 7, "submit")]

def test_runner_transition_after_done_is_idempotent(workspace: Path) -> None:
    state_path = _seed_state(
        workspace, "demo", current_phase="DONE", total_iterations=12
    )
    before = state_path.read_bytes()

    result = _run_cli(
        workspace, "transition", "--change-id", "demo", "--outcome", "complete"
    )

    assert result.returncode == 0, result.stderr
    assert state_path.read_bytes() == before


def test_runner_escalate_after_done_is_idempotent(workspace: Path) -> None:
    state_path = _seed_state(
        workspace, "demo", current_phase="DONE", total_iterations=12
    )
    before = state_path.read_bytes()

    result = _run_cli(
        workspace,
        "escalate",
        "--change-id",
        "demo",
        "--reason",
        "late host failure",
    )

    assert result.returncode == 0, result.stderr
    assert state_path.read_bytes() == before


def test_runner_escalate_is_executable_after_apply_outcome_failure(
    workspace: Path,
) -> None:
    state_path = _seed_state(
        workspace,
        "demo",
        current_phase="PLAN_REVIEW",
        total_iterations=2,
    )
    handoff = workspace / "openspec/changes/demo/handoffs/h-mismatch.json"
    handoff.parent.mkdir(parents=True)
    handoff.write_text('{"phase": "VALIDATE"}\n')

    failed = _run_cli(
        workspace,
        "apply-outcome",
        "--change-id",
        "demo",
        "--phase",
        "VALIDATE",
        "--outcome",
        "failed",
        "--handoff-id",
        str(handoff),
    )
    assert failed.returncode != 0

    parked = _run_cli(
        workspace,
        "escalate",
        "--change-id",
        "demo",
        "--reason",
        f"apply-outcome failed; retained handoff {handoff}",
    )
    assert parked.returncode == 0, parked.stderr
    state = json.loads(state_path.read_text())
    assert state["current_phase"] == "ESCALATE"
    assert state["previous_phase"] == "PLAN_REVIEW"
    assert state["total_iterations"] == 3
    assert state["phase_history"][-1]["outcome"] == "host_escalate"
    assert handoff.exists()


def test_runner_rejects_traversal_change_id(workspace: Path) -> None:
    result = _run_cli(
        workspace, "build-dispatch", "--phase", "IMPLEMENT",
        "--change-id", "../../etc/passwd",
    )
    assert result.returncode != 0
    assert "invalid change_id" in (result.stderr + result.stdout)


def test_runner_help_lists_subcommands(workspace: Path) -> None:
    result = _run_cli(workspace, "--help")
    assert result.returncode == 0
    assert "build-dispatch" in result.stdout
    assert "apply-outcome" in result.stdout


# ---------------------------------------------------------------------------
# Console interviewer subcommands across the real process boundary
# (encode-autopilot-gates-and-goal-gate-in-code, D3)
# ---------------------------------------------------------------------------


def _pending_gate(change_id: str = "demo") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "change_id": change_id,
        "gate": "proposal_approval",
        "phase": "PLAN",
        "requested_at": "2026-08-30T00:00:00+00:00",
        "prompt": "Approve this OpenSpec proposal and begin implementation?",
        "context": {"proposal_path": "proposal.md", "approach": "exists"},
        "posture": {"disposition": "block", "posture_present": False},
        "edge": {"outcome": "exists", "target": "PLAN_ITERATE"},
    }


def test_runner_gate_check_prints_the_pending_request(workspace: Path) -> None:
    _seed_state(
        workspace, "demo", current_phase="PLAN", pending_gate=_pending_gate(),
    )

    result = _run_cli(workspace, "gate-check", "demo")

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert json.loads(result.stdout)["gate"] == "proposal_approval"


def test_runner_gate_check_exits_three_when_nothing_is_pending(
    workspace: Path,
) -> None:
    _seed_state(workspace, "demo", current_phase="PLAN", pending_gate=None)

    result = _run_cli(workspace, "gate-check", "demo")

    assert result.returncode == 3
    assert result.stdout.strip() == ""


def test_runner_gate_answer_applies_the_edge(workspace: Path) -> None:
    state_path = _seed_state(
        workspace, "demo", current_phase="PLAN", pending_gate=_pending_gate(),
    )

    result = _run_cli(
        workspace, "gate-answer", "demo",
        "--gate", "proposal_approval", "--decision", "approved",
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    state = json.loads(state_path.read_text())
    assert state["current_phase"] == "PLAN_ITERATE"
    assert state["pending_gate"] is None
    assert state["gate_decisions"][-1]["resolution"] == "console_approved"


def test_runner_gate_answer_rejects_an_unknown_gate_name(workspace: Path) -> None:
    """argparse choices come from the Gate enum, so a typo cannot be recorded."""
    _seed_state(workspace, "demo", current_phase="PLAN", pending_gate=_pending_gate())

    result = _run_cli(
        workspace, "gate-answer", "demo",
        "--gate", "propsal_aproval", "--decision", "approved",
    )

    assert result.returncode != 0


def test_runner_init_persists_host_options(workspace: Path) -> None:
    result = _run_cli(
        workspace,
        "init",
        "--change-id",
        "demo-options",
        "--force",
        "--val-review",
        "--no-review",
    )

    assert result.returncode == 0, result.stderr
    state_path = workspace / "openspec/changes/demo-options/loop-state.json"
    state = json.loads(state_path.read_text())
    assert state["force"] is True
    assert state["val_review_enabled"] is True
    assert state["cli_review_enabled"] is False
