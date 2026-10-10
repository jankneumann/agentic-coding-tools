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
import hashlib
import json
import logging
import subprocess
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
from shared import dispatch_contract  # noqa: E402
from shared.approval_gate import ApprovalDecision  # noqa: E402
from shared.trust_posture import SCOPED_GATES, Gate, load_posture, posture_digest  # noqa: E402

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

# Exit code for `emit-result` when the loop is neither terminal nor parked
# (dispatch-contract D4): nothing is written.
EXIT_NOT_TERMINAL = dispatch_contract.EXIT_NOT_TERMINAL


def _launch_marker(change_id: str) -> dict | None:
    """The dispatch launch marker for this worktree, or None (standalone).

    "Dispatched child" in the dispatch-contract specs means this returned a
    marker (D10a); it is read only through ``dispatch_contract``.
    """
    return dispatch_contract.read_launch_marker(change_id, repo_root=Path.cwd())


def _last_decision(state: "autopilot.LoopState", gate: str) -> dict | None:
    for record in reversed(state.gate_decisions):
        if record.get("gate") == gate:
            return record
    return None


def _is_human_final(record: dict | None) -> bool:
    """A human-provenance decision is final for its subject (D5)."""
    provenance = (record or {}).get("provenance") or {}
    return provenance.get("source") == "human"


def _human_rejection_in_force(state: "autopilot.LoopState", gate: str) -> dict | None:
    """The human rejection of ``gate`` that still settles it, or None (D5).

    A human rejection is final for its subject: no posture change reopens it.
    The subject ends only when a human later approves ``escalate_resume`` —
    the operator explicitly resuming the run — after which the gate is asked
    again. Without that rule a rejected gate could never be re-asked.
    """
    decisions = state.gate_decisions
    for index in range(len(decisions) - 1, -1, -1):
        record = decisions[index]
        if record.get("gate") != gate:
            continue
        if not (_is_human_final(record) and record.get("outcome") == "blocked"):
            return None
        resumed = any(
            later.get("gate") == Gate.ESCALATE_RESUME.value
            and later.get("outcome") == "proceed"
            and _is_human_final(later)
            for later in decisions[index + 1:]
        )
        return None if resumed else record
    return None


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


def _load_park(change_id: str) -> dict | None:
    path = _state_path(change_id)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    park = raw.get("park") if isinstance(raw, dict) else None
    return park if isinstance(park, dict) and park else None


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
        if _launch_marker(args.change_id) is None and (
            _posture_moved(pending) or _scope_arrived(args.change_id, pending)
        ):
            # Standalone run: this worktree's posture is authoritative, and it
            # changed since the gate parked (D5). A dispatched child never
            # re-evaluates; it applies only its marker's gate_answer. A cloud
            # worker (no marker) re-evaluates once its roadmap scope is committed.
            return _reevaluate_pending(args, pending)
        sys.stdout.write(json.dumps(pending, indent=2, sort_keys=True) + "\n")
        return 0
    if getattr(args, "gate", None) is None:
        sys.stderr.write(f"runner: no gate pending for {args.change_id}\n")
        return EXIT_NO_PENDING_GATE
    return _evaluate_gate(args)


def _posture_moved(pending: dict) -> bool:
    recorded = (pending.get("posture") or {}).get("posture_digest")
    if not isinstance(recorded, str):
        return False
    try:
        current = posture_digest(load_posture(Path.cwd()))
    except Exception:  # noqa: BLE001 - an invalid posture is not a re-evaluation
        return False
    return current != recorded


def _scope_arrived(change_id: str, pending: dict) -> bool:
    """A scoped gate parked by the ``unscoped`` fallback whose roadmap scope is
    now committed at HEAD (a cloud worker that pulled the supervisor's checkpoint)."""
    if pending.get("gate") not in {g.value for g in SCOPED_GATES}:
        return False
    last = _last_decision(autopilot.load_state(_state_path(change_id)), str(pending["gate"]))
    if not last or last.get("scope") != "unscoped" or _is_human_final(last):
        return False
    return dispatch_contract.read_committed_dispatch_scope(change_id, repo_root=Path.cwd()) is not None


def _reevaluate_pending(args: argparse.Namespace, pending: dict) -> int:
    """Re-evaluate a standalone pending gate whose posture digest moved (D5)."""
    state_path = _state_path(args.change_id)
    state = autopilot.load_state(state_path)
    gate = Gate(str(pending.get("gate")))
    if _is_human_final(_last_decision(state, gate.value)):
        sys.stdout.write(json.dumps(pending, indent=2, sort_keys=True) + "\n")
        return 0
    session = autopilot._GateSession(
        change_id=args.change_id, state_path=state_path, repo_root=Path.cwd()
    )
    context = {k: v for k, v in (pending.get("context") or {}).items()}
    context.setdefault("change_id", args.change_id)
    decision = session.evaluate(gate, context)
    phase = str(pending.get("phase", state.current_phase))
    state.pending_gate = None
    session.record(state, decision, phase=phase)
    record = state.gate_decisions[-1]
    if decision.proceed:
        edge = pending.get("edge")
        if isinstance(edge, dict) and edge.get("outcome"):
            try:
                autopilot._apply_transition(
                    state, str(edge["outcome"]), change_dir=_change_dir(args.change_id)
                )
            except autopilot.GoalGateRefused as exc:
                autopilot.enter_escalate(state, f"goal gate refused: {exc.reason}")
        autopilot.save_state(state, state_path)
        sys.stdout.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return EXIT_NO_PENDING_GATE
    edge = pending.get("edge") if isinstance(pending.get("edge"), dict) else None
    if session.park(state, decision, phase=phase, context=context, edge=edge) == autopilot.GATE_PENDING:
        sys.stdout.write(json.dumps(state.pending_gate, indent=2, sort_keys=True) + "\n")
        return 0
    autopilot.enter_escalate(state, f"{gate.value}: {decision.resolution.value} — {decision.reason}")
    autopilot.save_state(state, state_path)
    sys.stdout.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return EXIT_GATE_PARKED


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
    prior = _human_rejection_in_force(state, gate.value)
    if prior is not None:
        # D5: a human rejection is final for its subject; a posture change
        # does not reopen it. The run is parked in ESCALATE (entered here if a
        # caller reached the gate outside it) so only an operator resume clears it.
        if state.current_phase != "ESCALATE":
            autopilot.enter_escalate(
                state, f"{gate.value}: rejected by a human; awaiting operator resume"
            )
            autopilot.save_state(state, state_path)
        sys.stdout.write(json.dumps(prior, indent=2, sort_keys=True) + "\n")
        sys.stderr.write(
            f"runner: gate {gate.value!r} was rejected by a human; not re-evaluated\n"
        )
        return EXIT_GATE_PARKED
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
        if gate is Gate.ESCALATE_RESUME:
            try:
                autopilot._apply_transition(
                    state, "resolved", change_dir=_change_dir(args.change_id)
                )
                autopilot.save_state(state, state_path)
            except (OSError, ValueError) as exc:
                sys.stderr.write(
                    f"runner: escalate resume was authorized but could not be "
                    f"persisted: {exc}\n"
                )
                return 1
        sys.stdout.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return EXIT_NO_PENDING_GATE

    # Most gates authorize work inside the current phase and carry no edge.
    # Escalate-resume is different: console approval must persist the same
    # canonical resolved edge used by automatic approval before host projection.
    edge = None
    if gate is Gate.ESCALATE_RESUME:
        edge = {"outcome": "resolved", "target": state.previous_phase}
    if session.park(
        state, decision, phase=phase, context=context, edge=edge
    ) == autopilot.GATE_PENDING:
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
    gate: Gate,
    pending: dict,
    approved: bool,
    note: str | None,
    *,
    approval_ref: str | None = None,
    answer: dict | None = None,
) -> ApprovalDecision:
    """Build the ApprovalDecision for an answer the operator gave in-conversation.

    Thin delegate (ri-04, D2): the shared shape now lives in
    shared.approval_gate.console_decision, so supervise's gate_router.py can
    build the identical record without importing autopilot.py. The record's
    provenance names ``approval_ref`` (D5), or — when the supervisor's answer
    was posture-derived — the posture provenance copied from the answer.
    """
    decision = shared_approval_gate.console_decision(
        gate, pending.get("posture") or {}, approved, note, approval_ref=approval_ref
    )
    provenance = (answer or {}).get("provenance") or {}
    if provenance.get("source") == "posture" and provenance.get("posture_digest"):
        import dataclasses

        decision = dataclasses.replace(
            decision,
            provenance={"source": "posture", "posture_digest": provenance["posture_digest"]},
        )
    return decision


def _answer_park(
    args: argparse.Namespace,
    state: "autopilot.LoopState",
    marker_answer: dict,
    approval_ref: str | None,
) -> int:
    """Clear a capability/permission park with the supervisor's escalate_resume (D11)."""
    if args.gate != Gate.ESCALATE_RESUME.value:
        sys.stderr.write(
            f"runner: run is parked ({state.park.get('kind')!r}); only escalate_resume "
            "answers a park; nothing was recorded\n"
        )
        return 2
    gate = Gate.ESCALATE_RESUME
    approved = args.decision == "approved"
    decision = _console_decision(
        gate,
        {"posture": {}},
        approved,
        args.note,
        approval_ref=approval_ref,
        answer=marker_answer,
    )
    state.gate_decisions.append(
        autopilot.build_gate_decision_record(
            decision, phase=state.current_phase, extra={"note": args.note}
        )
    )
    kind = state.park.get("kind")
    state.park = None
    if not approved:
        note = f" — {args.note}" if args.note else ""
        autopilot.enter_escalate(state, f"{kind} park: rejected{note}")
    autopilot.save_state(state, _state_path(args.change_id))
    return 0


def _cmd_gate_answer(args: argparse.Namespace) -> int:
    """Record a console decision, clear the pending gate, and apply the edge."""
    try:
        phase_agent._validate_change_id(args.change_id)
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2

    marker = _launch_marker(args.change_id)
    approval_ref = getattr(args, "approval_ref", None)
    marker_answer = (marker or {}).get("gate_answer") or {}
    if marker is not None and (
        approval_ref is None or approval_ref != marker_answer.get("approval_ref")
    ):
        # D5: a dispatched child applies only the answer its marker carries.
        sys.stderr.write(
            "runner: --approval-ref does not match the launch marker's gate_answer; "
            "nothing was recorded\n"
        )
        return 2
    resume_at = getattr(args, "resume_at", None)
    if resume_at is not None and (
        args.gate != Gate.ESCALATE_RESUME.value or args.decision != "approved"
    ):
        sys.stderr.write(
            "runner: --resume-at applies only to an approved escalate_resume; "
            "nothing was recorded\n"
        )
        return 2
    if marker is not None and resume_at != marker_answer.get("resume_at"):
        # The resume target is part of the supervisor's answer, never the child's.
        sys.stderr.write(
            "runner: --resume-at does not match the launch marker's gate_answer "
            f"({marker_answer.get('resume_at')!r}); nothing was recorded\n"
        )
        return 2
    if marker is not None and (
        args.gate != marker_answer.get("gate") or args.decision != marker_answer.get("decision")
    ):
        # The reference alone does not authorize a decision: the gate and the
        # decision must be the ones the supervisor recorded in the marker.
        sys.stderr.write(
            "runner: --gate/--decision do not match the launch marker's gate_answer "
            f"({marker_answer.get('gate')!r}, {marker_answer.get('decision')!r}); "
            "nothing was recorded\n"
        )
        return 2

    pending = _load_pending(args.change_id)
    state_for_park = (
        autopilot.load_state(_state_path(args.change_id))
        if pending is None and _state_path(args.change_id).exists()
        else None
    )
    if pending is None and state_for_park is not None and state_for_park.park:
        return _answer_park(args, state_for_park, marker_answer, approval_ref)
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
    decision = _console_decision(
        gate, pending, approved, args.note, approval_ref=approval_ref, answer=marker_answer
    )

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
    if resume_at == "VALIDATE" and outcome == "resolved":
        outcome = "revalidate"
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
    park = _load_park(args.change_id)
    if park is not None:
        # D11: a parked run has no authorized phase; this is a fault, not a stop.
        sys.stderr.write(
            f"runner: run is parked ({park.get('kind')!r}) for {args.change_id}; "
            "apply-outcome recorded nothing\n"
        )
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
            change_dir=_change_dir(args.change_id),
        )
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"runner: apply-outcome failed: {exc}\n")
        return 1
    return 0



def _cmd_init(args: argparse.Namespace) -> int:
    """Idempotently create the canonical durable INIT state."""
    try:
        phase_agent._validate_change_id(args.change_id)
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    path = _state_path(args.change_id)
    if path.exists():
        return 0
    now = autopilot._now_iso()
    state = autopilot.LoopState(
        change_id=args.change_id,
        force=args.force,
        val_review_enabled=args.val_review,
        cli_review_enabled=not args.no_review,
        started_at=now,
        phase_started_at=now,
    )
    try:
        autopilot.save_state(state, path)
    except OSError as exc:
        sys.stderr.write(f"runner: init failed: {exc}\n")
        return 1
    return 0


def _cmd_transition(args: argparse.Namespace) -> int:
    """Apply one canonical transition and durably save it."""
    try:
        phase_agent._validate_change_id(args.change_id)
        state = autopilot.load_state(_state_path(args.change_id))
    except ValueError as exc:
        sys.stderr.write(f"runner: transition failed: {exc}\n")
        return 2
    except OSError as exc:
        sys.stderr.write(f"runner: transition failed: {exc}\n")
        return 1

    if state.current_phase == "DONE":
        return 0

    try:
        autopilot._apply_transition(
            state, args.outcome, change_dir=_change_dir(args.change_id)
        )
    except autopilot.GatePending as exc:
        sys.stderr.write(f"runner: transition stopped: {exc}\n")
        return 0
    except autopilot.ParkActive as exc:
        sys.stderr.write(f"runner: transition refused: {exc}\n")
        return 2
    except autopilot.GoalGateRefused as exc:
        autopilot.enter_escalate(state, f"goal gate refused: {exc.reason}")
        try:
            autopilot.save_state(state, _state_path(args.change_id))
        except OSError as save_exc:
            sys.stderr.write(f"runner: transition failed: {save_exc}\n")
            return 1
        sys.stderr.write(f"runner: transition escalated: {exc}\n")
        return 0
    except ValueError as exc:
        # The host has already recorded the phase handoff through
        # ``apply-outcome``. An unsupported outcome is therefore a logical
        # phase failure, not invalid CLI syntax: park it durably so exit zero
        # permits the mandatory project-state step to publish ESCALATE.
        state.phase_history.append(
            {
                "phase": state.current_phase,
                "outcome": "transition_failed",
                "at": autopilot._now_iso(),
                "note": str(exc),
            }
        )
        autopilot.enter_escalate(state, f"logical transition failure: {exc}")
        try:
            autopilot.save_state(state, _state_path(args.change_id))
        except OSError as save_exc:
            sys.stderr.write(f"runner: transition failed: {save_exc}\n")
            return 1
        sys.stderr.write(
            f"runner: logical transition failed: {exc}; "
            "run parked in ESCALATE\n"
        )
        return 0

    try:
        autopilot.save_state(state, _state_path(args.change_id))
    except OSError as exc:
        sys.stderr.write(f"runner: transition failed: {exc}\n")
        return 1
    return 0


def _cmd_escalate(args: argparse.Namespace) -> int:
    """Durably park the host-driven run after an external phase failure."""
    if not isinstance(args.reason, str) or not args.reason.strip():
        sys.stderr.write("runner: --reason must be a non-empty string\n")
        return 2
    try:
        phase_agent._validate_change_id(args.change_id)
        state = autopilot.load_state(_state_path(args.change_id))
    except ValueError as exc:
        sys.stderr.write(f"runner: escalate failed: {exc}\n")
        return 2
    except OSError as exc:
        sys.stderr.write(f"runner: escalate failed: {exc}\n")
        return 1

    if state.current_phase == "DONE":
        return 0

    state.phase_history.append(
        {
            "phase": state.current_phase,
            "outcome": "host_escalate",
            "at": autopilot._now_iso(),
            "note": args.reason,
        }
    )
    autopilot.enter_escalate(state, args.reason)
    try:
        autopilot.save_state(state, _state_path(args.change_id))
    except OSError as exc:
        sys.stderr.write(f"runner: escalate failed: {exc}\n")
        return 1
    return 0


def _cmd_project_state(args: argparse.Namespace) -> int:
    """Read durable state and project it without mutating the state file."""
    try:
        phase_agent._validate_change_id(args.change_id)
        state = autopilot.load_state(_state_path(args.change_id))
        # Lazy by design: coordinator-free hosts never import the publisher.
        from queue_projection import QueueProjectionAdapter

        result = QueueProjectionAdapter(
            http_url=args.coordinator_url,
            api_key=args.api_key,
            change_path=str(_change_dir(args.change_id)),
        )(state, mode=args.mode)
    except ValueError as exc:
        sys.stderr.write(f"runner: project-state failed: {exc}\n")
        return 2
    except OSError as exc:
        sys.stderr.write(f"runner: project-state failed: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"runner: project-state failed: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    # Projection is observability-only. A structured degraded envelope is a
    # successfully reported projection attempt and must not halt phase work.
    return 0

# --------------------------------------------------------------------------- #
# dispatch-contract: park, record-degradation, emit-result
# --------------------------------------------------------------------------- #


def _degradation_codes() -> list[str]:
    schema = dispatch_contract.load_schema(dispatch_contract.RESULT_V2)
    return list(schema["$defs"]["Degradation"]["properties"]["code"]["enum"])


def _cmd_park(args: argparse.Namespace) -> int:
    """Record why the run stopped before a gate (D11); the only writer of `park`."""
    try:
        phase_agent._validate_change_id(args.change_id)
        state_path = _state_path(args.change_id)
        state = autopilot.load_state(state_path)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"runner: park failed: {exc}\n")
        return 2
    if args.kind == "permission_blocked":
        missing = [name for name in ("tool", "rule", "reason") if not getattr(args, name)]
        if missing:
            sys.stderr.write(f"runner: permission_blocked requires --{', --'.join(missing)}\n")
            return 2
        park = {
            "kind": "permission_blocked",
            "tool": args.tool,
            "rule": args.rule,
            "classifier_reason": args.reason,
            "command": dispatch_contract.redact_command(args.command),
            "reason": f"permission denied for {args.tool} under rule {args.rule}",
        }
    else:
        if not args.phase or not args.missing_lane:
            sys.stderr.write("runner: capability_unavailable requires --phase and --missing-lane\n")
            return 2
        lanes = sorted(set(args.missing_lane))
        park = {
            "kind": "capability_unavailable",
            "phase": args.phase,
            "missing_lanes": lanes,
            "reason": args.reason
            or f"{args.phase} review quorum unmet: missing {', '.join(lanes)}",
        }
    state.park = park
    autopilot.save_state(state, state_path)
    sys.stdout.write(json.dumps(park, indent=2, sort_keys=True) + "\n")
    return 0


def _cmd_record_degradation(args: argparse.Namespace) -> int:
    """Append one closed-code degradation (D10); the only writer of `degradations`."""
    try:
        phase_agent._validate_change_id(args.change_id)
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    codes = _degradation_codes()
    if args.code not in codes:
        sys.stderr.write(
            f"runner: unknown degradation code {args.code!r}; expected one of {', '.join(codes)}\n"
        )
        return 2
    if len(args.detail or "") > 512:
        sys.stderr.write("runner: --detail must be at most 512 characters\n")
        return 2
    state_path = _state_path(args.change_id)
    try:
        state = autopilot.load_state(state_path)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"runner: record-degradation failed: {exc}\n")
        return 2
    entry = {"code": args.code, "phase": args.phase, "detail": args.detail or ""}
    if entry not in state.degradations:
        if len(state.degradations) >= 32:
            sys.stderr.write("runner: at most 32 degradations are recorded\n")
            return 2
        state.degradations.append(entry)
        autopilot.save_state(state, state_path)
    return 0


def _git(*argv: str) -> bytes:
    completed = subprocess.run(["git", *argv], capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", "replace").strip() or "git failed")
    return completed.stdout


def _cmd_emit_result(args: argparse.Namespace) -> int:
    """Derive, write and print the dispatch result from committed loop state (D4)."""
    try:
        phase_agent._validate_change_id(args.change_id)
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    rel = _state_path(args.change_id).as_posix()
    try:
        commit = _git("rev-parse", "HEAD").decode().strip()
        committed = _git("show", f"HEAD:{rel}")
    except RuntimeError as exc:
        sys.stderr.write(f"runner: loop-state is not committed at HEAD: {exc}\n")
        return 2
    try:
        working = Path(rel).read_bytes()
    except OSError as exc:
        sys.stderr.write(f"runner: cannot read {rel}: {exc}\n")
        return 2
    if working != committed:
        sys.stderr.write(
            f"runner: {rel} differs from its HEAD version; commit it before emit-result\n"
        )
        return 2
    state = json.loads(committed.decode("utf-8"))
    marker = _launch_marker(args.change_id) or {}
    isolation = marker.get("isolation") or {}
    try:
        branch = args.branch or isolation.get("branch") or _git(
            "rev-parse", "--abbrev-ref", "HEAD"
        ).decode().strip()
    except RuntimeError as exc:
        sys.stderr.write(f"runner: cannot resolve the branch: {exc}\n")
        return 2
    from shared.environment_profile import host_id

    ctx = {
        "dispatch_id": args.dispatch_id,
        "change_id": args.change_id,
        "attempt": args.attempt,
        "lease_generation": args.generation,
        "worktree_ref": args.worktree_ref or isolation.get("worktree_ref"),
        "branch": branch,
        "host_id": args.host_id or isolation.get("host_id") or host_id(),
        "evidence": {
            "loop_state_path": rel,
            "commit": commit,
            "loop_state_digest": hashlib.sha256(committed).hexdigest(),
        },
    }
    try:
        result = dispatch_contract.result_from_loop_state(state, ctx)
    except dispatch_contract.DispatchContractError as exc:
        sys.stderr.write(f"runner: emit-result failed: {exc}\n")
        return 2
    if result is None:
        sys.stderr.write(f"runner: {dispatch_contract.NOT_TERMINAL_MESSAGE}\n")
        return EXIT_NOT_TERMINAL
    out = Path(dispatch_contract.result_relpath(args.change_id, args.dispatch_id, args.generation))
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    out.write_text(payload)
    sys.stdout.write(payload)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runner",
        description=(
            "Autopilot per-phase dispatch and human-gate CLI. Subcommands: "
            "build-dispatch, apply-outcome, transition, escalate, "
            "record-state-only-archetype, "
            "gate-check, gate-answer. Gate exit codes: 0 ask, 3 continue, "
            "4 parked."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Idempotently create canonical INIT state.")
    init.add_argument("--change-id", required=True)
    init.add_argument("--force", action="store_true")
    init.add_argument("--val-review", action="store_true")
    init.add_argument("--no-review", action="store_true")
    init.set_defaults(func=_cmd_init)

    tr = sub.add_parser("transition", help="Apply and persist a canonical phase edge.")
    tr.add_argument("--change-id", required=True)
    tr.add_argument("--outcome", required=True)
    tr.set_defaults(func=_cmd_transition)

    es = sub.add_parser(
        "escalate",
        help="Durably park the current phase after a host-side failure.",
    )
    es.add_argument("--change-id", required=True)
    es.add_argument("--reason", required=True)
    es.set_defaults(func=_cmd_escalate)

    ps = sub.add_parser(
        "project-state",
        help="Project the durable phase state to a configured coordinator.",
    )
    ps.add_argument("--change-id", required=True)
    ps.add_argument("--mode", required=True, choices=["submit", "reconcile"])
    ps.add_argument("--coordinator-url", required=True)
    ps.add_argument("--api-key", default=None)
    ps.set_defaults(func=_cmd_project_state)

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
    ga.add_argument(
        "--approval-ref",
        default=None,
        help=(
            "gate-decision:<id> from the resume request's gate_answer. Recorded in "
            "the decision's provenance; a dispatched child refuses a reference "
            "that differs from its launch marker's."
        ),
    )
    ga.add_argument(
        "--resume-at",
        default=None,
        choices=["VALIDATE"],
        help=(
            "Resume an approved escalate_resume at VALIDATE instead of the parked "
            "phase, so validation evidence is regenerated by this run. Must match "
            "the launch marker's gate_answer when one is present."
        ),
    )
    ga.set_defaults(func=_cmd_gate_answer)

    pk = sub.add_parser(
        "park",
        help="Record why the run stopped before a gate (permission or capability).",
    )
    pk.add_argument("change_id")
    pk.add_argument("--kind", required=True, choices=["permission_blocked", "capability_unavailable"])
    pk.add_argument("--tool", default=None)
    pk.add_argument("--rule", default=None, help="The matched permission rule, e.g. Bash(env *).")
    pk.add_argument("--command", default=None, help="The blocked command; stored redacted.")
    pk.add_argument("--reason", default=None, help="The classifier's reason (permission) or a note.")
    pk.add_argument("--phase", default=None, choices=list(dispatch_contract.REVIEW_PHASES))
    pk.add_argument("--missing-lane", action="append", default=None)
    pk.set_defaults(func=_cmd_park)

    rd = sub.add_parser("record-degradation", help="Append one closed-code degradation.")
    rd.add_argument("change_id")
    rd.add_argument("--code", required=True)
    rd.add_argument("--phase", required=True)
    rd.add_argument("--detail", default="")
    rd.set_defaults(func=_cmd_record_degradation)

    er = sub.add_parser(
        "emit-result",
        help="Write the dispatch result derived from the committed loop state.",
        description=(
            "Exit 0: result written to openspec/changes/<id>/dispatch-results/ "
            "and printed. Exit 2: loop-state uncommitted or invalid. Exit 5: "
            "the loop is not terminal or parked; nothing is written."
        ),
    )
    er.add_argument("change_id")
    er.add_argument("--dispatch-id", required=True)
    er.add_argument("--generation", required=True, type=int)
    er.add_argument("--attempt", required=True, type=int)
    er.add_argument("--worktree-ref", default=None)
    er.add_argument("--branch", default=None)
    er.add_argument("--host-id", default=None)
    er.set_defaults(func=_cmd_emit_result)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    func = args.func
    return int(func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
