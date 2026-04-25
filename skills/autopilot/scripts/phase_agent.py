"""Phase sub-agent dispatch with worktree isolation and crash recovery.

Wraps the harness ``Agent(...)`` invocation behind a dependency-injected
runner so the autopilot driver can call sub-agents for IMPLEMENT,
IMPL_REVIEW, and VALIDATE phases with bounded driver-side state delta.

Per design D6:
  - run_phase_subagent returns ONLY ``(outcome, handoff_id)`` to the driver.
  - The sub-agent transcript is consumed and discarded inside this module.
  - The next phase reads the structured PhaseRecord via ``read_handoff()``
    or the local fallback file.

Per design D7:
  - ``isolation="worktree"`` is set ONLY when phase == "IMPLEMENT".
  - IMPL_REVIEW and VALIDATE run in the shared checkout.

Per design D8:
  - On runner failure or malformed output, retry up to 3 times with the
    SAME incoming PhaseRecord (sub-agent reads partial state from disk).
  - After the third failure, write a phase-failed PhaseRecord to the
    coordinator and raise ``PhaseEscalationError``.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).resolve().parent
_SESSION_LOG_SCRIPTS = _THIS_DIR.parent.parent / "session-log" / "scripts"
if str(_SESSION_LOG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SESSION_LOG_SCRIPTS))

from phase_record import PhaseRecord  # noqa: E402

# ---------------------------------------------------------------------------
# Per-phase runtime config
# ---------------------------------------------------------------------------

# Phases that run in their own worktree (D7).
_WORKTREE_PHASES: set[str] = {"IMPLEMENT"}

# Crash-recovery cap (D8).
_MAX_ATTEMPTS = 3


class PhaseEscalationError(Exception):
    """Raised after the sub-agent fails the configured retry budget."""

    def __init__(
        self,
        phase: str,
        attempts: int,
        last_error: str,
    ) -> None:
        super().__init__(
            f"Phase {phase!r} failed {attempts} attempts; last error: {last_error}"
        )
        self.phase = phase
        self.attempts = attempts
        self.last_error = last_error


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------

SubagentRunner = Callable[..., tuple[str, str]]


def run_phase_subagent(
    *,
    phase: str,
    state_dict: dict[str, Any],
    incoming_handoff: PhaseRecord,
    subagent_runner: SubagentRunner,
    artifacts_manifest: list[str] | None = None,
    coordinator_writer: Any = None,
    max_attempts: int = _MAX_ATTEMPTS,
) -> tuple[str, str]:
    """Dispatch a phase sub-agent with bounded driver-visible delta.

    Args:
        phase: Phase id ("IMPLEMENT", "IMPL_REVIEW", "VALIDATE", ...).
        state_dict: Snapshot of LoopState fields the sub-agent prompt may
            reference (change_id, iteration, etc.). Passed by-value to
            keep the driver/sub-agent boundary explicit.
        incoming_handoff: PhaseRecord from the previous phase. Serialized
            into the prompt so the sub-agent can hydrate it via
            ``PhaseRecord.from_handoff_payload`` if needed.
        subagent_runner: Injected callable that actually invokes the
            harness Agent tool. Signature: ``(prompt, options) -> (outcome, handoff_id)``.
            In production the SKILL.md prompt layer provides a runner that
            calls Claude Code's ``Agent(...)`` and parses the result.
        artifacts_manifest: Optional list of repo-relative paths the
            sub-agent should read for context (proposal.md, design.md,
            tasks.md, etc.).
        coordinator_writer: Optional ``try_handoff_write``-shaped callable
            used by the failure path (D8) to record a phase-failed record
            before raising. Defaults to lazy-import via PhaseRecord.
        max_attempts: Override the retry budget. Default 3 per D8.

    Returns:
        ``(outcome, handoff_id)`` — the only two pieces of information
        propagated back to the driver. Transcript is consumed inside this
        function and never escapes.

    Raises:
        PhaseEscalationError: After ``max_attempts`` consecutive failures.
    """
    options = _build_options(phase)
    prompt = _build_prompt(phase, state_dict, incoming_handoff, artifacts_manifest)

    last_error = "no error captured"
    for attempt in range(1, max_attempts + 1):
        try:
            result = subagent_runner(prompt=prompt, options=options)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "phase_agent: %s attempt %d/%d raised: %s",
                phase, attempt, max_attempts, last_error,
            )
            continue

        outcome, handoff_id = _validate_result(result)
        if outcome is None or handoff_id is None:
            last_error = f"malformed runner result: {result!r}"
            logger.warning(
                "phase_agent: %s attempt %d/%d malformed: %s",
                phase, attempt, max_attempts, last_error,
            )
            continue

        return outcome, handoff_id

    # All attempts exhausted — write phase-failed record and raise (D8)
    _write_phase_failed_record(
        phase=phase,
        state_dict=state_dict,
        incoming_handoff=incoming_handoff,
        attempts=max_attempts,
        last_error=last_error,
        coordinator_writer=coordinator_writer,
    )
    raise PhaseEscalationError(phase, max_attempts, last_error)


# ---------------------------------------------------------------------------
# Prompt + options assembly
# ---------------------------------------------------------------------------


def _build_options(phase: str) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if phase in _WORKTREE_PHASES:
        options["isolation"] = "worktree"
    return options


def _build_prompt(
    phase: str,
    state_dict: dict[str, Any],
    incoming_handoff: PhaseRecord,
    artifacts_manifest: list[str] | None,
) -> str:
    """Assemble the standard sub-agent prompt scaffold.

    Three sections per D6:
      1. Phase + state context (machine-readable)
      2. Incoming PhaseRecord JSON (the structured handoff)
      3. Artifacts manifest (paths the sub-agent should read first)
    """
    incoming_json = json.dumps(incoming_handoff.to_handoff_payload(), indent=2)
    state_json = json.dumps(_safe_state_dict(state_dict), indent=2)

    parts = [
        f"# Autopilot Phase Sub-Agent — {phase}",
        "",
        "You are running as an autopilot phase sub-agent. Return exactly",
        "(outcome, handoff_id) when complete. Do not surface intermediate state.",
        "",
        "## Phase Context",
        "",
        "```json",
        state_json,
        "```",
        "",
        "## Incoming Handoff (previous phase's PhaseRecord)",
        "",
        "```json",
        incoming_json,
        "```",
        "",
    ]
    if artifacts_manifest:
        parts.append("## Artifacts Manifest")
        parts.append("")
        for path in artifacts_manifest:
            parts.append(f"- {path}")
        parts.append("")
    parts.append("## Phase Task")
    parts.append("")
    parts.append(_phase_task_instructions(phase))
    return "\n".join(parts)


def _safe_state_dict(state_dict: dict[str, Any]) -> dict[str, Any]:
    """Strip non-serializable values from state_dict so json.dumps succeeds."""
    out: dict[str, Any] = {}
    for k, v in state_dict.items():
        try:
            json.dumps(v)
        except (TypeError, ValueError):
            out[k] = repr(v)
        else:
            out[k] = v
    return out


_PHASE_TASKS: dict[str, str] = {
    "IMPLEMENT": (
        "Implement the next slice of work per tasks.md. Commit per task.\n"
        "Push commits to the feature branch. Return outcome 'continue' on\n"
        "success, 'escalate' on unrecoverable error."
    ),
    "IMPL_REVIEW": (
        "Run multi-vendor review against the implementation. Aggregate\n"
        "findings into a structured PhaseRecord. Return outcome 'converged'\n"
        "if no blocking findings, 'iterate' otherwise."
    ),
    "VALIDATE": (
        "Run validation phases (spec, evidence, deploy, smoke, security,\n"
        "e2e) per validate-feature. Aggregate results into a PhaseRecord.\n"
        "Return outcome 'continue' on PASS, 'escalate' on FAIL."
    ),
}


def _phase_task_instructions(phase: str) -> str:
    return _PHASE_TASKS.get(
        phase,
        f"Execute phase {phase}. Return (outcome, handoff_id) on completion.",
    )


# ---------------------------------------------------------------------------
# Result validation
# ---------------------------------------------------------------------------


def _validate_result(result: Any) -> tuple[str | None, str | None]:
    """Return (outcome, handoff_id) if shape matches, else (None, None)."""
    if not isinstance(result, tuple) or len(result) != 2:
        return None, None
    outcome, handoff_id = result
    if not isinstance(outcome, str) or not outcome:
        return None, None
    if not isinstance(handoff_id, str) or not handoff_id:
        return None, None
    return outcome, handoff_id


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------


def _write_phase_failed_record(
    *,
    phase: str,
    state_dict: dict[str, Any],
    incoming_handoff: PhaseRecord,
    attempts: int,
    last_error: str,
    coordinator_writer: Any,
) -> None:
    """Record a phase-failed PhaseRecord before raising PhaseEscalationError.

    Best-effort: failures inside this routine log a warning but do not
    suppress the escalation.
    """
    try:
        change_id = state_dict.get("change_id") or incoming_handoff.change_id
        record = PhaseRecord(
            change_id=change_id,
            phase_name=f"{phase} (failed)",
            agent_type="autopilot",
            summary=(
                f"Phase {phase} sub-agent failed after {attempts} attempts. "
                f"Last error: {last_error}"
            ),
            open_questions=[
                f"Why did {phase} fail repeatedly?",
                "Is the incoming handoff stale or malformed?",
            ],
        )
        record.write_both(coordinator_writer=coordinator_writer)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "phase_agent: writing phase-failed record raised: %s", exc,
        )


# ---------------------------------------------------------------------------
# Driver-facing wiring helper
# ---------------------------------------------------------------------------


def make_phase_callback(
    *,
    phase: str,
    subagent_runner: SubagentRunner,
    incoming_handoff_loader: Callable[[str | None], PhaseRecord] | None = None,
    artifacts_manifest: list[str] | None = None,
    coordinator_writer: Any = None,
) -> Callable[[Any], str]:
    """Produce an autopilot-compatible phase callback wrapping run_phase_subagent.

    The returned callback matches autopilot's existing callback signature
    ``(state) -> outcome`` while internally:
      1. Loading the incoming PhaseRecord from state.last_handoff_id
         (via incoming_handoff_loader, e.g. a coordinator read_handoff).
      2. Calling ``run_phase_subagent`` with the assembled prompt scaffold.
      3. Mutating ``state.last_handoff_id`` and ``state.handoff_ids`` with
         the returned handoff_id.
      4. Returning ONLY the outcome string to the driver.

    This realizes Layer 2 — the driver-side LoopState delta after the
    callback returns is bounded to ``last_handoff_id`` + one new entry in
    ``handoff_ids``. The sub-agent's transcript stays inside this module.

    Args:
        phase: Phase id to dispatch (e.g. "IMPLEMENT").
        subagent_runner: Runner that invokes the harness Agent tool.
        incoming_handoff_loader: ``Callable[[handoff_id | None], PhaseRecord]``
            used to hydrate the previous phase's record. The default loader
            constructs an empty bootstrap record when last_handoff_id is None
            (typical at the very first transition).
        artifacts_manifest: Optional repo-relative paths to include in the
            standard prompt scaffold.
        coordinator_writer: Forwarded to run_phase_subagent for the failure
            path's phase-failed record.

    Returns:
        ``(state) -> outcome`` callable suitable for use as
        ``implement_fn``, ``validate_fn``, or the IMPL_REVIEW phase wrapper
        in autopilot.run_loop.
    """
    loader = incoming_handoff_loader or _default_incoming_loader

    def callback(state: Any) -> str:
        last_id = getattr(state, "last_handoff_id", None)
        incoming = loader(last_id)
        state_change_id = getattr(state, "change_id", None)
        if incoming.change_id == "" and isinstance(state_change_id, str) and state_change_id:
            incoming.change_id = state_change_id

        state_dict = _state_snapshot(state)
        outcome, handoff_id = run_phase_subagent(
            phase=phase,
            state_dict=state_dict,
            incoming_handoff=incoming,
            subagent_runner=subagent_runner,
            artifacts_manifest=artifacts_manifest,
            coordinator_writer=coordinator_writer,
        )
        # Bounded driver-side state delta — D6
        state.last_handoff_id = handoff_id
        if hasattr(state, "handoff_ids"):
            state.handoff_ids.append(handoff_id)
        return outcome

    return callback


def _default_incoming_loader(handoff_id: str | None) -> PhaseRecord:
    """Bootstrap loader — returns an empty PhaseRecord when no prior handoff.

    Production use should pass a loader that calls ``read_handoff`` against
    the coordinator (or reads the local fallback file) and returns a
    hydrated PhaseRecord. This default exists so make_phase_callback works
    in tests without coordinator access.
    """
    return PhaseRecord(
        change_id="",
        phase_name="bootstrap",
        agent_type="autopilot",
        summary=(
            f"No incoming handoff (last_handoff_id={handoff_id!r}). "
            "Bootstrap phase entry."
        ),
    )


def _state_snapshot(state: Any) -> dict[str, Any]:
    """Extract a serializable snapshot of LoopState for the sub-agent prompt.

    Pulls only fields the sub-agent actually needs to reason about the
    phase. The sub-agent gets its work-context from the incoming handoff
    and on-disk artifacts, not from the LoopState directly — keeping the
    snapshot small reduces prompt-size pressure.
    """
    fields_of_interest = (
        "change_id",
        "current_phase",
        "iteration",
        "total_iterations",
        "max_phase_iterations",
        "findings_trend",
        "previous_phase",
    )
    out: dict[str, Any] = {}
    for name in fields_of_interest:
        if hasattr(state, name):
            out[name] = getattr(state, name)
    return out


__all__ = [
    "PhaseEscalationError",
    "make_phase_callback",
    "run_phase_subagent",
]
