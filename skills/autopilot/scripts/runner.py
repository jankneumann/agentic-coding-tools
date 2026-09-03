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
from shared import approval_gate as shared_approval_gate  # noqa: E402
from shared.approval_gate import ApprovalDecision  # noqa: E402
from shared.trust_posture import Gate  # noqa: E402

logger = logging.getLogger("autopilot.runner")

# Exit code for "no gate is pending, continue" — distinct from 2 (usage/refusal)
# so a host can branch on "nothing to ask" without parsing stderr. It is also
# what an evaluated gate returns on PROCEED: the decision was recorded, and the
# caller has nothing to ask anybody.
EXIT_NO_PENDING_GATE = 3

# Exit code for "the run is parked; stop". Reached when an evaluated gate comes
# back BLOCKED for a reason a console answer cannot resolve (rejected, timeout
# default-block, coordinator unreachable): the decision is recorded, the loop is
# in ESCALATE, and there is no question to put to the operator. Distinct from 0
# ("ask, then gate-answer") because the caller must NOT continue.
EXIT_GATE_PARKED = 4


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


def _parse_context(pairs: list[str] | None) -> dict[str, str]:
    """Assemble the gate context from repeated ``--context KEY=VALUE`` pairs."""
    context: dict[str, str] = {}
    for item in pairs or []:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"--context expects KEY=VALUE, got {item!r}")
        context[key.strip()] = value
    return context


def _cmd_gate_check(args: argparse.Namespace) -> int:
    """Report the outstanding gate, or evaluate ``--gate`` when none is.

    Precedence is deliberate: an already-pending gate is a question the operator
    has not answered yet, so it is printed unchanged and nothing is re-evaluated.
    Only when nothing is pending does ``--gate`` mean "evaluate this one now" —
    which is what makes the gates enforceable on the host-driven path, where the
    orchestrator (not ``run_loop``) owns the phase sequence.
    """
    try:
        phase_agent._validate_change_id(args.change_id)
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    pending = _load_pending(args.change_id)
    if pending is not None:
        sys.stdout.write(json.dumps(pending, indent=2, sort_keys=True) + "\n")
        return 0
    if getattr(args, "gate", None) is None:
        sys.stderr.write(f"runner: no gate pending for {args.change_id}\n")
        return EXIT_NO_PENDING_GATE
    return _evaluate_gate(args)


def _evaluate_gate(args: argparse.Namespace) -> int:
    """Evaluate one gate through the loop's own fail-closed default evaluator.

    Uses ``autopilot._GateSession`` rather than a second copy of the posture
    logic, so the CLI and ``run_loop`` cannot disagree about what a gate decides,
    where the decision is recorded, or when it is flushed to disk.
    """
    try:
        context = _parse_context(args.context)
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2

    state_path = _state_path(args.change_id)
    if not state_path.exists():
        sys.stderr.write(
            f"runner: no loop state at {state_path}; cannot evaluate a gate "
            f"before the run has state to record it in\n"
        )
        return 2
    try:
        state = autopilot.load_state(state_path)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"runner: cannot read {state_path}: {exc}\n")
        return 2

    gate = Gate(args.gate)
    phase = state.current_phase
    session = autopilot._GateSession(
        change_id=args.change_id,
        state_path=state_path,
        # The worktree the caller is driving: the posture in effect is the one
        # committed on this change's branch.
        repo_root=Path.cwd(),
    )
    try:
        decision = session.evaluate(gate, context)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"runner: gate {gate.value!r} evaluation failed: {exc}\n")
        return 1

    # Recorded and flushed BEFORE anything acts on it (design D1): a crash here
    # loses the action, never the authorization.
    session.record(state, decision, phase=phase)
    record = state.gate_decisions[-1]

    if decision.proceed:
        sys.stdout.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return EXIT_NO_PENDING_GATE

    # No `edge`: on this path the orchestrator owns current_phase (apply-outcome
    # never moves it), so gate-answer records the answer and the caller resumes.
    if session.park(state, decision, phase=phase, context=context) == autopilot.GATE_PENDING:
        sys.stdout.write(
            json.dumps(state.pending_gate, indent=2, sort_keys=True) + "\n"
        )
        return 0

    # rejected / timeout_default_block / coordinator_unreachable: a human was
    # consulted or could not be reached, so there is no question left to ask.
    reason = f"{gate.value}: {decision.resolution.value} — {decision.reason}"
    autopilot.enter_escalate(state, reason)
    autopilot.save_state(state, state_path)
    sys.stdout.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    sys.stderr.write(f"runner: {reason}; run parked in ESCALATE\n")
    return EXIT_GATE_PARKED


def _console_decision(
    gate: Gate, pending: dict, approved: bool, note: str | None
) -> ApprovalDecision:
    """Build the ApprovalDecision for an answer the operator gave in-conversation.

    Thin delegate (ri-04, D2): the shared shape now lives in
    shared.approval_gate.console_decision, so supervise's gate_router.py can
    build the identical record without importing autopilot.py.
    """
    return shared_approval_gate.console_decision(
        gate, pending.get("posture") or {}, approved, note
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
            "gate-check, gate-answer. Gate exit codes: 0 ask, 3 continue, "
            "4 parked."
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
        help="Report or evaluate a gate (exit 0 ask, 3 continue, 4 parked).",
        description=(
            "Report the pending gate, or evaluate one. With a gate already "
            "pending, prints loop-state's pending_gate as JSON conforming to "
            "contracts/events/gate-request.schema.json and exits 0 — the "
            "outstanding question is never re-evaluated. With nothing pending "
            "and --gate NAME, evaluates that gate against the trust posture "
            "(TRUST_POSTURE.md in the current worktree; absent means block) "
            "using the same fail-closed evaluator the loop uses, and records "
            "the decision in loop-state's gate_decisions. Exit codes: 0 — a "
            "gate is pending, ask the operator the printed `prompt` verbatim "
            "and answer with gate-answer; 3 — nothing to ask, continue "
            "(no gate pending, or the gate resolved PROCEED); 4 — the gate "
            "was BLOCKED for a reason no console answer resolves (rejected, "
            "timeout default-block, coordinator unreachable), the run is "
            "parked in ESCALATE and the caller must stop."
        ),
    )
    gc.add_argument("change_id", help="OpenSpec change identifier.")
    gc.add_argument(
        "--gate",
        default=None,
        choices=[g.value for g in Gate],
        help=(
            "Evaluate this gate when none is pending. Omit to only report an "
            "already-pending gate."
        ),
    )
    gc.add_argument(
        "--context",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help=(
            "Gate-specific evidence for the operator (repeatable), e.g. "
            "--context proposal_path=openspec/changes/x/proposal.md."
        ),
    )
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
