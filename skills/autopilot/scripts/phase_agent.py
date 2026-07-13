"""Phase sub-agent dispatch with worktree isolation and crash recovery.

Wraps the harness ``Agent(...)`` invocation behind a dependency-injected
runner so the autopilot driver can call sub-agents for IMPLEMENT,
IMPL_REVIEW, and VALIDATE phases with bounded driver-side state delta.

Per design D6:
  - run_phase_subagent returns ONLY ``(outcome, handoff_id)`` to the driver.
  - The sub-agent transcript is consumed and discarded inside this module.
  - The next phase reads the structured PhaseRecord via ``read_handoff()``
    or the local fallback file.

Per local CLI mutation-boundary policy:
  - ``isolation="worktree"`` is set for every write-capable phase.
  - INIT and SUBMIT_PR remain state-only and do not dispatch sub-agents.

Per design D8:
  - On runner failure or malformed output, retry up to 3 times with the
    SAME incoming PhaseRecord (sub-agent reads partial state from disk).
  - After the third failure, write a phase-failed PhaseRecord to the
    coordinator and raise ``PhaseEscalationError``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """UTC ISO-8601 timestamp for phase_history entries."""
    return datetime.now(timezone.utc).isoformat()


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

# Phases that can write files, generated artifacts, review checkpoints,
# validation evidence, or fixes. In local CLI execution these must not run in
# the shared checkout; cloud harnesses may short-circuit worktree setup via
# EnvironmentProfile.detect().
_WORKTREE_PHASES: set[str] = {
    "PLAN",
    "PLAN_ITERATE",
    "PLAN_REVIEW",
    "PLAN_FIX",
    "IMPLEMENT",
    "IMPL_ITERATE",
    "IMPL_REVIEW",
    "IMPL_FIX",
    "VALIDATE",
    "VAL_REVIEW",
    "VAL_FIX",
}

# Crash-recovery cap (D8).
_MAX_ATTEMPTS = 3

# Per-phase signal keys to lift from state_dict for the coordinator's
# resolve_archetype_for_phase endpoint (design D12). Mirrors the `signals`
# field in agent-coordinator/archetypes.yaml -> phase_mapping. Keep this
# list synchronized with that YAML when phase semantics change.
_PHASE_SIGNAL_KEYS: dict[str, list[str]] = {
    "INIT":         [],
    "GATEKEEPER":   ["gate_signals"],
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


def _selected_provider(provider: str | None = None) -> str | None:
    """Resolve the active provider from explicit arg or runtime env."""
    raw = provider or os.environ.get("AUTOPILOT_PROVIDER") or os.environ.get("AGENT_TYPE")
    if not raw:
        return None
    normalized = raw.strip()
    if normalized == "claude":
        return "claude_code"
    return normalized or None


def _build_options(
    phase: str,
    state_dict: dict[str, Any],
    *,
    provider: str | None = None,
) -> dict[str, Any]:
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
    selected_provider = _selected_provider(provider)
    resolved = coordination_bridge.try_resolve_archetype_for_phase(
        phase,
        signals,
        provider=selected_provider,
    )
    if resolved is not None:
        options["model"] = resolved["model"]
        options["system_prompt"] = resolved["system_prompt"]
        state_dict["_resolved_archetype"] = resolved["archetype"]
        # write_capable is an optional passthrough from the coordinator (older
        # coordinators may omit it); surface it for build-dispatch metadata.
        if "write_capable" in resolved:
            state_dict["_resolved_write_capable"] = resolved["write_capable"]
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
    prohibitions = _state_mutation_prohibitions(phase, state_dict)
    if prohibitions:
        parts.append("")
        parts.append(prohibitions)
    return "\n".join(parts)


# Write-capable phases must carry the state-mutation prohibitions (Layers B+C).
# This set is exactly the write-capable phase list from design D7 and mirrors
# _WORKTREE_PHASES. State-only phases (INIT, SUBMIT_PR) and the read-only
# GATEKEEPER judge are intentionally excluded.
_STATE_MUTATION_PROHIBITION_PHASES: frozenset[str] = frozenset(_WORKTREE_PHASES)


def _state_mutation_prohibitions(phase: str, state_dict: dict[str, Any]) -> str:
    """Return the Layer B + Layer C state-mutation prohibition block for *phase*.

    Write-capable phases append two explicit prohibitions to the dispatch
    prompt (design D1 Layers B + C):

      - Layer B: the sub-agent MUST NOT run ``runner.py apply-outcome`` (or any
        other runner.py subcommand that mutates orchestrator state).
      - Layer C: the sub-agent MUST NOT edit ``loop-state.json`` by any means
        (python3 -c, sed, jq, or any other shell tool).

    Read-only / state-only phases get an empty string (no prohibition needed).
    """
    if phase not in _STATE_MUTATION_PROHIBITION_PHASES:
        return ""
    change_id = state_dict.get("change_id")
    loop_state_path = (
        f"openspec/changes/{change_id}/loop-state.json"
        if isinstance(change_id, str) and change_id
        else "openspec/changes/<id>/loop-state.json"
    )
    return "\n".join([
        "## Orchestrator State Ownership (do not violate)",
        "",
        "You return `(outcome, handoff_id)` and exit. The orchestrator — NOT you —",
        "owns every state transition. Specifically:",
        "",
        "- DO NOT run `runner.py apply-outcome` or any other `runner.py` subcommand",
        "  that modifies orchestrator state. The orchestrator runs apply-outcome",
        "  after you return.",
        f"- DO NOT edit `{loop_state_path}` by any means (python3 -c, sed, jq, or any",
        "  other shell tool). The orchestrator owns this file, including",
        "  `current_phase`. Editing it directly corrupts the loop.",
    ])


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
    "GATEKEEPER": (
        "You are the autopilot gatekeeper. Decide whether this change can run\n"
        "autonomously through implementation. Judge two things, NOT raw size:\n"
        "  1. VERIFIABILITY — can the intended outcomes be objectively checked?\n"
        "     Inspect state.gate_signals (has_specs, has_tasks, has_proposal,\n"
        "     has_work_packages) and the artifacts themselves. WHEN/THEN specs,\n"
        "     a task breakdown, and testable acceptance criteria make outcomes\n"
        "     verifiable; a vague description does not.\n"
        "  2. RISK — what is the blast radius and reversibility if a slice goes\n"
        "     wrong? Weigh has_db_migration, has_security_signal,\n"
        "     external_dep_count, and write scope.\n"
        "Account for autopilot's downstream safeguards: multi-vendor PLAN/IMPL\n"
        "review convergence, the VALIDATE phase, and a MANDATORY human merge\n"
        "gate (nothing reaches main without operator approval). Bias toward\n"
        "letting verifiable work proceed — large but well-specified changes are\n"
        "fine. Reserve escalation for work whose outcomes cannot be verified or\n"
        "whose risk is high AND hard to reverse.\n"
        "Return outcome 'proceed' for verifiable, acceptable-risk work;\n"
        "'proceed_with_review' to also enable the extra VAL_REVIEW phase; or\n"
        "'escalate' to stop for a human when outcomes are unverifiable or the\n"
        "risk is unacceptable."
    ),
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
        "Start by running /implement-feature so worktree.py can adopt the\n"
        "resolved feature parent branch. Do not merge the feature branch into\n"
        "a harness/default-branch checkout to get context; abort if branch\n"
        "adoption fails. Push commits to the feature branch. Return outcome\n"
        "'complete' on success, 'failed' on unrecoverable error."
    ),
    "IMPL_ITERATE": (
        "Run /iterate-on-implementation for state.change_id. Refine the\n"
        "implementation by fixing bugs, edge cases, and quality issues.\n"
        "Return outcome 'complete' when refinements settle, 'failed' otherwise."
    ),
    "IMPL_REVIEW": (
        "Run multi-vendor review against the implementation. Aggregate\n"
        "findings into a structured PhaseRecord. Return outcome 'converged'\n"
        "if no blocking findings, 'not_converged' if blocking findings need\n"
        "another round, or 'max_iter' if the iteration cap is exhausted."
    ),
    "IMPL_FIX": (
        "Apply review findings from the previous IMPL_REVIEW handoff via\n"
        "/iterate-on-implementation in fix mode. Return outcome 'fixed'\n"
        "on success, 'stuck' if findings cannot be resolved within budget."
    ),
    "VALIDATE": (
        "Run validation phases (spec, evidence, deploy, smoke, security,\n"
        "e2e) per validate-feature. Aggregate results into a PhaseRecord.\n"
        "Return outcome 'passed' on PASS, 'failed' on FAIL."
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


# ---------------------------------------------------------------------------
# Production-path helpers (wire-autopilot-phase-subagents)
#
# These two functions form the prose↔Python boundary used by SKILL.md per
# design D1/D2/D3/D4. They are invoked across separate process invocations
# (one for build-dispatch, one for apply-outcome), so all state lives on
# disk in `loop-state.json` plus a tiny per-run cache file.
# ---------------------------------------------------------------------------

# Fixed separator used to fold `system_prompt` into the dispatched prompt
# (D2). NOT parameterized — every dispatch in this skill uses this exact
# string and spec scenarios assert it verbatim.
_PROMPT_SEPARATOR = "\n\n---\n\n"

# OpenSpec change-id pattern (also enforced by OpenSpec itself). Rejects
# `..`, `/`, empty strings, oversized values, and non-ASCII characters
# before any path is constructed.
_CHANGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# Filename of the per-run resolution cache, written by build-dispatch and
# consumed (then deleted) by apply-outcome. Lives inside the change dir.
_RESOLUTION_CACHE_FILENAME = ".phase-resolution-cache.json"


def _validate_change_id(change_id: str) -> None:
    """Raise ValueError if *change_id* fails the OpenSpec pattern (D4)."""
    if not isinstance(change_id, str) or not _CHANGE_ID_PATTERN.match(change_id):
        raise ValueError(
            f"invalid change_id {change_id!r}: must match "
            f"{_CHANGE_ID_PATTERN.pattern!r} (no '..', '/', or non-ASCII)"
        )


def _change_dir(change_id: str) -> Path:
    """Return the absolute path to ``openspec/changes/<change_id>/``.

    Resolves against the current working directory and verifies the
    resolved path lives under ``<cwd>/openspec/changes/`` — defense in
    depth on top of the regex check in :func:`_validate_change_id`.
    """
    base = Path.cwd().resolve() / "openspec" / "changes"
    candidate = (base / change_id).resolve()
    if base != candidate.parent:
        # Defensive: the regex makes this unreachable, but verify anyway.
        raise ValueError(
            f"change_id {change_id!r} resolves outside openspec/changes/"
        )
    return candidate


def _cache_path(change_id: str) -> Path:
    return _change_dir(change_id) / _RESOLUTION_CACHE_FILENAME


def _state_path(change_id: str) -> Path:
    return _change_dir(change_id) / "loop-state.json"


def _checksum_for_cache(change_id: str, phase: str, archetype: str | None) -> str:
    """SHA-256 over change_id + phase + archetype (or 'null')."""
    arch_bytes = (archetype if archetype is not None else "null").encode("utf-8")
    h = hashlib.sha256()
    h.update(change_id.encode("utf-8"))
    h.update(phase.encode("utf-8"))
    h.update(arch_bytes)
    return h.hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write *payload* to *path* via tempfile + os.replace (atomic on POSIX).

    Guarantees: on any failure path the temp file is unlinked AND the
    underlying file descriptor is closed. The two have to be tracked
    separately because `os.fdopen` could (theoretically — extremely
    rare) raise after `mkstemp` returned, in which case the with-block
    never owns the fd and we'd leak it without an explicit close.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # nosec B108: dir= confines the tempfile to the target directory (not
    # /tmp), which is the canonical pattern for atomic same-fs replace.
    fd, tmp = tempfile.mkstemp(  # noqa: S108
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    fd_consumed = False
    try:
        fh = os.fdopen(fd, "w", encoding="utf-8")
        fd_consumed = True  # the file object now owns the fd
        try:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        finally:
            fh.close()
        os.replace(tmp, path)
    except Exception:
        # Two distinct cleanup concerns: an orphaned fd (only when
        # os.fdopen failed) and an orphaned tmp file (always).
        if not fd_consumed:
            try:
                os.close(fd)
            except OSError:
                # Best-effort fd cleanup; the original exception is re-raised
                # below, so silencing here only suppresses cleanup noise.
                pass  # nosec B110
        try:
            os.unlink(tmp)
        except OSError:
            # Best-effort tmp-file cleanup; the original exception is re-raised
            # below, so silencing here only suppresses cleanup noise.
            pass  # nosec B110
        raise


def _atomic_unlink(path: Path) -> None:
    """Atomically remove *path* by renaming to a sibling temp first.

    Per D4 cleanup-on-success: a crash mid-delete leaves the cache
    discoverable under a different name rather than half-deleted.
    """
    if not path.exists():
        return
    tmp = path.with_name(path.name + ".unlinking")
    try:
        os.replace(path, tmp)
    except OSError:
        # Best-effort fallback to direct unlink — the cache file may be
        # gone already (concurrent worker, manual cleanup), and that's fine.
        try:
            path.unlink()
        except OSError:
            pass  # nosec B110
        return
    try:
        tmp.unlink()
    except OSError:
        # The rename succeeded but the orphan unlink failed. Filesystem
        # GC or the next _atomic_unlink call will sweep the leftover.
        pass  # nosec B110


def _hydrate_incoming_handoff(
    change_id: str,
    last_handoff_id: str | None,
    current_phase: str,
) -> PhaseRecord:
    """Bootstrap a PhaseRecord for the prompt scaffold.

    Cross-process production path can't easily reach back into the
    coordinator for a structured handoff, so we synthesize a minimal
    bootstrap record. The sub-agent reads concrete state from disk
    artifacts (proposal.md, design.md, loop-state.json) anyway.
    """
    return PhaseRecord(
        change_id=change_id,
        phase_name=f"bootstrap (current_phase={current_phase})",
        agent_type="autopilot",
        summary=(
            f"Bootstrap incoming handoff for phase {current_phase!r} "
            f"(last_handoff_id={last_handoff_id!r}). The sub-agent should "
            "read on-disk artifacts for concrete prior context."
        ),
    )


def build_phase_dispatch_kwargs(
    phase: str,
    change_id: str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Return the dispatch payload for a phase sub-agent (D3).

    Side effect: writes ``openspec/changes/<change_id>/.phase-resolution-cache.json``
    so :func:`apply_phase_outcome` can later propagate the resolved
    archetype into ``LoopState.phase_archetype``.

    Args:
        phase: Phase id (e.g. "IMPLEMENT", "PLAN_ITERATE").
        change_id: OpenSpec change identifier. Must match
            ``^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`` (raises ``ValueError``
            otherwise — before any filesystem access).

    Returns:
        ``{prompt, model, system_prompt, isolation, archetype}``. ``prompt``
        is the **already-folded** final string SKILL.md passes verbatim
        to ``Agent(...)`` — no further concatenation in prose.
    """
    # Validation runs before any path construction to make path-traversal
    # attempts a hard fail rather than a partial side-effect.
    _validate_change_id(change_id)

    state_dict = _read_state_dict(change_id)
    state_dict["change_id"] = change_id  # ensure available for signal extraction
    current_phase = state_dict.get("current_phase", phase)
    last_handoff_id = state_dict.get("last_handoff_id")

    incoming = _hydrate_incoming_handoff(change_id, last_handoff_id, current_phase)

    # _build_options writes _resolved_archetype into state_dict on the
    # archetype path; we read it back below to populate the cache.
    selected_provider = _selected_provider(provider)
    options = _build_options(phase, state_dict, provider=selected_provider)
    phase_prompt = _build_prompt(phase, state_dict, incoming, artifacts_manifest=None)

    system_prompt = options.get("system_prompt")
    model = options.get("model")
    isolation = options.get("isolation")
    archetype = state_dict.get("_resolved_archetype")
    write_capable = state_dict.get("_resolved_write_capable")

    if isinstance(system_prompt, str) and system_prompt:
        folded_prompt = f"{system_prompt}{_PROMPT_SEPARATOR}{phase_prompt}"
    else:
        folded_prompt = phase_prompt

    # Cache write — atomic. Schema v1 per D4.
    cache_payload: dict[str, Any] = {
        "schema_version": 1,
        "change_id": change_id,
        "phase": phase,
        "archetype": archetype,
        "checksum": _checksum_for_cache(change_id, phase, archetype),
    }
    _atomic_write_json(_cache_path(change_id), cache_payload)

    return {
        "schema_version": 1,
        "change_id": change_id,
        "phase": phase,
        "provider": selected_provider,
        "prompt": folded_prompt,
        "model": model,
        "system_prompt": system_prompt,
        "isolation": isolation,
        "archetype": archetype,
        "write_capable": write_capable,
        "expected_outcomes": _expected_outcomes_for_phase(phase),
    }


def _expected_outcomes_for_phase(phase: str) -> list[str]:
    """Return allowed outcomes for a phase dispatch payload."""
    return {
        "GATEKEEPER": ["proceed", "proceed_with_review", "escalate"],
        "PLAN_ITERATE": ["complete", "failed"],
        "PLAN_REVIEW": ["converged", "not_converged", "max_iter"],
        "IMPLEMENT": ["complete", "failed"],
        "IMPL_ITERATE": ["complete", "failed"],
        "IMPL_REVIEW": ["converged", "not_converged", "max_iter"],
        "VALIDATE": ["passed", "failed"],
        "VAL_REVIEW": ["converged", "not_converged"],
    }.get(phase, ["complete", "failed"])


def build_phase_dispatch_payload(
    phase: str,
    change_id: str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Return a provider-neutral phase dispatch payload."""
    payload = build_phase_dispatch_kwargs(
        phase=phase,
        change_id=change_id,
        provider=provider,
    )
    if payload.get("provider") is None:
        payload["provider"] = "claude_code"
    return payload


def _read_state_dict(change_id: str) -> dict[str, Any]:
    """Load loop-state.json for *change_id*, returning a dict snapshot.

    Missing files yield a minimal dict with just `change_id` so the
    helper still functions during the very first phase (before
    autopilot has written the state file).
    """
    path = _state_path(change_id)
    if not path.exists():
        return {"change_id": change_id}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "phase_agent: failed to read %s (%s); falling back to bare state",
            path, exc,
        )
        return {"change_id": change_id}
    if isinstance(data, dict):
        return data
    return {"change_id": change_id}


def _read_cache(change_id: str) -> dict[str, Any] | None:
    """Read the resolution cache, returning None on any error or missing file."""
    path = _cache_path(change_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "phase_agent: failed to parse cache file %s (%s); treating as missing",
            path, exc,
        )
        return None
    if not isinstance(data, dict):
        return None
    return data


def apply_phase_outcome(
    change_id: str,
    phase: str,
    outcome: str,
    handoff_id: str,
    *,
    allow_phase_mismatch: bool = False,
) -> None:
    """Update loop-state.json after a phase sub-agent returns (D4).

    **No-transition contract (design D1 Layer A / Task 3):** this function
    updates ONLY the fields it owns — ``last_handoff_id``, ``handoff_ids``
    (append), ``phase_archetype``, and a new ``phase_history`` entry. It
    NEVER modifies ``current_phase``. The orchestrator is the sole writer
    of ``current_phase``.

    **Phase-mismatch guard (Task 3.2-3.4):** on the non-replay path, if
    *phase* does not equal loop-state's ``current_phase`` the call raises
    ``ValueError`` (surfaced as a non-zero exit by the runner CLI) unless
    *allow_phase_mismatch* is set. The escape hatch bypasses the guard for
    operator-conscious recovery; it does NOT relax the no-transition
    contract — ``current_phase`` is still left untouched.

    Idempotent: calling twice with the same arguments leaves the state
    unchanged (no duplicate handoff_id append, no archetype overwrite, no
    duplicate phase_history entry).

    Replay rule: if loaded ``state.last_handoff_id == handoff_id`` AND
    ``state.previous_phase == phase`` (or ``state.current_phase == phase``),
    treat as a replay — preserve ``phase_archetype``, skip the phase-mismatch
    guard, and skip cache validation entirely. The prior successful call
    deleted the cache, so a missing cache on replay is expected and SHALL
    NOT raise.

    Otherwise: validate cache change_id+phase+checksum, write
    ``phase_archetype`` from the cache (or None on any mismatch), append a
    ``phase_history`` entry, and atomically delete the cache.
    """
    _validate_change_id(change_id)

    state_path = _state_path(change_id)
    if not state_path.exists():
        # apply-outcome must RECORD the phase result (handoff id, phase history,
        # escalation state). A missing loop-state means it cannot — failing loud here
        # so `runner.py apply-outcome` exits non-zero and the escalation wrapper parks
        # the loop, rather than the orchestrator silently continuing with no record.
        raise ValueError(
            f"apply_phase_outcome: loop state {state_path} does not exist; "
            "cannot record phase outcome (escalating)"
        )

    try:
        state = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"apply_phase_outcome: failed to read/parse loop state {state_path} "
            f"({exc}); cannot record phase outcome (escalating)"
        ) from exc

    if not isinstance(state, dict):
        raise ValueError(
            f"apply_phase_outcome: loop state {state_path} is not a mapping "
            f"(got {type(state).__name__}); cannot record phase outcome (escalating)"
        )

    is_replay = (
        state.get("last_handoff_id") == handoff_id
        and (
            state.get("previous_phase") == phase
            or state.get("current_phase") == phase
        )
    )

    if is_replay:
        # Preserve phase_archetype, ensure handoff_ids has the id at most once.
        ids = state.get("handoff_ids")
        if isinstance(ids, list) and handoff_id not in ids:
            ids.append(handoff_id)
            state["handoff_ids"] = ids
        # Note: spec says replay should NOT cause an error or warning even
        # when the cache file is absent. We deliberately don't peek at it.
        _save_state(state_path, state)
        # Sweep any orphaned cache from a prior crashed run that left the
        # state.last_handoff_id correct but the cache on disk. Idempotent.
        _atomic_unlink(_cache_path(change_id))
        return

    # Phase-mismatch guard (Task 3.2-3.4). The orchestrator dispatches phase X
    # while current_phase == X and applies the outcome before transitioning, so
    # a mismatch means the caller is applying an outcome for the wrong phase.
    # current_phase is NEVER modified either way — the flag only bypasses the
    # guard, it does not enable a transition.
    current_phase = state.get("current_phase")
    if not allow_phase_mismatch and current_phase != phase:
        raise ValueError(
            f"--phase {phase!r} does not match current_phase="
            f"{current_phase!r}. apply-outcome does not transition phases and "
            f"refuses to apply an outcome for a non-current phase. Use "
            f"--allow-phase-mismatch to apply anyway (current_phase will not be "
            f"modified)."
        )

    # Non-replay path: cache validation governs the archetype write.
    cache = _read_cache(change_id)
    archetype: str | None = None
    if cache is None:
        logger.warning(
            "phase_agent.apply_phase_outcome: cache missing for change=%s phase=%s; "
            "writing phase_archetype=None",
            change_id, phase,
        )
    else:
        cache_change_id = cache.get("change_id")
        cache_phase = cache.get("phase")
        cache_checksum = cache.get("checksum")
        cache_archetype = cache.get("archetype")
        if cache_change_id != change_id:
            logger.warning(
                "phase_agent.apply_phase_outcome: cache change_id mismatch "
                "(expected=%s, got=%s); writing phase_archetype=None",
                change_id, cache_change_id,
            )
        elif cache_phase != phase:
            logger.warning(
                "phase_agent.apply_phase_outcome: cache phase mismatch "
                "(expected=%s, got=%s); writing phase_archetype=None",
                phase, cache_phase,
            )
        else:
            expected = _checksum_for_cache(
                change_id, phase,
                cache_archetype if isinstance(cache_archetype, str) else None,
            )
            if cache_checksum != expected:
                logger.warning(
                    "phase_agent.apply_phase_outcome: cache checksum mismatch for "
                    "change=%s phase=%s; writing phase_archetype=None",
                    change_id, phase,
                )
            else:
                # archetype may legitimately be None (bridge fallback).
                archetype = cache_archetype if isinstance(cache_archetype, str) else None

    # Update state fields.
    ids = state.get("handoff_ids")
    if not isinstance(ids, list):
        ids = []
    if handoff_id not in ids:
        ids.append(handoff_id)
    state["handoff_ids"] = ids
    state["last_handoff_id"] = handoff_id
    state["phase_archetype"] = archetype

    # Append a phase_history entry recording this outcome (Task 3.6 / spec).
    # current_phase is deliberately NOT touched here.
    history = state.get("phase_history")
    if not isinstance(history, list):
        history = []
    history.append({
        "phase": phase,
        "outcome": outcome,
        "at": _now_iso(),
    })
    state["phase_history"] = history

    _save_state(state_path, state)
    _atomic_unlink(_cache_path(change_id))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    """Persist *state* dict to *path* atomically."""
    _atomic_write_json(path, state)


_STATE_ONLY_PHASES_FILE_LEVEL: frozenset[str] = frozenset({"INIT", "PLAN", "SUBMIT_PR"})


def record_state_only_archetype(change_id: str, phase: str) -> None:
    """Resolve and persist phase_archetype for a state-only phase.

    State-only phases (INIT, PLAN, SUBMIT_PR) don't dispatch a sub-agent
    via the harness `Agent(...)` tool — they run inline from SKILL.md
    prose (assess_complexity, slash-command invocation, gh pr create
    respectively). The spec still requires `loop-state.json:phase_archetype`
    to be populated for these phases so observability covers all 13
    non-terminal phases (closes VAL_REVIEW finding G-V-001).

    SKILL.md shells out to `runner.py record-state-only-archetype` at the
    entry point of each state-only phase. Idempotent: safe to re-invoke;
    replays leave state unchanged on failure.

    Failure modes:
      * Missing `loop-state.json` → log warning, no-op.
      * Bridge unavailable / coordinator returns None → write `phase_archetype = None`
        (matches the bridge-failure fallback semantics from D9).
    """
    _validate_change_id(change_id)
    if phase not in _STATE_ONLY_PHASES_FILE_LEVEL:
        raise ValueError(
            f"phase must be one of {sorted(_STATE_ONLY_PHASES_FILE_LEVEL)}; got {phase!r}"
        )
    state_path = _state_path(change_id)
    if not state_path.exists():
        logger.warning(
            "record_state_only_archetype: %s missing for change=%s; nothing to record",
            state_path, change_id,
        )
        return
    try:
        with state_path.open("r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "record_state_only_archetype: failed to read %s (%s); aborting update",
            state_path, exc,
        )
        return
    if not isinstance(state, dict):
        logger.warning(
            "record_state_only_archetype: unexpected state shape in %s; aborting",
            state_path,
        )
        return

    archetype: str | None = None
    try:
        import coordination_bridge  # type: ignore[import-not-found]
        resolved = coordination_bridge.try_resolve_archetype_for_phase(phase, {})
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "record_state_only_archetype(%s) bridge raised: %s; "
            "writing phase_archetype=None",
            phase, exc,
        )
        resolved = None

    if isinstance(resolved, dict):
        candidate = resolved.get("archetype")
        if isinstance(candidate, str) and candidate:
            archetype = candidate

    state["phase_archetype"] = archetype
    _save_state(state_path, state)


__all__ = [
    "PhaseEscalationError",
    "apply_phase_outcome",
    "build_phase_dispatch_payload",
    "build_phase_dispatch_kwargs",
    "make_phase_callback",
    "record_state_only_archetype",
    "run_phase_subagent",
]
