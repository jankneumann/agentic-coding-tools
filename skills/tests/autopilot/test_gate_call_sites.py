"""The autopilot gates exist in code, at the right sites, with the right context.

Spec: openspec/changes/encode-autopilot-gates-and-goal-gate-in-code/specs/
      skill-workflow/spec.md
      Requirements: "Autopilot Gate Call Sites", "Goal Gate at DONE"
Design decisions: D1 (injected seam), D2 (one site per gate), D3, D6.

The AST walk is the load-bearing test of this change. Behavioural tests prove
the seven gates fire on the right edges *today*; the AST walk is what makes
"no gate whose only enforcement is prose" a structural property — add a ninth
member to `Gate` without a call site and this file goes red.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import autopilot
from autopilot import GATE_PENDING, GatePending, GoalGateRefused, LoopState, run_loop

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.approval_gate import ApprovalDecision, Outcome, Resolution  # noqa: E402
from shared.trust_posture import Disposition, Gate  # noqa: E402

_AUTOPILOT_PY = Path(autopilot.__file__).resolve()
_ORCHESTRATOR_PY = (
    _AUTOPILOT_PY.parents[2] / "autopilot-roadmap" / "scripts" / "orchestrator.py"
)

# `replan_required` is the roadmap orchestrator's gate, not autopilot's (D2).
_ROADMAP_GATES = {Gate.REPLAN_REQUIRED}
_AUTOPILOT_GATES = [g for g in Gate if g not in _ROADMAP_GATES]


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def decision(
    gate: Gate,
    *,
    proceed: bool = True,
    resolution: Resolution | None = None,
    disposition: Disposition = Disposition.AUTO,
) -> ApprovalDecision:
    if resolution is None:
        resolution = Resolution.AUTO if proceed else Resolution.POSTURE_BLOCK
    return ApprovalDecision(
        gate=gate,
        outcome=Outcome.PROCEED if proceed else Outcome.BLOCKED,
        resolution=resolution,
        disposition=disposition,
        reason=f"test decision for {gate.value}",
        posture_present=True,
    )


@dataclass
class FakeGateEvaluator:
    """Scriptable evaluator: per-gate overrides on top of an auto default."""

    overrides: dict[Gate, ApprovalDecision] = field(default_factory=dict)
    default_proceed: bool = True
    calls: list[tuple[Gate, dict[str, Any]]] = field(default_factory=list)

    def evaluate(
        self, gate: Gate, context: dict[str, Any] | None = None
    ) -> ApprovalDecision:
        self.calls.append((gate, dict(context or {})))
        if gate in self.overrides:
            return self.overrides[gate]
        return decision(gate, proceed=self.default_proceed)

    def context_for(self, gate: Gate) -> dict[str, Any]:
        for called, ctx in self.calls:
            if called is gate:
                return ctx
        raise AssertionError(f"gate {gate.value} was never evaluated")

    @property
    def gates_called(self) -> list[Gate]:
        return [g for g, _ in self.calls]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PASSING_REPORT = (
    "# Validation Report\n\n"
    "## Spec Compliance\n\n**Status**: pass\n\n"
    "## Validation Review\n\n**Status**: pass\n"
)


def make_change_dir(tmp_path: Path, *, report: str | None = _PASSING_REPORT) -> Path:
    change_dir = tmp_path / "change"
    change_dir.mkdir(exist_ok=True)
    (change_dir / "proposal.md").write_text(
        "---\ndeployable: false\n---\n\n# Proposal\n"
    )
    if report is not None:
        (change_dir / "validation-report.md").write_text(report)
    return change_dir


def drive(
    tmp_path: Path,
    evaluator: FakeGateEvaluator,
    *,
    change_dir: Path | None = None,
    **kwargs: Any,
) -> LoopState:
    """Run the loop over a change whose phases all succeed."""
    change_dir = change_dir if change_dir is not None else make_change_dir(tmp_path)
    worktree = tmp_path / "wt"
    worktree.mkdir(exist_ok=True)
    kwargs.setdefault(
        "assess_complexity_fn",
        lambda **_kw: {"force_required": False, "val_review_enabled": False},
    )
    kwargs.setdefault(
        "converge_fn",
        lambda **_kw: {"converged": True, "findings_count": 0, "blocking_findings": []},
    )
    return run_loop(
        kwargs.pop("change_id", "gate-demo"),
        change_dir,
        worktree,
        state_path=kwargs.pop("state_path", tmp_path / "loop-state.json"),
        gate_evaluator=evaluator,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Structural: one evaluate(Gate.X) call site per gate
# ---------------------------------------------------------------------------


def _gate_call_sites(source_path: Path) -> dict[str, int]:
    """Count `…evaluate(Gate.<MEMBER>, …)` calls per gate member in a module."""
    tree = ast.parse(source_path.read_text(), filename=str(source_path))
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "evaluate"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if (
            isinstance(first, ast.Attribute)
            and isinstance(first.value, ast.Name)
            and first.value.id == "Gate"
        ):
            counts[first.attr] = counts.get(first.attr, 0) + 1
    return counts


@pytest.mark.parametrize("gate", _AUTOPILOT_GATES, ids=lambda g: g.value)
def test_every_autopilot_gate_has_exactly_one_call_site(gate: Gate) -> None:
    """Enumerated from `Gate`, not from a hardcoded list.

    A gate added to the enum with no call site fails here rather than shipping
    as a human checkpoint that only SKILL.md prose enforces.
    """
    counts = _gate_call_sites(_AUTOPILOT_PY)
    assert counts.get(gate.name, 0) == 1, (
        f"{gate.value} has {counts.get(gate.name, 0)} call sites in "
        f"{_AUTOPILOT_PY.name}; expected exactly one"
    )


def test_replan_required_is_not_autopilots_gate() -> None:
    """It belongs to autopilot-roadmap's orchestrator (D2), not to this loop."""
    counts = _gate_call_sites(_AUTOPILOT_PY)
    assert Gate.REPLAN_REQUIRED.name not in counts


@pytest.mark.skipif(
    not _ORCHESTRATOR_PY.exists(), reason="autopilot-roadmap orchestrator not present"
)
def test_replan_required_has_a_call_site_in_the_roadmap_orchestrator() -> None:
    counts = _gate_call_sites(_ORCHESTRATOR_PY)
    assert counts.get(Gate.REPLAN_REQUIRED.name, 0) == 1


def test_transition_stays_a_pure_state_outcome_function() -> None:
    """The gates live in handlers; `transition()` remains the centralised table."""
    source = ast.parse(_AUTOPILOT_PY.read_text())
    fn = next(
        n for n in source.body
        if isinstance(n, ast.FunctionDef) and n.name == "transition"
    )
    assert [a.arg for a in fn.args.args] == ["state", "outcome"]
    assert not _gate_call_sites_in_node(fn)


def _gate_call_sites_in_node(node: ast.AST) -> list[str]:
    found = []
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "evaluate"
        ):
            found.append(ast.dump(child.func))
    return found


# ---------------------------------------------------------------------------
# Behavioural: each gate fires at its D2 site with its documented context
# ---------------------------------------------------------------------------


def test_auto_evaluator_runs_the_happy_path_with_zero_gate_pending(
    tmp_path: Path,
) -> None:
    evaluator = FakeGateEvaluator()
    state = drive(tmp_path, evaluator)

    assert state.current_phase == "DONE"
    assert state.pending_gate is None
    assert evaluator.gates_called == [
        Gate.PROPOSAL_APPROVAL,
        Gate.PR_CREATION,
        Gate.MERGE,
    ]
    assert [d["resolution"] for d in state.gate_decisions] == ["auto", "auto", "auto"]


def test_proposal_approval_carries_the_proposal_path_and_approach(
    tmp_path: Path,
) -> None:
    evaluator = FakeGateEvaluator()
    change_dir = make_change_dir(tmp_path)
    drive(tmp_path, evaluator, change_dir=change_dir)

    ctx = evaluator.context_for(Gate.PROPOSAL_APPROVAL)
    assert ctx["proposal_path"] == str(change_dir / "proposal.md")
    assert ctx["approach"] == "exists"


def test_gatekeeper_escalation_gates_the_escalate_verdict(tmp_path: Path) -> None:
    evaluator = FakeGateEvaluator()
    state = drive(
        tmp_path,
        evaluator,
        gatekeeper_fn=lambda _s: "escalate",
        assess_complexity_fn=lambda **_kw: {
            "force_required": False,
            "signals": {"has_security_signal": True},
        },
        gate_check_fn=lambda _s: False,
    )

    ctx = evaluator.context_for(Gate.GATEKEEPER_ESCALATION)
    assert ctx["gate_verdict"] == "escalate"
    assert ctx["gate_signals"] == "has_security_signal"
    # PROCEED takes the edge that already existed: the loop escalates.
    assert state.current_phase == "ESCALATE"
    assert state.previous_phase == "GATEKEEPER"


def test_plan_review_convergence_failure_gates_max_iter(tmp_path: Path) -> None:
    evaluator = FakeGateEvaluator()
    state = drive(
        tmp_path,
        evaluator,
        converge_fn=lambda **_kw: {
            "converged": False, "findings_count": 2, "blocking_findings": [],
        },
        gate_check_fn=lambda _s: False,
    )

    ctx = evaluator.context_for(Gate.PLAN_REVIEW_CONVERGENCE_FAILURE)
    assert ctx["convergence_reason"] == "max_iter"
    assert ctx["rounds"] == state.max_phase_iterations
    assert state.current_phase == "ESCALATE"


def test_validation_failure_gates_the_val_fix_edge(tmp_path: Path) -> None:
    evaluator = FakeGateEvaluator()
    outcomes = iter(["failed", "passed"])
    state = drive(
        tmp_path, evaluator, validate_fn=lambda _s: next(outcomes),
    )

    ctx = evaluator.context_for(Gate.VALIDATION_FAILURE)
    assert ctx["outcome"] == "failed"
    assert "failing_section" in ctx
    # PROCEED takes the existing VALIDATE -> VAL_FIX edge and the run recovers.
    assert state.current_phase == "DONE"


def test_escalate_resume_is_a_gate_not_a_stub(tmp_path: Path) -> None:
    """Spec: on proceed the loop returns to previous_phase; on block it stays."""
    state_path = tmp_path / "loop-state.json"
    change_dir = make_change_dir(tmp_path)
    autopilot.save_state(
        LoopState(
            change_id="gate-demo",
            current_phase="ESCALATE",
            previous_phase="IMPLEMENT",
            escalation_reason="implementation stuck",
        ),
        state_path,
    )
    evaluator = FakeGateEvaluator()

    state = drive(tmp_path, evaluator, change_dir=change_dir, state_path=state_path)

    ctx = evaluator.context_for(Gate.ESCALATE_RESUME)
    assert ctx["previous_phase"] == "IMPLEMENT"
    assert ctx["escalation_reason"] == "implementation stuck"
    assert state.current_phase == "DONE"  # resumed through IMPLEMENT and finished


def test_escalate_resume_blocked_keeps_the_loop_in_escalate(tmp_path: Path) -> None:
    state_path = tmp_path / "loop-state.json"
    change_dir = make_change_dir(tmp_path)
    autopilot.save_state(
        LoopState(
            change_id="gate-demo",
            current_phase="ESCALATE",
            previous_phase="IMPLEMENT",
        ),
        state_path,
    )
    evaluator = FakeGateEvaluator(
        overrides={Gate.ESCALATE_RESUME: decision(Gate.ESCALATE_RESUME, proceed=False)}
    )

    state = drive(tmp_path, evaluator, change_dir=change_dir, state_path=state_path)

    assert state.current_phase == "ESCALATE"
    assert state.gate_decisions[-1]["gate"] == "escalate_resume"
    assert state.gate_decisions[-1]["outcome"] == "blocked"


def test_pr_creation_gate_runs_before_the_pr_is_created(tmp_path: Path) -> None:
    created: list[str] = []
    evaluator = FakeGateEvaluator(
        overrides={Gate.PR_CREATION: decision(Gate.PR_CREATION, proceed=False)}
    )

    state = drive(
        tmp_path,
        evaluator,
        submit_pr_fn=lambda s: created.append(s.change_id) or "created",
    )

    assert created == [], "a blocked pr_creation gate must leave no PR behind"
    assert state.current_phase == "SUBMIT_PR"
    assert state.pending_gate["gate"] == "pr_creation"
    ctx = evaluator.context_for(Gate.PR_CREATION)
    assert ctx["branch"] == "openspec/gate-demo"


def test_merge_gate_records_authorization_and_never_merges(tmp_path: Path) -> None:
    evaluator = FakeGateEvaluator()
    state = drive(tmp_path, evaluator)

    merge_records = [d for d in state.gate_decisions if d["gate"] == "merge"]
    assert len(merge_records) == 1
    assert merge_records[0]["merge_authorized"] is True
    assert state.goal_gate["evidence"]["merge_authorized"] is True
    # The authorization is all it does — there is no merge call site at all.
    assert "gh pr merge" not in _AUTOPILOT_PY.read_text()


# ---------------------------------------------------------------------------
# Persistence: the record lands on disk before the loop acts on it
# ---------------------------------------------------------------------------


def test_decision_is_persisted_before_the_transition_is_applied(
    tmp_path: Path,
) -> None:
    """The decision must survive a crash between "approved" and "phase moved"."""
    state_path = tmp_path / "loop-state.json"
    seen: list[dict[str, Any]] = []

    class CrashingEvaluator(FakeGateEvaluator):
        def evaluate(self, gate, context=None):
            if gate is Gate.PR_CREATION and state_path.exists():
                # Snapshot what disk knows at the moment of the *next* gate:
                # the previous gate's record must already be there.
                seen.append(json.loads(state_path.read_text()))
            return super().evaluate(gate, context)

    drive(tmp_path, CrashingEvaluator(), state_path=state_path)

    assert seen, "pr_creation gate never ran"
    on_disk = seen[0]
    assert on_disk["current_phase"] != "DONE"
    assert [d["gate"] for d in on_disk["gate_decisions"]] == ["proposal_approval"]


# ---------------------------------------------------------------------------
# gate_pending + the two _apply_transition enforcement checks (D3, D6)
# ---------------------------------------------------------------------------


def test_posture_block_sets_pending_gate_and_returns_gate_pending(
    tmp_path: Path,
) -> None:
    evaluator = FakeGateEvaluator(default_proceed=False)
    state_path = tmp_path / "loop-state.json"

    state = drive(tmp_path, evaluator, state_path=state_path)

    assert state.current_phase == "PLAN"
    pending = state.pending_gate
    assert pending["gate"] == "proposal_approval"
    assert pending["phase"] == "PLAN"
    assert pending["edge"] == {"outcome": "exists", "target": "PLAN_ITERATE"}
    assert pending["prompt"]
    # Persisted, not just in memory — the host reads it from disk.
    assert json.loads(state_path.read_text())["pending_gate"]["gate"] == (
        "proposal_approval"
    )


@pytest.mark.parametrize(
    "resolution",
    [
        Resolution.TIMEOUT_BLOCK,
        Resolution.REJECTED,
        Resolution.COORDINATOR_UNREACHABLE,
    ],
)
def test_notify_family_block_parks_like_escalate(
    tmp_path: Path, resolution: Resolution
) -> None:
    """A human WAS consulted (or could not be) — there is nothing to ask again."""
    evaluator = FakeGateEvaluator(
        overrides={
            Gate.PROPOSAL_APPROVAL: decision(
                Gate.PROPOSAL_APPROVAL,
                proceed=False,
                resolution=resolution,
                disposition=Disposition.NOTIFY_WITH_TIMEOUT,
            )
        }
    )

    state = drive(tmp_path, evaluator)

    assert state.current_phase == "PLAN"
    assert state.pending_gate is None
    assert state.gate_decisions[-1]["resolution"] == resolution.value


def test_apply_transition_raises_while_a_gate_is_pending() -> None:
    state = LoopState(
        change_id="demo",
        current_phase="PLAN",
        pending_gate={"gate": "proposal_approval"},
    )
    with pytest.raises(GatePending) as exc:
        autopilot._apply_transition(state, "exists")

    assert exc.value.gate == "proposal_approval"
    assert state.current_phase == "PLAN"


def test_run_loop_reports_a_pending_gate_and_does_not_advance(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "loop-state.json"
    change_dir = make_change_dir(tmp_path)
    autopilot.save_state(
        LoopState(
            change_id="gate-demo",
            current_phase="PLAN",
            pending_gate={"gate": "proposal_approval", "phase": "PLAN"},
        ),
        state_path,
    )
    events: list[tuple[str, str]] = []

    state = drive(
        tmp_path,
        FakeGateEvaluator(),
        change_dir=change_dir,
        state_path=state_path,
        status_fn=lambda _s, event, message, _u: events.append((event, message)),
    )

    assert state.current_phase == "PLAN"
    assert any(event == "gate.pending" for event, _ in events)
    assert any("proposal_approval" in message for _, message in events)


# ---------------------------------------------------------------------------
# Goal gate at DONE (D6)
# ---------------------------------------------------------------------------


def test_hand_edited_submit_pr_with_empty_history_never_reaches_done(
    tmp_path: Path,
) -> None:
    change_dir = make_change_dir(tmp_path)
    state_path = tmp_path / "loop-state.json"
    autopilot.save_state(
        LoopState(change_id="gate-demo", current_phase="SUBMIT_PR"), state_path,
    )

    state = drive(
        tmp_path, FakeGateEvaluator(), change_dir=change_dir, state_path=state_path,
        gate_check_fn=lambda _s: False,
    )

    assert state.current_phase == "ESCALATE"
    assert state.current_phase != "DONE"
    assert "no VALIDATE passed record" in (state.escalation_reason or "")
    assert state.goal_gate["verdict"] == "refused"


def test_failed_report_section_refuses_done_naming_the_section(
    tmp_path: Path,
) -> None:
    change_dir = make_change_dir(
        tmp_path,
        report=(
            "# Validation Report\n\n"
            "## Spec Compliance\n\n**Status**: fail\n"
        ),
    )

    state = drive(
        tmp_path, FakeGateEvaluator(), change_dir=change_dir,
        gate_check_fn=lambda _s: False,
    )

    assert state.current_phase == "ESCALATE"
    assert state.goal_gate["verdict"] == "refused"
    assert "Spec Compliance" in state.goal_gate["reason"]


def test_apply_transition_raises_goal_gate_refused_directly(tmp_path: Path) -> None:
    change_dir = make_change_dir(tmp_path)
    state = LoopState(change_id="gate-demo", current_phase="SUBMIT_PR")

    with pytest.raises(GoalGateRefused) as exc:
        autopilot._apply_transition(state, "created", change_dir=change_dir)

    assert exc.value.reason == "no VALIDATE passed record"
    assert state.current_phase == "SUBMIT_PR"


def test_abandoned_escalation_reaches_done_without_reading_the_report(
    tmp_path: Path,
) -> None:
    change_dir = make_change_dir(tmp_path, report=None)
    state = LoopState(
        change_id="gate-demo", current_phase="ESCALATE", previous_phase="IMPLEMENT",
    )

    autopilot._apply_transition(state, "abandoned", change_dir=change_dir)

    assert state.current_phase == "DONE"
    assert state.goal_gate == {"verdict": "abandoned"}


def test_stale_report_refuses_done(tmp_path: Path) -> None:
    """A report modified after this run's VALIDATE record belongs to another run."""
    import os

    change_dir = make_change_dir(tmp_path)
    state = LoopState(
        change_id="gate-demo",
        current_phase="SUBMIT_PR",
        phase_history=[{
            "phase": "VALIDATE",
            "outcome": "passed",
            "at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }],
    )
    report = change_dir / "validation-report.md"
    now = datetime.now(timezone.utc).timestamp()
    os.utime(report, (now, now))

    with pytest.raises(GoalGateRefused) as exc:
        autopilot._apply_transition(state, "created", change_dir=change_dir)

    assert exc.value.reason == "validate record predates report"


def test_passing_evidence_reaches_done_with_a_passed_verdict(tmp_path: Path) -> None:
    state = drive(tmp_path, FakeGateEvaluator())

    assert state.current_phase == "DONE"
    assert state.goal_gate["verdict"] == "passed"


def test_gate_pending_is_not_a_transition_outcome() -> None:
    """`gate_pending` parks; it must never be reachable as a table edge."""
    for table in autopilot.TRANSITIONS.values():
        assert GATE_PENDING not in table
        assert GATE_PENDING not in table.values()


def test_pending_gate_produced_by_the_loop_validates_against_the_contract(
    tmp_path: Path,
) -> None:
    """The GateRequest the loop writes is the one the host's schema expects."""
    import jsonschema

    contracts = (
        Path(__file__).resolve().parents[3]
        / "openspec" / "changes" / "encode-autopilot-gates-and-goal-gate-in-code"
        / "contracts" / "events"
    )
    schema = json.loads((contracts / "gate-request.schema.json").read_text())
    decision_schema = json.loads((contracts / "gate-decision.schema.json").read_text())

    state = drive(tmp_path, FakeGateEvaluator(default_proceed=False))

    jsonschema.validate(state.pending_gate, schema)
    for record in state.gate_decisions:
        jsonschema.validate(record, decision_schema)


def test_every_recorded_decision_validates_on_the_happy_path(tmp_path: Path) -> None:
    import jsonschema

    contracts = (
        Path(__file__).resolve().parents[3]
        / "openspec" / "changes" / "encode-autopilot-gates-and-goal-gate-in-code"
        / "contracts" / "events"
    )
    schema = json.loads((contracts / "gate-decision.schema.json").read_text())

    state = drive(tmp_path, FakeGateEvaluator())

    assert state.gate_decisions
    for record in state.gate_decisions:
        jsonschema.validate(record, schema)
