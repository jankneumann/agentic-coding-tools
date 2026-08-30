"""CLI entry points for the autopilot per-phase dispatch helpers.

This script is the prose↔Python boundary between SKILL.md and the
in-process helpers in ``phase_agent.py``. SKILL.md shells out to:

    python3 runner.py build-dispatch --phase X --change-id Y
    python3 runner.py apply-outcome --change-id Y --phase X \\
                                    --outcome Z --handoff-id H

``build-dispatch`` prints a JSON object on stdout (``{prompt, model,
system_prompt, isolation, archetype}``) and writes a per-run resolution
cache file. The orchestrator passes ``prompt`` verbatim to
``Agent(...)`` — no string concatenation in prose (D2).

``apply-outcome`` updates ``loop-state.json`` with the new
``last_handoff_id`` / ``handoff_ids`` / ``phase_archetype`` (consuming
the cache file) and prints nothing on stdout.

Both subcommands exit zero on success and non-zero on validation /
configuration errors. They never raise unhandled exceptions: errors
are formatted as a one-line stderr message.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
Design decisions: D1, D3, D4.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Sibling-module import — allow running both as ``python runner.py`` and
# ``python -m skills.autopilot.scripts.runner``.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
# skills/ — for the shared trust-posture / approval-gate contract packages.
_SKILLS_ROOT = _THIS_DIR.parent.parent
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

import autopilot  # type: ignore[import-not-found]  # noqa: E402
import phase_agent  # type: ignore[import-not-found]  # noqa: E402
from shared.approval_gate import (  # noqa: E402
    ApprovalDecision,
    Outcome,
    Resolution,
)
from shared.trust_posture import Disposition, Gate  # noqa: E402

logger = logging.getLogger("autopilot.runner")

# Exit code for "no gate is pending" — distinct from 2 (usage/refusal) so a
# host can branch on "nothing to ask" without parsing stderr.
EXIT_NO_PENDING_GATE = 3


def _change_dir(change_id: str) -> Path:
    return Path("openspec") / "changes" / change_id


def _state_path(change_id: str) -> Path:
    return _change_dir(change_id) / "loop-state.json"


def _load_pending(change_id: str) -> dict | None:
    """Return the pending GateRequest, or None (missing state included)."""
    path = _state_path(change_id)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    pending = raw.get("pending_gate") if isinstance(raw, dict) else None
    return pending if isinstance(pending, dict) else None


def _cmd_gate_check(args: argparse.Namespace) -> int:
    """Print the pending GateRequest as JSON. Exit 0 pending / 3 none."""
    try:
        phase_agent._validate_change_id(args.change_id)
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    pending = _load_pending(args.change_id)
    if pending is None:
        sys.stderr.write(f"runner: no gate pending for {args.change_id}\n")
        return EXIT_NO_PENDING_GATE
    sys.stdout.write(json.dumps(pending, indent=2, sort_keys=True) + "\n")
    return 0


def _console_decision(
    gate: Gate, pending: dict, approved: bool, note: str | None
) -> ApprovalDecision:
    """Build the ApprovalDecision for an answer the operator gave in-conversation.

    Deliberately the SAME record shape a coordinator decision produces (design
    D4) — the console is a different interviewer, not a different concept.
    """
    posture = pending.get("posture") or {}
    try:
        disposition = Disposition(posture.get("disposition", Disposition.BLOCK.value))
    except ValueError:
        disposition = Disposition.BLOCK
    suffix = f" — {note}" if note else ""
    return ApprovalDecision(
        gate=gate,
        outcome=Outcome.PROCEED if approved else Outcome.BLOCKED,
        resolution=(
            Resolution.CONSOLE_APPROVED if approved else Resolution.CONSOLE_REJECTED
        ),
        disposition=disposition,
        reason=(
            f"gate {gate.value!r} "
            f"{'approved' if approved else 'rejected'} by the operator"
            f"{suffix}"
        ),
        posture_present=bool(posture.get("posture_present", False)),
    )


def _cmd_gate_answer(args: argparse.Namespace) -> int:
    """Record a console decision, clear the pending gate, and apply the edge."""
    try:
        phase_agent._validate_change_id(args.change_id)
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2

    pending = _load_pending(args.change_id)
    if pending is None:
        sys.stderr.write(f"runner: no gate pending for {args.change_id}\n")
        return 2
    if pending.get("gate") != args.gate:
        # Mutate nothing: answering the wrong question is a host bug, and
        # recording it would attribute a decision the operator never made.
        sys.stderr.write(
            f"runner: pending gate is {pending.get('gate')!r}, "
            f"not {args.gate!r}; nothing was recorded\n"
        )
        return 2

    state_path = _state_path(args.change_id)
    state = autopilot.load_state(state_path)
    gate = Gate(args.gate)
    approved = args.decision == "approved"
    decision = _console_decision(gate, pending, approved, args.note)

    state.gate_decisions.append(
        autopilot.build_gate_decision_record(
            decision, phase=str(pending.get("phase", state.current_phase)),
            extra={"note": args.note},
        )
    )
    # Cleared before the edge is applied: _apply_transition refuses to move a
    # phase while a gate is pending, and this answer is what un-pends it.
    state.pending_gate = None

    if not approved:
        note = f" — {args.note}" if args.note else ""
        autopilot.enter_escalate(state, f"{gate.value}: rejected{note}")
        autopilot.save_state(state, state_path)
        return 0

    if gate is Gate.MERGE:
        autopilot.record_merge_authorization(
            state, (pending.get("context") or {}).get("pr_url")
        )

    edge = pending.get("edge")
    if not isinstance(edge, dict):
        # Gates whose approval authorizes work inside the phase (PR creation)
        # carry no edge — record the answer and leave the phase where it is.
        autopilot.save_state(state, state_path)
        return 0

    outcome = str(edge.get("outcome", ""))
    if edge.get("target") == "ESCALATE":
        # enter_escalate (not the bare table edge) so previous_phase and
        # escalation_reason are populated for the resume path.
        autopilot.enter_escalate(
            state, f"{gate.value}: {outcome} approved for escalation"
        )
        autopilot.save_state(state, state_path)
        return 0

    try:
        autopilot._apply_transition(
            state, outcome, change_dir=_change_dir(args.change_id)
        )
    except autopilot.GoalGateRefused as exc:
        autopilot.enter_escalate(state, f"goal gate refused: {exc.reason}")
        autopilot.save_state(state, state_path)
        sys.stderr.write(f"runner: {exc}; escalated\n")
        return 0
    except ValueError as exc:
        sys.stderr.write(f"runner: cannot apply gate edge: {exc}\n")
        return 1
    autopilot.save_state(state, state_path)
    return 0


def _cmd_build_dispatch(args: argparse.Namespace) -> int:
    try:
        result = phase_agent.build_phase_dispatch_kwargs(
            phase=args.phase,
            change_id=args.change_id,
            provider=args.provider,
        )
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"runner: build-dispatch failed: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


def _cmd_record_state_only_archetype(args: argparse.Namespace) -> int:
    """Record phase_archetype for a state-only phase (INIT or SUBMIT_PR).

    SKILL.md INIT/SUBMIT_PR sections shell to this so phase_archetype is
    populated for state-only phases the same way build-dispatch populates
    it for the 7 dispatching phases (closes IMPL_REVIEW finding R-001).
    """
    for name in ("change_id", "phase"):
        val = getattr(args, name, "")
        if not isinstance(val, str) or not val.strip():
            sys.stderr.write(f"runner: --{name.replace('_', '-')} must be a non-empty string\n")
            return 2
    try:
        phase_agent.record_state_only_archetype(
            change_id=args.change_id,
            phase=args.phase,
        )
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"runner: record-state-only-archetype failed: {exc}\n")
        return 1
    return 0


def _cmd_apply_outcome(args: argparse.Namespace) -> int:
    # Reject empty/whitespace-only IDs early. argparse only checks the
    # arg is present, not non-empty; phase_agent rejects deeper but the
    # CLI surface is the right place to fail fast.
    for name in ("change_id", "phase", "outcome", "handoff_id"):
        val = getattr(args, name, "")
        if not isinstance(val, str) or not val.strip():
            sys.stderr.write(f"runner: --{name.replace('_', '-')} must be a non-empty string\n")
            return 2
    pending = _load_pending(args.change_id)
    if pending is not None:
        # Refuse rather than record: while a gate is unanswered the run is
        # parked, so an outcome arriving now belongs to no authorized phase.
        # Exit 0 — this is a stop, not a failure (the caller's escalation
        # wrapper treats non-zero as a fault to escalate).
        sys.stderr.write(
            f"runner: gate {pending.get('gate')!r} is pending for "
            f"{args.change_id}; apply-outcome recorded nothing. "
            f"Answer it with `runner.py gate-answer`.\n"
        )
        return 0
    try:
        phase_agent.apply_phase_outcome(
            change_id=args.change_id,
            phase=args.phase,
            outcome=args.outcome,
            handoff_id=args.handoff_id,
            allow_phase_mismatch=args.allow_phase_mismatch,
        )
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"runner: apply-outcome failed: {exc}\n")
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runner",
        description=(
            "Autopilot per-phase dispatch and human-gate CLI. Subcommands: "
            "build-dispatch, apply-outcome, record-state-only-archetype, "
            "gate-check, gate-answer."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bd = sub.add_parser(
        "build-dispatch",
        help="Resolve archetype, fold system_prompt into prompt, write cache, emit JSON.",
    )
    bd.add_argument("--phase", required=True, help="Phase id (e.g. IMPLEMENT).")
    bd.add_argument("--change-id", required=True, help="OpenSpec change identifier.")
    bd.add_argument(
        "--provider",
        default=None,
        help="Optional provider id for provider-neutral dispatch payloads.",
    )
    bd.set_defaults(func=_cmd_build_dispatch)

    ao = sub.add_parser(
        "apply-outcome",
        help="Update loop-state.json with handoff_id and consume the cache.",
        description=(
            "Update loop-state.json with the sub-agent's (outcome, handoff_id): "
            "sets last_handoff_id, appends handoff_ids and phase_history, and "
            "records phase_archetype. It NEVER modifies current_phase — the "
            "orchestrator is the sole writer of phase transitions. By default the "
            "command errors if --phase does not match loop-state's current_phase; "
            "pass --allow-phase-mismatch to apply anyway (current_phase is still "
            "left untouched)."
        ),
    )
    ao.add_argument("--change-id", required=True)
    ao.add_argument("--phase", required=True)
    ao.add_argument("--outcome", required=True, help="Outcome string from the sub-agent.")
    ao.add_argument("--handoff-id", required=True)
    ao.add_argument(
        "--allow-phase-mismatch",
        action="store_true",
        help=(
            "Bypass the phase-mismatch guard when --phase differs from "
            "loop-state's current_phase (operator recovery). Does NOT enable "
            "current_phase modification — apply-outcome never transitions phases."
        ),
    )
    ao.set_defaults(func=_cmd_apply_outcome)

    rs = sub.add_parser(
        "record-state-only-archetype",
        help="Resolve archetype for INIT/SUBMIT_PR and write to loop-state.json.",
    )
    rs.add_argument("--change-id", required=True)
    rs.add_argument(
        "--phase",
        required=True,
        choices=["INIT", "PLAN", "SUBMIT_PR"],
        help="State-only phase id (INIT, PLAN, or SUBMIT_PR).",
    )
    rs.set_defaults(func=_cmd_record_state_only_archetype)

    gc = sub.add_parser(
        "gate-check",
        help="Print the pending GateRequest as JSON (exit 0 pending, 3 none).",
        description=(
            "Print loop-state's pending_gate as JSON conforming to "
            "contracts/events/gate-request.schema.json. Exit 0 when a gate is "
            "pending, 3 when none is. The host renders the printed `prompt` "
            "verbatim to the operator and answers with gate-answer."
        ),
    )
    gc.add_argument("change_id", help="OpenSpec change identifier.")
    gc.set_defaults(func=_cmd_gate_check)

    ga = sub.add_parser(
        "gate-answer",
        help="Record the operator's answer to the pending gate and apply its edge.",
        description=(
            "Record an ApprovalDecision with resolution console_approved or "
            "console_rejected, clear pending_gate, and apply the gate's edge "
            "(approved) or enter ESCALATE naming the gate and note (rejected). "
            "Exits 2 without mutating anything when no gate is pending or "
            "--gate does not match the pending request."
        ),
    )
    ga.add_argument("change_id", help="OpenSpec change identifier.")
    ga.add_argument(
        "--gate", required=True, choices=[g.value for g in Gate],
        help="The gate being answered; must match the pending request.",
    )
    ga.add_argument("--decision", required=True, choices=["approved", "rejected"])
    ga.add_argument("--note", default=None, help="Operator note recorded with the decision.")
    ga.set_defaults(func=_cmd_gate_answer)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    func = args.func
    return int(func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
