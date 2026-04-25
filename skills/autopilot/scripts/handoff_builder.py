"""Build a structured PhaseRecord from autopilot LoopState at phase boundaries.

The autopilot driver's ``_maybe_handoff`` calls ``build_phase_record(state,
prev_phase, next_phase)`` at each ``_HANDOFF_BOUNDARIES`` transition. The
resulting PhaseRecord is then persisted via ``handoff_fn`` (Layer 1) — the
markdown lands in ``session-log.md`` and the structured payload becomes the
incoming context for the next phase's sub-agent (Layer 2).

Per-phase builders specialize what they pull from LoopState. The default
builder produces a minimal record (change_id + summary + phase_name) so
unhandled boundaries still write a valid handoff.

See:
    openspec/changes/phase-record-compaction/design.md (decisions D1, D6)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

_THIS_DIR = Path(__file__).resolve().parent
_SESSION_LOG_SCRIPTS = _THIS_DIR.parent.parent / "session-log" / "scripts"
if str(_SESSION_LOG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SESSION_LOG_SCRIPTS))

from phase_record import (  # noqa: E402
    Decision,
    FileRef,
    PhaseRecord,
)

# ---------------------------------------------------------------------------
# Phase name mapping — autopilot state-machine phases → human-readable names
# matching session-log/SKILL.md "Phase Names" table.
# ---------------------------------------------------------------------------

_BASE_PHASE_NAMES: dict[str, str] = {
    "PLAN": "Plan",
    "PLAN_REVIEW": "Plan Review",
    "PLAN_FIX": "Plan Fix",
    "IMPLEMENT": "Implementation",
    "IMPL_REVIEW": "Implementation Review",
    "VALIDATE": "Validation",
    "VAL_REVIEW": "Validation Review",
    "SUBMIT_PR": "Submit PR",
    "ESCALATE": "Escalation",
    "DONE": "Done",
}

# Phases that carry an iteration counter from state.iteration
_ITERATION_PHASES: dict[str, str] = {
    "PLAN_ITERATE": "Plan Iteration",
    "IMPL_ITERATE": "Implementation Iteration",
}


def _phase_name_for(phase: str, state: Any) -> str:
    """Resolve the human-readable phase name for a state-machine phase id."""
    if phase in _ITERATION_PHASES:
        n = max(int(getattr(state, "iteration", 0)), 1)
        return f"{_ITERATION_PHASES[phase]} {n}"
    return _BASE_PHASE_NAMES.get(phase, phase)


# ---------------------------------------------------------------------------
# Per-phase builders — each takes (state, prev, next) and returns kwargs to
# merge into the default PhaseRecord constructor call.
# ---------------------------------------------------------------------------


def _builder_default(state: Any, prev: str, nxt: str) -> dict[str, Any]:
    """Default builder — minimal valid PhaseRecord."""
    summary = (
        f"Autopilot transition {prev} -> {nxt} for change {state.change_id}."
    )
    completed_work: list[str] = []
    if hasattr(state, "iteration") and state.iteration:
        completed_work.append(f"{prev} iteration {state.iteration}")
    return {
        "summary": summary,
        "completed_work": completed_work,
    }


def _builder_plan_iterate(state: Any, prev: str, nxt: str) -> dict[str, Any]:
    """PLAN_ITERATE → next: plan iteration just completed."""
    findings = list(getattr(state, "findings_trend", []))
    latest = findings[-1] if findings else 0
    summary = (
        f"Plan Iteration {state.iteration} complete for {state.change_id}; "
        f"transitioning {prev} -> {nxt}. Latest findings count: {latest}."
    )
    completed: list[str] = [f"Plan Iteration {state.iteration} self-review"]
    if findings:
        completed.append(f"findings trend: {findings}")
    return {
        "summary": summary,
        "completed_work": completed,
        "next_steps": [f"Proceed to {nxt}"],
    }


def _builder_plan_review(state: Any, prev: str, nxt: str) -> dict[str, Any]:
    """PLAN_REVIEW → IMPLEMENT: convergence reached, ready to implement."""
    findings = list(getattr(state, "findings_trend", []))
    latest = findings[-1] if findings else 0
    summary = (
        f"Plan review converged for {state.change_id}; transitioning "
        f"{prev} -> {nxt}. {latest} blocking findings remaining."
    )
    decisions: list[Decision] = []
    if nxt == "IMPLEMENT":
        decisions.append(
            Decision(
                title="Plan ready for implementation",
                rationale=f"Plan review converged with {latest} findings",
            )
        )
    return {
        "summary": summary,
        "completed_work": [f"Plan review (findings: {findings or [latest]})"],
        "decisions": decisions,
        "next_steps": ["Begin implementation per work-packages.yaml"],
    }


def _builder_impl_iterate(state: Any, prev: str, nxt: str) -> dict[str, Any]:
    """IMPL_ITERATE → next: implementation iteration just completed."""
    pkgs = dict(getattr(state, "packages_status", {}))
    completed_pkgs = [pid for pid, status in pkgs.items() if status == "complete"]
    summary = (
        f"Implementation Iteration {state.iteration} complete for "
        f"{state.change_id}; transitioning {prev} -> {nxt}. "
        f"{len(completed_pkgs)}/{len(pkgs)} packages complete."
    )
    completed_work: list[str] = []
    for pid in completed_pkgs:
        completed_work.append(f"Package {pid} complete")
    if not completed_work:
        completed_work.append(f"Implementation iteration {state.iteration}")
    return {
        "summary": summary,
        "completed_work": completed_work,
        "next_steps": [f"Proceed to {nxt}"],
    }


def _builder_impl_review(state: Any, prev: str, nxt: str) -> dict[str, Any]:
    """IMPL_REVIEW → VALIDATE: implementation review complete."""
    findings = list(getattr(state, "findings_trend", []))
    latest = findings[-1] if findings else 0
    summary = (
        f"Implementation review complete for {state.change_id}; "
        f"transitioning {prev} -> {nxt}. {latest} blocking findings remaining."
    )
    return {
        "summary": summary,
        "completed_work": [f"Implementation review (findings: {findings or [latest]})"],
        "next_steps": ["Run validation phases per validate-feature"],
    }


def _builder_validate(state: Any, prev: str, nxt: str) -> dict[str, Any]:
    """VALIDATE → next: validation phases complete."""
    summary = (
        f"Validation complete for {state.change_id}; transitioning "
        f"{prev} -> {nxt}."
    )
    next_steps = ["/cleanup-feature " + state.change_id] if nxt == "SUBMIT_PR" else [
        f"Proceed to {nxt}",
    ]
    return {
        "summary": summary,
        "completed_work": ["Validation phases (spec, evidence, smoke)"],
        "next_steps": next_steps,
        "relevant_files": [
            FileRef(
                path=f"openspec/changes/{state.change_id}/validation-report.md",
                description="validation report",
            ),
        ],
    }


def _builder_val_review(state: Any, prev: str, nxt: str) -> dict[str, Any]:
    """VAL_REVIEW → SUBMIT_PR: validation review converged."""
    summary = (
        f"Validation review complete for {state.change_id}; ready to "
        f"submit PR ({prev} -> {nxt})."
    )
    return {
        "summary": summary,
        "completed_work": ["Validation review converged"],
        "next_steps": ["Open PR via SUBMIT_PR phase"],
    }


# Map prev_phase → builder function. Builders dispatch on the just-completed
# phase (the source of the transition).
_BUILDERS: dict[str, Callable[[Any, str, str], dict[str, Any]]] = {
    "PLAN_ITERATE": _builder_plan_iterate,
    "PLAN_REVIEW": _builder_plan_review,
    "IMPL_ITERATE": _builder_impl_iterate,
    "IMPL_REVIEW": _builder_impl_review,
    "VALIDATE": _builder_validate,
    "VAL_REVIEW": _builder_val_review,
}


def build_phase_record(state: Any, prev_phase: str, next_phase: str) -> PhaseRecord:
    """Build a PhaseRecord summarizing the just-completed phase.

    Args:
        state: LoopState (duck-typed; must expose change_id, iteration,
            findings_trend, packages_status, blocking_findings).
        prev_phase: Source phase id (the one being exited).
        next_phase: Destination phase id (the one being entered).

    Returns:
        PhaseRecord populated from state via the per-prev-phase builder.
        Always returns a valid record — unhandled prev_phase falls back to
        the default builder.
    """
    builder = _BUILDERS.get(prev_phase, _builder_default)
    overrides = builder(state, prev_phase, next_phase)

    # Default agent_type: autopilot driver. Tests override via the state if
    # needed (e.g., fixture-based agent identity).
    agent_type = getattr(state, "agent_type", "autopilot") or "autopilot"

    # Translate blocking findings into open_questions so downstream phases
    # see them in the record.
    blocking = list(getattr(state, "blocking_findings", []))
    open_questions: list[str] = []
    for finding in blocking:
        title = finding.get("title") if isinstance(finding, dict) else None
        if title:
            open_questions.append(title)

    return PhaseRecord(
        change_id=state.change_id,
        phase_name=_phase_name_for(prev_phase, state),
        agent_type=agent_type,
        summary=overrides.get("summary", f"{prev_phase} -> {next_phase}"),
        decisions=overrides.get("decisions", []),
        alternatives=overrides.get("alternatives", []),
        trade_offs=overrides.get("trade_offs", []),
        open_questions=overrides.get("open_questions", open_questions),
        completed_work=overrides.get("completed_work", []),
        in_progress=overrides.get("in_progress", []),
        next_steps=overrides.get("next_steps", []),
        relevant_files=overrides.get("relevant_files", []),
    )


__all__ = ["build_phase_record"]
