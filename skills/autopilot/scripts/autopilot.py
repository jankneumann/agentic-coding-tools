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
    """Persistent state for the autopilot loop."""

    schema_version: int = 1
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
    started_at: str = ""
    phase_started_at: str = ""
    previous_phase: str | None = None
    escalation_reason: str | None = None
    val_review_enabled: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def save_state(state: LoopState, path: str | Path) -> None:
    """Serialize *state* to JSON at *path*."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(state), indent=2) + "\n")


def load_state(path: str | Path) -> LoopState:
    """Deserialize a LoopState from the JSON file at *path*."""
    data = json.loads(Path(path).read_text())
    return LoopState(**{k: v for k, v in data.items() if k in LoopState.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

TRANSITIONS: dict[str, dict[str, str]] = {
    "INIT": {"next": "PLAN"},
    "PLAN": {"exists": "PLAN_REVIEW", "created": "PLAN_REVIEW", "failed": "ESCALATE"},
    "PLAN_REVIEW": {"converged": "IMPLEMENT", "not_converged": "PLAN_FIX", "max_iter": "ESCALATE"},
    "PLAN_FIX": {"fixed": "PLAN_REVIEW", "stuck": "ESCALATE"},
    "IMPLEMENT": {"complete": "IMPL_REVIEW", "failed": "ESCALATE"},
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
# Callback protocol (optional typing aid for callers)
# ---------------------------------------------------------------------------

class PhaseFn(Protocol):
    """Signature for phase callback functions."""

    def __call__(self, state: LoopState, **kwargs: Any) -> str:
        """Execute phase work and return an outcome string."""
        ...


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
    implement_fn: Callable[[LoopState], str] | None = None,
    validate_fn: Callable[[LoopState], str] | None = None,
    submit_pr_fn: Callable[[LoopState], str] | None = None,
    handoff_fn: Callable[[LoopState, str], None] | None = None,
    memory_fn: Callable[[LoopState, str], str | None] | None = None,
    gate_check_fn: Callable[[LoopState], bool] | None = None,
    converge_fn: Callable[..., Any] | None = None,
    assess_complexity_fn: Callable[..., Any] | None = None,
    status_fn: Callable[[LoopState, str, str, bool], None] | None = None,
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
    status_fn:
        Called on phase transitions and escalations to report status.
        Signature: ``(state, event_type, message, urgent) -> None``.
        Wrapped in try/except with 5s timeout — never crashes the loop.
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
        logger.info(
            "Resumed loop state at phase=%s iteration=%d",
            state.current_phase, state.total_iterations,
        )
    else:
        state = LoopState(
            change_id=change_id,
            started_at=_now_iso(),
            phase_started_at=_now_iso(),
        )
        logger.info("Created new loop state for %s", change_id)

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
                implement_fn=implement_fn,
                validate_fn=validate_fn,
                submit_pr_fn=submit_pr_fn,
                handoff_fn=handoff_fn,
                memory_fn=memory_fn,
                gate_check_fn=gate_check_fn,
                converge_fn=_converge,
                assess_complexity_fn=_assess,
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

        # Write handoff at major boundaries
        _maybe_handoff(prev_phase, state.current_phase, state, handoff_fn)

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
    implement_fn: Callable[[LoopState], str] | None,
    validate_fn: Callable[[LoopState], str] | None,
    submit_pr_fn: Callable[[LoopState], str] | None,
    handoff_fn: Callable[[LoopState, str], None] | None,
    memory_fn: Callable[[LoopState, str], str | None] | None,
    gate_check_fn: Callable[[LoopState], bool] | None,
    converge_fn: Callable[..., Any] | None,
    assess_complexity_fn: Callable[..., Any] | None,
) -> str | None:
    """Run a single phase and return the outcome string, or None to pause."""
    phase = state.current_phase

    if phase == "INIT":
        return _phase_init(state, change_dir, assess_complexity_fn)

    if phase == "PLAN":
        return _phase_plan(state, change_dir, plan_fn)

    if phase == "PLAN_REVIEW":
        return _phase_review(state, change_dir, worktree_path, converge_fn, fix_mode="inline")

    if phase == "PLAN_FIX":
        # Plan fixes are handled inline by the convergence loop; if we land
        # here the prior convergence round did not converge — retry review.
        return "fixed"

    if phase == "IMPLEMENT":
        return _phase_implement(state, implement_fn)

    if phase == "IMPL_REVIEW":
        return _phase_review(state, change_dir, worktree_path, converge_fn, fix_mode="targeted")

    if phase == "IMPL_FIX":
        return "fixed"

    if phase == "VALIDATE":
        return _phase_validate(state, validate_fn)

    if phase == "VAL_REVIEW":
        return _phase_review(state, change_dir, worktree_path, converge_fn, fix_mode="targeted")

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
    """Run complexity assessment and configure the loop accordingly."""
    state.phase_started_at = _now_iso()

    if assess_complexity_fn is not None:
        wp_path = change_dir / "work-packages.yaml"
        proposal_path = change_dir / "proposal.md"
        result = assess_complexity_fn(
            work_packages_path=wp_path,
            proposal_path=proposal_path if proposal_path.exists() else None,
        )
        # Support both GateResult dataclass and dict
        force_required = getattr(result, "force_required", None)
        if force_required is None and isinstance(result, dict):
            force_required = result.get("force_required", False)
        val_review = getattr(result, "val_review_enabled", None)
        if val_review is None and isinstance(result, dict):
            val_review = result.get("val_review_enabled", False)

        if force_required:
            warnings = getattr(result, "warnings", [])
            if isinstance(result, dict):
                warnings = result.get("warnings", [])
            enter_escalate(
                state,
                f"Complexity gate: force_required — {'; '.join(warnings)}",
            )
            return "next"  # will be overridden by escalate
        state.val_review_enabled = bool(val_review)
    return "next"


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
) -> str:
    """Run a convergence review loop for the current review phase."""
    state.iteration += 1
    state.phase_started_at = _now_iso()

    if state.iteration > state.max_phase_iterations:
        state.iteration = 0
        return "max_iter"

    if converge_fn is not None:
        review_type = _PHASE_TO_REVIEW_TYPE.get(state.current_phase, "plan")
        result = converge_fn(
            change_id=state.change_id,
            review_type=review_type,
            artifacts_dir=change_dir,
            worktree_path=worktree_path,
            fix_mode=fix_mode,
        )
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
    ("PLAN_REVIEW", "IMPLEMENT"),
    ("IMPL_REVIEW", "VALIDATE"),
    ("VALIDATE", "VAL_REVIEW"),
    ("VAL_REVIEW", "SUBMIT_PR"),
    ("VALIDATE", "SUBMIT_PR"),
}


def _maybe_handoff(
    prev_phase: str,
    next_phase: str,
    state: LoopState,
    handoff_fn: Callable[[LoopState, str], None] | None,
) -> None:
    if handoff_fn is None:
        return
    if (prev_phase, next_phase) in _HANDOFF_BOUNDARIES:
        desc = f"Transition {prev_phase} -> {next_phase} for {state.change_id}"
        handoff_fn(state, desc)
