"""End-to-end: a real TRUST_POSTURE.md file drives the real loop.

Spec: openspec/changes/encode-autopilot-gates-and-goal-gate-in-code/specs/
      skill-workflow/spec.md
      Scenarios: "Auto posture reaches SUBMIT_PR without interaction",
                 "Default posture parks at the same points as today",
                 "Coordinator unreachable during notify parks the loop"
Design decisions: D1, D3.

Unlike test_gate_call_sites.py (which scripts an evaluator), these tests use the
real `ApprovalGate` reading a real posture file. Only the coordinator transport
and the audit sink are faked — everything from "what does the file say" to
"where does the loop stop" is production code.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

import autopilot
from autopilot import run_loop

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.approval_gate import ApprovalGate, CoordinatorUnavailable  # noqa: E402
from shared.trust_posture import Gate  # noqa: E402

# The gates a happy-path run actually reaches. The other four wrap failure edges
# (gatekeeper escalation, convergence failure, validation failure, escalate
# resume) and correctly never fire when nothing fails.
_HAPPY_PATH_GATES = ["proposal_approval", "pr_creation", "merge"]

_PASSING_REPORT = (
    "# Validation Report\n\n"
    "## Spec Compliance\n\n**Status**: pass\n"
)


class RecordingAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, record: dict[str, Any]) -> bool:
        self.records.append(record)
        return True


class UnreachableCoordinator:
    """Every call fails the way a down coordinator does — the fail-closed trigger."""

    def request_approval(self, **_kwargs: Any) -> str:
        raise CoordinatorUnavailable("coordinator is down")

    def push_notification(self, **_kwargs: Any) -> bool:
        raise CoordinatorUnavailable("coordinator is down")

    def check_approval(self, _approval_id: str) -> str:
        raise CoordinatorUnavailable("coordinator is down")


def write_posture(worktree: Path, gates: dict[str, dict[str, Any]]) -> Path:
    lines = ["---", "schema_version: 1", "gates:"]
    for name, cfg in gates.items():
        lines.append(f"  {name}:")
        for key, value in cfg.items():
            lines.append(f"    {key}: {value}")
    lines += ["---", "", "# Trust posture (test fixture)", ""]
    path = worktree / "TRUST_POSTURE.md"
    path.write_text("\n".join(lines))
    return path


def all_auto() -> dict[str, dict[str, Any]]:
    return {gate.value: {"disposition": "auto"} for gate in Gate}


@pytest.fixture()
def scene(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A change dir with DONE evidence, a worktree, and a fake transport."""
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text(
        "---\ndeployable: false\n---\n\n# Proposal\n"
    )
    (change_dir / "validation-report.md").write_text(_PASSING_REPORT)
    worktree = tmp_path / "wt"
    worktree.mkdir()

    audit = RecordingAudit()
    coordinator = UnreachableCoordinator()

    def build(change_id: str, repo_root: Path) -> ApprovalGate:
        # The real gate service, reading the real posture file at repo_root —
        # only the transport and the sink are substituted.
        return ApprovalGate(
            coordinator=coordinator,
            audit=audit,
            agent_id=f"autopilot:{change_id}",
            repo_root=str(repo_root),
        )

    monkeypatch.setattr(autopilot, "_build_gate_evaluator", build)
    return {
        "change_dir": change_dir,
        "worktree": worktree,
        "state_path": tmp_path / "loop-state.json",
        "audit": audit,
    }


def drive(scene: dict[str, Any], **kwargs: Any) -> autopilot.LoopState:
    return run_loop(
        "e2e-demo",
        scene["change_dir"],
        scene["worktree"],
        state_path=scene["state_path"],
        assess_complexity_fn=lambda **_kw: {
            "force_required": False, "val_review_enabled": False,
        },
        converge_fn=lambda **_kw: {
            "converged": True, "findings_count": 0, "blocking_findings": [],
        },
        **kwargs,
    )


# ---------------------------------------------------------------------------


def test_all_auto_posture_runs_through_submit_pr_without_interaction(
    scene: dict[str, Any],
) -> None:
    write_posture(scene["worktree"], all_auto())

    state = drive(scene)

    assert state.current_phase == "DONE"
    assert state.pending_gate is None
    assert [d["gate"] for d in state.gate_decisions] == _HAPPY_PATH_GATES
    assert {d["resolution"] for d in state.gate_decisions} == {"auto"}
    assert all(d["posture_present"] for d in state.gate_decisions)
    # SUBMIT_PR was genuinely reached and authorized, not skipped.
    assert state.goal_gate["evidence"]["merge_authorized"] is True
    # Every decision reached the audit sink too, not just loop state.
    assert [r["gate"] for r in scene["audit"].records] == _HAPPY_PATH_GATES


def test_absent_posture_parks_at_plan_on_proposal_approval(
    scene: dict[str, Any],
) -> None:
    """No TRUST_POSTURE.md is the fail-closed default — the ri-04 contract."""
    assert not (scene["worktree"] / "TRUST_POSTURE.md").exists()

    state = drive(scene)

    assert state.current_phase == "PLAN"
    assert state.pending_gate is not None
    assert state.pending_gate["gate"] == "proposal_approval"
    assert state.pending_gate["posture"]["posture_present"] is False
    assert state.gate_decisions[-1]["resolution"] == "posture_block"


def test_coordinator_unreachable_during_notify_parks_at_submit_pr(
    scene: dict[str, Any],
) -> None:
    posture = all_auto()
    posture["merge"] = {
        "disposition": "notify_with_timeout",
        "timeout_seconds": 60,
        "default_action": "proceed",
    }
    write_posture(scene["worktree"], posture)

    state = drive(scene)

    assert state.current_phase == "SUBMIT_PR"
    assert state.current_phase != "DONE"
    # A down coordinator is not a decision — it parks, and it does NOT raise a
    # console question, because nobody could be asked.
    assert state.pending_gate is None
    merge_record = state.gate_decisions[-1]
    assert merge_record["gate"] == "merge"
    assert merge_record["outcome"] == "blocked"
    assert merge_record["resolution"] == "coordinator_unreachable"


def test_the_default_evaluator_is_built_lazily_and_only_once(
    scene: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1: importing/starting autopilot must never require a coordinator."""
    write_posture(scene["worktree"], all_auto())
    builds: list[str] = []
    real_build = autopilot._build_gate_evaluator

    def counting_build(change_id: str, repo_root: Path) -> Any:
        builds.append(change_id)
        return real_build(change_id, repo_root)

    monkeypatch.setattr(autopilot, "_build_gate_evaluator", counting_build)

    # A run that never reaches a gate builds nothing.
    autopilot.save_state(
        autopilot.LoopState(change_id="e2e-demo", current_phase="DONE"),
        scene["state_path"],
    )
    drive(scene)
    assert builds == []

    scene["state_path"].unlink()
    drive(scene)
    assert builds == ["e2e-demo"], "the default evaluator must be built once, on demand"
