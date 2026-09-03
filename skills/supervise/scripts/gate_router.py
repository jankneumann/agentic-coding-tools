"""The single supervise seam onto the approval gate service (ri-04, D2).

Every gate the supervise skill raises — the ``roadmap_approval`` gate at the end
of ``cycle``, the ``execute`` precondition, and the resolution of a parked
child's ``pending_gate`` / ``policy_pause`` — goes through exactly one of the
four public entry points here: :func:`evaluate`, :func:`answer`,
:func:`resolve_parked`, :func:`require_approval_ref`. No other module under
``skills/supervise/scripts/`` may import :class:`~shared.approval_gate.ApprovalGate`,
:func:`~shared.approval_gate.build_default_gate`, or call ``.check_filed`` — that
invariant is enforced structurally by an AST scan
(``skills/tests/supervise/test_gate_router.py::test_only_gate_router_imports_approval_gate``).

Design: ``openspec/changes/route-supervise-gates-through-the-approval-gate-service/design.md``
decisions D2 (this module's shape), D3 (``approval_ref`` resolution),
D4 (the prior-record rule), D5 (the ``cycle`` gate protocol),
D6 (the evaluation log), D7 (the mirror projection).
"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Union

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

from shared.approval_gate import (  # noqa: E402
    ApprovalDecision,
    ApprovalGate,
    Outcome,
    build_default_gate,
    build_gate_decision_record,
    console_decision,
)
from shared.trust_posture import Disposition, Gate  # noqa: E402

_RUNTIME_SCRIPTS = _SKILLS_ROOT / "roadmap-runtime" / "scripts"
if str(_RUNTIME_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_SCRIPTS))

from checkpoint import CheckpointManager  # type: ignore[import-untyped]  # noqa: E402
from models import (  # type: ignore[import-untyped]  # noqa: E402
    Roadmap,
    completed_external_refs,
    load_roadmap,
)

# cycle_state.py is imported lazily inside the functions that need it (never at
# module level): it imports this module's `evaluate` / `answer` / `resolve_parked`
# from its subcommand handlers, and does heavy import-time work of its own
# (`_load_runtime_models`) — a top-level import in either direction is a cycle.

#: A parked-but-unfiled block has no timeout to anchor a deadline to. Neither
#: `autopilot.build_gate_request` nor `cycle_state` has a precedent for one (the
#: former carries no deadline at all), so this is new: 7 days.
DEFAULT_BLOCK_HORIZON = timedelta(days=7)

#: The gate-decision `phase` value every router-written record carries. Not the
#: supervise *verb* (that is a separate `verb` extra) — a constant so a reader
#: can `grep` records this module wrote regardless of which verb produced them.
_PHASE = "SUPERVISE"

_TERMINAL_BLOCK_RESOLUTIONS = frozenset({"rejected", "console_rejected"})


class ApprovalRefError(ValueError):
    """Raised when an `approval_ref` does not resolve to an authorizing record (D3)."""


class GateRefusalError(ValueError):
    """Raised when a gate cannot be routed at all — not a decision, a refusal.

    Distinct from a BLOCKED :class:`ApprovalDecision`: a refusal means the
    router could not even construct a valid pending-gate projection (e.g. a
    roadmap naming no `change_id` at all for `roadmap_approval` — D7), so
    nothing is recorded or parked.
    """


@dataclass(frozen=True)
class RoutedDecision:
    """The result of routing one gate through :func:`evaluate` or :func:`answer`."""

    decision: ApprovalDecision
    record: dict[str, Any]
    reused: bool = False


@dataclass(frozen=True)
class ParkedResolution:
    """The result of :func:`resolve_parked`."""

    outcome: str  # "proceed" | "blocked"
    routed: RoutedDecision
    resume_result: Optional[dict[str, Any]] = None
    pending_gate_entry: Optional[dict[str, Any]] = None


# --------------------------------------------------------------------------- #
# D5: roadmap fingerprint — the shape an approval authorizes, not its progress
# --------------------------------------------------------------------------- #

#: Collapses the progress statuses to one value; SKIPPED and SUPERSEDED stay
#: distinct because a `refine-roadmap` supersession narrows the approved scope
#: without touching item_id/change_id/depends_on (D5).
_PROGRESS_STATUS_VALUES = frozenset(
    {"candidate", "approved", "in_progress", "completed", "failed", "blocked", "replan_required"}
)


def _normalized_status(status: Any) -> str:
    value = status.value if hasattr(status, "value") else str(status)
    return value if value not in _PROGRESS_STATUS_VALUES else "progress"


def roadmap_fingerprint(roadmap: Roadmap) -> str:
    """sha256 of the roadmap's authorized DAG shape (D5).

    Sorted ``(item_id, change_id, sorted(depends_on), sorted(external_depends_on),
    normalized_status)`` tuples — deterministic, no wall clock. An item merely
    completing does not move it; a superseded/skipped item, a changed
    `external_depends_on` edge, or a changed `depends_on` set does.
    """
    import hashlib

    parts = sorted(
        "|".join(
            [
                item.item_id,
                item.change_id or "",
                ",".join(sorted(item.depends_on)),
                ",".join(sorted(item.external_depends_on)),
                _normalized_status(item.status),
            ]
        )
        for item in roadmap.items
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Subject keys + the D4 prior-record rule
# --------------------------------------------------------------------------- #


def _subject_key(
    gate: Gate, *, roadmap_id: str, dispatch_id: Optional[str], fingerprint: Optional[str]
) -> tuple:
    if gate is Gate.ROADMAP_APPROVAL:
        return (gate.value, roadmap_id, fingerprint)
    return (gate.value, roadmap_id, dispatch_id)


def _matches_subject(record: dict[str, Any], gate: Gate, key: tuple) -> bool:
    if record.get("gate") != gate.value:
        return False
    if record.get("roadmap_id") != key[1]:
        return False
    if gate is Gate.ROADMAP_APPROVAL:
        return record.get("roadmap_fingerprint") == key[2]
    return record.get("dispatch_id") == key[2]


def _latest_record_for_subject(
    checkpoint: Any, gate: Gate, key: tuple
) -> Optional[dict[str, Any]]:
    candidates = [
        record
        for record in (getattr(checkpoint, "gate_decisions", None) or [])
        if _matches_subject(record, gate, key)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: str(r.get("recorded_at") or ""))


# --------------------------------------------------------------------------- #
# Mirror projection (D7)
# --------------------------------------------------------------------------- #


def _read_current_mirror(repo_root: Path) -> Optional[dict[str, Any]]:
    from cycle_state import MIRROR_PATH  # lazy: see module docstring

    path = repo_root / MIRROR_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _resolve_pending_change_id(
    gate: Gate, roadmap: Roadmap, repo_root: Path, record: dict[str, Any]
) -> Optional[str]:
    if gate is not Gate.ROADMAP_APPROVAL:
        return record.get("change_id")
    external_done = completed_external_refs(repo_root)
    ready = roadmap.ready_items(external_done, include_in_progress=True)
    ready = sorted(ready, key=lambda i: (i.priority, i.item_id))
    for item in ready:
        if item.change_id:
            return item.change_id
    for item in roadmap.items:
        if item.change_id:
            return item.change_id
    return None


def _pending_gate_entry(
    gate: Gate,
    decision: ApprovalDecision,
    record: dict[str, Any],
    *,
    roadmap: Roadmap,
    repo_root: Path,
    now: datetime,
) -> dict[str, Any]:
    change_id = _resolve_pending_change_id(gate, roadmap, repo_root, record)
    if change_id is None:
        raise GateRefusalError(
            f"roadmap {roadmap.roadmap_id!r} names no change_id anywhere in its "
            "items; refusing to park roadmap_approval rather than project an "
            "entry that would silently vanish on write"
        )
    requested_at = record.get("recorded_at") or now.isoformat()
    approval_id = decision.approval_id
    # Anchored on `approval_id` plus a persisted `timeout_seconds`, not on
    # `default_action is not None` -- a `coordinator_unreachable` decision
    # after a successful filing carries both but no `default_action` (the
    # timer never got to expire), and still deserves the window the posture
    # granted rather than the multi-day block-horizon default.
    timeout_seconds = _timeout_seconds_from_context(record) if approval_id else None
    if approval_id and timeout_seconds:
        parsed = _parse_iso(requested_at) or now
        deadline = (parsed + timedelta(seconds=timeout_seconds)).isoformat()
    else:
        parsed = _parse_iso(requested_at) or now
        deadline = (parsed + DEFAULT_BLOCK_HORIZON).isoformat()
    entry: dict[str, Any] = {
        "gate": gate.value,
        "change_id": change_id,
        "requested_at": requested_at,
        "deadline": deadline,
        "disposition": record.get("disposition"),
        "approval_id": approval_id,
        "source": "supervise",
        "decision_id": record.get("decision_id"),
    }
    return entry


def _timeout_seconds_from_context(record: dict[str, Any]) -> Optional[int]:
    value = record.get("timeout_seconds")
    return int(value) if isinstance(value, int) else None


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _project(
    gate: Gate,
    decision: ApprovalDecision,
    record: dict[str, Any],
    key: tuple,
    *,
    roadmap: Roadmap,
    repo_root: Path,
    prior_decision_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> None:
    """Upsert/remove the gate's `pending_gates` entry and, for a `roadmap_approval`
    proceed, upsert the standing decision (D7). Reads the current mirror, merges
    the change, and writes through `cycle_state.write_mirror` (idempotent — an
    unchanged write preserves `written_at`).

    The mirror's `pendingGate` shape carries no `dispatch_id`/`roadmap_fingerprint`
    (only `decision_id`), so removal of a stale entry for this subject is keyed by
    `decision_id`: the record's own (covers re-surfacing the same entry) and the
    prior record's, when this call followed one (covers a fresh decision
    superseding an older parked one for the same subject).
    """
    from cycle_state import _extract_supervisor_record, write_mirror  # lazy

    moment = now or datetime.now(timezone.utc)
    current = _extract_supervisor_record(_read_current_mirror(repo_root)) or {
        "pending_gates": [],
        "standing_decisions": [],
        "back_edge": {"last_digest_at": None, "last_fingerprint": None, "digested_stubs": []},
    }
    stale_ids = {record.get("decision_id")}
    if prior_decision_id is not None:
        stale_ids.add(prior_decision_id)
    pending = [
        entry
        for entry in current.get("pending_gates", [])
        if entry.get("decision_id") not in stale_ids
    ]
    standing = list(current.get("standing_decisions", []))

    if decision.outcome is Outcome.PROCEED:
        if gate is Gate.ROADMAP_APPROVAL:
            standing = [
                d for d in standing if d.get("scope") != key[1] or d.get("decision") != "roadmap_approval:proceed"
            ]
            standing.append(
                {
                    "id": record.get("decision_id"),
                    "decided_at": record.get("recorded_at") or moment.isoformat(),
                    "scope": key[1],
                    "decision": "roadmap_approval:proceed",
                    "rationale": record.get("note"),
                }
            )
    else:
        entry = _pending_gate_entry(gate, decision, record, roadmap=roadmap, repo_root=repo_root, now=moment)
        pending.append(entry)

    merged = {
        "written_at": moment.isoformat(),
        "pending_gates": pending,
        "standing_decisions": standing,
        "back_edge": current.get(
            "back_edge", {"last_digest_at": None, "last_fingerprint": None, "digested_stubs": []}
        ),
    }
    write_mirror(repo_root, merged, now=moment)


# --------------------------------------------------------------------------- #
# Correlation extras
# --------------------------------------------------------------------------- #


def _correlation_extra(
    gate: Gate,
    context: dict[str, Any],
    *,
    roadmap: Roadmap,
    fingerprint: Optional[str],
    verb: str,
) -> dict[str, Any]:
    extra: dict[str, Any] = {
        "decision_id": str(uuid.uuid4()),
        "source": "supervise",
        "verb": verb,
        "roadmap_id": roadmap.roadmap_id,
    }
    for key in ("change_id", "dispatch_id", "item_id"):
        value = context.get(key)
        if value is not None:
            extra[key] = value
    if gate is Gate.ROADMAP_APPROVAL:
        extra["roadmap_fingerprint"] = fingerprint
    return extra


# --------------------------------------------------------------------------- #
# evaluate() — D2, D4
# --------------------------------------------------------------------------- #


def evaluate(
    gate: Union[Gate, str],
    context: Optional[dict[str, Any]] = None,
    *,
    workspace: Path,
    repo_root: Path,
    evaluator: Optional[ApprovalGate] = None,
    now: Optional[datetime] = None,
) -> RoutedDecision:
    """Evaluate `gate` for the roadmap at `workspace`, applying the D4 prior-record
    rule first. `context` may carry `dispatch_id` / `change_id` / `item_id` (for a
    child-attempt gate) and `verb` (`cycle` | `execute` | `resume`, default
    `cycle`) — these correlate the record without being stripped from what the
    coordinator notification sees.
    """
    gate_enum = gate if isinstance(gate, Gate) else Gate(gate)
    ctx = dict(context or {})
    workspace = Path(workspace)
    repo_root = Path(repo_root)
    moment = now or datetime.now(timezone.utc)

    manager = CheckpointManager(workspace, repo_root)
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    checkpoint = manager.load() if manager.exists() else manager.create(roadmap)

    fingerprint = roadmap_fingerprint(roadmap) if gate_enum is Gate.ROADMAP_APPROVAL else None
    dispatch_id = ctx.get("dispatch_id")
    key = _subject_key(gate_enum, roadmap_id=roadmap.roadmap_id, dispatch_id=dispatch_id, fingerprint=fingerprint)

    service = evaluator or build_default_gate(agent_id="supervise", repo_root=str(repo_root))

    prior = _latest_record_for_subject(checkpoint, gate_enum, key)
    if prior is not None:
        routed = _apply_prior_record(prior, gate_enum, key, service=service)
        if routed is not None:
            # Project (which can refuse, e.g. `GateRefusalError` for a blocked
            # decision naming no `change_id`) BEFORE persisting a NEW record --
            # a refusal must never follow a partial write. A reused record was
            # already persisted on a prior call and is not re-recorded here.
            _project(
                gate_enum, routed.decision, routed.record, key,
                roadmap=roadmap, repo_root=repo_root,
                prior_decision_id=prior.get("decision_id"), now=moment,
            )
            if not routed.reused:
                manager.record_gate_decision(checkpoint, routed.record)
            return routed

    verb = str(ctx.get("verb", "cycle"))
    # A literal per-gate call site for  (mirroring the
    # one-call-site-per-gate discipline autopilot.py and the roadmap
    # orchestrator enforce for their own gates via an AST scan — D2, D1):
    # every other gate this router evaluates is a child-attempt gate reached
    # dynamically through resolve_parked, so only this one is pinned literally.
    if gate_enum is Gate.ROADMAP_APPROVAL:
        decision = service.evaluate(Gate.ROADMAP_APPROVAL, ctx)
    else:
        decision = service.evaluate(gate_enum, ctx)
    extra = _correlation_extra(gate_enum, ctx, roadmap=roadmap, fingerprint=fingerprint, verb=verb)
    record = build_gate_decision_record(decision, phase=_PHASE, extra=extra)
    # Project before persisting -- see the prior-record branch above for why.
    _project(
        gate_enum, decision, record, key,
        roadmap=roadmap, repo_root=repo_root,
        prior_decision_id=prior.get("decision_id") if prior is not None else None,
        now=moment,
    )
    manager.record_gate_decision(checkpoint, record)
    return RoutedDecision(decision=decision, record=record, reused=False)


def _apply_prior_record(
    prior: dict[str, Any],
    gate: Gate,
    key: tuple,
    *,
    service: ApprovalGate,
) -> Optional[RoutedDecision]:
    """D4 step 0. Returns a `RoutedDecision` when the prior record settles this
    evaluation without a fresh `ApprovalGate.evaluate` call, or `None` to fall
    through to a fresh evaluation (a posture flip on an open `posture_block`).

    Never persists: a `reused=False` result carries a freshly built, unpersisted
    `record` that the caller must `_project` (which can refuse) before it calls
    `manager.record_gate_decision` -- refusal must never follow a partial write.
    """
    outcome = prior.get("outcome")
    if outcome == "proceed":
        return RoutedDecision(decision=_decision_from_record(prior), record=prior, reused=True)

    resolution = prior.get("resolution")
    if resolution == "posture_block":
        posture = service.posture_loader(service.repo_root, path=service.posture_path)
        current_gd = posture.disposition_for(gate)
        if current_gd.disposition.value == prior.get("disposition"):
            return RoutedDecision(decision=_decision_from_record(prior), record=prior, reused=True)
        return None  # hot reload: fall through and re-evaluate

    # A denied/rejected coordinator or console answer is terminal (D4 step 0.4)
    # regardless of whether the record still carries the `approval_id` it was
    # filed under -- checked BEFORE the `approval_id` branch below so a
    # terminal rejection is never re-polled through `check_filed`.
    if resolution in _TERMINAL_BLOCK_RESOLUTIONS:
        return RoutedDecision(decision=_decision_from_record(prior), record=prior, reused=True)

    if prior.get("approval_id"):
        # A missing `notified` is coerced to the fail-closed `False`, never
        # passed through as `None` -- `check_filed`'s contract takes a `bool`.
        prior_notified = prior.get("notified")
        checked = service.check_filed(
            gate, prior["approval_id"],
            notified=prior_notified if prior_notified is not None else False,
        )
        if checked is None:
            # still pending server-side: re-surface, record nothing new
            return RoutedDecision(decision=_decision_from_record(prior), record=prior, reused=True)
        if (
            checked.outcome.value == prior.get("outcome")
            and checked.resolution.value == prior.get("resolution")
        ):
            # Same terminal state as before (e.g. still `expired` ->
            # `timeout_block`, or still coordinator-unreachable): `check_filed`
            # always returns a terminal decision for a terminal server status,
            # never `None`, so this equality check is what tells "unchanged"
            # apart from "a late answer resolved" -- re-surface, record nothing new.
            return RoutedDecision(decision=_decision_from_record(prior), record=prior, reused=True)
        # A late answer resolved: build a new terminal decision for the same
        # subject (carrying the same correlation ids the original filing had),
        # never re-filing or re-notifying (D4 step 0.3). Left unpersisted --
        # the caller records it only after `_project` succeeds.
        extra = {
            k: prior[k]
            for k in ("source", "verb", "roadmap_id", "change_id", "dispatch_id", "item_id", "roadmap_fingerprint")
            if k in prior
        }
        extra["decision_id"] = str(uuid.uuid4())
        record = build_gate_decision_record(checked, phase=_PHASE, extra=extra)
        return RoutedDecision(decision=checked, record=record, reused=False)

    return None


def _decision_from_record(record: dict[str, Any]) -> ApprovalDecision:
    """Rehydrate an `ApprovalDecision` from a persisted record, for a reused or
    re-surfaced prior — callers of `evaluate`/`answer` need the same shape a
    fresh decision has."""
    from shared.approval_gate import DefaultAction, Resolution

    default_action = record.get("default_action")
    return ApprovalDecision(
        gate=Gate(record["gate"]),
        outcome=Outcome(record["outcome"]),
        resolution=Resolution(record["resolution"]),
        disposition=Disposition(record["disposition"]),
        reason=record.get("reason", ""),
        approval_id=record.get("approval_id"),
        default_action=DefaultAction(default_action) if default_action else None,
        posture_present=bool(record.get("posture_present", False)),
        notified=record.get("notified"),
        timeout_seconds=record.get("timeout_seconds"),
    )


# --------------------------------------------------------------------------- #
# answer() — console decisions (D5)
# --------------------------------------------------------------------------- #


def answer(
    gate: Union[Gate, str],
    *,
    workspace: Path,
    repo_root: Path,
    approved: bool,
    note: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoutedDecision:
    """Record a console decision. For every gate except `roadmap_approval` this
    requires a prior parked record for the subject (mirrors `runner.py
    gate-answer`); `roadmap_approval` may originate one — the operator's command
    IS the human answer."""
    gate_enum = gate if isinstance(gate, Gate) else Gate(gate)
    ctx = dict(context or {})
    workspace = Path(workspace)
    repo_root = Path(repo_root)
    moment = now or datetime.now(timezone.utc)

    manager = CheckpointManager(workspace, repo_root)
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    checkpoint = manager.load() if manager.exists() else manager.create(roadmap)

    fingerprint = roadmap_fingerprint(roadmap) if gate_enum is Gate.ROADMAP_APPROVAL else None
    dispatch_id = ctx.get("dispatch_id")
    key = _subject_key(gate_enum, roadmap_id=roadmap.roadmap_id, dispatch_id=dispatch_id, fingerprint=fingerprint)

    prior = _latest_record_for_subject(checkpoint, gate_enum, key)
    if prior is not None and prior.get("outcome") == "blocked":
        posture = {"disposition": prior.get("disposition"), "posture_present": prior.get("posture_present", False)}
    elif gate_enum is Gate.ROADMAP_APPROVAL:
        from shared.trust_posture import load_posture

        live = load_posture(repo_root)
        gd = live.disposition_for(gate_enum)
        posture = {"disposition": gd.disposition.value, "posture_present": live.present}
    else:
        raise GateRefusalError(
            f"gate {gate_enum.value!r} has no parked record to answer; "
            "answering a question nobody asked is refused without recording"
        )

    decision = console_decision(gate_enum, posture, approved, note)
    verb = str(ctx.get("verb", "cycle"))
    extra = _correlation_extra(gate_enum, ctx, roadmap=roadmap, fingerprint=fingerprint, verb=verb)
    if note is not None:
        extra["note"] = note
    record = build_gate_decision_record(decision, phase=_PHASE, extra=extra)
    # Project before persisting -- a `GateRefusalError` (e.g. a blocked answer
    # naming no `change_id`) must never follow a partial write.
    _project(
        gate_enum, decision, record, key,
        roadmap=roadmap, repo_root=repo_root,
        prior_decision_id=prior.get("decision_id") if prior is not None else None,
        now=moment,
    )
    manager.record_gate_decision(checkpoint, record)
    return RoutedDecision(decision=decision, record=record, reused=False)


# --------------------------------------------------------------------------- #
# resolve_parked() — D4 step 1
# --------------------------------------------------------------------------- #


def resolve_parked(
    attempt: dict[str, Any],
    *,
    workspace: Path,
    repo_root: Path,
    adapter: Any,
    evaluator: Optional[ApprovalGate] = None,
    now: Optional[datetime] = None,
) -> ParkedResolution:
    """Resolve a parked dispatch attempt (`policy_pause` -> `escalate_resume`,
    `pending_gate` -> `Gate(parked.gate)`) against the current posture and, on
    PROCEED, resume it through `adapter.resume(...)`."""
    parked = attempt.get("parked") or {}
    kind = parked.get("kind")
    if kind == "policy_pause":
        gate_enum = Gate.ESCALATE_RESUME
    elif kind == "pending_gate":
        raw_gate = parked.get("gate")
        if not raw_gate:
            raise GateRefusalError("parked pending_gate carries no gate name")
        try:
            gate_enum = Gate(raw_gate)
        except ValueError:
            raise GateRefusalError(f"unknown parked gate {raw_gate!r}") from None
    else:
        raise GateRefusalError(f"unknown parked kind {kind!r}")

    dispatch_id = attempt.get("dispatch_id")
    context = {
        "dispatch_id": dispatch_id,
        "change_id": attempt.get("change_id"),
        "item_id": attempt.get("item_id"),
        "verb": "resume",
        "reason": parked.get("reason"),
    }
    moment = now or datetime.now(timezone.utc)
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    routed = evaluate(
        gate_enum, context, workspace=workspace, repo_root=repo_root, evaluator=evaluator, now=moment
    )

    if routed.decision.outcome is Outcome.PROCEED:
        approval_ref = f"gate-decision:{routed.record.get('decision_id')}"
        resume_result = adapter.resume(
            workspace, dispatch_id=dispatch_id, approval_ref=approval_ref, kind=kind
        )
        return ParkedResolution(outcome="proceed", routed=routed, resume_result=resume_result)

    # Reuse the same deadline computation every other blocked path gets
    # (`requested_at + timeout_seconds` when an approval was filed, else
    # `+ DEFAULT_BLOCK_HORIZON`) — gate_enum here is never ROADMAP_APPROVAL
    # (a parked attempt's gate is one of autopilot's own, or escalate_resume),
    # so `roadmap` only satisfies the helper's signature and is not consulted
    # for change_id resolution.
    entry = _pending_gate_entry(
        gate_enum, routed.decision, routed.record, roadmap=roadmap, repo_root=repo_root, now=moment
    )
    return ParkedResolution(outcome="blocked", routed=routed, pending_gate_entry=entry)


# --------------------------------------------------------------------------- #
# require_approval_ref() — D3
# --------------------------------------------------------------------------- #

_REF_PREFIX = "gate-decision:"


def require_approval_ref(
    checkpoint: Any,
    approval_ref: str,
    *,
    gate: Union[Gate, str],
    dispatch_id: Optional[str] = None,
    roadmap_id: Optional[str] = None,
    roadmap: Optional[Roadmap] = None,
) -> dict[str, Any]:
    """Resolve `approval_ref` to a `proceed` record for `gate` (and, for
    `dispatch_id`-scoped gates, the exact dispatch) or raise `ApprovalRefError`.

    For `Gate.ROADMAP_APPROVAL`, `roadmap` is required: the record's stamped
    `roadmap_fingerprint` is recomputed against `roadmap`'s CURRENT shape and
    rejected if it no longer matches (D3) — a caller that retained an old
    reference across a `refine-roadmap` or replan does not get to reuse it.
    """
    gate_enum = gate if isinstance(gate, Gate) else Gate(gate)
    if not isinstance(approval_ref, str) or not approval_ref.startswith(_REF_PREFIX):
        raise ApprovalRefError(f"malformed approval_ref: {approval_ref!r}")
    decision_id = approval_ref[len(_REF_PREFIX):]

    if gate_enum is Gate.ROADMAP_APPROVAL and roadmap is None:
        raise ApprovalRefError("roadmap_approval requires a roadmap to check the fingerprint against")

    for record in getattr(checkpoint, "gate_decisions", None) or []:
        if record.get("decision_id") != decision_id:
            continue
        if record.get("gate") != gate_enum.value:
            raise ApprovalRefError(f"approval_ref {approval_ref!r} is for gate {record.get('gate')!r}, not {gate_enum.value!r}")
        if record.get("outcome") != "proceed":
            raise ApprovalRefError(f"approval_ref {approval_ref!r} did not resolve to a proceed decision")
        if dispatch_id is not None and record.get("dispatch_id") != dispatch_id:
            raise ApprovalRefError(f"approval_ref {approval_ref!r} is for a different dispatch")
        if roadmap_id is not None and record.get("roadmap_id") != roadmap_id:
            raise ApprovalRefError(f"approval_ref {approval_ref!r} is for a different roadmap")
        if gate_enum is Gate.ROADMAP_APPROVAL:
            current_fp = roadmap_fingerprint(roadmap)
            if record.get("roadmap_fingerprint") != current_fp:
                raise ApprovalRefError(
                    f"approval_ref {approval_ref!r} was stamped for a different roadmap shape "
                    "(roadmap_fingerprint mismatch) — refuse unapproved roadmap execution"
                )
        return record
    raise ApprovalRefError(f"approval_ref {approval_ref!r} does not resolve to any recorded decision")


# --------------------------------------------------------------------------- #
# gate_log() — D6
# --------------------------------------------------------------------------- #


def gate_log(workspace: Path, repo_root: Path) -> list[dict[str, Any]]:
    """The sidecar `gate_decisions` for the roadmap at `workspace`, unioned with
    each ready-or-not item's child `gate_decisions` resolved through the
    attempt's recorded worktree (D6). Sorted by `recorded_at`."""
    workspace = Path(workspace)
    repo_root = Path(repo_root)
    manager = CheckpointManager(workspace, repo_root)
    records: list[dict[str, Any]] = []
    if not manager.exists():
        return records
    checkpoint = manager.load()
    for record in getattr(checkpoint, "gate_decisions", None) or []:
        tagged = dict(record)
        tagged.setdefault("origin", "checkpoint")
        records.append(tagged)

    attempts_by_change: dict[str, dict[str, Any]] = {}
    for attempt in getattr(checkpoint, "dispatch_attempts", None) or []:
        change_id = attempt.get("change_id")
        if change_id:
            attempts_by_change[change_id] = attempt

    for item in getattr(_load_roadmap_quiet(workspace, repo_root), "items", None) or []:
        change_id = item.change_id
        if not change_id:
            continue
        loop_state_path = _resolve_child_loop_state_path(
            attempts_by_change.get(change_id), repo_root, change_id
        )
        if loop_state_path is None:
            continue
        if not loop_state_path.is_file():
            records.append(
                {"gate": None, "origin": change_id, "degraded": True, "reason": "loop-state unreadable"}
            )
            continue
        try:
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            records.append(
                {"gate": None, "origin": change_id, "degraded": True, "reason": "loop-state unreadable"}
            )
            continue
        for record in loop_state.get("gate_decisions", []) or []:
            tagged = dict(record)
            tagged.setdefault("origin", change_id)
            records.append(tagged)

    records.sort(key=lambda r: str(r.get("recorded_at") or ""))
    return records


def _load_roadmap_quiet(workspace: Path, repo_root: Path) -> Optional[Roadmap]:
    path = workspace / "roadmap.yaml"
    if not path.is_file():
        return None
    try:
        return load_roadmap(path, repo_root)
    except (OSError, ValueError):
        return None


def _resolve_child_loop_state_path(
    attempt: Optional[dict[str, Any]], repo_root: Path, change_id: str
) -> Optional[Path]:
    if attempt is not None:
        isolation = attempt.get("isolation") or {}
        worktree_path = isolation.get("worktree_path")
        if worktree_path:
            return Path(worktree_path) / "openspec" / "changes" / change_id / "loop-state.json"
        evidence_path = ((attempt.get("evidence") or {}).get("loop_state_path"))
        if evidence_path:
            return Path(evidence_path)
    # Fallback: the change has since merged into the supervisor's own tree.
    fallback = repo_root / "openspec" / "changes" / change_id / "loop-state.json"
    return fallback if fallback.parent.is_dir() else None
