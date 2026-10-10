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

import contextlib
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Callable, Optional, Union

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
from shared import dispatch_contract  # noqa: E402
from shared.trust_posture import Disposition, Gate, posture_digest  # noqa: E402

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

_POLICY_PAUSE_REASON = "supervised phase retry budget exhausted"

# --------------------------------------------------------------------------- #
# Dispatch result closure (dispatch-contract D3, "Dispatch Result Closure")
# --------------------------------------------------------------------------- #

#: The child gates a parked ``pending_gate`` may name (the Gate enum minus
#: ``roadmap_approval``, which a child never evaluates).
_CHILD_GATES = tuple(gate.value for gate in Gate if gate is not Gate.ROADMAP_APPROVAL)

#: Exactly one answer or resume path for every ``(outcome class, parked.kind,
#: parked.gate)`` the result schema permits. The closure contract test derives
#: the permitted set from ``dispatch-result.schema.json`` and compares.
ANSWER_PATHS: dict[tuple[str, Optional[str], Optional[str]], str] = {
    ("success", None, None): "orchestrator: complete the item and write its learning entry",
    ("failed", None, None): "orchestrator._handle_failure",
    ("vendor_limit", None, None): "orchestrator._handle_vendor_limit",
    **{
        ("parked", "pending_gate", gate): "resolve_parked: evaluate Gate(parked.gate)"
        for gate in _CHILD_GATES
    },
    ("parked", "policy_pause", None): "resolve_parked: escalate_resume for the generation",
    ("parked", "policy_pause", "escalate_resume"): "resolve_parked: escalate_resume for the generation",
    ("parked", "permission_blocked", None): "resolve_parked: escalate_resume keyed by rule fingerprint (D9)",
    ("parked", "capability_unavailable", None): "resolve_parked: escalate_resume keyed by missing-lane set (D9)",
}

_CAPABILITY_KINDS = frozenset({"permission_blocked", "capability_unavailable"})


def has_answer_path(kind: str, gate: Optional[str]) -> bool:
    """The apply-time predicate the execution adapter injects (D3)."""
    return ("parked", kind, gate) in ANSWER_PATHS


@contextlib.contextmanager
def _mirror_projection_lock(repo_root: Path) -> Iterator[None]:
    """Serialize the derived mirror's read-merge-write projection."""
    identity = hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()
    lock_dir = Path(tempfile.gettempdir()) / "supervise-mirror-projection-locks"
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(lock_dir / f"{identity}.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextlib.contextmanager
def _escalate_subject_lock(workspace: Path, dispatch_id: str, generation: int) -> Iterator[None]:
    """Serialize one parked escalation generation without blocking other work."""
    with _subject_lock(workspace, f"{dispatch_id}|{generation}"):
        yield


def _fingerprint_subject_lock(workspace: Path, fingerprint: str) -> contextlib.AbstractContextManager[None]:
    """Serialize one capability/permission escalation subject (D9): keyed by
    workspace + dedupe fingerprint, the identity its members share."""
    return _subject_lock(workspace, f"fingerprint|{fingerprint}")


@contextlib.contextmanager
def _subject_lock(workspace: Path, subject: str) -> Iterator[None]:
    identity = hashlib.sha256(f"{workspace.resolve()}|{subject}".encode()).hexdigest()
    lock_dir = Path(tempfile.gettempdir()) / "supervise-escalate-subject-locks"
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(lock_dir / f"{identity}.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


_NO_PARKED_ESCALATION = (
    "escalate_resume requires a current parked policy_pause attempt "
    "or pending_gate attempt for gate escalate_resume"
)


def _is_escalate_park(parked: Any) -> bool:
    """True for the parked shapes an `escalate_resume` answer covers: the
    supervisor's own `policy_pause`, and a child's `pending_gate` whose gate is
    `escalate_resume` (autopilot escalated under a `block` posture)."""
    if not isinstance(parked, dict):
        return False
    kind = parked.get("kind")
    return kind == "policy_pause" or (
        kind == "pending_gate" and parked.get("gate") == Gate.ESCALATE_RESUME.value
    )


def _serialize_escalate_resolution(method: Callable[..., Any]) -> Callable[..., Any]:
    """Keep approval I/O single-flight for a parked escalation generation."""
    def wrapped(attempt: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        if not _is_escalate_park(attempt.get("parked")):
            return method(attempt, *args, **kwargs)
        dispatch_id = attempt.get("dispatch_id")
        generation = attempt.get("lease_generation")
        workspace = kwargs.get("workspace")
        if not isinstance(dispatch_id, str) or not isinstance(generation, int) or not isinstance(workspace, Path):
            return method(attempt, *args, **kwargs)
        with _escalate_subject_lock(workspace, dispatch_id, generation):
            return method(attempt, *args, **kwargs)
    return wrapped


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


def _serialize_escalate_answer(method: Callable[..., Any]) -> Callable[..., Any]:
    """Serialize manual answers with routing for the current parked generation."""
    @wraps(method)
    def wrapped(gate: Union[Gate, str], *args: Any, **kwargs: Any) -> Any:
        gate_enum = gate if isinstance(gate, Gate) else Gate(gate)
        if gate_enum is not Gate.ESCALATE_RESUME:
            return method(gate, *args, **kwargs)

        workspace = Path(kwargs["workspace"])
        repo_root = Path(kwargs["repo_root"])
        context = dict(kwargs.get("context") or {})
        dispatch_id = context.get("dispatch_id")
        if not isinstance(dispatch_id, str):
            raise GateRefusalError("escalate_resume requires a dispatch_id")

        manager = CheckpointManager(workspace, repo_root)
        if not manager.exists():
            raise GateRefusalError(_NO_PARKED_ESCALATION)
        attempt = _current_parked_escalate_attempt(
            manager.load(), dispatch_id=dispatch_id
        )
        if attempt is None:
            raise GateRefusalError(_NO_PARKED_ESCALATION)
        generation = attempt.get("lease_generation")
        requested_generation = context.get("lease_generation")
        if requested_generation is not None and requested_generation != generation:
            raise GateRefusalError("escalate_resume answer does not match the current parked generation")

        with _escalate_subject_lock(workspace, dispatch_id, generation):
            return method(gate_enum, *args, **kwargs)

    return wrapped


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
    gate: Gate, *, roadmap_id: str, dispatch_id: Optional[str], fingerprint: Optional[str],
    lease_generation: Optional[int] = None,
) -> tuple:
    if gate is Gate.ROADMAP_APPROVAL:
        return (gate.value, roadmap_id, fingerprint)
    if gate is Gate.ESCALATE_RESUME:
        return (gate.value, roadmap_id, dispatch_id, lease_generation)
    return (gate.value, roadmap_id, dispatch_id)


def _matches_subject(record: dict[str, Any], gate: Gate, key: tuple) -> bool:
    if record.get("gate") != gate.value:
        return False
    if record.get("roadmap_id") != key[1]:
        return False
    if gate is Gate.ROADMAP_APPROVAL:
        return record.get("roadmap_fingerprint") == key[2]
    if record.get("dispatch_id") != key[2]:
        return False
    if gate is Gate.ESCALATE_RESUME:
        record_generation = record.get("lease_generation")
        return record_generation is None or record_generation == key[3]
    return True


def _latest_record_for_subject(
    checkpoint: Any, gate: Gate, key: tuple
) -> Optional[dict[str, Any]]:
    candidates = [
        record
        for record in (getattr(checkpoint, "gate_decisions", None) or [])
        if _matches_subject(record, gate, key)
    ]
    if gate is Gate.ESCALATE_RESUME:
        attempt = _current_parked_escalate_attempt(
            checkpoint, dispatch_id=key[2]
        )
        candidates = [
            record
            for record in candidates
            if record.get("lease_generation") is not None
            or (
                attempt is not None
                and attempt.get("lease_generation") == key[3]
                and _legacy_record_matches_attempt(record, attempt)
            )
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: str(r.get("recorded_at") or ""))


def _current_parked_escalate_attempt(
    checkpoint: Any, *, dispatch_id: str, lease_generation: Optional[int] = None
) -> Optional[dict[str, Any]]:
    candidates = [
        attempt
        for attempt in (getattr(checkpoint, "dispatch_attempts", None) or [])
        if (
            attempt.get("dispatch_id") == dispatch_id
            and attempt.get("status") == "parked"
            and _is_escalate_park(attempt.get("parked"))
            and (lease_generation is None or attempt.get("lease_generation") == lease_generation)
        )
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda attempt: (
            attempt.get("lease_generation")
            if isinstance(attempt.get("lease_generation"), int)
            else 0,
            str(attempt.get("resolved_at") or attempt.get("prepared_at") or ""),
        ),
    )


def _legacy_record_matches_attempt(record: dict[str, Any], attempt: dict[str, Any]) -> bool:
    recorded_at = _parse_iso(record.get("recorded_at"))
    parked_at = _parse_iso(attempt.get("resolved_at"))
    return recorded_at is not None and parked_at is not None and recorded_at >= parked_at


def _newest_blocked_escalate_record(
    checkpoint: Any,
    *,
    roadmap_id: str,
    dispatch_id: str,
    lease_generation: int,
    allow_legacy: bool,
) -> Optional[dict[str, Any]]:
    """Select an answerable escalation generation without generation-blind reuse."""
    attempt = _current_parked_escalate_attempt(
        checkpoint, dispatch_id=dispatch_id, lease_generation=lease_generation
    )
    candidates = [
        record for record in (getattr(checkpoint, "gate_decisions", None) or [])
        if record.get("gate") == Gate.ESCALATE_RESUME.value
        and record.get("roadmap_id") == roadmap_id
        and record.get("dispatch_id") == dispatch_id
        and record.get("outcome") == "blocked"
        and (
            record.get("lease_generation") == lease_generation
            or (
                allow_legacy
                and record.get("lease_generation") is None
                and attempt is not None
                and _legacy_record_matches_attempt(record, attempt)
            )
        )
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda record: (
            record.get("lease_generation") if isinstance(record.get("lease_generation"), int) else 0,
            str(record.get("recorded_at") or ""),
        ),
    )


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
    # Same tie-break dispatch uses: priority, then roadmap list position. The
    # mirror entry has to name the change the next dispatch will actually pick,
    # so ordering here by item_id would project the wrong change_id whenever a
    # tier's list order contradicts its item ids. ``ready_items`` preserves
    # roadmap order, so position comes from the roadmap itself.
    positions = {item.item_id: index for index, item in enumerate(roadmap.items)}
    ready = roadmap.ready_items(external_done, include_in_progress=True)
    ready = sorted(ready, key=lambda i: (i.priority, positions[i.item_id]))
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


def _project_unlocked(
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
    with _mirror_projection_lock(repo_root):
        _project_unlocked(
            gate,
            decision,
            record,
            key,
            roadmap=roadmap,
            repo_root=repo_root,
            prior_decision_id=prior_decision_id,
            now=now,
        )


def reconcile_escalation_pending_gates(
    repo_root: Path,
    prior: Optional[dict[str, Any]],
    *,
    now: Optional[Union[str, datetime]] = None,
) -> dict[str, Any]:
    """Rebuild derived escalate-resume pending gates from checkpoint authority."""
    root = Path(repo_root).resolve()
    if isinstance(now, datetime):
        moment = now
    else:
        moment = _parse_iso(now) if isinstance(now, str) else None
    moment = moment or datetime.now(timezone.utc)
    reconciled = dict(prior or {})
    reconciled.setdefault("written_at", moment.isoformat())
    reconciled.setdefault("standing_decisions", [])
    reconciled.setdefault(
        "back_edge",
        {"last_digest_at": None, "last_fingerprint": None, "digested_stubs": []},
    )
    pending = list(reconciled.get("pending_gates", []))
    authoritative_ids: set[str] = set()
    restored: dict[str, dict[str, Any]] = {}

    roadmaps_root = root / "openspec" / "roadmaps"
    for checkpoint_path in sorted(roadmaps_root.glob("*/checkpoint.json")):
        workspace = checkpoint_path.parent
        try:
            roadmap = load_roadmap(workspace / "roadmap.yaml", root)
            checkpoint = CheckpointManager(workspace, root).load()
        except (FileNotFoundError, OSError, TypeError, ValueError):
            continue
        escalation_records = [
            record
            for record in checkpoint.gate_decisions
            if record.get("gate") == Gate.ESCALATE_RESUME.value
        ]
        authoritative_ids.update(
            record["decision_id"]
            for record in escalation_records
            if isinstance(record.get("decision_id"), str)
        )
        current_attempts: dict[str, dict[str, Any]] = {}
        for attempt in checkpoint.dispatch_attempts:
            dispatch_id = attempt.get("dispatch_id")
            if not isinstance(dispatch_id, str):
                continue
            is_parked = (
                attempt.get("status") == "parked"
                and attempt.get("parked", {}).get("kind") == "policy_pause"
            )
            is_prepared = (
                attempt.get("status") == "prepared"
                and attempt.get("continuation", {}).get("kind") == "policy_pause"
            )
            if is_parked or is_prepared:
                previous = current_attempts.get(dispatch_id)
                if previous is None or attempt.get("lease_generation", 0) > previous.get(
                    "lease_generation", 0
                ):
                    current_attempts[dispatch_id] = attempt
        for dispatch_id, attempt in current_attempts.items():
            if attempt.get("status") != "parked":
                continue
            key = _subject_key(
                Gate.ESCALATE_RESUME,
                roadmap_id=roadmap.roadmap_id,
                dispatch_id=dispatch_id,
                fingerprint=None,
                lease_generation=attempt.get("lease_generation"),
            )
            record = _latest_record_for_subject(checkpoint, Gate.ESCALATE_RESUME, key)
            if record is None or record.get("outcome") != "blocked":
                continue
            decision = _decision_from_record(record)
            entry = _pending_gate_entry(
                Gate.ESCALATE_RESUME,
                decision,
                record,
                roadmap=roadmap,
                repo_root=root,
                now=moment,
            )
            restored[record["decision_id"]] = entry

    pending = [
        entry
        for entry in pending
        if entry.get("decision_id") not in authoritative_ids
    ]
    pending.extend(restored[key] for key in sorted(restored))
    reconciled["pending_gates"] = pending
    return reconciled


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
    if gate is Gate.ESCALATE_RESUME:
        generation = context.get("lease_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise GateRefusalError("escalate_resume requires a positive lease_generation")
        extra["lease_generation"] = generation
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
    persist: bool = True,
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
    key = _subject_key(
        gate_enum, roadmap_id=roadmap.roadmap_id, dispatch_id=dispatch_id, fingerprint=fingerprint,
        lease_generation=ctx.get("lease_generation"),
    )

    service = evaluator or build_default_gate(agent_id="supervise", repo_root=str(repo_root))

    prior = _latest_record_for_subject(checkpoint, gate_enum, key)
    if prior is not None:
        routed = _apply_prior_record(prior, gate_enum, key, service=service)
        if routed is not None:
            # Project (which can refuse, e.g. `GateRefusalError` for a blocked
            # decision naming no `change_id`) BEFORE persisting a NEW record --
            # a refusal must never follow a partial write. A reused record was
            # already persisted on a prior call and is not re-recorded here.
            if persist:
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
    if persist:
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
    provenance = prior.get("provenance") or {}
    if provenance.get("source") == "human":
        # D5: a human decision is final for its subject.
        return RoutedDecision(decision=_decision_from_record(prior), record=prior, reused=True)
    if resolution == "posture_block":
        posture = service.posture_loader(service.repo_root, path=service.posture_path)
        recorded_digest = provenance.get("posture_digest")
        if isinstance(recorded_digest, str):
            # D5: compare the whole parsed posture, so a notify_with_timeout
            # parameter change also re-evaluates.
            if recorded_digest == posture_digest(posture):
                return RoutedDecision(decision=_decision_from_record(prior), record=prior, reused=True)
            return None
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
            # Either still pending server-side, or server-side `expired` with
            # `notified=False` (the notification was never delivered, so an
            # `expired` status tells us nothing new -- check_filed returns
            # `None` rather than manufacture a decision). Either way: nothing
            # changed, re-surface the prior unchanged, record nothing new.
            return RoutedDecision(decision=_decision_from_record(prior), record=prior, reused=True)
        if (
            checked.outcome.value == prior.get("outcome")
            and checked.resolution.value == prior.get("resolution")
        ):
            # Same terminal state as before for a case `check_filed` DOES
            # re-decide every call (e.g. still `expired` + notified=True ->
            # `_apply_default`, or still coordinator-unreachable): this
            # equality check is what tells "unchanged" apart from "a late
            # answer resolved" for those -- re-surface, record nothing new.
            return RoutedDecision(decision=_decision_from_record(prior), record=prior, reused=True)
        # A late answer resolved: build a new terminal decision for the same
        # subject (carrying the same correlation ids the original filing had),
        # never re-filing or re-notifying (D4 step 0.3). Left unpersisted --
        # the caller records it only after `_project` succeeds.
        extra = {
            k: prior[k]
            for k in (
                "source",
                "verb",
                "roadmap_id",
                "change_id",
                "dispatch_id",
                "item_id",
                "roadmap_fingerprint",
                "lease_generation",
            )
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
        provenance=record.get("provenance"),
        scope=record.get("scope"),
    )


# --------------------------------------------------------------------------- #
# answer() — console decisions (D5)
# --------------------------------------------------------------------------- #


@_serialize_escalate_answer
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
    resume_at = ctx.get("resume_at")
    workspace = Path(workspace)
    repo_root = Path(repo_root)
    moment = now or datetime.now(timezone.utc)

    manager = CheckpointManager(workspace, repo_root)
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    checkpoint = manager.load() if manager.exists() else manager.create(roadmap)

    fingerprint = roadmap_fingerprint(roadmap) if gate_enum is Gate.ROADMAP_APPROVAL else None
    dispatch_id = ctx.get("dispatch_id")
    selected: Optional[dict[str, Any]] = None
    if gate_enum is Gate.ESCALATE_RESUME:
        requested_generation = ctx.get("lease_generation")
        current_attempt = _current_parked_escalate_attempt(
            checkpoint,
            dispatch_id=dispatch_id,
        )
        if current_attempt is None:
            raise GateRefusalError(_NO_PARKED_ESCALATION)
        generation = current_attempt["lease_generation"]
        if requested_generation is not None and requested_generation != generation:
            raise GateRefusalError("escalate_resume answer does not match the current parked generation")
        selected = _newest_blocked_escalate_record(
            checkpoint, roadmap_id=roadmap.roadmap_id, dispatch_id=dispatch_id,
            lease_generation=generation,
            allow_legacy=requested_generation is None,
        )
        if selected is None:
            raise GateRefusalError("escalate_resume has no blocked record to answer for this dispatch/generation")
        ctx = {
            "dispatch_id": dispatch_id,
            "change_id": current_attempt["change_id"],
            "item_id": current_attempt["item_id"],
            "lease_generation": generation,
            "verb": "resume",
            "reason": (
                _POLICY_PAUSE_REASON
                if current_attempt["parked"]["kind"] == "policy_pause"
                else current_attempt["parked"].get("reason")
            ),
        }
    key = _subject_key(
        gate_enum, roadmap_id=roadmap.roadmap_id, dispatch_id=dispatch_id, fingerprint=fingerprint,
        lease_generation=ctx.get("lease_generation"),
    )

    prior = selected if gate_enum is Gate.ESCALATE_RESUME else _latest_record_for_subject(checkpoint, gate_enum, key)
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
    if resume_at is not None:
        if gate_enum is not Gate.ESCALATE_RESUME or not approved or resume_at != "VALIDATE":
            raise GateRefusalError("resume_at=VALIDATE applies only to an approved escalate_resume")
        extra["resume_at"] = resume_at
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


@_serialize_escalate_resolution
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
    if kind in _CAPABILITY_KINDS:
        return _resolve_capability_park(
            attempt, workspace=workspace, repo_root=repo_root, adapter=adapter,
            evaluator=evaluator, now=now,
        )
    evaluator = _with_attempt_scope(evaluator, attempt, repo_root)
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
        "reason": _POLICY_PAUSE_REASON if kind == "policy_pause" else parked.get("reason"),
    }
    if gate_enum is Gate.ESCALATE_RESUME:
        # Both escalation parks key on (dispatch_id, lease_generation) -- the
        # same subject `answer` records under -- so a console answer for this
        # generation is found by the D4 prior-record rule below.
        generation = attempt.get("lease_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise GateRefusalError(f"{kind} attempt requires a positive lease_generation")
        context["lease_generation"] = generation
    moment = now or datetime.now(timezone.utc)
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    routed = evaluate(
        gate_enum, context, workspace=workspace, repo_root=repo_root, evaluator=evaluator, now=moment,
        persist=kind != "policy_pause",
    )

    if kind != "policy_pause":
        if routed.decision.outcome is Outcome.PROCEED:
            approval_ref = f"gate-decision:{routed.record.get('decision_id')}"
            resume_result = adapter.resume(
                workspace, dispatch_id=dispatch_id, approval_ref=approval_ref, kind=kind
            )
            return ParkedResolution(outcome="proceed", routed=routed, resume_result=resume_result)
        entry = _pending_gate_entry(
            gate_enum, routed.decision, routed.record, roadmap=roadmap, repo_root=repo_root, now=moment
        )
        return ParkedResolution(outcome="blocked", routed=routed, pending_gate_entry=entry)

    key = _subject_key(
        gate_enum, roadmap_id=roadmap.roadmap_id, dispatch_id=dispatch_id, fingerprint=None,
        lease_generation=generation,
    )
    if routed.decision.outcome is Outcome.PROCEED:
        approval_ref = f"gate-decision:{routed.record.get('decision_id')}"
        if routed.reused:
            resume_result = adapter.resume(
                workspace, dispatch_id=dispatch_id, approval_ref=approval_ref, kind=kind
            )
        else:
            resume_result = adapter.resume_with_gate_decision(
                workspace, dispatch_id=dispatch_id, approval_ref=approval_ref, kind=kind, record=routed.record
            )
        _project(gate_enum, routed.decision, routed.record, key, roadmap=roadmap, repo_root=repo_root, now=moment)
        return ParkedResolution(outcome="proceed", routed=routed, resume_result=resume_result)

    entry = _pending_gate_entry(
        gate_enum, routed.decision, routed.record, roadmap=roadmap, repo_root=repo_root, now=moment
    )
    if not routed.reused:
        manager = CheckpointManager(workspace, repo_root)
        if not hasattr(adapter, "resume_with_gate_decision"):
            manager.record_gate_decision(manager.load(), routed.record)
        else:
            with manager.transaction() as current:
                fresh = next(
                    (candidate for candidate in current.dispatch_attempts if candidate.get("dispatch_id") == dispatch_id),
                    None,
                )
                if (
                    fresh is None
                    or fresh.get("status") != "parked"
                    or fresh.get("parked", {}).get("kind") != "policy_pause"
                    or fresh.get("lease_generation") != generation
                ):
                    raise GateRefusalError("stale policy_pause resolution")
                winner = _latest_record_for_subject(current, gate_enum, key)
                if winner is not None:
                    routed = RoutedDecision(decision=_decision_from_record(winner), record=winner, reused=True)
                    entry = _pending_gate_entry(
                        gate_enum, routed.decision, routed.record, roadmap=roadmap, repo_root=repo_root, now=moment
                    )
                else:
                    current.gate_decisions.append(dict(routed.record))
    _project(gate_enum, routed.decision, routed.record, key, roadmap=roadmap, repo_root=repo_root, now=moment)
    return ParkedResolution(outcome="blocked", routed=routed, pending_gate_entry=entry)


def _with_attempt_scope(
    evaluator: Optional[ApprovalGate], attempt: dict[str, Any], repo_root: Path
) -> ApprovalGate:
    """The supervisor applies the D8 scope rule from the same recorded fact the
    child's marker carries: the attempt's verified ``roadmap_approval_ref``."""
    import dataclasses

    ref = attempt.get("roadmap_approval_ref")

    def reader(_context: dict[str, Any]) -> Optional[dict[str, Any]]:
        return {"roadmap_approval_ref": ref} if ref else None

    if evaluator is None:
        return build_default_gate(agent_id="supervise", repo_root=str(repo_root), marker_reader=reader)
    if isinstance(evaluator, ApprovalGate) and evaluator.marker_reader is None:
        return dataclasses.replace(evaluator, marker_reader=reader)
    return evaluator


# --------------------------------------------------------------------------- #
# Capability / permission parks — one escalation per fingerprint (D9)
# --------------------------------------------------------------------------- #


def _redacted_parked(parked: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(parked)
    if cleaned.get("command") is not None:
        cleaned["command"] = dispatch_contract.redact_command(str(cleaned["command"]))
    return cleaned


def _fingerprint_members(checkpoint: Any, fingerprint: str) -> list[dict[str, Any]]:
    return sorted(
        (
            attempt
            for attempt in (getattr(checkpoint, "dispatch_attempts", None) or [])
            if attempt.get("status") == "parked"
            and (attempt.get("parked") or {}).get("kind") in _CAPABILITY_KINDS
            and dispatch_contract.dedupe_fingerprint(attempt["parked"]) == fingerprint
        ),
        key=lambda attempt: str(attempt.get("dispatch_id")),
    )


def _subject_records(checkpoint: Any, fingerprint: str, roadmap_id: str) -> list[dict[str, Any]]:
    return [
        record
        for record in (getattr(checkpoint, "gate_decisions", None) or [])
        if record.get("gate") == Gate.ESCALATE_RESUME.value
        and record.get("dedupe_fingerprint") == fingerprint
        and record.get("roadmap_id") == roadmap_id
        and "dispatch_ids" in record
    ]


def _answered_after(checkpoint: Any, fingerprint: str, subject: dict[str, Any]) -> bool:
    """A ``proceed`` for this fingerprint was recorded after ``subject``."""
    since = str(subject.get("recorded_at") or "")
    return any(
        record.get("gate") == Gate.ESCALATE_RESUME.value
        and record.get("dedupe_fingerprint") == fingerprint
        and record.get("outcome") == "proceed"
        and str(record.get("recorded_at") or "") > since
        for record in (getattr(checkpoint, "gate_decisions", None) or [])
    )


def _fingerprint_entry(
    record: dict[str, Any], decision: ApprovalDecision, *, roadmap: Roadmap, repo_root: Path, now: datetime
) -> dict[str, Any]:
    entry = _pending_gate_entry(
        Gate.ESCALATE_RESUME, decision, record, roadmap=roadmap, repo_root=repo_root, now=now
    )
    entry["dedupe_fingerprint"] = record["dedupe_fingerprint"]
    entry["dispatch_ids"] = [dict(item) for item in record["dispatch_ids"]]
    return entry


def _project_fingerprint(
    entry: Optional[dict[str, Any]], *, repo_root: Path, stale_ids: set[str], now: datetime
) -> None:
    """Upsert (or, with ``entry=None``, remove) the one pending entry of a fingerprint."""
    from cycle_state import _extract_supervisor_record, write_mirror  # lazy

    with _mirror_projection_lock(repo_root):
        current = _extract_supervisor_record(_read_current_mirror(repo_root)) or {
            "pending_gates": [],
            "standing_decisions": [],
            "back_edge": {"last_digest_at": None, "last_fingerprint": None, "digested_stubs": []},
        }
        pending = [
            item for item in current.get("pending_gates", []) if item.get("decision_id") not in stale_ids
        ]
        if entry is not None:
            pending.append(entry)
        write_mirror(
            repo_root,
            {
                "written_at": now.isoformat(),
                "pending_gates": pending,
                "standing_decisions": list(current.get("standing_decisions", [])),
                "back_edge": current.get(
                    "back_edge", {"last_digest_at": None, "last_fingerprint": None, "digested_stubs": []}
                ),
            },
            now=now,
        )


def _fan_out_resume(
    members: list[dict[str, Any]],
    decision: ApprovalDecision,
    *,
    fingerprint: str,
    roadmap: Roadmap,
    workspace: Path,
    adapter: Any,
    extra: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Write one per-dispatch ``proceed`` record and resume each member through
    its own generation-checked CAS (D9). Returns ``(records, resumed, skipped)``."""
    manager = CheckpointManager(workspace)
    records: list[dict[str, Any]] = []
    for member in members:
        record_extra = {
            "decision_id": str(uuid.uuid4()),
            "source": "supervise",
            "verb": "resume",
            "roadmap_id": roadmap.roadmap_id,
            "dispatch_id": member["dispatch_id"],
            "change_id": member.get("change_id"),
            "item_id": member.get("item_id"),
            "lease_generation": member["lease_generation"],
            "dedupe_fingerprint": fingerprint,
        }
        record_extra.update(extra or {})
        records.append(build_gate_decision_record(decision, phase=_PHASE, extra=record_extra))
    checkpoint = manager.load()
    for record in records:
        manager.record_gate_decision(checkpoint, record)
    resumed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for record in records:
        kind = None
        for member in members:
            if member["dispatch_id"] == record["dispatch_id"]:
                kind = (member.get("parked") or {}).get("kind")
        try:
            request = adapter.resume(
                workspace,
                dispatch_id=record["dispatch_id"],
                approval_ref=f"gate-decision:{record['decision_id']}",
                kind=kind,
            )
        except (ValueError, ApprovalRefError) as exc:
            skipped.append({"dispatch_id": record["dispatch_id"], "reason": str(exc)})
            continue
        resumed.append(request)
    return records, resumed, skipped


def _resolve_capability_park(
    attempt: dict[str, Any],
    *,
    workspace: Path,
    repo_root: Path,
    adapter: Any,
    evaluator: Optional[ApprovalGate],
    now: Optional[datetime],
) -> ParkedResolution:
    """One ``escalate_resume`` subject per dedupe fingerprint (D9), single-flight
    per workspace + fingerprint: evaluate, project and record run under one lock."""
    workspace = Path(workspace)
    fingerprint = dispatch_contract.dedupe_fingerprint(attempt["parked"])
    with _fingerprint_subject_lock(workspace, fingerprint):
        return _resolve_capability_park_locked(
            attempt, fingerprint, workspace=workspace, repo_root=Path(repo_root), adapter=adapter,
            evaluator=evaluator, now=now,
        )


def _resolve_capability_park_locked(
    attempt: dict[str, Any],
    fingerprint: str,
    *,
    workspace: Path,
    repo_root: Path,
    adapter: Any,
    evaluator: Optional[ApprovalGate],
    now: Optional[datetime],
) -> ParkedResolution:
    moment = now or datetime.now(timezone.utc)
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    manager = CheckpointManager(workspace, repo_root)
    checkpoint = manager.load()
    members = _fingerprint_members(checkpoint, fingerprint)
    if not any(m["dispatch_id"] == attempt.get("dispatch_id") for m in members):
        # A concurrent resolver on this fingerprint already resumed this
        # attempt (its fan-out covered every member); report that answer
        # instead of evaluating a subject with no members.
        return _already_resumed(checkpoint, attempt, fingerprint)
    listed = [
        {"dispatch_id": m["dispatch_id"], "lease_generation": m["lease_generation"]} for m in members
    ]
    service = evaluator or build_default_gate(agent_id="supervise", repo_root=str(repo_root))
    prior_subjects = _subject_records(checkpoint, fingerprint, roadmap.roadmap_id)
    prior = max(prior_subjects, key=lambda r: str(r.get("recorded_at") or "")) if prior_subjects else None
    if prior is not None and _answered_after(checkpoint, fingerprint, prior):
        # The subject was answered (the fan-out's per-dispatch proceed records);
        # a park on this fingerprint since then is a new subject.
        prior = None

    if (
        prior is not None
        and prior.get("outcome") == "blocked"
        and (prior.get("provenance") or {}).get("source") == "human"
    ):
        # D5: a human rejection is final for its fingerprint subject; the
        # posture is never consulted, so only a new operator answer
        # (answer_escalation) clears it. When the membership changed since the
        # rejection, the subject is extended durably (the rejection carried
        # forward, listing the current members) and re-projected, so the
        # listing an operator answers is exactly the one recorded.
        decision = _decision_from_record(prior)
        if prior.get("dispatch_ids") == listed:
            entry = _fingerprint_entry(prior, decision, roadmap=roadmap, repo_root=repo_root, now=moment)
            routed = RoutedDecision(decision=decision, record=prior, reused=True)
            return ParkedResolution(outcome="blocked", routed=routed, pending_gate_entry=entry)
        extended = dict(prior)
        extended.update(
            decision_id=str(uuid.uuid4()),
            recorded_at=datetime.now(timezone.utc).isoformat(),
            dispatch_ids=listed,
            extends_decision_id=prior.get("decision_id"),
            parked_commands=[
                _redacted_parked(m["parked"]).get("command") for m in members if m["parked"].get("command")
            ],
        )
        stale = {r["decision_id"] for r in prior_subjects if isinstance(r.get("decision_id"), str)}
        entry = _fingerprint_entry(extended, decision, roadmap=roadmap, repo_root=repo_root, now=moment)
        _project_fingerprint(entry, repo_root=repo_root, stale_ids=stale | {extended["decision_id"]}, now=moment)
        manager.record_gate_decision(manager.load(), extended)
        routed = RoutedDecision(decision=decision, record=extended, reused=False)
        return ParkedResolution(outcome="blocked", routed=routed, pending_gate_entry=entry)
    if prior is not None and prior.get("outcome") == "blocked":
        routed = _apply_prior_record(prior, Gate.ESCALATE_RESUME, (), service=service)
        if routed is not None and routed.reused and prior.get("dispatch_ids") == listed:
            entry = _fingerprint_entry(prior, routed.decision, roadmap=roadmap, repo_root=repo_root, now=moment)
            return ParkedResolution(outcome="blocked", routed=routed, pending_gate_entry=entry)

    reasons = sorted({str((m.get("parked") or {}).get("reason") or "") for m in members})
    decision = service.evaluate(
        Gate.ESCALATE_RESUME,
        {
            "change_id": attempt.get("change_id"),
            "dispatch_ids": ",".join(item["dispatch_id"] for item in listed),
            "reason": "; ".join(reasons)[:1024],
            "verb": "resume",
        },
    )
    stale = {r["decision_id"] for r in prior_subjects if isinstance(r.get("decision_id"), str)}
    if decision.outcome is Outcome.PROCEED:
        records, resumed, skipped = _fan_out_resume(
            members, decision, fingerprint=fingerprint, roadmap=roadmap, workspace=workspace, adapter=adapter
        )
        _project_fingerprint(None, repo_root=repo_root, stale_ids=stale, now=moment)
        own = next((r for r in records if r["dispatch_id"] == attempt["dispatch_id"]), records[0])
        own_request = next((r for r in resumed if r.get("dispatch_id") == attempt["dispatch_id"]), None)
        return ParkedResolution(
            outcome="proceed",
            routed=RoutedDecision(decision=decision, record=own, reused=False),
            resume_result=own_request or {"resumed": resumed, "skipped": skipped},
        )

    extra = {
        "decision_id": str(uuid.uuid4()),
        "source": "supervise",
        "verb": "resume",
        "roadmap_id": roadmap.roadmap_id,
        "change_id": attempt.get("change_id"),
        "dedupe_fingerprint": fingerprint,
        "dispatch_ids": listed,
        "parked_commands": [
            _redacted_parked(m["parked"]).get("command") for m in members if m["parked"].get("command")
        ],
    }
    record = build_gate_decision_record(decision, phase=_PHASE, extra=extra)
    entry = _fingerprint_entry(record, decision, roadmap=roadmap, repo_root=repo_root, now=moment)
    _project_fingerprint(entry, repo_root=repo_root, stale_ids=stale | {record["decision_id"]}, now=moment)
    manager.record_gate_decision(manager.load(), record)
    return ParkedResolution(
        outcome="blocked",
        routed=RoutedDecision(decision=decision, record=record, reused=False),
        pending_gate_entry=entry,
    )


def _already_resumed(checkpoint: Any, attempt: dict[str, Any], fingerprint: str) -> ParkedResolution:
    dispatch_id = attempt.get("dispatch_id")
    generation = attempt.get("lease_generation")
    record = next(
        (
            r for r in reversed(getattr(checkpoint, "gate_decisions", None) or [])
            if r.get("gate") == Gate.ESCALATE_RESUME.value
            and r.get("outcome") == "proceed"
            and r.get("dedupe_fingerprint") == fingerprint
            and r.get("dispatch_id") == dispatch_id
            and r.get("lease_generation") == generation
        ),
        None,
    )
    current = next(
        (a for a in (getattr(checkpoint, "dispatch_attempts", None) or []) if a.get("dispatch_id") == dispatch_id),
        None,
    )
    if record is None or current is None:
        raise GateRefusalError("stale capability park resolution: the attempt is no longer parked")
    return ParkedResolution(
        outcome="proceed",
        routed=RoutedDecision(decision=_decision_from_record(record), record=record, reused=True),
        resume_result={"dispatch_id": dispatch_id, "lease_generation": current.get("lease_generation")},
    )


def answer_escalation(
    fingerprint: str,
    *,
    workspace: Path,
    repo_root: Path,
    approved: bool,
    adapter: Any,
    note: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Answer one fingerprint escalation (D9): an approval writes one
    ``escalate_resume`` record per listed dispatch (its own ``dispatch_id`` and
    projected ``lease_generation``, the shared fingerprint, human provenance)
    and resumes each through its own CAS; a member whose generation moved
    since projection is skipped and reported. Single-flight with
    ``resolve_parked`` on the same workspace + fingerprint."""
    workspace = Path(workspace)
    with _fingerprint_subject_lock(workspace, fingerprint):
        return _answer_escalation_locked(
            fingerprint, workspace=workspace, repo_root=Path(repo_root), approved=approved,
            adapter=adapter, note=note, now=now,
        )


def _answer_escalation_locked(
    fingerprint: str,
    *,
    workspace: Path,
    repo_root: Path,
    approved: bool,
    adapter: Any,
    note: Optional[str],
    now: Optional[datetime],
) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
    manager = CheckpointManager(workspace, repo_root)
    checkpoint = manager.load()
    subjects = [
        r for r in _subject_records(checkpoint, fingerprint, roadmap.roadmap_id) if r.get("outcome") == "blocked"
    ]
    if not subjects:
        raise GateRefusalError("escalate_resume has no open escalation for this fingerprint")
    subject = max(subjects, key=lambda r: str(r.get("recorded_at") or ""))
    decision = console_decision(
        Gate.ESCALATE_RESUME,
        {"disposition": subject.get("disposition"), "posture_present": subject.get("posture_present", False)},
        approved,
        note,
    )
    stale = {r["decision_id"] for r in subjects if isinstance(r.get("decision_id"), str)}
    if not approved:
        record = build_gate_decision_record(
            decision, phase=_PHASE,
            extra={
                "decision_id": str(uuid.uuid4()), "source": "supervise", "verb": "resume",
                "roadmap_id": roadmap.roadmap_id, "change_id": subject.get("change_id"),
                "dedupe_fingerprint": fingerprint, "dispatch_ids": subject["dispatch_ids"], "note": note,
            },
        )
        entry = _fingerprint_entry(record, decision, roadmap=roadmap, repo_root=repo_root, now=moment)
        _project_fingerprint(entry, repo_root=repo_root, stale_ids=stale, now=moment)
        manager.record_gate_decision(checkpoint, record)
        return {"outcome": "blocked", "resumed": [], "skipped": [], "records": [record]}
    by_id = {a.get("dispatch_id"): a for a in checkpoint.dispatch_attempts}
    members: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in subject["dispatch_ids"]:
        current = by_id.get(item["dispatch_id"])
        if (
            current is None
            or current.get("status") != "parked"
            or current.get("lease_generation") != item["lease_generation"]
        ):
            skipped.append({"dispatch_id": item["dispatch_id"], "reason": "generation changed since projection"})
            continue
        members.append(current)
    # The answer authorizes only the dispatches its durable subject lists. A
    # member that parked on this fingerprint after the subject was recorded
    # stays parked; its own resolve_parked persists and projects a subject the
    # operator can then answer (D9 provenance).
    records, resumed, failed = _fan_out_resume(
        members, decision, fingerprint=fingerprint, roadmap=roadmap, workspace=workspace, adapter=adapter,
        extra={"note": note} if note else None,
    )
    _project_fingerprint(None, repo_root=repo_root, stale_ids=stale, now=moment)
    return {"outcome": "proceed", "resumed": resumed, "skipped": skipped + failed, "records": records}


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
    lease_generation: Optional[int] = None,
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
        if gate_enum is Gate.ESCALATE_RESUME and lease_generation is not None:
            record_generation = record.get("lease_generation")
            if record_generation is not None and record_generation != lease_generation:
                raise ApprovalRefError(f"approval_ref {approval_ref!r} is for a different lease generation")
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


def gate_log(
    workspace: Path, repo_root: Path, *, managed_root: Optional[Path] = None
) -> list[dict[str, Any]]:
    """The sidecar `gate_decisions` for the roadmap at `workspace`, unioned with
    each ready-or-not item's child `gate_decisions` resolved through the
    attempt's recorded worktree (D6). Sorted by `recorded_at`.

    The attempt's portable `worktree_ref` resolves against `managed_root`
    (default `<repo_root>/.git-worktrees`) or, for harness-provided isolation,
    `repo_root` (dispatch-contract D7)."""
    workspace = Path(workspace)
    repo_root = Path(repo_root)
    managed = Path(managed_root) if managed_root is not None else repo_root / ".git-worktrees"
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
            attempts_by_change.get(change_id), repo_root, change_id, managed
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
    attempt: Optional[dict[str, Any]], repo_root: Path, change_id: str, managed_root: Path
) -> Optional[Path]:
    if attempt is not None:
        from shared import dispatch_contract

        worktree = dispatch_contract.resolve_worktree(
            attempt.get("isolation") or {}, repo_root=repo_root, managed_root=managed_root
        )
        if worktree is not None:
            return worktree / "openspec" / "changes" / change_id / "loop-state.json"
    # Fallback: the change has since merged into the supervisor's own tree.
    fallback = repo_root / "openspec" / "changes" / change_id / "loop-state.json"
    return fallback if fallback.parent.is_dir() else None
