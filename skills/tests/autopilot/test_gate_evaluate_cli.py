"""`runner.py gate-check --gate` evaluates — the host-driven enforcement path.

Spec: openspec/changes/encode-autopilot-gates-and-goal-gate-in-code/specs/
      skill-workflow/spec.md
      Requirement: "Console Interviewer Protocol"
      Scenario: "An unattended run with an auto-everything posture reaches
                 SUBMIT_PR without interaction; with the default posture it
                 parks exactly where it does today"
Contracts: contracts/events/{gate-request,gate-decision}.schema.json
Design decisions: D1 (one evaluator seam), D3 (gate_pending is an outcome).

`run_loop` has no non-test callers: production autopilot is the model reading
SKILL.md and shelling to this CLI. So the seven `gates.evaluate(...)` call sites
inside the loop's phase handlers never fire on the real path, and a `gate-check`
that could only *report* a pending gate always said "nothing pending, continue".
These tests pin the evaluating half — the thing that makes `pending_gate` ever
get set outside a test.
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
from shared.approval_gate import ApprovalGate, CoordinatorUnavailable  # noqa: E402
from shared.trust_posture import Gate  # noqa: E402

_CONTRACTS = (
    Path(__file__).resolve().parents[3]
    / "openspec" / "schemas"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _SilentAudit:
    """The audit sink is not what these tests are about; keep it off the network."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, record: dict[str, Any]) -> bool:
        self.records.append(record)
        return True


class _UnreachableCoordinator:
    """Every call fails the way a down coordinator does — the fail-closed trigger."""

    def request_approval(self, **_kwargs: Any) -> str:
        raise CoordinatorUnavailable("coordinator is down")

    def push_notification(self, **_kwargs: Any) -> bool:
        raise CoordinatorUnavailable("coordinator is down")

    def check_approval(self, _approval_id: str) -> str:
        raise CoordinatorUnavailable("coordinator is down")


class _EvaluatorSpy:
    """Stands in for `_build_gate_evaluator`, recording how the CLI called it.

    Returns a REAL `ApprovalGate` reading the REAL posture file at the repo root
    the CLI passed it — only the coordinator transport and the audit sink are
    faked. So "which posture applies" and "what does that posture decide" stay
    production code; only the network is not.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, Path]] = []
        self.contexts: list[dict[str, Any]] = []

    def __call__(self, change_id: str, repo_root: Path) -> ApprovalGate:
        self.calls.append((change_id, Path(repo_root)))
        spy = self

        class _Gate(ApprovalGate):
            def evaluate(self, gate: Any, context: Any = None) -> Any:
                spy.contexts.append(dict(context or {}))
                return super().evaluate(gate, context)

        return _Gate(
            coordinator=_UnreachableCoordinator(),
            audit=_SilentAudit(),
            agent_id=f"autopilot:{change_id}",
            repo_root=str(repo_root),
            poll_interval_seconds=0.001,
        )


@pytest.fixture()
def evaluator(monkeypatch: pytest.MonkeyPatch) -> _EvaluatorSpy:
    spy = _EvaluatorSpy()
    monkeypatch.setattr(autopilot, "_build_gate_evaluator", spy)
    return spy


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
    state = autopilot.LoopState(change_id=change_id, current_phase="PLAN")
    state.pending_gate = pending
    for key, value in overrides.items():
        setattr(state, key, value)
    state_path = change_dir / "loop-state.json"
    autopilot.save_state(state, state_path)
    return state_path


def write_posture(workspace: Path, gates: dict[str, dict[str, Any]]) -> Path:
    lines = ["---", "schema_version: 1", "gates:"]
    for name, cfg in gates.items():
        lines.append(f"  {name}:")
        for key, value in cfg.items():
            lines.append(f"    {key}: {value}")
    lines += ["---", "", "# Trust posture (test fixture)", ""]
    path = workspace / "TRUST_POSTURE.md"
    path.write_text("\n".join(lines))
    return path


def read_state(state_path: Path) -> dict[str, Any]:
    return json.loads(state_path.read_text())


# ---------------------------------------------------------------------------
# PROCEED — exit 3, "nothing to ask, continue"
# ---------------------------------------------------------------------------


def test_auto_posture_records_a_decision_and_says_continue(
    workspace: Path, evaluator: _EvaluatorSpy, capsys: pytest.CaptureFixture[str]
) -> None:
    """The acceptance criterion's first half: auto-everything never parks."""
    import jsonschema

    state_path = seed(workspace)
    write_posture(workspace, {g.value: {"disposition": "auto"} for g in Gate})

    rc = runner.main(["gate-check", "demo", "--gate", "proposal_approval"])

    assert rc == runner.EXIT_NO_PENDING_GATE
    state = read_state(state_path)
    assert state["pending_gate"] is None, "an auto gate must not park the run"
    assert state["current_phase"] == "PLAN"
    record = state["gate_decisions"][-1]
    assert record["gate"] == "proposal_approval"
    assert record["resolution"] == "auto"
    assert record["outcome"] == "proceed"
    assert record["posture_present"] is True
    jsonschema.validate(
        record, json.loads((_CONTRACTS / "gate-decision.schema.json").read_text())
    )
    assert json.loads(capsys.readouterr().out) == record


# ---------------------------------------------------------------------------
# posture_block — exit 0, "ask the operator"
# ---------------------------------------------------------------------------


def test_absent_posture_parks_with_a_schema_valid_request(
    workspace: Path, evaluator: _EvaluatorSpy, capsys: pytest.CaptureFixture[str]
) -> None:
    """No TRUST_POSTURE.md is the fail-closed default: every gate blocks."""
    import jsonschema

    state_path = seed(workspace)
    assert not (workspace / "TRUST_POSTURE.md").exists()

    rc = runner.main(["gate-check", "demo", "--gate", "proposal_approval"])

    assert rc == 0
    state = read_state(state_path)
    pending = state["pending_gate"]
    assert pending is not None
    assert pending["gate"] == "proposal_approval"
    assert pending["change_id"] == "demo"
    assert pending["phase"] == "PLAN"
    assert pending["posture"] == {"disposition": "block", "posture_present": False}
    assert pending["prompt"].strip(), "the host renders this verbatim"
    jsonschema.validate(
        pending, json.loads((_CONTRACTS / "gate-request.schema.json").read_text())
    )
    assert state["gate_decisions"][-1]["resolution"] == "posture_block"
    # Parking is not escalating: the operator can still answer this one.
    assert state["current_phase"] == "PLAN"
    assert json.loads(capsys.readouterr().out) == pending


def test_the_printed_request_is_answerable_by_gate_answer(
    workspace: Path, evaluator: _EvaluatorSpy
) -> None:
    """The two halves of the protocol compose: what gate-check parks, gate-answer clears."""
    state_path = seed(workspace)

    assert runner.main(["gate-check", "demo", "--gate", "pr_creation"]) == 0
    rc = runner.main(
        ["gate-answer", "demo", "--gate", "pr_creation", "--decision", "approved"]
    )

    assert rc == 0
    state = read_state(state_path)
    assert state["pending_gate"] is None
    assert state["gate_decisions"][-1]["resolution"] == "console_approved"


# ---------------------------------------------------------------------------
# A pending gate outranks --gate
# ---------------------------------------------------------------------------


def test_a_pending_gate_is_printed_and_nothing_else_is_evaluated(
    workspace: Path, evaluator: _EvaluatorSpy, capsys: pytest.CaptureFixture[str]
) -> None:
    """An outstanding question is not silently replaced by a different one."""
    pending = {
        "schema_version": 1,
        "change_id": "demo",
        "gate": "merge",
        "phase": "SUBMIT_PR",
        "requested_at": "2026-08-30T00:00:00+00:00",
        "prompt": "Authorize merging this pull request?",
    }
    state_path = seed(workspace, pending=pending, current_phase="SUBMIT_PR")
    before = state_path.read_bytes()
    write_posture(workspace, {g.value: {"disposition": "auto"} for g in Gate})

    rc = runner.main(["gate-check", "demo", "--gate", "proposal_approval"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == pending
    assert evaluator.calls == [], "the pending gate must short-circuit evaluation"
    assert state_path.read_bytes() == before


# ---------------------------------------------------------------------------
# Non-posture_block BLOCKED — exit 4, "parked, stop"
# ---------------------------------------------------------------------------


def test_coordinator_unreachable_escalates_and_reports_parked(
    workspace: Path, evaluator: _EvaluatorSpy, capsys: pytest.CaptureFixture[str]
) -> None:
    """No console answer resolves an unreachable coordinator, so there is nothing to ask."""
    state_path = seed(workspace)
    write_posture(
        workspace,
        {
            "proposal_approval": {
                "disposition": "notify_with_timeout",
                "timeout_seconds": 1,
                "default_action": "block",
            }
        },
    )

    rc = runner.main(["gate-check", "demo", "--gate", "proposal_approval"])

    assert rc == runner.EXIT_GATE_PARKED
    assert rc != 0 and rc != runner.EXIT_NO_PENDING_GATE
    state = read_state(state_path)
    assert state["current_phase"] == "ESCALATE"
    assert state["previous_phase"] == "PLAN"
    assert "proposal_approval" in state["escalation_reason"]
    assert "coordinator_unreachable" in state["escalation_reason"]
    # Parked, not pending: a gate-answer would have nothing to answer.
    assert state["pending_gate"] is None
    record = state["gate_decisions"][-1]
    assert record["resolution"] == "coordinator_unreachable"
    assert record["outcome"] == "blocked"
    assert record["phase"] == "PLAN"
    assert json.loads(capsys.readouterr().out) == record


# ---------------------------------------------------------------------------
# Context threading
# ---------------------------------------------------------------------------


def test_context_pairs_reach_the_evaluator_and_the_request(
    workspace: Path, evaluator: _EvaluatorSpy
) -> None:
    state_path = seed(workspace)

    rc = runner.main([
        "gate-check", "demo", "--gate", "proposal_approval",
        "--context", "proposal_path=openspec/changes/demo/proposal.md",
        "--context", "approach=created",
    ])

    assert rc == 0
    assert evaluator.contexts == [
        {
            "proposal_path": "openspec/changes/demo/proposal.md",
            "approach": "created",
        }
    ]
    pending = read_state(state_path)["pending_gate"]
    assert pending["context"] == evaluator.contexts[0]


def test_context_values_may_contain_equals_signs(
    workspace: Path, evaluator: _EvaluatorSpy
) -> None:
    """A PR URL with a query string must not be truncated at its first `=`."""
    seed(workspace)

    rc = runner.main([
        "gate-check", "demo", "--gate", "merge",
        "--context", "pr_url=https://example.test/pr/1?tab=files",
    ])

    assert rc == 0
    assert evaluator.contexts[0]["pr_url"] == "https://example.test/pr/1?tab=files"


def test_a_malformed_context_pair_is_refused_before_anything_is_evaluated(
    workspace: Path, evaluator: _EvaluatorSpy
) -> None:
    state_path = seed(workspace)
    before = state_path.read_bytes()

    rc = runner.main(["gate-check", "demo", "--gate", "merge", "--context", "oops"])

    assert rc == 2
    assert evaluator.calls == []
    assert state_path.read_bytes() == before


# ---------------------------------------------------------------------------
# The unchanged half of the contract
# ---------------------------------------------------------------------------


def test_no_gate_and_nothing_pending_leaves_state_byte_for_byte(
    workspace: Path, evaluator: _EvaluatorSpy
) -> None:
    """The pre-existing `gate-check <id>` behaviour is untouched."""
    state_path = seed(workspace)
    before = state_path.read_bytes()

    assert runner.main(["gate-check", "demo"]) == runner.EXIT_NO_PENDING_GATE

    assert state_path.read_bytes() == before
    assert evaluator.calls == []


def test_evaluating_without_loop_state_is_refused_not_invented(
    workspace: Path, evaluator: _EvaluatorSpy
) -> None:
    """A decision with nowhere durable to be recorded is not a decision."""
    (workspace / "openspec" / "changes" / "demo").mkdir(parents=True)

    rc = runner.main(["gate-check", "demo", "--gate", "merge"])

    assert rc == 2
    assert evaluator.calls == []
    assert not (workspace / "openspec" / "changes" / "demo" / "loop-state.json").exists()


# ---------------------------------------------------------------------------
# It is the loop's own evaluator, not a second copy of the posture logic
# ---------------------------------------------------------------------------


def test_the_cli_uses_the_loops_own_default_evaluator_builder(
    workspace: Path, evaluator: _EvaluatorSpy
) -> None:
    """If the CLI grew its own posture logic, the two paths could disagree."""
    seed(workspace)

    runner.main(["gate-check", "demo", "--gate", "proposal_approval"])

    assert evaluator.calls == [("demo", workspace)]


@pytest.mark.parametrize("gate", list(Gate), ids=lambda g: g.value)
def test_every_gate_is_evaluable_from_the_cli(
    gate: Gate, workspace: Path, evaluator: _EvaluatorSpy
) -> None:
    """`--gate` accepts the enum, not a hand-maintained subset of it."""
    state_path = seed(workspace)

    rc = runner.main(["gate-check", "demo", "--gate", gate.value])

    assert rc == 0
    assert read_state(state_path)["pending_gate"]["gate"] == gate.value
