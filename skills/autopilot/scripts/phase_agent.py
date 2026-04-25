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
import os
import sys
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).resolve().parent
_SESSION_LOG_SCRIPTS = _THIS_DIR.parent.parent / "session-log" / "scripts"
if str(_SESSION_LOG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SESSION_LOG_SCRIPTS))

# Bridge for the per-phase archetype resolution endpoint (OpenSpec
# add-per-phase-archetype-resolution; design D4). Imported lazily at module
# load so tests can monkeypatch try_resolve_archetype_for_phase.
_BRIDGE_SCRIPTS = _THIS_DIR.parent.parent / "coordination-bridge" / "scripts"
if str(_BRIDGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_SCRIPTS))

import coordination_bridge  # type: ignore[import-not-found]  # noqa: E402
from phase_record import PhaseRecord  # noqa: E402

# ---------------------------------------------------------------------------
# Per-phase runtime config
# ---------------------------------------------------------------------------

# Phases that run in their own worktree (D7).
_WORKTREE_PHASES: set[str] = {"IMPLEMENT"}

# Crash-recovery cap (D8).
_MAX_ATTEMPTS = 3

# Per-phase signal keys to lift from state_dict for the coordinator's
# resolve_archetype_for_phase endpoint (design D12). Mirrors the `signals`
# field in agent-coordinator/archetypes.yaml -> phase_mapping. Keep this
# list synchronized with that YAML when phase semantics change.
_PHASE_SIGNAL_KEYS: dict[str, list[str]] = {
    "INIT":         [],
    "PLAN":         ["capabilities_touched"],
    "PLAN_ITERATE": ["capabilities_touched", "iteration_count"],
    "PLAN_REVIEW":  ["proposal_loc", "capabilities_touched"],
    "PLAN_FIX":     ["findings_severity", "findings_count"],
    "IMPLEMENT":    ["loc_estimate", "write_allow", "dependencies", "complexity"],
    "IMPL_ITERATE": ["iteration_count", "write_allow"],
    "IMPL_REVIEW":  ["files_changed", "lines_changed"],
    "IMPL_FIX":     ["findings_severity", "findings_count"],
    "VALIDATE":     ["test_count", "suite_duration"],
    "VAL_REVIEW":   ["findings_severity"],
    "VAL_FIX":      ["findings_severity"],
    "SUBMIT_PR":    [],
}

# Operator override env var (D8): "PHASE=model[,PHASE=model]*". Forces a
# specific model for the named phase; sets options["model"] only — the
# system_prompt is left to the harness default to keep override behavior
# predictable.
_PHASE_MODEL_OVERRIDE_ENV = "AUTOPILOT_PHASE_MODEL_OVERRIDE"


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
    options = _build_options(phase, state_dict)
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


def _extract_signals_for_phase(phase: str, state_dict: dict[str, Any]) -> dict[str, Any]:
    """Lift the per-phase signal keys from *state_dict*.

    Returns a dict containing only those keys listed in
    :data:`_PHASE_SIGNAL_KEYS` for *phase* and present in *state_dict*.
    Missing keys are silently dropped (per spec D12). Unknown phases get
    an empty dict — they pass no signals and the coordinator falls back
    to the archetype default model.
    """
    keys = _PHASE_SIGNAL_KEYS.get(phase, [])
    return {k: state_dict[k] for k in keys if k in state_dict}


def _parse_phase_model_override(raw: str | None) -> dict[str, str]:
    """Parse ``AUTOPILOT_PHASE_MODEL_OVERRIDE`` into ``{phase: model}``.

    Format: ``<PHASE>=<model>[,<PHASE>=<model>]*``. Whitespace around
    keys/values is tolerated. Per spec D8:

    - Empty input returns ``{}``.
    - Entries missing ``=`` are warned and skipped.
    - Unknown phase names (not in :data:`_PHASE_SIGNAL_KEYS`) are warned
      and skipped — typo protection.
    - Empty model values are warned and skipped.
    - Unknown model names pass through (validated downstream by the harness).
    """
    if not raw or not raw.strip():
        return {}
    out: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            logger.warning(
                "%s: malformed entry %r (missing '='); skipping",
                _PHASE_MODEL_OVERRIDE_ENV, entry,
            )
            continue
        phase, model = entry.split("=", 1)
        phase = phase.strip()
        model = model.strip()
        if phase not in _PHASE_SIGNAL_KEYS:
            logger.warning(
                "%s: unknown phase %r; skipping (known phases: %s)",
                _PHASE_MODEL_OVERRIDE_ENV, phase, sorted(_PHASE_SIGNAL_KEYS.keys()),
            )
            continue
        if not model:
            logger.warning(
                "%s: empty model for phase %r; skipping",
                _PHASE_MODEL_OVERRIDE_ENV, phase,
            )
            continue
        out[phase] = model
    return out


def _check_phase_model_override(phase: str) -> str | None:
    """Return the override model for *phase* if set in the env var, else None."""
    overrides = _parse_phase_model_override(os.environ.get(_PHASE_MODEL_OVERRIDE_ENV))
    return overrides.get(phase)


def _build_options(phase: str, state_dict: dict[str, Any]) -> dict[str, Any]:
    """Assemble sub-agent dispatch options for *phase*.

    Resolution order (precedence high → low):
      1. ``AUTOPILOT_PHASE_MODEL_OVERRIDE`` env var (D8) — sets ``model``
         only; leaves ``system_prompt`` to the harness default.
      2. Coordinator archetype resolution (D5) — sets both ``model`` and
         ``system_prompt`` from the resolved archetype, and records the
         archetype name in ``state_dict["_resolved_archetype"]`` so
         ``make_phase_callback`` can propagate it to ``LoopState.phase_archetype``.
      3. Bridge failure (D9) — leaves ``options`` without ``model`` /
         ``system_prompt``; the harness default applies; phase still
         dispatches normally.

    ``isolation="worktree"`` is set independently for phases in
    :data:`_WORKTREE_PHASES`.

    Mutates *state_dict* by writing ``_resolved_archetype`` only on the
    archetype-resolution path (path 2). The override path (path 1) does
    NOT record an archetype because the operator's choice carries no
    archetype semantics.
    """
    options: dict[str, Any] = {}
    if phase in _WORKTREE_PHASES:
        options["isolation"] = "worktree"

    # Path 1: operator override
    override = _check_phase_model_override(phase)
    if override:
        options["model"] = override
        return options

    # Path 2: coordinator archetype resolution
    signals = _extract_signals_for_phase(phase, state_dict)
    resolved = coordination_bridge.try_resolve_archetype_for_phase(phase, signals)
    if resolved is not None:
        options["model"] = resolved["model"]
        options["system_prompt"] = resolved["system_prompt"]
        state_dict["_resolved_archetype"] = resolved["archetype"]
    # Path 3 (bridge None): leave options untouched. The bridge already
    # logs a structured warning; no need to double-log here.

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


# Per spec D6: every non-terminal phase has a _PHASE_TASKS entry. State-only
# phases (INIT, SUBMIT_PR per D13) use a None sentinel — they record their
# resolved archetype for audit (via the autopilot driver) but do not dispatch
# a sub-agent.
_PHASE_TASKS: dict[str, str | None] = {
    "INIT": None,  # D13: state-only — no sub-agent dispatch
    "PLAN": (
        "Run /plan-feature for the change described in state.change_id.\n"
        "Produce proposal.md, design.md, tasks.md, work-packages.yaml, and\n"
        "specs/. Return outcome 'created' (or 'exists' if already present),\n"
        "'failed' on unrecoverable error."
    ),
    "PLAN_ITERATE": (
        "Run /iterate-on-plan for state.change_id. Refine the proposal\n"
        "across completeness, clarity, feasibility, scope, consistency,\n"
        "testability, parallelizability, and assumptions axes. Return\n"
        "outcome 'complete' when refinements settle, 'failed' otherwise."
    ),
    "PLAN_REVIEW": (
        "Run /parallel-review-plan for state.change_id (multi-vendor plan\n"
        "review). Aggregate findings into a structured PhaseRecord. Return\n"
        "outcome 'converged' if no blocking findings, 'not_converged'\n"
        "otherwise, 'max_iter' once max_phase_iterations is exhausted."
    ),
    "PLAN_FIX": (
        "Apply review findings from the previous PLAN_REVIEW handoff via\n"
        "/iterate-on-plan in fix mode. Return outcome 'fixed' on success,\n"
        "'stuck' if findings cannot be resolved within the budget."
    ),
    "IMPLEMENT": (
        "Implement the next slice of work per tasks.md. Commit per task.\n"
        "Push commits to the feature branch. Return outcome 'continue' on\n"
        "success, 'escalate' on unrecoverable error."
    ),
    "IMPL_ITERATE": (
        "Run /iterate-on-implementation for state.change_id. Refine the\n"
        "implementation by fixing bugs, edge cases, and quality issues.\n"
        "Return outcome 'complete' when refinements settle, 'failed' otherwise."
    ),
    "IMPL_REVIEW": (
        "Run multi-vendor review against the implementation. Aggregate\n"
        "findings into a structured PhaseRecord. Return outcome 'converged'\n"
        "if no blocking findings, 'iterate' otherwise."
    ),
    "IMPL_FIX": (
        "Apply review findings from the previous IMPL_REVIEW handoff via\n"
        "/iterate-on-implementation in fix mode. Return outcome 'fixed'\n"
        "on success, 'stuck' if findings cannot be resolved within budget."
    ),
    "VALIDATE": (
        "Run validation phases (spec, evidence, deploy, smoke, security,\n"
        "e2e) per validate-feature. Aggregate results into a PhaseRecord.\n"
        "Return outcome 'continue' on PASS, 'escalate' on FAIL."
    ),
    "VAL_REVIEW": (
        "Review validation findings from the previous VALIDATE handoff.\n"
        "Identify blocking failures vs. acceptable warnings. Return outcome\n"
        "'converged' if validation passes critique, 'not_converged' otherwise."
    ),
    "VAL_FIX": (
        "Apply validation findings via /iterate-on-implementation focused\n"
        "on the specific failures (test fixes, security findings, etc.).\n"
        "Return outcome 'fixed' on success, 'stuck' otherwise."
    ),
    "SUBMIT_PR": None,  # D13: state-only — no sub-agent dispatch
}


def _phase_task_instructions(phase: str) -> str:
    """Return the task instruction string for *phase*.

    Falls back to a generic execute-and-report instruction for unknown
    phases (backward-compat with phase strings outside the registered
    13 non-terminal phases). State-only phases (None sentinel) get a
    short audit-only instruction; they should not be reaching this
    function under normal autopilot dispatch.
    """
    entry = _PHASE_TASKS.get(phase)
    if entry is None:
        if phase in _PHASE_TASKS:
            # State-only sentinel — emit a short audit-only instruction.
            return (
                f"Phase {phase} is a state-only transition. No sub-agent work.\n"
                "Return ('continue', '<audit-only-handoff-id>')."
            )
        return f"Execute phase {phase}. Return (outcome, handoff_id) on completion."
    return entry


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
        # D7: propagate the archetype name resolved by _build_options into
        # LoopState.phase_archetype for audit/observability. Override path
        # and bridge-failure path leave _resolved_archetype unset, so we
        # explicitly null the field for those cases (so downstream
        # observability surfaces "default-fallback" phases).
        if hasattr(state, "phase_archetype"):
            state.phase_archetype = state_dict.get("_resolved_archetype")
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
