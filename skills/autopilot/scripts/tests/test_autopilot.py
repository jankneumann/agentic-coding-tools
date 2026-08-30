"""Tests for the autopilot state machine conductor.

All tests use mocks — no real file I/O or external dependencies.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure the scripts directory is importable
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from autopilot import (
    LoopState,
    check_escalation_resolved,
    enter_escalate,
    load_state,
    run_loop,
    save_state,
    transition,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.approval_gate import ApprovalDecision, Outcome, Resolution  # noqa: E402
from shared.trust_posture import Disposition, Gate  # noqa: E402


# ---------------------------------------------------------------------------
# Gate seam test doubles
#
# The tests in this module exercise the PHASE MACHINERY (transition table,
# escalation, convergence, callbacks), not the trust-posture gates — those have
# their own suites under skills/tests/autopilot/test_gate_*.py. Production
# defaults to a fail-closed evaluator (no TRUST_POSTURE.md => every gate blocks),
# which would park each of these runs at its first gate and tell us nothing about
# the machinery. So they inject a double instead of weakening the default.
#
# The double is deliberately NOT all-auto: escalate_resume blocks, mirroring the
# pre-gate `check_escalation_resolved` stub that returned False. An all-auto
# escalate_resume would make ESCALATE self-resolving and turn every "the loop
# parks at ESCALATE" test into an infinite resume loop.
# ---------------------------------------------------------------------------


class MachineryGateEvaluator:
    """Auto-approves every gate except escalate_resume, which parks."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def evaluate(self, gate: Gate, context: dict | None = None) -> ApprovalDecision:
        self.calls.append((gate.value, dict(context or {})))
        if gate is Gate.ESCALATE_RESUME:
            return ApprovalDecision(
                gate=gate,
                outcome=Outcome.BLOCKED,
                resolution=Resolution.POSTURE_BLOCK,
                disposition=Disposition.BLOCK,
                reason="escalation not resolved",
                posture_present=False,
            )
        return ApprovalDecision(
            gate=gate,
            outcome=Outcome.PROCEED,
            resolution=Resolution.AUTO,
            disposition=Disposition.AUTO,
            reason="auto",
            posture_present=True,
        )


@pytest.fixture(autouse=True)
def machinery_gates(monkeypatch: pytest.MonkeyPatch) -> MachineryGateEvaluator:
    """Inject the machinery double wherever this module's runs build a default.

    Patches the lazy default *builder*, not the fail-closed posture logic, so
    production still defaults to block.
    """
    evaluator = MachineryGateEvaluator()
    monkeypatch.setattr(
        "autopilot._build_gate_evaluator", lambda change_id, repo_root: evaluator
    )
    return evaluator


_PASSING_REPORT = (
    "# Validation Report\n\n"
    "## Spec Compliance\n\n**Status**: pass\n\n"
    "## Validation Review\n\n**Status**: pass\n"
)


def make_change_dir(tmp_path: Path, *, evidence: bool = True) -> Path:
    """An OpenSpec change dir carrying the evidence the goal gate needs for DONE.

    Reaching DONE now requires a passing validation report plus a VALIDATE
    history entry that postdates it (design D5), so a run that wants to finish
    has to supply the artifact. `deployable: false` keeps the required-section
    set deterministic instead of deriving it from git.
    """
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text(
        "---\ndeployable: false\n---\n\n# Proposal\n"
    )
    if evidence:
        (change_dir / "validation-report.md").write_text(_PASSING_REPORT)
    return change_dir

# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def test_state_save_load_roundtrip(tmp_path: Path) -> None:
    """save_state then load_state produces an identical LoopState."""
    state = LoopState(
        change_id="test-123",
        current_phase="IMPLEMENT",
        iteration=2,
        total_iterations=7,
        findings_trend=[5, 3, 1],
        blocking_findings=[{"id": "F1", "severity": "high"}],
        val_review_enabled=True,
        previous_phase="PLAN_REVIEW",
        escalation_reason="stuck",
    )
    path = tmp_path / "state.json"
    save_state(state, path)
    loaded = load_state(path)
    assert asdict(loaded) == asdict(state)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_initial_state_defaults() -> None:
    """A fresh LoopState has the expected default values."""
    state = LoopState()
    assert state.schema_version == 5  # bumped 4->5 by the trust-posture gate fields
    assert state.change_id == ""
    assert state.current_phase == "INIT"
    assert state.iteration == 0
    assert state.total_iterations == 0
    assert state.max_phase_iterations == 3
    assert state.findings_trend == []
    assert state.blocking_findings == []
    assert state.vendor_availability == {}
    assert state.packages_status == {}
    assert state.package_authors == {}
    assert state.implementation_strategy == {}
    assert state.memory_ids == []
    assert state.handoff_ids == []
    assert state.started_at == ""
    assert state.phase_started_at == ""
    assert state.previous_phase is None
    assert state.escalation_reason is None
    assert state.val_review_enabled is False
    assert state.error is None
    # v5 gate fields default empty — never to an invented decision.
    assert state.gate_decisions == []
    assert state.pending_gate is None
    assert state.goal_gate is None


# ---------------------------------------------------------------------------
# Transition function
# ---------------------------------------------------------------------------


def test_transition_init_to_gatekeeper() -> None:
    """INIT -> GATEKEEPER by default (judge evaluates verifiability/risk)."""
    state = LoopState(current_phase="INIT")
    assert transition(state, "next") == "GATEKEEPER"


def test_transition_init_to_plan_with_force() -> None:
    """--force skips the judge: INIT -> PLAN directly."""
    state = LoopState(current_phase="INIT", force=True)
    assert transition(state, "next") == "PLAN"


def test_transition_gatekeeper_proceed() -> None:
    state = LoopState(current_phase="GATEKEEPER")
    assert transition(state, "proceed") == "PLAN"
    assert transition(state, "proceed_with_review") == "PLAN"


def test_transition_gatekeeper_escalate() -> None:
    state = LoopState(current_phase="GATEKEEPER")
    assert transition(state, "escalate") == "ESCALATE"


def test_transition_plan_to_plan_iterate() -> None:
    """PLAN -> PLAN_ITERATE (always, regardless of cli_review_enabled)."""
    state = LoopState(current_phase="PLAN")
    assert transition(state, "exists") == "PLAN_ITERATE"
    assert transition(state, "created") == "PLAN_ITERATE"


def test_transition_plan_iterate_to_plan_review_cli() -> None:
    """PLAN_ITERATE -> PLAN_REVIEW when cli_review_enabled=True."""
    state = LoopState(current_phase="PLAN_ITERATE", cli_review_enabled=True)
    assert transition(state, "complete") == "PLAN_REVIEW"


def test_transition_plan_iterate_to_implement_no_cli() -> None:
    """PLAN_ITERATE -> IMPLEMENT when cli_review_enabled=False."""
    state = LoopState(current_phase="PLAN_ITERATE", cli_review_enabled=False)
    assert transition(state, "complete") == "IMPLEMENT"


def test_transition_plan_iterate_failed() -> None:
    state = LoopState(current_phase="PLAN_ITERATE")
    assert transition(state, "failed") == "ESCALATE"


def test_transition_plan_review_converged() -> None:
    state = LoopState(current_phase="PLAN_REVIEW")
    assert transition(state, "converged") == "IMPLEMENT"


def test_transition_plan_review_not_converged() -> None:
    state = LoopState(current_phase="PLAN_REVIEW")
    assert transition(state, "not_converged") == "PLAN_FIX"


def test_transition_plan_review_max_iter() -> None:
    state = LoopState(current_phase="PLAN_REVIEW")
    assert transition(state, "max_iter") == "ESCALATE"


def test_transition_implement_to_impl_iterate() -> None:
    """IMPLEMENT -> IMPL_ITERATE (always)."""
    state = LoopState(current_phase="IMPLEMENT")
    assert transition(state, "complete") == "IMPL_ITERATE"


def test_transition_impl_iterate_to_impl_review_cli() -> None:
    """IMPL_ITERATE -> IMPL_REVIEW when cli_review_enabled=True."""
    state = LoopState(current_phase="IMPL_ITERATE", cli_review_enabled=True)
    assert transition(state, "complete") == "IMPL_REVIEW"


def test_transition_impl_iterate_to_validate_no_cli() -> None:
    """IMPL_ITERATE -> VALIDATE when cli_review_enabled=False."""
    state = LoopState(current_phase="IMPL_ITERATE", cli_review_enabled=False)
    assert transition(state, "complete") == "VALIDATE"


def test_transition_impl_iterate_failed() -> None:
    state = LoopState(current_phase="IMPL_ITERATE")
    assert transition(state, "failed") == "ESCALATE"


def test_transition_validate_to_submit_pr() -> None:
    """VALIDATE + passed with val_review_enabled=False -> SUBMIT_PR."""
    state = LoopState(current_phase="VALIDATE", val_review_enabled=False)
    assert transition(state, "passed") == "SUBMIT_PR"


def test_transition_validate_to_val_review() -> None:
    """VALIDATE + passed with val_review_enabled=True -> VAL_REVIEW."""
    state = LoopState(current_phase="VALIDATE", val_review_enabled=True)
    assert transition(state, "passed") == "VAL_REVIEW"


def test_transition_invalid_outcome() -> None:
    state = LoopState(current_phase="INIT")
    with pytest.raises(ValueError, match="Invalid outcome"):
        transition(state, "bogus")


def test_transition_invalid_phase() -> None:
    state = LoopState(current_phase="NONEXISTENT")
    with pytest.raises(ValueError, match="No transitions defined"):
        transition(state, "next")


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


def test_escalate_sets_previous_phase() -> None:
    state = LoopState(current_phase="IMPL_REVIEW")
    enter_escalate(state, "review stuck")
    assert state.current_phase == "ESCALATE"
    assert state.previous_phase == "IMPL_REVIEW"
    assert state.escalation_reason == "review stuck"


def test_escalate_resolved_returns_to_previous() -> None:
    """ESCALATE + resolved with previous_phase=IMPL_REVIEW -> IMPL_REVIEW."""
    state = LoopState(current_phase="ESCALATE", previous_phase="IMPL_REVIEW")
    assert transition(state, "resolved") == "IMPL_REVIEW"


def test_escalate_resolved_no_previous_raises() -> None:
    state = LoopState(current_phase="ESCALATE", previous_phase=None)
    with pytest.raises(ValueError, match="previous_phase is None"):
        transition(state, "resolved")


def test_check_escalation_resolved_default_false() -> None:
    state = LoopState(current_phase="ESCALATE")
    assert check_escalation_resolved(state) is False


def test_check_escalation_resolved_with_callback() -> None:
    state = LoopState(current_phase="ESCALATE")
    assert check_escalation_resolved(state, lambda s: True) is True


# ---------------------------------------------------------------------------
# run_loop — resume from saved state
# ---------------------------------------------------------------------------


def test_resume_from_saved_state(tmp_path: Path) -> None:
    """Load state from file, run_loop continues from saved phase."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    state = LoopState(
        change_id="resume-1",
        current_phase="SUBMIT_PR",
        total_iterations=10,
        # Resuming straight into SUBMIT_PR skips VALIDATE, so the evidence the
        # goal gate needs has to come from the earlier run that produced it.
        phase_history=[{
            "phase": "VALIDATE",
            "outcome": "passed",
            "at": datetime.now(timezone.utc).isoformat(),
        }],
    )
    state_path = tmp_path / "state.json"
    save_state(state, state_path)

    result = run_loop(
        "resume-1",
        change_dir,
        wt,
        state_path=state_path,
    )
    assert result.current_phase == "DONE"
    assert result.total_iterations == 11  # one transition: SUBMIT_PR -> DONE


# ---------------------------------------------------------------------------
# Full happy path
# ---------------------------------------------------------------------------


def test_full_happy_path(tmp_path: Path) -> None:
    """Mock all callbacks — run from INIT to DONE without findings."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    # Complexity gate: no force_required, val_review disabled
    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})

    # Convergence: always converges immediately
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "happy-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
    )

    assert result.current_phase == "DONE"
    assert result.error is None
    # Phases: INIT->PLAN->PLAN_ITERATE->PLAN_REVIEW->IMPLEMENT->IMPL_ITERATE->IMPL_REVIEW->VALIDATE->SUBMIT_PR->DONE
    assert result.total_iterations >= 9


def test_full_happy_path_no_cli_review(tmp_path: Path) -> None:
    """With cli_review_enabled=False, review phases are skipped."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})

    # Convergence should NOT be called when cli_review_enabled=False
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "no-review-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
        cli_review_enabled=False,
    )

    assert result.current_phase == "DONE"
    assert result.error is None
    assert result.cli_review_enabled is False
    # Phases: INIT->PLAN->PLAN_ITERATE->IMPLEMENT->IMPL_ITERATE->VALIDATE->SUBMIT_PR->DONE
    assert result.total_iterations >= 7
    # Convergence should not have been called (no review phases)
    converge_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Plan review fix loop
# ---------------------------------------------------------------------------


def test_plan_review_fix_loop(tmp_path: Path) -> None:
    """Convergence fails round 1, succeeds round 2."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    # First call: not converged; second call: converged (PLAN_REVIEW)
    # Third call: converged (IMPL_REVIEW)
    converge_results = iter([
        {"converged": False, "findings_count": 3, "blocking_findings": [{"id": "F1"}]},
        {"converged": True, "findings_count": 0, "blocking_findings": []},
        # For IMPL_REVIEW
        {"converged": True, "findings_count": 0, "blocking_findings": []},
    ])
    converge_mock = MagicMock(side_effect=lambda **kw: next(converge_results))
    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})

    result = run_loop(
        "fix-loop-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
    )

    assert result.current_phase == "DONE"
    # Should have gone through PLAN_ITERATE -> PLAN_REVIEW -> PLAN_FIX -> PLAN_REVIEW -> IMPLEMENT ...
    assert 3 in result.findings_trend or len(result.findings_trend) >= 1


# ---------------------------------------------------------------------------
# Complexity gate
# ---------------------------------------------------------------------------


def test_complexity_gate_blocks(tmp_path: Path) -> None:
    """assess_complexity returns force_required -> ESCALATE."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": True})

    result = run_loop(
        "complex-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
    )

    assert result.current_phase == "ESCALATE"
    assert "force_required" in (result.escalation_reason or "")


# ---------------------------------------------------------------------------
# GATEKEEPER judge gate
# ---------------------------------------------------------------------------


def test_gatekeeper_escalate_stops_loop(tmp_path: Path) -> None:
    """A judge verdict of 'escalate' halts the loop at ESCALATE."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": False, "signals": {}})
    gatekeeper_mock = MagicMock(return_value="escalate")

    result = run_loop(
        "gate-esc-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        gatekeeper_fn=gatekeeper_mock,
    )

    assert result.current_phase == "ESCALATE"
    assert result.gate_verdict == "escalate"
    # Escalation context must be preserved so the resolve-and-resume path works.
    assert result.previous_phase == "GATEKEEPER"
    assert result.escalation_reason is not None
    gatekeeper_mock.assert_called_once()


def test_force_bypasses_scope_safety_floor_in_init(tmp_path: Path) -> None:
    """--force overrides the deterministic scope-safety floor at INIT."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    # Gate reports a broad-write-scope block, but --force should override it.
    assess_mock = MagicMock(return_value={
        "force_required": True,
        "signals": {"has_broad_write_scope": True},
        "warnings": ["Broad write scope detected; require --force"],
    })
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "force-floor-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
        force=True,
    )

    assert result.current_phase == "DONE"
    assert result.error is None
    # assess_complexity must receive force=True so its own decision stays consistent.
    assert assess_mock.call_args.kwargs.get("force") is True


def test_gatekeeper_proceed_with_review_enables_val_review(tmp_path: Path) -> None:
    """'proceed_with_review' flips val_review_enabled and continues to DONE."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": False, "signals": {}})
    gatekeeper_mock = MagicMock(return_value="proceed_with_review")
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "gate-rev-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        gatekeeper_fn=gatekeeper_mock,
        converge_fn=converge_mock,
    )

    assert result.current_phase == "DONE"
    assert result.gate_verdict == "proceed_with_review"
    assert result.val_review_enabled is True


def test_gatekeeper_permissive_fallback_without_judge(tmp_path: Path) -> None:
    """No gatekeeper_fn -> permissive verdict derived from signals."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    # Risk signal present -> fallback should enable validation review.
    assess_mock = MagicMock(return_value={
        "force_required": False,
        "signals": {"has_security_signal": True},
    })
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "gate-fb-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
    )

    assert result.current_phase == "DONE"
    assert result.gate_verdict == "proceed_with_review"
    assert result.val_review_enabled is True


def test_force_skips_gatekeeper(tmp_path: Path) -> None:
    """--force bypasses the judge entirely (it is never called)."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": False, "signals": {}})
    gatekeeper_mock = MagicMock(return_value="escalate")
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "gate-force-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        gatekeeper_fn=gatekeeper_mock,
        converge_fn=converge_mock,
        force=True,
    )

    assert result.current_phase == "DONE"
    gatekeeper_mock.assert_not_called()


def test_iterate_callbacks_called(tmp_path: Path) -> None:
    """iterate_plan_fn and iterate_impl_fn are called in the loop."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })
    iterate_plan_mock = MagicMock(return_value="complete")
    iterate_impl_mock = MagicMock(return_value="complete")

    result = run_loop(
        "iterate-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
        iterate_plan_fn=iterate_plan_mock,
        iterate_impl_fn=iterate_impl_mock,
    )

    assert result.current_phase == "DONE"
    iterate_plan_mock.assert_called_once()
    iterate_impl_mock.assert_called_once()


def test_iterate_plan_failure_escalates(tmp_path: Path) -> None:
    """iterate_plan_fn returning 'failed' leads to ESCALATE."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={"force_required": False, "val_review_enabled": False})
    iterate_plan_mock = MagicMock(return_value="failed")

    result = run_loop(
        "iterate-fail-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        iterate_plan_fn=iterate_plan_mock,
    )

    assert result.current_phase == "ESCALATE"


def test_cli_review_enabled_persisted(tmp_path: Path) -> None:
    """cli_review_enabled is saved/loaded in state."""
    state = LoopState(
        change_id="cli-1",
        current_phase="PLAN_ITERATE",
        cli_review_enabled=False,
    )
    path = tmp_path / "state.json"
    save_state(state, path)
    loaded = load_state(path)
    assert loaded.cli_review_enabled is False


def test_complexity_gate_enables_val_review(tmp_path: Path) -> None:
    """assess_complexity with val_review_enabled -> state reflects it."""
    change_dir = make_change_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()

    assess_mock = MagicMock(return_value={
        "force_required": False,
        "val_review_enabled": True,
        "strategies": {"default": "parallel"},
    })

    # Need convergence to work for all review phases
    converge_mock = MagicMock(return_value={
        "converged": True, "findings_count": 0, "blocking_findings": [],
    })

    result = run_loop(
        "val-review-1",
        change_dir,
        wt,
        state_path=tmp_path / "state.json",
        assess_complexity_fn=assess_mock,
        converge_fn=converge_mock,
    )

    assert result.val_review_enabled is True
    assert result.current_phase == "DONE"


# ---------------------------------------------------------------------------
# Provider smoke path (skills/autopilot/scripts/smoke_provider_dispatch.py)
# ---------------------------------------------------------------------------

_SMOKE = Path(__file__).resolve().parent.parent / "smoke_provider_dispatch.py"
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _run_smoke(*args: str, env: dict[str, str] | None = None):
    """Run the operator smoke script in a subprocess with a hard timeout."""
    child_env = dict(os.environ)
    for name in (
        "LOCAL_INFERENCE_BASE_URL",
        "LOCAL_INFERENCE_API_KEY",
        "LOCAL_INFERENCE_MAX_CONCURRENCY",
    ):
        child_env.pop(name, None)
    child_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(_SMOKE), *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        env=child_env,
    )


def test_smoke_accepts_local_selector_in_dry_run() -> None:
    """`local` dry-run needs no environment and never touches the network."""
    proc = _run_smoke("--provider", "local", "--dry-run", "--json")

    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body["provider"] == "local"
    assert body["payload"]["provider"] == "local"
    assert body["result"]["outcome"] == "complete"
    assert body["result"]["dispatch_tier"] == "dry_run"
    model = body["payload"]["model"]
    assert model
    assert model not in {"opus", "sonnet", "haiku", "fable"}


def test_smoke_local_rejects_claude_alias_override() -> None:
    """`local` is a non-Claude provider; Claude aliases stay invalid."""
    proc = _run_smoke(
        "--provider", "local", "--dry-run", "--model", "sonnet", "--json"
    )

    assert proc.returncode != 0
    assert "Claude alias" in proc.stderr


def test_smoke_local_uses_a_trust_boundary_permitted_phase() -> None:
    """`local` drives INIT/runner, not IMPLEMENT/implementer (trust boundary D3)."""
    proc = _run_smoke("--provider", "local", "--dry-run", "--json")

    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body["payload"]["phase"] == "INIT"
    assert body["payload"]["archetype"] in {
        "runner",
        "analyst",
        "documenter",
        "validator",
    }


def test_smoke_local_real_mode_refuses_an_unresolved_archetype() -> None:
    """A resolver refusal is a hard smoke failure — never a dispatch anyway."""
    started = time.monotonic()
    proc = _run_smoke("--provider", "local", "--json")
    elapsed = time.monotonic() - started

    assert elapsed < 60
    assert proc.returncode != 0
    assert proc.stdout.strip() == "", "no dispatch result may be produced"
    assert "trust boundary" in proc.stderr
    assert "No dispatch attempted" in proc.stderr


def test_smoke_local_real_mode_unreachable_endpoint_refuses_before_dispatch() -> None:
    """Even with an endpoint configured, an unconfirmed archetype stops the run."""
    started = time.monotonic()
    proc = _run_smoke(
        "--provider",
        "local",
        "--json",
        env={"LOCAL_INFERENCE_BASE_URL": "http://127.0.0.1:9/v1"},
    )
    elapsed = time.monotonic() - started

    assert elapsed < 60
    assert proc.returncode != 0
    assert "trust boundary" in proc.stderr
    assert "No dispatch attempted" in proc.stderr


def test_smoke_local_real_mode_reports_fallback_for_a_dead_endpoint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the resolver confirming a permitted archetype, a dead endpoint
    degrades to the structured fallback instead of hanging (spec: local smoke)."""
    sys.path.insert(0, str(_REPO_ROOT / "skills" / "session-log" / "scripts"))
    import phase_agent
    import provider_dispatch
    import smoke_provider_dispatch

    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setattr(
        phase_agent.coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda *a, **k: {
            "archetype": "runner",
            "model": "qwen3-coder-30b-a3b",
            "system_prompt": "You are a focused runner.",
        },
    )
    provider_dispatch.reset_local_adapter_state()

    started = time.monotonic()
    exit_code = smoke_provider_dispatch.main(["--provider", "local", "--json"])
    elapsed = time.monotonic() - started
    provider_dispatch.reset_local_adapter_state()

    assert elapsed < 60
    assert exit_code == 1
    body = json.loads(capsys.readouterr().out)
    assert body["payload"]["phase"] == "INIT"
    assert body["payload"]["archetype"] == "runner"
    assert body["payload"]["model"] == "qwen3-coder-30b-a3b"
    assert body["result"]["dispatch_tier"] == "fallback"
    assert body["result"]["outcome"] == "failed"
    assert any("local" in w for w in body["result"]["warnings"])


def test_smoke_rejects_gemini_naming_the_supported_roster() -> None:
    proc = _run_smoke("--provider", "gemini", "--dry-run", "--json")

    assert proc.returncode != 0
    combined = proc.stderr + proc.stdout
    assert "gemini" in combined
    for supported in ("claude_code", "codex", "antigravity", "grok", "pi", "local"):
        assert supported in combined
