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
    """

    schema_version: int = 4
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

    Migrates older snapshots forward (D7): v2 files load with
    ``phase_archetype = None`` and ``schema_version = 3``; the migration is
    persisted on the next ``save_state`` call.
    """
    data = json.loads(Path(path).read_text())
    state = LoopState(
        **{k: v for k, v in data.items() if k in LoopState.__dataclass_fields__}
    )
    # Forward migration: bump schema_version on load so callers see the current
    # shape immediately. New fields (phase_archetype, force, gate_signals,
    # gate_verdict) default via the dataclass; the bump persists on next save.
    if state.schema_version < 4:
        state.schema_version = 4
    return state


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
        status_fn, state, "status.escalated",
        f"Escalated: {reason}", urgent=True,
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
        "--change-id", change_id,
        "--phase", phase,
        "--outcome", outcome,
        "--handoff-id", handoff_id,
    ]
    if allow_phase_mismatch:
        cmd.append("--allow-phase-mismatch")
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        logger.warning(
            "apply-outcome exited %d for phase=%s change=%s: %s",
            completed.returncode, phase, change_id, completed.stderr.strip(),
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
        history.append({
            "phase": phase,
            "outcome": "apply_outcome_failed",
            "at": _now_iso(),
            "note": (
                f"runner.py apply-outcome exited {rc}; handoff {handoff_id} "
                f"retained un-applied. Resolve the underlying cause and resume."
            ),
        })
        raw["phase_history"] = history
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
                    status_fn, load_state(path), "status.escalated",
                    f"apply-outcome failed for {phase}; escalated", urgent=True,
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
            rc, exc, handoff_id, change_id,
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
            phase, exc,
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


def _apply_transition(
    state: LoopState,
    outcome: str,
    status_fn: Callable[[LoopState, str, str, bool], None] | None = None,
) -> LoopState:
    """Compute and apply the transition, updating bookkeeping fields."""
    old_phase = state.current_phase
    next_phase = transition(state, outcome)
    state.current_phase = next_phase
    state.phase_started_at = _now_iso()
    state.total_iterations += 1
    _safe_status_call(
        status_fn, state, "phase.transition",
        f"Phase {old_phase} -> {next_phase}", urgent=False,
    )
    return state


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
            state.current_phase, state.total_iterations,
        )
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
            )
        except Exception as exc:
            logger.error("Phase %s raised: %s", phase, exc)
            state.error = str(exc)
            enter_escalate(state, f"Exception in {phase}: {exc}", status_fn=status_fn)
            save_state(state, state_path)
            break

        if outcome is None:
            # Phase signalled "stay" (e.g. unresolved escalation)
            save_state(state, state_path)
            break

        # If phase handler already changed the phase (e.g. enter_escalate),
        # skip the normal transition — just save and continue.
        if state.current_phase != phase:
            save_state(state, state_path)
            continue

        prev_phase = state.current_phase
        _apply_transition(state, outcome, status_fn=status_fn)

        # Write handoff at major boundaries (with optional token instrumentation)
        _maybe_handoff(
            prev_phase, state.current_phase, state, handoff_fn,
            token_meter_fn=token_meter_fn,
        )

        save_state(state, state_path)

    # Report DONE status
    if state.current_phase == "DONE":
        _safe_status_call(
            status_fn, state, "phase.transition",
            f"Loop completed for {change_id}", urgent=False,
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
) -> str | None:
    """Run a single phase and return the outcome string, or None to pause."""
    phase = state.current_phase

    if phase == "INIT":
        return _phase_init(state, change_dir, assess_complexity_fn)

    if phase == "GATEKEEPER":
        return _phase_gatekeeper(state, gatekeeper_fn)

    if phase == "PLAN":
        return _phase_plan(state, change_dir, plan_fn)

    if phase == "PLAN_ITERATE":
        return _phase_iterate(state, iterate_plan_fn)

    if phase == "PLAN_REVIEW":
        return _phase_review(
            state, change_dir, worktree_path, converge_fn,
            fix_mode="inline", post_fix_validator_fn=post_fix_validator_fn,
        )

    if phase == "PLAN_FIX":
        # Plan fixes are handled inline by the convergence loop; if we land
        # here the prior convergence round did not converge — retry review.
        return "fixed"

    if phase == "IMPLEMENT":
        return _phase_implement(state, implement_fn)

    if phase == "IMPL_ITERATE":
        return _phase_iterate(state, iterate_impl_fn)

    if phase == "IMPL_REVIEW":
        return _phase_review(
            state, change_dir, worktree_path, converge_fn,
            fix_mode="targeted", post_fix_validator_fn=post_fix_validator_fn,
        )

    if phase == "IMPL_FIX":
        return "fixed"

    if phase == "VALIDATE":
        return _phase_validate(state, validate_fn)

    if phase == "VAL_REVIEW":
        return _phase_review(
            state, change_dir, worktree_path, converge_fn,
            fix_mode="targeted", post_fix_validator_fn=post_fix_validator_fn,
        )

    if phase == "VAL_FIX":
        return "fixed"

    if phase == "SUBMIT_PR":
        return _phase_submit_pr(state, submit_pr_fn)

    if phase == "ESCALATE":
        return _phase_escalate(state, gate_check_fn)

    if phase == "DONE":
        return None

    raise ValueError(f"Unknown phase {phase!r}")


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

_GATEKEEPER_OUTCOMES: frozenset[str] = frozenset(
    {"proceed", "proceed_with_review", "escalate"}
)


def _default_gate_verdict(signals: dict[str, Any]) -> str:
    """Permissive verdict from signals alone — never escalates."""
    if any(bool(signals.get(k)) for k in _RISK_SIGNAL_KEYS):
        return "proceed_with_review"
    return "proceed"


def _phase_gatekeeper(
    state: LoopState,
    gatekeeper_fn: Callable[[LoopState], str] | None,
) -> str:
    """Judge whether the change is verifiable and low-risk enough to automate.

    The judge sub-agent reads ``state.gate_signals`` plus the plan artifacts and
    returns ``proceed`` / ``proceed_with_review`` / ``escalate``. When no judge
    is wired (headless CI, coordinator down, unit tests) the gate falls back to
    a permissive signal-only verdict rather than blocking.
    """
    state.phase_started_at = _now_iso()

    outcome: str | None = None
    if gatekeeper_fn is not None:
        outcome = gatekeeper_fn(state)
    if outcome not in _GATEKEEPER_OUTCOMES:
        # No judge, or an unrecognized verdict — degrade permissively.
        outcome = _default_gate_verdict(state.gate_signals)

    state.gate_verdict = outcome
    if outcome == "proceed_with_review":
        state.val_review_enabled = True
    elif outcome == "escalate":
        # Route through the escalation helper so previous_phase and
        # escalation_reason are populated. The bare table transition
        # (GATEKEEPER -> ESCALATE) would leave both unset, making the saved
        # state unhelpful and causing transition() to raise on the
        # ESCALATE "resolved" -> _previous_phase resume path.
        enter_escalate(
            state,
            "GATEKEEPER judged the change unverifiable or too risky for "
            "autonomous execution",
        )
    return outcome


def _phase_plan(
    state: LoopState,
    change_dir: Path,
    plan_fn: Callable[[LoopState], str] | None,
) -> str:
    """Check for existing proposal or delegate to plan callback."""
    proposal_path = change_dir / "proposal.md"
    if proposal_path.exists():
        return "exists"

    if plan_fn is not None:
        return plan_fn(state)

    # No callback and no existing proposal — stub returns "created"
    return "created"


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
    """Delegate to validation callback (stub if absent)."""
    state.phase_started_at = _now_iso()
    if validate_fn is not None:
        return validate_fn(state)
    return "passed"


def _phase_submit_pr(
    state: LoopState,
    submit_pr_fn: Callable[[LoopState], str] | None,
) -> str:
    """Delegate to PR submission callback (stub if absent)."""
    state.phase_started_at = _now_iso()
    # D7: state-only phases must still record phase_archetype.
    _resolve_phase_archetype_for_state_only(state, "SUBMIT_PR")
    if submit_pr_fn is not None:
        return submit_pr_fn(state)
    return "created"


def _phase_escalate(
    state: LoopState,
    gate_check_fn: Callable[[LoopState], bool] | None,
) -> str | None:
    """Check whether escalation has been resolved. Return None to pause."""
    if check_escalation_resolved(state, gate_check_fn):
        return "resolved"
    # Stay in ESCALATE — caller should save and break
    return None


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
            prev_phase, next_phase,
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
