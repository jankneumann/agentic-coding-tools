"""State machine conductor for the autopilot skill.

Orchestrates the full plan-review-implement-validate-submit lifecycle,
delegating phase-specific work to callback functions injected by the
SKILL.md prompt layer.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sibling module imports (convergence_loop, complexity_gate, etc.)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from convergence_loop import converge  # type: ignore[import-untyped]
except ImportError:
    converge = None  # type: ignore[assignment]

# coordination_bridge ships under skills/coordination-bridge/scripts/. Make
# sure that directory is on sys.path so the lazy import inside
# _resolve_phase_archetype_for_state_only resolves it. The actual import
# is lazy (inside the function) to avoid mypy strict-mode complications
# with cross-package import-not-found warnings.
_BRIDGE_SCRIPTS = _SCRIPTS_DIR.parent.parent / "coordination-bridge" / "scripts"
if str(_BRIDGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_SCRIPTS))

try:
    from complexity_gate import assess_complexity  # type: ignore[import-untyped]
except ImportError:
    assess_complexity = None  # type: ignore[assignment]

try:
    from implementation_strategy_selector import select_strategies  # type: ignore[import-untyped]
except ImportError:
    select_strategies = None  # type: ignore[assignment]

# The trust-posture gate contract (ri-04) and the interviewer that executes it
# (ri-05) live under skills/shared/. They are imported eagerly and unguarded:
# a gate the loop cannot evaluate must be a loud import error, never a silently
# skipped human checkpoint. Constructing the *default* evaluator stays lazy
# (see _build_gate_evaluator) so importing this module never needs a coordinator.
_SKILLS_ROOT = _SCRIPTS_DIR.parent.parent
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

from shared import approval_gate as shared_approval_gate  # noqa: E402
from shared.approval_gate import (  # noqa: E402
    ApprovalDecision,
    Resolution,
    build_default_gate,
)
from shared.trust_posture import Gate  # noqa: E402

LOOP_STATE_SCHEMA_VERSION = 5


# ---------------------------------------------------------------------------
# LoopState dataclass  (mirrors convergence-state.schema.json)
# ---------------------------------------------------------------------------


@dataclass
class LoopState:
    """Persistent state for the autopilot loop.

    Schema versions:
        1 — initial
        2 — adds last_handoff_id (phase-record-compaction)
        3 — adds phase_archetype (per OpenSpec
            add-per-phase-archetype-resolution; design decision D7)
        4 — adds force, gate_signals, gate_verdict (GATEKEEPER judge gate —
            replaces deterministic complexity blocking)
        5 — adds gate_decisions, pending_gate, goal_gate (trust-posture gates
            and the DONE evidence check; OpenSpec
            encode-autopilot-gates-and-goal-gate-in-code, design D7)
    """

    schema_version: int = LOOP_STATE_SCHEMA_VERSION
    change_id: str = ""
    current_phase: str = "INIT"
    iteration: int = 0
    total_iterations: int = 0
    max_phase_iterations: int = 3
    findings_trend: list[int] = field(default_factory=list)
    blocking_findings: list[dict[str, Any]] = field(default_factory=list)
    vendor_availability: dict[str, bool] = field(default_factory=dict)
    packages_status: dict[str, str] = field(default_factory=dict)
    package_authors: dict[str, str] = field(default_factory=dict)
    implementation_strategy: dict[str, str] = field(default_factory=dict)
    memory_ids: list[str] = field(default_factory=list)
    handoff_ids: list[str] = field(default_factory=list)
    # Append-only log of {phase, outcome, at[, note]} entries. Written by
    # runner.py apply-outcome (cross-process path) and the apply-outcome-failure
    # escalation wrapper. Declared here so autopilot's dataclass round-trip
    # (asdict/load_state) preserves it rather than dropping it on save.
    phase_history: list[dict[str, Any]] = field(default_factory=list)
    last_handoff_id: str | None = None
    started_at: str = ""
    phase_started_at: str = ""
    previous_phase: str | None = None
    escalation_reason: str | None = None
    val_review_enabled: bool = False
    cli_review_enabled: bool = True
    error: str | None = None
    # NEW (v3): name of the archetype resolved for the current phase. Set by
    # phase_agent._build_options after a successful coordinator resolution;
    # remains None when resolution falls back to the harness default (D9) or
    # for phases where archetype injection is bypassed (operator override
    # path per D8). Persisted in loop-state.json and emitted in
    # POST /status/report payloads alongside `phase`.
    phase_archetype: str | None = None
    # NEW (v4): GATEKEEPER judge gate.
    # `force` mirrors the --force flag so resume is faithful; when True the
    # GATEKEEPER judge is skipped (operator override of the risk judgment).
    # `gate_signals` is the risk + verifiability profile gathered at INIT and
    # handed to the judge sub-agent. `gate_verdict` records the judge's
    # decision (proceed / proceed_with_review / escalate) for observability
    # and resume.
    force: bool = False
    gate_signals: dict[str, Any] = field(default_factory=dict)
    gate_verdict: str | None = None
    # NEW (v5): trust-posture gate records.
    # `gate_decisions` is the append-only audit log of every ApprovalDecision
    # the loop acted on (contracts/events/gate-decision.schema.json). It is
    # written BEFORE the loop acts on a decision so a crash can never lose the
    # authorization for a transition that already happened.
    # `pending_gate` is a GateRequest (contracts/events/gate-request.schema.json)
    # the host must answer via `runner.py gate-answer`; while it is set the loop
    # refuses to transition at all (`_apply_transition` raises GatePending).
    # `goal_gate` records the DONE evidence verdict (goal_gate.check_goal_gate).
    gate_decisions: list[dict[str, Any]] = field(default_factory=list)
    pending_gate: dict[str, Any] | None = None
    goal_gate: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def save_state(state: LoopState, path: str | Path) -> None:
    """Serialize *state* to JSON at *path*."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(state), indent=2) + "\n")


def load_state(path: str | Path) -> LoopState:
    """Deserialize a LoopState from the JSON file at *path*.

    Migrates older snapshots forward (D7): a v4 file loads with
    ``gate_decisions = []``, ``pending_gate = None`` and ``goal_gate = None``
    while every field it did carry (``phase_history`` included) is preserved;
    the migration is persisted on the next ``save_state`` call.
    """
    data = json.loads(Path(path).read_text())
    state = LoopState(**{k: v for k, v in data.items() if k in LoopState.__dataclass_fields__})
    # Forward migration: bump schema_version on load so callers see the current
    # shape immediately. New fields (phase_archetype, force, gate_signals,
    # gate_verdict, gate_decisions, pending_gate, goal_gate) default via the
    # dataclass; the bump persists on next save.
    if state.schema_version < LOOP_STATE_SCHEMA_VERSION:
        state.schema_version = LOOP_STATE_SCHEMA_VERSION
    return state


def persist_and_project(
    state: LoopState,
    path: str | Path,
    queue_projection_fn: Callable[..., Any] | None = None,
    *,
    mode: str = "submit",
) -> dict[str, Any]:
    """Persist authoritative state, then best-effort project it to the queue.

    The callback (typically the coordination-bridge ``try_submit_work`` /
    ``try_reconcile_projection`` helpers) does not always raise on failure —
    when the coordinator is unreachable or refuses the payload it returns a
    structured ``{"status": "skipped"|"failed", ...}`` envelope instead. A
    non-success envelope is classified the same as a raised exception: it is
    never reported as ``"ok"``, so callers (and the run loop) can see that
    the previous queue generation may still be live.
    """
    save_state(state, path)
    if queue_projection_fn is None:
        return {"status": "skipped", "reason": "projection_callback_absent"}
    try:
        response = queue_projection_fn(state, mode=mode)
    except Exception as exc:
        logger.warning("Queue projection failed after state persistence: %s", exc)
        return {"status": "failed", "reason": "projection_failed", "error": str(exc)}
    if isinstance(response, dict):
        envelope_status = response.get("status")
        if envelope_status is not None and envelope_status != "ok":
            reason = response.get("reason") or response.get("error")
            logger.warning(
                "Queue projection callback returned non-success status %r after "
                "state persistence (mode=%s): %s",
                envelope_status,
                mode,
                reason,
            )
            return {"status": envelope_status, "reason": reason, "response": response}
    return {"status": "ok", "response": response}


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

TRANSITIONS: dict[str, dict[str, str]] = {
    "INIT": {"next": "GATEKEEPER_OR_PLAN"},
    "GATEKEEPER": {
        "proceed": "PLAN",
        "proceed_with_review": "PLAN",
        "escalate": "ESCALATE",
    },
    "PLAN": {"exists": "PLAN_ITERATE", "created": "PLAN_ITERATE", "failed": "ESCALATE"},
    "PLAN_ITERATE": {"complete": "PLAN_REVIEW_OR_IMPLEMENT", "failed": "ESCALATE"},
    "PLAN_REVIEW": {"converged": "IMPLEMENT", "not_converged": "PLAN_FIX", "max_iter": "ESCALATE"},
    "PLAN_FIX": {"fixed": "PLAN_REVIEW", "stuck": "ESCALATE"},
    "IMPLEMENT": {"complete": "IMPL_ITERATE", "failed": "ESCALATE"},
    "IMPL_ITERATE": {"complete": "IMPL_REVIEW_OR_VALIDATE", "failed": "ESCALATE"},
    "IMPL_REVIEW": {"converged": "VALIDATE", "not_converged": "IMPL_FIX", "max_iter": "ESCALATE"},
    "IMPL_FIX": {"fixed": "IMPL_REVIEW", "stuck": "ESCALATE"},
    "VALIDATE": {"passed": "VAL_REVIEW_OR_SUBMIT", "failed": "VAL_FIX"},
    "VAL_REVIEW": {"converged": "SUBMIT_PR", "not_converged": "VAL_FIX", "max_iter": "ESCALATE"},
    "VAL_FIX": {"fixed": "VALIDATE", "stuck": "ESCALATE"},
    "SUBMIT_PR": {"created": "DONE"},
    "ESCALATE": {"resolved": "_previous_phase", "abandoned": "DONE"},
}


def transition(state: LoopState, outcome: str) -> str:
    """Return the next phase given current *state* and *outcome*.

    Raises ``ValueError`` for invalid phase/outcome combinations.
    """
    phase = state.current_phase
    table = TRANSITIONS.get(phase)
    if table is None:
        raise ValueError(f"No transitions defined for phase {phase!r}")
    target = table.get(outcome)
    if target is None:
        raise ValueError(f"Invalid outcome {outcome!r} for phase {phase!r}")

    # Dynamic resolution
    if target == "GATEKEEPER_OR_PLAN":
        # --force is an explicit operator override of the risk judgment, so it
        # skips the GATEKEEPER judge entirely and proceeds straight to PLAN.
        return "PLAN" if state.force else "GATEKEEPER"
    if target == "PLAN_REVIEW_OR_IMPLEMENT":
        return "PLAN_REVIEW" if state.cli_review_enabled else "IMPLEMENT"
    if target == "IMPL_REVIEW_OR_VALIDATE":
        return "IMPL_REVIEW" if state.cli_review_enabled else "VALIDATE"
    if target == "VAL_REVIEW_OR_SUBMIT":
        return "VAL_REVIEW" if state.val_review_enabled else "SUBMIT_PR"
    if target == "_previous_phase":
        if state.previous_phase is None:
            raise ValueError("ESCALATE resolved but previous_phase is None")
        return state.previous_phase
    return target


# ---------------------------------------------------------------------------
# Gate seam (design D1) — one injected evaluator, lazily defaulted
# ---------------------------------------------------------------------------

# The outcome a phase handler returns when a gate parked the loop awaiting a
# host-recorded answer. It is deliberately NOT a member of any TRANSITIONS
# table: `gate_pending` never moves a phase, it stops the loop where it stands.
GATE_PENDING = "gate_pending"

GATE_REQUEST_SCHEMA_VERSION = 1


class GateEvaluator(Protocol):
    """The approval-gate surface the loop depends on (``ApprovalGate``)."""

    def evaluate(self, gate: Gate, context: dict[str, Any] | None = None) -> ApprovalDecision:
        """Resolve *gate* against the trust posture and return a decision."""
        ...


class GatePending(RuntimeError):
    """Raised by ``_apply_transition`` while ``state.pending_gate`` is set.

    The single enforcement point (D6): no path — run_loop, ``gate-answer``, or a
    hand-edited ``current_phase`` — may move a phase while a gate is unanswered.
    """

    def __init__(self, gate: str) -> None:
        self.gate = gate
        super().__init__(f"gate {gate!r} is pending; the loop cannot transition")


class GoalGateRefused(RuntimeError):
    """Raised by ``_apply_transition`` when the DONE evidence check refuses."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"goal gate refused: {reason}")


# Operator-facing question per gate. The host renders `prompt` verbatim
# (AskUserQuestion), so each one has to be answerable without reading the code.
_GATE_PROMPTS: dict[Gate, str] = {
    Gate.GATEKEEPER_ESCALATION: (
        "The GATEKEEPER judged this change too risky or unverifiable to automate. "
        "Escalate it for human handling?"
    ),
    Gate.PROPOSAL_APPROVAL: "Approve this OpenSpec proposal and begin implementation?",
    Gate.PLAN_REVIEW_CONVERGENCE_FAILURE: (
        "Plan review did not converge. Escalate for human handling?"
    ),
    Gate.VALIDATION_FAILURE: "Validation failed. Continue into the fix loop?",
    Gate.ESCALATE_RESUME: "Has this escalation been resolved? Resume the loop?",
    Gate.PR_CREATION: "Create the pull request for this change?",
    Gate.MERGE: (
        "Authorize merging this pull request? "
        "(autopilot records the authorization only; /cleanup-feature merges)"
    ),
    Gate.REPLAN_REQUIRED: "Re-decompose the roadmap around the failed item?",
}


def _fallback_gate_session(state: LoopState) -> "_GateSession":
    """A gate session for callers that reach a phase handler without run_loop.

    Only the direct-helper unit tests do that. The fallback is strictly more
    conservative than the injected one — same fail-closed evaluator, but no
    state file to persist to — so it can never turn a gate off.
    """
    return _GateSession(
        change_id=state.change_id,
        state_path=None,
        repo_root=Path.cwd(),
    )


def _build_gate_evaluator(change_id: str, repo_root: Path) -> GateEvaluator:
    """Construct the production evaluator. Called on FIRST gate, not at import.

    ``repo_root`` is the worktree the loop is driving, so the posture in effect
    is the one committed on this change's branch.
    """
    return build_default_gate(
        agent_id=f"autopilot:{change_id}" if change_id else "autopilot",
        repo_root=str(repo_root),
    )


def _scalar_context(context: dict[str, Any]) -> dict[str, Any]:
    """Coerce a gate context to the scalars gate-request.schema.json allows."""
    coerced: dict[str, Any] = {}
    for key, value in context.items():
        coerced[key] = (
            value if isinstance(value, (str, int, float, bool, type(None))) else str(value)
        )
    return coerced


def build_gate_request(
    *,
    change_id: str,
    gate: Gate,
    phase: str,
    decision: ApprovalDecision,
    context: dict[str, Any],
    edge: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the GateRequest persisted as ``LoopState.pending_gate``.

    Conforms to ``contracts/events/gate-request.schema.json``. ``edge`` is
    omitted for gates whose approval does not itself move a phase (PR creation),
    so ``gate-answer`` knows to record the answer without transitioning.
    """
    request: dict[str, Any] = {
        "schema_version": GATE_REQUEST_SCHEMA_VERSION,
        "change_id": change_id,
        "gate": gate.value,
        "phase": phase,
        "requested_at": _now_iso(),
        "prompt": _GATE_PROMPTS.get(gate, f"Approve gate {gate.value}?"),
        "context": _scalar_context(context),
        "posture": {
            "disposition": decision.disposition.value,
            "posture_present": decision.posture_present,
        },
    }
    if edge is not None:
        request["edge"] = dict(edge)
    return request


@dataclass
class _GateSession:
    """Owns the gate seam for one ``run_loop`` invocation.

    Satisfies :class:`GateEvaluator` itself, so the call sites read
    ``gates.evaluate(Gate.X, ...)`` whether the evaluator was injected or built
    lazily. Also owns *persistence*: every decision is appended to
    ``LoopState.gate_decisions`` and flushed to disk BEFORE the loop acts on it,
    so a crash between "human said yes" and "phase moved" loses the phase move,
    never the authorization.
    """

    change_id: str
    state_path: Path | None
    repo_root: Path
    evaluator: GateEvaluator | None = None

    def evaluate(self, gate: Gate, context: dict[str, Any] | None = None) -> ApprovalDecision:
        if self.evaluator is None:
            self.evaluator = _build_gate_evaluator(self.change_id, self.repo_root)
        return self.evaluator.evaluate(gate, dict(context or {}))

    def record(
        self,
        state: LoopState,
        decision: ApprovalDecision,
        *,
        phase: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        state.gate_decisions.append(build_gate_decision_record(decision, phase=phase, extra=extra))
        self._flush(state)

    def park(
        self,
        state: LoopState,
        decision: ApprovalDecision,
        *,
        phase: str,
        context: dict[str, Any],
        edge: dict[str, str] | None = None,
    ) -> str | None:
        """Park the loop on a BLOCKED decision; return the phase outcome.

        ``posture_block`` means nobody has been asked yet — that is the
        interactive case, so it raises a GateRequest the host can answer and
        returns ``gate_pending``. The other BLOCKED resolutions
        (``timeout_default_block``, ``rejected``, ``coordinator_unreachable``)
        mean a human WAS consulted or could not be reached; those park exactly
        as an unresolved ESCALATE does today — return None, save, stop.
        """
        if decision.resolution is Resolution.POSTURE_BLOCK:
            state.pending_gate = build_gate_request(
                change_id=self.change_id,
                gate=decision.gate,
                phase=phase,
                decision=decision,
                context=context,
                edge=edge,
            )
            self._flush(state)
            return GATE_PENDING
        return None

    def _flush(self, state: LoopState) -> None:
        if self.state_path is None:
            # Only the direct-helper callers (unit tests calling a phase
            # handler on its own) have no state file; run_loop always supplies
            # one, which is what makes "recorded before the loop acts" true.
            logger.debug("gate session has no state_path; decision not persisted")
            return
        save_state(state, self.state_path)


# Thin delegating alias (ri-04, D2): the record shape now lives in
# shared.approval_gate so supervise's gate_router.py can share it without
# importing autopilot.py. This module's own seven call sites (and
# test_gate_call_sites' single-call-site invariant per gate) are untouched.
build_gate_decision_record = shared_approval_gate.build_gate_decision_record


# ---------------------------------------------------------------------------
# Escalation helpers
# ---------------------------------------------------------------------------


def enter_escalate(
    state: LoopState,
    reason: str,
    status_fn: Callable[[LoopState, str, str, bool], None] | None = None,
) -> LoopState:
    """Transition *state* into ESCALATE, recording the originating phase."""
    state.previous_phase = state.current_phase
    state.escalation_reason = reason
    state.current_phase = "ESCALATE"
    state.phase_started_at = _now_iso()
    _safe_status_call(
        status_fn,
        state,
        "status.escalated",
        f"Escalated: {reason}",
        urgent=True,
    )
    return state


def check_escalation_resolved(
    state: LoopState,
    gate_check_fn: Callable[[LoopState], bool] | None = None,
) -> bool:
    """Return True if the escalation has been resolved.

    Delegates to *gate_check_fn* if provided; otherwise returns False
    (stub behaviour — actual resolution depends on phase-specific gates).
    """
    if gate_check_fn is not None:
        return gate_check_fn(state)
    return False


# ---------------------------------------------------------------------------
# apply-outcome failure handling (design D9 / Task 5.5)
# ---------------------------------------------------------------------------

# Result of a runner.py apply-outcome invocation. Value is the process exit
# code (0 == success). The orchestrator treats any non-zero code as a failure
# that must escalate rather than silently continue.
ApplyOutcomeRunner = Callable[..., int]


def _default_apply_outcome_runner(
    *,
    change_id: str,
    phase: str,
    outcome: str,
    handoff_id: str,
    allow_phase_mismatch: bool,
) -> int:
    """Shell out to ``runner.py apply-outcome`` and return its exit code."""
    import subprocess  # local import — keeps module import cheap

    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "runner.py"),
        "apply-outcome",
        "--change-id",
        change_id,
        "--phase",
        phase,
        "--outcome",
        outcome,
        "--handoff-id",
        handoff_id,
    ]
    if allow_phase_mismatch:
        cmd.append("--allow-phase-mismatch")
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        logger.warning(
            "apply-outcome exited %d for phase=%s change=%s: %s",
            completed.returncode,
            phase,
            change_id,
            completed.stderr.strip(),
        )
    return completed.returncode


def apply_outcome_or_escalate(
    *,
    change_id: str,
    phase: str,
    outcome: str,
    handoff_id: str,
    state_path: str | Path,
    allow_phase_mismatch: bool = False,
    apply_runner: ApplyOutcomeRunner | None = None,
    status_fn: Callable[[LoopState, str, str, bool], None] | None = None,
) -> int:
    """Run apply-outcome and escalate on failure (design D9).

    Invokes ``runner.py apply-outcome`` (via *apply_runner*, injectable for
    tests). On a zero exit, returns 0 and leaves the state as apply-outcome
    wrote it. On a non-zero exit the orchestrator MUST NOT continue silently;
    instead it:

      1. Retains the un-applied handoff file (this function never deletes it).
      2. Appends a ``phase_history`` entry recording the apply-outcome failure.
      3. Transitions ``current_phase`` to ``ESCALATE`` with ``previous_phase``
         set to the failing *phase*.

    Best-effort (D9.1): if the ESCALATE write ALSO fails (corrupt/read-only
    loop-state), the failure is logged at CRITICAL with the handoff path and
    the underlying cause, and the function returns the non-zero exit code. The
    retained handoff file remains the durable record for operator resume.

    Returns the apply-outcome exit code (0 on success, non-zero on failure).
    """
    runner = apply_runner or _default_apply_outcome_runner
    rc = runner(
        change_id=change_id,
        phase=phase,
        outcome=outcome,
        handoff_id=handoff_id,
        allow_phase_mismatch=allow_phase_mismatch,
    )
    if rc == 0:
        return 0

    # Non-zero exit — escalate. Operate on the raw JSON dict so unknown keys
    # (phase_history, checkpoints, etc.) survive the round-trip.
    path = Path(state_path)
    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError(f"unexpected loop-state shape in {path}")

        history = raw.get("phase_history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "phase": phase,
                "outcome": "apply_outcome_failed",
                "at": _now_iso(),
                "note": (
                    f"runner.py apply-outcome exited {rc}; handoff {handoff_id} "
                    f"retained un-applied. Resolve the underlying cause and resume."
                ),
            }
        )
        raw["phase_history"] = history
        # v5 pass-through (D7): a v4 file being escalated must come back out as
        # a v5 file, or the next load_state migration would silently invent the
        # gate fields at a point where nobody can tell they were never recorded.
        raw.setdefault("gate_decisions", [])
        raw.setdefault("pending_gate", None)
        raw.setdefault("goal_gate", None)
        raw["schema_version"] = LOOP_STATE_SCHEMA_VERSION
        raw["previous_phase"] = phase
        raw["current_phase"] = "ESCALATE"
        raw["escalation_reason"] = (
            f"apply-outcome failed (exit {rc}) for phase {phase}; handoff "
            f"{handoff_id} retained un-applied"
        )
        raw["phase_started_at"] = _now_iso()
        path.write_text(json.dumps(raw, indent=2) + "\n")

        if status_fn is not None:
            # Reload a dataclass view for the status callback signature.
            try:
                _safe_status_call(
                    status_fn,
                    load_state(path),
                    "status.escalated",
                    f"apply-outcome failed for {phase}; escalated",
                    urgent=True,
                )
            except Exception:  # noqa: BLE001
                logger.debug("status_fn call after escalate failed", exc_info=True)
    except Exception as exc:  # noqa: BLE001
        # D9.1 double-failure: cannot even write the ESCALATE transition.
        logger.critical(
            "apply-outcome failed (exit %d) AND the ESCALATE write also failed "
            "(%s). Handoff %s is retained at its path under "
            "openspec/changes/%s/handoffs/; loop-state may be inconsistent. "
            "Operator must resolve manually before resume.",
            rc,
            exc,
            handoff_id,
            change_id,
        )
    return rc


# ---------------------------------------------------------------------------
# Callback protocol (optional typing aid for callers)
# ---------------------------------------------------------------------------


class PhaseFn(Protocol):
    """Signature for phase callback functions."""

    def __call__(self, state: LoopState, **kwargs: Any) -> str:
        """Execute phase work and return an outcome string."""
        ...


# ---------------------------------------------------------------------------
# State-only archetype resolver (D7 — wire-autopilot-phase-subagents)
# ---------------------------------------------------------------------------

# Phases that record `phase_archetype` on the state machine itself rather
# than via a sub-agent dispatch. Per D7 these are INIT and SUBMIT_PR.
_STATE_ONLY_PHASES: frozenset[str] = frozenset({"INIT", "SUBMIT_PR"})


def _resolve_phase_archetype_for_state_only(
    state: LoopState,
    phase: str,
) -> None:
    """Resolve and record the archetype for a state-only phase.

    State-only phases (INIT, SUBMIT_PR) do not dispatch a sub-agent — they
    are state transitions executed inline by the loop driver. The spec
    requires `LoopState.phase_archetype` to be populated for these phases
    too, so observability dashboards can correlate every non-terminal
    phase with its archetype.

    The resolution path mirrors `phase_agent._build_options`'s archetype
    branch: it queries the coordinator via
    ``coordination_bridge.try_resolve_archetype_for_phase(phase, signals)``
    and records the resolved archetype name on `state.phase_archetype`.

    On any failure (bridge unavailable, coordinator returns None,
    malformed response), `state.phase_archetype` is left as None — this
    matches the bridge-failure fallback semantics from
    `add-per-phase-archetype-resolution` D9.
    """
    if phase not in _STATE_ONLY_PHASES:
        # Defensive — caller is expected to gate on _STATE_ONLY_PHASES, but
        # keep the function tolerant rather than raising.
        return
    try:
        # Lazy import keeps the cross-package dependency out of module-load
        # type checking and gracefully degrades if the bridge module is
        # missing (e.g., minimal harness environments).
        import coordination_bridge  # type: ignore[import-not-found]

        resolved = coordination_bridge.try_resolve_archetype_for_phase(phase, {})
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "_resolve_phase_archetype_for_state_only(%s) bridge raised: %s; "
            "leaving phase_archetype=None",
            phase,
            exc,
        )
        return
    if not isinstance(resolved, dict):
        return
    archetype = resolved.get("archetype")
    if isinstance(archetype, str) and archetype:
        state.phase_archetype = archetype


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_change_dir(state: LoopState, change_dir: str | Path | None) -> Path:
    """The change directory to read DONE evidence from.

    Callers that already know it (run_loop) pass it; the cross-process callers
    (``runner.py gate-answer``) fall back to the canonical layout, which is the
    same one ``phase_agent`` uses to find loop-state.json.
    """
    if change_dir is not None:
        return Path(change_dir)
    return Path("openspec") / "changes" / state.change_id


def _apply_transition(
    state: LoopState,
    outcome: str,
    status_fn: Callable[[LoopState, str, str, bool], None] | None = None,
    *,
    change_dir: str | Path | None = None,
) -> LoopState:
    """Compute and apply the transition, updating bookkeeping fields.

    The single enforcement point for both code-level gates (design D6). Every
    path into DONE — run_loop, ``gate-answer``, a hand-edited ``current_phase``
    — comes through here, so this is the only place the two checks need to live:

    1. ``state.pending_gate`` set → ``GatePending``. No phase moves while a
       human question is outstanding.
    2. resolved target is DONE (and the edge is not ESCALATE/abandoned) → the
       goal gate must find its evidence, or ``GoalGateRefused``.
    """
    if state.pending_gate:
        raise GatePending(str(state.pending_gate.get("gate", "unknown")))

    old_phase = state.current_phase
    next_phase = transition(state, outcome)

    if next_phase == "DONE":
        _check_done_evidence(state, old_phase, outcome, change_dir)

    state.current_phase = next_phase
    state.phase_started_at = _now_iso()
    state.total_iterations += 1
    _safe_status_call(
        status_fn,
        state,
        "phase.transition",
        f"Phase {old_phase} -> {next_phase}",
        urgent=False,
    )
    return state


def _check_done_evidence(
    state: LoopState,
    from_phase: str,
    outcome: str,
    change_dir: str | Path | None,
) -> None:
    """Run the goal gate for a DONE-targeted edge; record the verdict either way.

    ``ESCALATE`` → ``abandoned`` is the one edge that reaches DONE without
    evidence: abandoning a change is a decision not to validate it, so demanding
    a passing validation report would make abandonment impossible.
    """
    if from_phase == "ESCALATE" and outcome == "abandoned":
        state.goal_gate = {"verdict": "abandoned"}
        return

    # Imported here rather than at module scope: goal_gate imports validate-
    # feature's gate_logic, and this keeps `import autopilot` from pulling in
    # another skill's dependency tree for runs that never reach DONE.
    import goal_gate as goal_gate_module  # type: ignore[import-not-found]

    verdict = goal_gate_module.check_goal_gate(state, _resolve_change_dir(state, change_dir))
    # Merge rather than replace: the merge gate records its authorization into
    # goal_gate.evidence before SUBMIT_PR -> DONE is applied (design D2).
    prior_evidence = dict((state.goal_gate or {}).get("evidence") or {})
    prior_evidence.update(verdict.evidence)
    state.goal_gate = {
        "verdict": verdict.verdict,
        "reason": verdict.reason,
        "evidence": prior_evidence,
    }
    if verdict.verdict != "passed":
        raise GoalGateRefused(verdict.reason)


def _is_review_phase(phase: str) -> bool:
    return phase in ("PLAN_REVIEW", "IMPL_REVIEW", "VAL_REVIEW")


def _is_iterate_phase(phase: str) -> bool:
    return phase in ("PLAN_ITERATE", "IMPL_ITERATE")


def _safe_status_call(
    status_fn: Callable[[LoopState, str, str, bool], None] | None,
    state: LoopState,
    event_type: str,
    message: str,
    urgent: bool = False,
) -> None:
    """Call status_fn with a 5-second timeout, catching all errors."""
    if status_fn is None:
        return
    import signal

    def _timeout_handler(signum: int, frame: Any) -> None:
        raise TimeoutError("status_fn timed out")

    old_handler = None
    try:
        # Use SIGALRM for timeout on Unix; skip timeout on other platforms
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(5)
        except (AttributeError, OSError):
            pass

        status_fn(state, event_type, message, urgent)
    except Exception:
        logger.debug("status_fn call failed", exc_info=True)
    finally:
        try:
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
        except (AttributeError, OSError):
            pass


# ---------------------------------------------------------------------------
# run_loop — main entry point
# ---------------------------------------------------------------------------


def run_loop(
    change_id: str,
    change_dir: str | Path,
    worktree_path: str | Path,
    *,
    state_path: str | Path | None = None,
    plan_fn: Callable[[LoopState], str] | None = None,
    iterate_plan_fn: Callable[[LoopState], str] | None = None,
    iterate_impl_fn: Callable[[LoopState], str] | None = None,
    implement_fn: Callable[[LoopState], str] | None = None,
    validate_fn: Callable[[LoopState], str] | None = None,
    submit_pr_fn: Callable[[LoopState], str] | None = None,
    handoff_fn: Callable[[LoopState, Any], str | None] | None = None,
    token_meter_fn: Callable[[LoopState, str, str, str], None] | None = None,
    memory_fn: Callable[[LoopState, str], str | None] | None = None,
    gate_check_fn: Callable[[LoopState], bool] | None = None,
    converge_fn: Callable[..., Any] | None = None,
    assess_complexity_fn: Callable[..., Any] | None = None,
    gatekeeper_fn: Callable[[LoopState], str] | None = None,
    post_fix_validator_fn: Callable[[Path], list[str]] | None = None,
    status_fn: Callable[[LoopState, str, str, bool], None] | None = None,
    queue_projection_fn: Callable[..., Any] | None = None,
    gate_evaluator: GateEvaluator | None = None,
    cli_review_enabled: bool = True,
    force: bool = False,
    max_global_iterations: int = 50,
) -> LoopState:
    """Drive the autopilot loop from the current phase to DONE or ESCALATE.

    Parameters
    ----------
    change_id:
        OpenSpec change identifier.
    change_dir:
        Path to ``openspec/changes/<change_id>/``.
    worktree_path:
        Git worktree root for this feature.
    state_path:
        Where to persist ``LoopState`` JSON.  Defaults to
        ``<change_dir>/loop-state.json``.
    plan_fn / implement_fn / validate_fn / submit_pr_fn:
        Callbacks for phases that require external tool invocations.
        Each receives the current state and returns an outcome string.
    iterate_plan_fn:
        Callback for PLAN_ITERATE phase (self-review of plan artifacts).
        Receives state, returns outcome ("complete" or "failed").
    iterate_impl_fn:
        Callback for IMPL_ITERATE phase (self-review of implementation).
        Receives state, returns outcome ("complete" or "failed").
    handoff_fn:
        Called at major transition boundaries with a description.
    memory_fn:
        Called to write coordination memory; returns an optional memory_id.
    gate_check_fn:
        Passed through to ``check_escalation_resolved``.
    converge_fn:
        Override for the convergence loop (defaults to sibling module).
    assess_complexity_fn:
        Override for complexity assessment (defaults to sibling module).
    post_fix_validator_fn:
        Passed through to convergence loop as ``post_fix_validator``.
        Called after fixes are applied during review phases to catch
        regressions (e.g. test failures on changed files).
    status_fn:
        Called on phase transitions and escalations to report status.
        Signature: ``(state, event_type, message, urgent) -> None``.
        Wrapped in try/except with 5s timeout — never crashes the loop.
    gate_evaluator:
        Executes the trust-posture human gates (design D1). Defaults to
        ``approval_gate.build_default_gate()``, built lazily on the first gate
        so a run that never reaches one needs no coordinator. With no
        ``TRUST_POSTURE.md`` present every gate resolves to ``block`` — the
        fail-closed ri-04 contract, which is what makes an un-postured repo
        behave exactly as it did before gates existed.
    cli_review_enabled:
        Whether multi-vendor review phases (PLAN_REVIEW, IMPL_REVIEW)
        should run.  True when vendor CLIs are available (CLI mode),
        False for headless/cloud/API execution.  Defaults to True.
    max_global_iterations:
        Safety cap on total loop iterations.
    """
    change_dir = Path(change_dir)
    worktree_path = Path(worktree_path)

    if state_path is None:
        state_path = change_dir / "loop-state.json"
    state_path = Path(state_path)

    # Resolve function defaults
    _converge = converge_fn or converge
    _assess = assess_complexity_fn or assess_complexity

    # ---- Load or create state ----
    if state_path.exists():
        state = load_state(state_path)
        # Update cli_review_enabled from caller (may change between resumes)
        state.cli_review_enabled = cli_review_enabled
        logger.info(
            "Resumed loop state at phase=%s iteration=%d",
            state.current_phase,
            state.total_iterations,
        )
        if queue_projection_fn is not None:
            persist_and_project(state, state_path, queue_projection_fn, mode="reconcile")
    else:
        state = LoopState(
            change_id=change_id,
            started_at=_now_iso(),
            phase_started_at=_now_iso(),
            cli_review_enabled=cli_review_enabled,
        )
        logger.info("Created new loop state for %s", change_id)

    # The --force flag (operator override of the GATEKEEPER risk judgment) is
    # re-applied from the caller on every run, mirroring cli_review_enabled so a
    # resume honors the flag the operator passed this time.
    state.force = force

    gates = _GateSession(
        change_id=change_id,
        state_path=state_path,
        repo_root=worktree_path,
        evaluator=gate_evaluator,
    )

    # Re-entry with an unanswered gate: report and return rather than run a
    # phase whose transition _apply_transition would refuse anyway.
    if state.pending_gate:
        pending = str(state.pending_gate.get("gate", "unknown"))
        logger.info("Gate %s is pending for %s; not advancing", pending, change_id)
        _safe_status_call(
            status_fn,
            state,
            "gate.pending",
            f"Gate {pending} awaiting a decision (runner.py gate-check {change_id})",
            urgent=True,
        )
        return state

    # ---- Main loop ----
    while state.current_phase != "DONE" and state.total_iterations < max_global_iterations:
        phase = state.current_phase
        logger.info("Phase %s (iteration %d)", phase, state.total_iterations)

        try:
            outcome = _run_phase(
                state,
                change_dir=change_dir,
                worktree_path=worktree_path,
                plan_fn=plan_fn,
                iterate_plan_fn=iterate_plan_fn,
                iterate_impl_fn=iterate_impl_fn,
                implement_fn=implement_fn,
                validate_fn=validate_fn,
                submit_pr_fn=submit_pr_fn,
                handoff_fn=handoff_fn,
                memory_fn=memory_fn,
                gate_check_fn=gate_check_fn,
                converge_fn=_converge,
                assess_complexity_fn=_assess,
                gatekeeper_fn=gatekeeper_fn,
                post_fix_validator_fn=post_fix_validator_fn,
                gates=gates,
            )
        except Exception as exc:
            logger.error("Phase %s raised: %s", phase, exc)
            state.error = str(exc)
            enter_escalate(state, f"Exception in {phase}: {exc}", status_fn=status_fn)
            # ESCALATE is a phase change like any other transition — route it
            # through the same persist-then-project seam so a coordinated run
            # can't durably enter ESCALATE while the previous queue
            # generation stays active.
            persist_and_project(state, state_path, queue_projection_fn, mode="submit")
            break

        if outcome == GATE_PENDING:
            # A gate raised a question for the host. Park in place — the answer
            # arrives out of band via `runner.py gate-answer`.
            pending = str((state.pending_gate or {}).get("gate", "unknown"))
            save_state(state, state_path)
            _safe_status_call(
                status_fn,
                state,
                "gate.pending",
                f"Gate {pending} awaiting a decision at {phase}",
                urgent=True,
            )
            break

        if outcome is None:
            # Phase signalled "stay" (e.g. unresolved escalation, or a gate that
            # blocked after a human was consulted or the coordinator was down)
            save_state(state, state_path)
            break

        # If phase handler already changed the phase (e.g. enter_escalate),
        # skip the normal transition — just persist (and project) and continue.
        if state.current_phase != phase:
            persist_and_project(state, state_path, queue_projection_fn, mode="submit")
            continue

        prev_phase = state.current_phase
        try:
            _apply_transition(
                state,
                outcome,
                status_fn=status_fn,
                change_dir=change_dir,
            )
        except GoalGateRefused as exc:
            # A refusal is never a silent stop: it lands as an ESCALATE whose
            # reason names the missing evidence.
            enter_escalate(
                state,
                f"goal gate refused: {exc.reason}",
                status_fn=status_fn,
            )
            persist_and_project(state, state_path, queue_projection_fn, mode="submit")
            break
        except GatePending as exc:
            save_state(state, state_path)
            _safe_status_call(
                status_fn,
                state,
                "gate.pending",
                f"Gate {exc.gate} awaiting a decision at {phase}",
                urgent=True,
            )
            break

        # Write handoff at major boundaries (with optional token instrumentation)
        _maybe_handoff(
            prev_phase,
            state.current_phase,
            state,
            handoff_fn,
            token_meter_fn=token_meter_fn,
        )

        persist_and_project(state, state_path, queue_projection_fn, mode="submit")

    # Report DONE status
    if state.current_phase == "DONE":
        _safe_status_call(
            status_fn,
            state,
            "phase.transition",
            f"Loop completed for {change_id}",
            urgent=False,
        )

    # Final memory on completion
    if state.current_phase == "DONE" and memory_fn is not None:
        mid = memory_fn(state, f"Loop completed for {change_id}")
        if mid:
            state.memory_ids.append(mid)
            save_state(state, state_path)

    return state


# ---------------------------------------------------------------------------
# Phase dispatch
# ---------------------------------------------------------------------------


def _run_phase(
    state: LoopState,
    *,
    change_dir: Path,
    worktree_path: Path,
    plan_fn: Callable[[LoopState], str] | None,
    iterate_plan_fn: Callable[[LoopState], str] | None,
    iterate_impl_fn: Callable[[LoopState], str] | None,
    implement_fn: Callable[[LoopState], str] | None,
    validate_fn: Callable[[LoopState], str] | None,
    submit_pr_fn: Callable[[LoopState], str] | None,
    handoff_fn: Callable[[LoopState, Any], str | None] | None,
    memory_fn: Callable[[LoopState, str], str | None] | None,
    gate_check_fn: Callable[[LoopState], bool] | None,
    converge_fn: Callable[..., Any] | None,
    assess_complexity_fn: Callable[..., Any] | None,
    post_fix_validator_fn: Callable[[Path], list[str]] | None,
    gatekeeper_fn: Callable[[LoopState], str] | None = None,
    gates: _GateSession | None = None,
) -> str | None:
    """Run a single phase and return the outcome string, or None to pause."""
    phase = state.current_phase
    gates = gates or _fallback_gate_session(state)

    if phase == "INIT":
        return _phase_init(state, change_dir, assess_complexity_fn)

    if phase == "GATEKEEPER":
        return _phase_gatekeeper(state, gatekeeper_fn, gates)

    if phase == "PLAN":
        return _phase_plan(state, change_dir, plan_fn, gates)

    if phase == "PLAN_ITERATE":
        return _phase_iterate(state, iterate_plan_fn)

    if phase == "PLAN_REVIEW":
        return _gate_convergence_failure(
            state,
            gates,
            phase,
            _phase_review(
                state,
                change_dir,
                worktree_path,
                converge_fn,
                fix_mode="inline",
                post_fix_validator_fn=post_fix_validator_fn,
            ),
        )

    if phase == "PLAN_FIX":
        # Plan fixes are handled inline by the convergence loop; if we land
        # here the prior convergence round did not converge — retry review.
        return _gate_convergence_failure(state, gates, phase, "fixed")

    if phase == "IMPLEMENT":
        return _phase_implement(state, implement_fn)

    if phase == "IMPL_ITERATE":
        return _phase_iterate(state, iterate_impl_fn)

    if phase == "IMPL_REVIEW":
        return _phase_review(
            state,
            change_dir,
            worktree_path,
            converge_fn,
            fix_mode="targeted",
            post_fix_validator_fn=post_fix_validator_fn,
        )

    if phase == "IMPL_FIX":
        return "fixed"

    if phase == "VALIDATE":
        return _gate_validation_failure(
            state,
            gates,
            phase,
            _phase_validate(state, validate_fn),
        )

    if phase == "VAL_REVIEW":
        return _phase_review(
            state,
            change_dir,
            worktree_path,
            converge_fn,
            fix_mode="targeted",
            post_fix_validator_fn=post_fix_validator_fn,
        )

    if phase == "VAL_FIX":
        return _gate_validation_failure(state, gates, phase, "fixed")

    if phase == "SUBMIT_PR":
        return _phase_submit_pr(state, submit_pr_fn, gates)

    if phase == "ESCALATE":
        return _phase_escalate(state, gate_check_fn, gates)

    if phase == "DONE":
        return None

    raise ValueError(f"Unknown phase {phase!r}")


# ---------------------------------------------------------------------------
# Gate call sites owned by _run_phase (design D2)
# ---------------------------------------------------------------------------

# The (phase, outcome) pairs each _run_phase-owned gate wraps. Keeping them in
# one place is what lets each gate keep exactly one `evaluate(Gate.X` call site
# while covering two phases.
_CONVERGENCE_FAILURE_EDGES = {("PLAN_REVIEW", "max_iter"), ("PLAN_FIX", "stuck")}
_VALIDATION_FAILURE_EDGES = {("VALIDATE", "failed"), ("VAL_FIX", "stuck")}


def _gate_convergence_failure(
    state: LoopState, gates: _GateSession, phase: str, outcome: str
) -> str | None:
    """Gate the plan-review convergence-failure edge (PLAN_REVIEW / PLAN_FIX)."""
    if (phase, outcome) not in _CONVERGENCE_FAILURE_EDGES:
        return outcome
    context = {
        "convergence_reason": outcome,
        "rounds": state.max_phase_iterations,
        "findings_trend": ", ".join(str(n) for n in state.findings_trend),
    }
    decision = gates.evaluate(Gate.PLAN_REVIEW_CONVERGENCE_FAILURE, context)
    gates.record(state, decision, phase=phase)
    if not decision.proceed:
        return gates.park(
            state,
            decision,
            phase=phase,
            context=context,
            edge={"outcome": outcome, "target": "ESCALATE"},
        )
    return outcome


def _gate_validation_failure(
    state: LoopState, gates: _GateSession, phase: str, outcome: str
) -> str | None:
    """Gate the validation-failure edge (VALIDATE failed / VAL_FIX stuck)."""
    if (phase, outcome) not in _VALIDATION_FAILURE_EDGES:
        return outcome
    context = {
        "failing_section": _failing_validation_section(state),
        "outcome": outcome,
    }
    decision = gates.evaluate(Gate.VALIDATION_FAILURE, context)
    gates.record(state, decision, phase=phase)
    if not decision.proceed:
        return gates.park(
            state,
            decision,
            phase=phase,
            context=context,
            edge={"outcome": outcome, "target": TRANSITIONS[phase][outcome]},
        )
    return outcome


def _failing_validation_section(state: LoopState) -> str:
    """Best-effort name of what failed, for the operator-facing gate context."""
    titles = [
        f.get("title") for f in state.blocking_findings if isinstance(f, dict) and f.get("title")
    ]
    return "; ".join(str(t) for t in titles) if titles else "unspecified"


# ---------------------------------------------------------------------------
# Individual phase implementations
# ---------------------------------------------------------------------------


def _phase_init(
    state: LoopState,
    change_dir: Path,
    assess_complexity_fn: Callable[..., Any] | None,
) -> str:
    """Gather the risk + verifiability signal profile and apply the scope floor.

    INIT no longer blocks on size. It records the ``gate_signals`` profile (for
    the GATEKEEPER judge) and enforces only the deterministic scope-safety floor
    — a broad write scope flips ``force_required`` and escalates unless --force
    was given. Everything else is handed to the judge.
    """
    state.phase_started_at = _now_iso()
    # D7: state-only phases must still record phase_archetype so observability
    # surfaces are uniform across the non-terminal phases.
    _resolve_phase_archetype_for_state_only(state, "INIT")

    if assess_complexity_fn is not None:
        wp_path = change_dir / "work-packages.yaml"
        proposal_path = change_dir / "proposal.md"
        result = assess_complexity_fn(
            work_packages_path=wp_path,
            proposal_path=proposal_path if proposal_path.exists() else None,
            force=state.force,
        )

        def _field(name: str, default: Any) -> Any:
            """Support both GateResult dataclass and dict results."""
            value = getattr(result, name, None)
            if value is None and isinstance(result, dict):
                value = result.get(name, default)
            return default if value is None else value

        # Persist the signal profile so the GATEKEEPER judge (and resume) sees it.
        state.gate_signals = dict(_field("signals", {}))

        # Scope-safety floor — the only deterministic block remaining. --force is
        # an explicit operator override of this floor, so honor state.force here
        # (the documented bypass) rather than escalating unconditionally.
        force_required = _field("force_required", False)
        if force_required and not state.force:
            warnings = _field("warnings", [])
            enter_escalate(
                state,
                f"Scope-safety gate: force_required — {'; '.join(warnings)}",
            )
            return "next"  # will be overridden by escalate
        # Risk-signal-driven validation review (e.g. db migration, security).
        if _field("val_review_enabled", False):
            state.val_review_enabled = True
    return "next"


# Permissive headless fallback: when no judge model is reachable, proceed —
# enabling validation review only when a risk signal is present.
_RISK_SIGNAL_KEYS: tuple[str, ...] = (
    "has_db_migration",
    "has_security_signal",
    "has_broad_write_scope",
)

_GATEKEEPER_OUTCOMES: frozenset[str] = frozenset({"proceed", "proceed_with_review", "escalate"})

# Gate status for "could not be checked" (OpenSpec introduce-fitness-function-gates,
# design decision D6). A fail-open path must be distinguishable from a real pass,
# so every permissive fallback records a DEGRADED entry naming what was not
# checked and why. Mirrors the DEGRADED status parsed by
# skills/validate-feature/scripts/gate_logic.py.
DEGRADED_STATUS = "DEGRADED"


def record_degraded(state: LoopState, phase: str, note: str) -> None:
    """Append a DEGRADED entry for *phase* to the state's phase history.

    The note MUST say, in one line, what was not checked and why. Also emitted
    to stderr so the degradation is visible in headless runs whose state file
    nobody reads.
    """
    entry = {
        "phase": phase,
        "outcome": DEGRADED_STATUS,
        "at": _now_iso(),
        "note": note,
    }
    state.phase_history.append(entry)
    print(f"[{DEGRADED_STATUS}] {phase}: {note}", file=sys.stderr)


def _default_gate_verdict(signals: dict[str, Any]) -> str:
    """Permissive verdict from signals alone — never escalates."""
    if any(bool(signals.get(k)) for k in _RISK_SIGNAL_KEYS):
        return "proceed_with_review"
    return "proceed"


def _phase_gatekeeper(
    state: LoopState,
    gatekeeper_fn: Callable[[LoopState], str] | None,
    gates: _GateSession | None = None,
) -> str | None:
    """Judge whether the change is verifiable and low-risk enough to automate.

    The judge sub-agent reads ``state.gate_signals`` plus the plan artifacts and
    returns ``proceed`` / ``proceed_with_review`` / ``escalate``. When no judge
    is wired (headless CI, coordinator down, unit tests) the gate falls back to
    a permissive signal-only verdict rather than blocking.
    """
    gates = gates or _fallback_gate_session(state)
    state.phase_started_at = _now_iso()

    outcome: str | None = None
    if gatekeeper_fn is not None:
        outcome = gatekeeper_fn(state)
    if outcome not in _GATEKEEPER_OUTCOMES:
        # No judge, or an unrecognized verdict — degrade permissively, but say
        # so out loud (D6). Failing open silently made an unjudged run
        # indistinguishable from one the judge actually cleared.
        reason = (
            "no dispatch adapter available"
            if gatekeeper_fn is None
            else f"judge returned an unrecognized verdict {outcome!r}"
        )
        outcome = _default_gate_verdict(state.gate_signals)
        record_degraded(
            state,
            "GATEKEEPER",
            f"Risk/verifiability judgment NOT CHECKED — {reason}; fell back to "
            f"the permissive signal-only verdict {outcome!r}.",
        )

    state.gate_verdict = outcome
    if outcome == "proceed_with_review":
        state.val_review_enabled = True
    elif outcome == "escalate":
        # The escalation itself is gated: BLOCKED means a human wants to look
        # before the loop even parks the change as escalated.
        context = {
            "gate_verdict": outcome,
            "gate_signals": _signal_summary(state.gate_signals),
        }
        decision = gates.evaluate(Gate.GATEKEEPER_ESCALATION, context)
        gates.record(state, decision, phase="GATEKEEPER")
        if not decision.proceed:
            return gates.park(
                state,
                decision,
                phase="GATEKEEPER",
                context=context,
                edge={"outcome": outcome, "target": "ESCALATE"},
            )
        # Route through the escalation helper so previous_phase and
        # escalation_reason are populated. The bare table transition
        # (GATEKEEPER -> ESCALATE) would leave both unset, making the saved
        # state unhelpful and causing transition() to raise on the
        # ESCALATE "resolved" -> _previous_phase resume path.
        enter_escalate(
            state,
            "GATEKEEPER judged the change unverifiable or too risky for autonomous execution",
        )
    return outcome


def _signal_summary(signals: dict[str, Any]) -> str:
    """The risk signals that are set, as one operator-readable line."""
    present = sorted(k for k, v in signals.items() if v)
    return ", ".join(present) if present else "none"


def _phase_plan(
    state: LoopState,
    change_dir: Path,
    plan_fn: Callable[[LoopState], str] | None,
    gates: _GateSession | None = None,
) -> str | None:
    """Check for existing proposal or delegate to plan callback, then gate it."""
    gates = gates or _fallback_gate_session(state)
    proposal_path = change_dir / "proposal.md"
    if proposal_path.exists():
        outcome = "exists"
    elif plan_fn is not None:
        outcome = plan_fn(state)
    else:
        # No callback and no existing proposal — stub returns "created"
        outcome = "created"

    if outcome not in ("exists", "created"):
        return outcome

    # A proposal now exists; leaving PLAN commits the run to implementing it,
    # so this is the human's approve-the-plan checkpoint.
    context = {
        "proposal_path": str(proposal_path),
        # Which way the proposal arrived: pre-existing on disk, or authored by
        # this run's plan callback. The operator needs to know which they are
        # approving.
        "approach": outcome,
    }
    decision = gates.evaluate(Gate.PROPOSAL_APPROVAL, context)
    gates.record(state, decision, phase="PLAN")
    if not decision.proceed:
        return gates.park(
            state,
            decision,
            phase="PLAN",
            context=context,
            edge={"outcome": outcome, "target": "PLAN_ITERATE"},
        )
    return outcome


def _phase_iterate(
    state: LoopState,
    iterate_fn: Callable[[LoopState], str] | None,
) -> str:
    """Delegate to iterate callback (self-review loop). Always runs."""
    state.phase_started_at = _now_iso()
    if iterate_fn is not None:
        return iterate_fn(state)
    # No callback — stub returns "complete" (iterate is a no-op without a callback)
    return "complete"


_PHASE_TO_REVIEW_TYPE: dict[str, str] = {
    "PLAN_REVIEW": "plan",
    "IMPL_REVIEW": "implementation",
    "VAL_REVIEW": "implementation",
}


def _phase_review(
    state: LoopState,
    change_dir: Path,
    worktree_path: Path,
    converge_fn: Callable[..., Any] | None,
    fix_mode: str,
    post_fix_validator_fn: Callable[[Path], list[str]] | None = None,
) -> str:
    """Run a convergence review loop for the current review phase."""
    state.iteration += 1
    state.phase_started_at = _now_iso()

    if state.iteration > state.max_phase_iterations:
        state.iteration = 0
        return "max_iter"

    if converge_fn is not None:
        review_type = _PHASE_TO_REVIEW_TYPE.get(state.current_phase, "plan")
        converge_kwargs: dict[str, Any] = {
            "change_id": state.change_id,
            "review_type": review_type,
            "artifacts_dir": change_dir,
            "worktree_path": worktree_path,
            "fix_mode": fix_mode,
        }
        if post_fix_validator_fn is not None:
            converge_kwargs["post_fix_validator"] = post_fix_validator_fn
        result = converge_fn(**converge_kwargs)
        # Support both ConvergenceResult dataclass and dict
        converged = getattr(result, "converged", None)
        if converged is None and isinstance(result, dict):
            converged = result.get("converged", False)

        if isinstance(result, dict):
            findings_count = result.get("findings_count", 0)
            blocking = result.get("blocking_findings", [])
        else:
            # ConvergenceResult dataclass
            consensus = getattr(result, "consensus", None) or {}
            summary = consensus.get("summary", {}) if isinstance(consensus, dict) else {}
            findings_count = summary.get("total_unique_findings", 0)
            blocking = getattr(result, "escalate_findings", []) or []

        state.findings_trend.append(findings_count)
        state.blocking_findings = blocking

        if converged:
            state.iteration = 0
            return "converged"
        return "not_converged"

    # No converge function — assume converged
    state.iteration = 0
    return "converged"


def _phase_implement(
    state: LoopState,
    implement_fn: Callable[[LoopState], str] | None,
) -> str:
    """Delegate to implementation callback (stub if absent)."""
    state.phase_started_at = _now_iso()
    if implement_fn is not None:
        return implement_fn(state)
    return "complete"


def _phase_validate(
    state: LoopState,
    validate_fn: Callable[[LoopState], str] | None,
) -> str:
    """Delegate to validation callback (stub if absent) and record the evidence."""
    state.phase_started_at = _now_iso()
    outcome = validate_fn(state) if validate_fn is not None else "passed"
    # The goal gate at DONE needs a VALIDATE record from THIS run to bind the
    # validation report to it (design D5 condition b). Cross-process runs get
    # that record from `runner.py apply-outcome`; an in-process run_loop has no
    # other writer, so without this line the goal gate could never pass and DONE
    # would be unreachable for the in-process driver.
    state.phase_history.append({"phase": "VALIDATE", "outcome": outcome, "at": _now_iso()})
    return outcome


def _phase_submit_pr(
    state: LoopState,
    submit_pr_fn: Callable[[LoopState], str] | None,
    gates: _GateSession | None = None,
) -> str | None:
    """Gate PR creation, delegate to the callback, then gate merge authorization."""
    gates = gates or _fallback_gate_session(state)
    state.phase_started_at = _now_iso()
    # D7: state-only phases must still record phase_archetype.
    _resolve_phase_archetype_for_state_only(state, "SUBMIT_PR")

    branch = f"openspec/{state.change_id}" if state.change_id else ""
    pr_context = {"branch": branch, "change_id": state.change_id}
    # Before the side effect, not after: a blocked pr_creation gate must mean no
    # PR exists.
    pr_decision = gates.evaluate(Gate.PR_CREATION, pr_context)
    gates.record(state, pr_decision, phase="SUBMIT_PR")
    if not pr_decision.proceed:
        # No `edge`: approving PR creation authorizes work *inside* SUBMIT_PR,
        # it does not move a phase, so gate-answer records it and stops there.
        return gates.park(state, pr_decision, phase="SUBMIT_PR", context=pr_context)

    outcome = submit_pr_fn(state) if submit_pr_fn is not None else "created"
    if outcome != "created":
        return outcome

    # The loop NEVER merges (ri-12 owns headless merge; /cleanup-feature is the
    # merge executor). This gate records the authorization and nothing else.
    merge_context = {
        "pr_url": _pr_url(state),
        "branch": branch,
        "change_id": state.change_id,
    }
    merge_decision = gates.evaluate(Gate.MERGE, merge_context)
    gates.record(
        state,
        merge_decision,
        phase="SUBMIT_PR",
        extra=(
            {"merge_authorized": True, "pr_url": merge_context["pr_url"]}
            if merge_decision.proceed
            else None
        ),
    )
    if not merge_decision.proceed:
        return gates.park(
            state,
            merge_decision,
            phase="SUBMIT_PR",
            context=merge_context,
            edge={"outcome": outcome, "target": "DONE"},
        )
    record_merge_authorization(state, merge_context["pr_url"])
    return outcome


def record_merge_authorization(state: LoopState, pr_url: str | None) -> None:
    """Record that merge was authorized — the loop never merges (design D2).

    Written into ``goal_gate.evidence`` so the authorization travels with the
    DONE verdict; ``_check_done_evidence`` merges the goal gate's own evidence
    on top rather than replacing it.
    """
    state.goal_gate = {
        "verdict": "pending",
        "reason": "merge authorized; DONE evidence not yet checked",
        "evidence": {"merge_authorized": True, "pr_url": pr_url},
    }


def _pr_url(state: LoopState) -> str | None:
    """The PR URL, when this run recorded one.

    ``submit_pr_fn`` returns an outcome string, not a URL, so the loop only
    knows the URL if a phase_history entry carried it (the cross-process path
    writes one via `apply-outcome --note`). None is a legitimate answer and the
    gate context/audit record keep the key either way so the shape is stable.
    """
    for entry in reversed(state.phase_history):
        if not isinstance(entry, dict) or entry.get("phase") != "SUBMIT_PR":
            continue
        note = entry.get("note")
        if isinstance(note, str) and "http" in note:
            return note[note.index("http") :].split()[0]
    return None


def _phase_escalate(
    state: LoopState,
    gate_check_fn: Callable[[LoopState], bool] | None,
    gates: _GateSession | None = None,
) -> str | None:
    """Gate the ESCALATE resume edge. Return None to pause.

    ``gate_check_fn`` (the coordinator poll) stays a pre-condition: an explicit
    "not resolved yet" means there is nothing to ask a human about. With no
    poller wired, the approval gate IS the resolution signal — which is the
    point of replacing the old ``return False`` stub.
    """
    gates = gates or _fallback_gate_session(state)
    if gate_check_fn is not None and not check_escalation_resolved(state, gate_check_fn):
        return None

    context = {
        "escalation_reason": state.escalation_reason or "",
        "previous_phase": state.previous_phase or "",
    }
    decision = gates.evaluate(Gate.ESCALATE_RESUME, context)
    gates.record(state, decision, phase="ESCALATE")
    if not decision.proceed:
        # Stay in ESCALATE — caller saves and breaks
        return gates.park(
            state,
            decision,
            phase="ESCALATE",
            context=context,
            edge={"outcome": "resolved", "target": state.previous_phase or ""},
        )
    return "resolved"


# ---------------------------------------------------------------------------
# Handoff helper
# ---------------------------------------------------------------------------

_HANDOFF_BOUNDARIES: set[tuple[str, str]] = {
    ("PLAN_ITERATE", "PLAN_REVIEW"),
    ("PLAN_ITERATE", "IMPLEMENT"),
    ("PLAN_REVIEW", "IMPLEMENT"),
    ("IMPL_ITERATE", "IMPL_REVIEW"),
    ("IMPL_ITERATE", "VALIDATE"),
    ("IMPL_REVIEW", "VALIDATE"),
    ("VALIDATE", "VAL_REVIEW"),
    ("VAL_REVIEW", "SUBMIT_PR"),
    ("VALIDATE", "SUBMIT_PR"),
}


def _maybe_handoff(
    prev_phase: str,
    next_phase: str,
    state: LoopState,
    handoff_fn: Callable[[LoopState, Any], str | None] | None,
    token_meter_fn: Callable[[LoopState, str, str, str], None] | None = None,
) -> None:
    """Dispatch a structured PhaseRecord handoff at known boundaries.

    Builds a PhaseRecord summarizing the just-completed prev_phase via
    handoff_builder.build_phase_record, calls handoff_fn(state, record),
    and records the returned handoff_id (if any) on the state.

    handoff_fn signature: ``Callable[[LoopState, PhaseRecord], str | None]``
    where the return is the coordinator-issued handoff_id (or local
    fallback marker), or None if no id could be recorded.

    token_meter_fn signature:
        ``Callable[[LoopState, event_type, prev_phase, next_phase], None]``
    The driver calls it twice per boundary: once with event_type=
    "phase_token_pre" before the handoff, and once with "phase_token_post"
    after. Implementations typically call ``phase_token_meter.measure_context``
    against the current driver context and emit an audit entry to the
    coordinator. Failures inside token_meter_fn are caught and logged
    (token instrumentation must never crash the loop — D9).
    """
    if handoff_fn is None:
        return
    if (prev_phase, next_phase) not in _HANDOFF_BOUNDARIES:
        return

    if token_meter_fn is not None:
        try:
            token_meter_fn(state, "phase_token_pre", prev_phase, next_phase)
        except Exception as exc:  # noqa: BLE001
            logger.warning("token_meter_fn (pre) failed: %s", exc)

    try:
        from handoff_builder import build_phase_record  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "handoff_builder not importable; skipping structured handoff at %s -> %s",
            prev_phase,
            next_phase,
        )
        return
    record = build_phase_record(state, prev_phase, next_phase)
    handoff_id = handoff_fn(state, record)
    if isinstance(handoff_id, str) and handoff_id:
        state.handoff_ids.append(handoff_id)
        state.last_handoff_id = handoff_id

    if token_meter_fn is not None:
        try:
            token_meter_fn(state, "phase_token_post", prev_phase, next_phase)
        except Exception as exc:  # noqa: BLE001
            logger.warning("token_meter_fn (post) failed: %s", exc)
