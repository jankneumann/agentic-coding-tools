"""The console interviewer protocol: `runner.py gate-check` / `gate-answer`.

Spec: openspec/changes/encode-autopilot-gates-and-goal-gate-in-code/specs/
      skill-workflow/spec.md
      Requirement: "Console Interviewer Protocol"
Contracts: contracts/events/{gate-request,gate-decision}.schema.json
Design decisions: D3 (gate_pending is an outcome, the ask lives in the host),
                  D4 (console resolutions share the coordinator record shape).

The *ask* is host-executed — autopilot scripts may not drive a TTY or an LLM.
What these tests pin is the enforcement half: no phase moves without a recorded
ApprovalDecision, and a wrong or missing answer mutates nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import autopilot
import runner

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.trust_posture import Gate  # noqa: E402

_CONTRACTS = (
    Path(__file__).resolve().parents[3]
    / "openspec" / "changes" / "encode-autopilot-gates-and-goal-gate-in-code"
    / "contracts" / "events"
)


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A cwd whose openspec/changes/<id>/ layout the runner CLI resolves against."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def seed(
    workspace: Path,
    change_id: str = "demo",
    *,
    pending: dict[str, Any] | None = None,
    **overrides: Any,
) -> Path:
    change_dir = workspace / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "proposal.md").write_text(
        "---\ndeployable: false\n---\n\n# Proposal\n"
    )
    state = autopilot.LoopState(change_id=change_id, current_phase="PLAN")
    state.pending_gate = pending
    for key, value in overrides.items():
        setattr(state, key, value)
    state_path = change_dir / "loop-state.json"
    autopilot.save_state(state, state_path)
    return state_path


def pending_request(
    gate: Gate = Gate.PROPOSAL_APPROVAL,
    *,
    phase: str = "PLAN",
    edge: dict[str, str] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "change_id": "demo",
        "gate": gate.value,
        "phase": phase,
        "requested_at": "2026-08-30T00:00:00+00:00",
        "prompt": f"Approve {gate.value}?",
        "context": context if context is not None else {"proposal_path": "p.md"},
        "posture": {"disposition": "block", "posture_present": False},
        **({"edge": edge} if edge is not None else {}),
    }


def read_state(state_path: Path) -> dict[str, Any]:
    return json.loads(state_path.read_text())


# ---------------------------------------------------------------------------
# gate-check
# ---------------------------------------------------------------------------


def test_gate_check_prints_schema_valid_json_and_exits_zero(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import jsonschema

    request = pending_request(
        edge={"outcome": "exists", "target": "PLAN_ITERATE"},
    )
    seed(workspace, pending=request)

    rc = runner.main(["gate-check", "demo"])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == request
    schema = json.loads((_CONTRACTS / "gate-request.schema.json").read_text())
    jsonschema.validate(printed, schema)


def test_gate_check_exits_three_when_no_gate_is_pending(workspace: Path) -> None:
    """A distinct code so a host can branch without parsing stderr."""
    seed(workspace, pending=None)

    assert runner.main(["gate-check", "demo"]) == runner.EXIT_NO_PENDING_GATE


def test_gate_check_exits_three_when_there_is_no_loop_state(
    workspace: Path,
) -> None:
    assert runner.main(["gate-check", "demo"]) == runner.EXIT_NO_PENDING_GATE


# ---------------------------------------------------------------------------
# gate-answer — approved
# ---------------------------------------------------------------------------


def test_gate_answer_approved_records_clears_and_applies_the_edge(
    workspace: Path,
) -> None:
    import jsonschema

    state_path = seed(
        workspace,
        pending=pending_request(edge={"outcome": "exists", "target": "PLAN_ITERATE"}),
    )

    rc = runner.main([
        "gate-answer", "demo", "--gate", "proposal_approval", "--decision", "approved",
    ])

    assert rc == 0
    state = read_state(state_path)
    assert state["pending_gate"] is None
    assert state["current_phase"] == "PLAN_ITERATE"
    record = state["gate_decisions"][-1]
    assert record["resolution"] == "console_approved"
    assert record["outcome"] == "proceed"
    assert record["gate"] == "proposal_approval"
    schema = json.loads((_CONTRACTS / "gate-decision.schema.json").read_text())
    jsonschema.validate(record, schema)


def test_gate_answer_without_an_edge_records_but_does_not_transition(
    workspace: Path,
) -> None:
    """pr_creation authorizes work *inside* SUBMIT_PR; approving it moves nothing."""
    state_path = seed(
        workspace,
        current_phase="SUBMIT_PR",
        pending=pending_request(Gate.PR_CREATION, phase="SUBMIT_PR", context={}),
    )

    rc = runner.main([
        "gate-answer", "demo", "--gate", "pr_creation", "--decision", "approved",
    ])

    assert rc == 0
    state = read_state(state_path)
    assert state["current_phase"] == "SUBMIT_PR"
    assert state["pending_gate"] is None
    assert state["gate_decisions"][-1]["resolution"] == "console_approved"


def test_gate_answer_approving_merge_records_authorization(workspace: Path) -> None:
    state_path = seed(
        workspace,
        current_phase="SUBMIT_PR",
        pending=pending_request(
            Gate.MERGE,
            phase="SUBMIT_PR",
            edge={"outcome": "created", "target": "DONE"},
            context={"pr_url": "https://example.test/pr/7"},
        ),
    )

    rc = runner.main([
        "gate-answer", "demo", "--gate", "merge", "--decision", "approved",
    ])

    assert rc == 0
    state = read_state(state_path)
    # Merge is authorized, but the loop still owes DONE its evidence, so the
    # goal gate refuses and the run escalates rather than silently finishing.
    assert state["current_phase"] == "ESCALATE"
    assert state["goal_gate"]["evidence"]["merge_authorized"] is True
    assert state["goal_gate"]["evidence"]["pr_url"] == "https://example.test/pr/7"
    assert state["current_phase"] != "DONE"


def test_gate_answer_escalation_edge_populates_previous_phase(
    workspace: Path,
) -> None:
    """Approving an escalation gate must leave a resumable ESCALATE, not a bare one."""
    state_path = seed(
        workspace,
        current_phase="GATEKEEPER",
        pending=pending_request(
            Gate.GATEKEEPER_ESCALATION,
            phase="GATEKEEPER",
            edge={"outcome": "escalate", "target": "ESCALATE"},
            context={"gate_verdict": "escalate"},
        ),
    )

    rc = runner.main([
        "gate-answer", "demo",
        "--gate", "gatekeeper_escalation", "--decision", "approved",
    ])

    assert rc == 0
    state = read_state(state_path)
    assert state["current_phase"] == "ESCALATE"
    assert state["previous_phase"] == "GATEKEEPER"
    assert state["escalation_reason"]


# ---------------------------------------------------------------------------
# gate-answer — rejected
# ---------------------------------------------------------------------------


def test_gate_answer_rejected_enters_escalate_with_the_note(workspace: Path) -> None:
    state_path = seed(
        workspace,
        pending=pending_request(edge={"outcome": "exists", "target": "PLAN_ITERATE"}),
    )

    rc = runner.main([
        "gate-answer", "demo", "--gate", "proposal_approval",
        "--decision", "rejected", "--note", "scope too wide",
    ])

    assert rc == 0
    state = read_state(state_path)
    assert state["current_phase"] == "ESCALATE"
    assert "proposal_approval" in state["escalation_reason"]
    assert "scope too wide" in state["escalation_reason"]
    record = state["gate_decisions"][-1]
    assert record["resolution"] == "console_rejected"
    assert record["outcome"] == "blocked"
    assert record["note"] == "scope too wide"


# ---------------------------------------------------------------------------
# gate-answer — refusals mutate nothing
# ---------------------------------------------------------------------------


def test_mismatched_gate_answer_exits_two_and_mutates_nothing(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = seed(
        workspace,
        current_phase="SUBMIT_PR",
        pending=pending_request(Gate.MERGE, phase="SUBMIT_PR", context={}),
    )
    before = state_path.read_text()

    rc = runner.main([
        "gate-answer", "demo", "--gate", "proposal_approval", "--decision", "approved",
    ])

    assert rc == 2
    assert state_path.read_text() == before
    assert "merge" in capsys.readouterr().err


def test_gate_answer_with_no_pending_gate_exits_two(workspace: Path) -> None:
    state_path = seed(workspace, pending=None)
    before = state_path.read_text()

    rc = runner.main([
        "gate-answer", "demo", "--gate", "proposal_approval", "--decision", "approved",
    ])

    assert rc == 2
    assert state_path.read_text() == before


# ---------------------------------------------------------------------------
# apply-outcome is blocked while a gate is pending
# ---------------------------------------------------------------------------


def test_apply_outcome_refuses_while_a_gate_is_pending(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not an error — a stop. The escalation wrapper escalates on non-zero exits."""
    state_path = seed(
        workspace,
        current_phase="PLAN",
        pending=pending_request(),
    )
    before = state_path.read_text()

    rc = runner.main([
        "apply-outcome", "--change-id", "demo", "--phase", "PLAN",
        "--outcome", "exists", "--handoff-id", "h-1",
    ])

    assert rc == 0
    assert state_path.read_text() == before
    assert "proposal_approval" in capsys.readouterr().err


def test_apply_outcome_still_works_when_no_gate_is_pending(workspace: Path) -> None:
    state_path = seed(workspace, current_phase="PLAN", pending=None)

    rc = runner.main([
        "apply-outcome", "--change-id", "demo", "--phase", "PLAN",
        "--outcome", "exists", "--handoff-id", "h-1",
    ])

    assert rc == 0
    assert read_state(state_path)["last_handoff_id"] == "h-1"
