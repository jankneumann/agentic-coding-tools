"""Project-keyed projection of pending human gates.

Pending gates live in each repository (parked dispatch attempts in
``checkpoint.json``, ``pending_gate`` in ``loop-state.json``). A collector in
the repository pushes the whole pending set for its project; this service
stores the latest snapshot per project and answers one question across every
enrolled project: what is waiting for a decision?

The stored snapshot is a cache of what a repository last reported. Nothing
here records a decision. A decision is made through the approval service when
the gate carries an approval request, and in the repository otherwise; it
reaches this table only as the gate's absence from a later snapshot.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .approval import (
    ApprovalRequest,
    ApprovalService,
    get_approval_service,
    normalize_request_id,
)
from .config import GateProjectionConfig, get_config
from .db import DatabaseClient, get_db

logger = logging.getLogger(__name__)

TABLE = "gate_projection_snapshots"
PROJECT_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
GATE_ID_PATTERN = r"^[a-f0-9]{16}$"
MAX_GATES = 500
MAX_SOURCE_ERRORS = 100
# Upper bound on the pending approvals joined into one listing.
PENDING_APPROVAL_LIMIT = 500

APPROVAL_OPTIONS = ["approved", "denied"]
REPOSITORY_OPTIONS = ["approved", "rejected"]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SourceError(BaseModel):
    """A gate source the collector could not read."""

    path: str = Field(max_length=500)
    error: str = Field(max_length=500)


class SnapshotGate(BaseModel):
    """One pending gate as a repository reported it.

    Timestamps stay strings: they are echoed back to the reader exactly as the
    collector wrote them, and only the coordinator's own ``received_at`` is
    ever compared against a clock.
    """

    gate_id: str = Field(pattern=GATE_ID_PATTERN)
    gate: str = Field(min_length=1, max_length=64)
    source: Literal["checkpoint", "loop_state"]
    subject: str = Field(min_length=1, max_length=300)
    prompt: str | None = Field(default=None, max_length=4000)
    requested_at: str | None = Field(default=None, max_length=64)
    deadline: str | None = Field(default=None, max_length=64)
    timeout_seconds: int | None = Field(default=None, ge=0)
    default_action: str | None = Field(default=None, max_length=64)
    disposition: str = Field(default="block", max_length=64)
    approval_id: str | None = Field(default=None, max_length=64)
    answer_hint: str | None = Field(default=None, max_length=1000)
    phase: str | None = Field(default=None, max_length=64)
    roadmap_id: str | None = Field(default=None, max_length=200)
    change_id: str | None = Field(default=None, max_length=200)
    item_id: str | None = Field(default=None, max_length=200)
    dispatch_id: str | None = Field(default=None, max_length=300)


class GateSnapshotRequest(BaseModel):
    """The complete pending set of one project at one moment."""

    project: str = Field(pattern=PROJECT_PATTERN, max_length=200)
    collected_at: datetime
    gates: list[SnapshotGate] = Field(max_length=MAX_GATES)
    source_errors: list[SourceError] = Field(
        default_factory=list, max_length=MAX_SOURCE_ERRORS
    )


class GateDecisionRequest(BaseModel):
    """A decision on a listed gate that carries an approval request."""

    project: str = Field(pattern=PROJECT_PATTERN, max_length=200)
    gate_id: str = Field(pattern=GATE_ID_PATTERN)
    decision: Literal["approved", "denied"]
    reason: str | None = Field(default=None, max_length=2000)
    decided_by: str | None = Field(default=None, max_length=200)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProjectNotEnrolledError(Exception):
    """The project is not in ``GATE_PROJECTION_PROJECTS``."""

    def __init__(self, project: str) -> None:
        super().__init__(f"Project not enrolled: {project}")
        self.project = project


class GateNotFoundError(Exception):
    """No stored snapshot of the project holds this gate."""


class GateNotDecidableError(Exception):
    """The gate exists but cannot be decided through the coordinator."""

    def __init__(self, reason: str, answer_hint: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.answer_hint = answer_hint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso(value: Any) -> str | None:
    parsed = _parse_dt(value)
    return parsed.isoformat() if parsed else None


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    """Return a row's snapshot, whether the driver decoded the JSONB or not."""
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _gates(row: dict[str, Any]) -> list[dict[str, Any]]:
    gates = _payload(row).get("gates")
    return [g for g in gates if isinstance(g, dict)] if isinstance(gates, list) else []


def _source_errors(row: dict[str, Any]) -> list[dict[str, Any]]:
    errors = _payload(row).get("source_errors")
    if not isinstance(errors, list):
        return []
    return [e for e in errors if isinstance(e, dict)]


def _orphan_gate(approval: ApprovalRequest) -> dict[str, Any]:
    """Describe a pending approval that no enrolled snapshot references."""
    return {
        "project": None,
        "project_status": None,
        "gate_id": None,
        "gate": approval.operation.removeprefix("gate:"),
        "source": "approval_service",
        "subject": approval.resource or approval.operation,
        "options": list(APPROVAL_OPTIONS),
        "deadline": _iso(approval.expires_at),
        "decision_route": "approval_service",
        "approval_id": approval.id,
        "answer_hint": f"POST /approvals/{approval.id}/decide",
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GateProjectionService:
    """Stores per-project gate snapshots and lists what awaits a decision."""

    def __init__(
        self,
        db: DatabaseClient | None = None,
        approvals: ApprovalService | None = None,
        config: GateProjectionConfig | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = db
        self._approvals = approvals
        self._config = config
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    @property
    def approvals(self) -> ApprovalService:
        if self._approvals is None:
            self._approvals = get_approval_service()
        return self._approvals

    @property
    def config(self) -> GateProjectionConfig:
        return self._config or get_config().gate_projection

    def _require_enrolled(self, project: str) -> None:
        if project not in self.config.projects:
            raise ProjectNotEnrolledError(project)

    async def replace_snapshot(self, snapshot: GateSnapshotRequest) -> dict[str, Any]:
        """Replace the project's stored snapshot with this one."""
        self._require_enrolled(snapshot.project)
        payload = {
            "gates": [g.model_dump(mode="json") for g in snapshot.gates],
            "source_errors": [e.model_dump(mode="json") for e in snapshot.source_errors],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        received_at = self._now().isoformat()
        row = {
            "project": snapshot.project,
            "collected_at": snapshot.collected_at.isoformat(),
            "received_at": received_at,
            "payload": payload,
            "digest": digest,
        }
        match = {"project": snapshot.project}
        if not await self.db.update(TABLE, match, row):
            try:
                await self.db.insert(TABLE, row)
            except Exception:
                # A concurrent first push won the insert; ours is the later
                # snapshot, so it replaces that row.
                if not await self.db.update(TABLE, match, row):
                    raise
        return {
            "success": True,
            "project": snapshot.project,
            "gate_count": len(snapshot.gates),
            "digest": digest,
            "received_at": received_at,
        }

    async def delete_snapshot(self, project: str) -> dict[str, Any]:
        """Drop the project's snapshot; the next push restores it."""
        self._require_enrolled(project)
        existed = bool(await self.db.query(TABLE, f"project=eq.{project}"))
        if existed:
            await self.db.delete(TABLE, {"project": project})
        return {"success": True, "project": project, "deleted": existed}

    async def list_pending(self) -> dict[str, Any]:
        """List pending gates of every enrolled project, with project health."""
        now = self._now()
        enrolled = sorted(self.config.projects)
        if not enrolled:
            return {"generated_at": now.isoformat(), "gates": [], "projects": []}

        rows = {
            r.get("project"): r
            for r in await self.db.query(TABLE)
            if r.get("project") in self.config.projects
        }
        pending = {
            a.id: a for a in await self.approvals.list_pending(limit=PENDING_APPROVAL_LIMIT)
        }

        # Approvals a snapshot references that are not pending were decided (or
        # never existed); one batched read tells the two apart.
        referenced: set[str] = set()
        for row in rows.values():
            for gate in _gates(row):
                approval_id = normalize_request_id(gate.get("approval_id"))
                if approval_id:
                    referenced.add(approval_id)
        unresolved = sorted(referenced - pending.keys())
        decided: set[str] = set()
        if unresolved:
            decided = {a.id for a in await self.approvals.get_requests(unresolved)}

        gates: list[dict[str, Any]] = []
        projects: list[dict[str, Any]] = []
        for project in enrolled:
            stored = rows.get(project)
            if stored is None:
                projects.append(
                    {
                        "project": project,
                        "status": "degraded",
                        "reason": "no_snapshot",
                        "collected_at": None,
                        "received_at": None,
                        "gate_count": 0,
                        "decided_awaiting_sync": 0,
                        "source_errors": [],
                    }
                )
                continue
            row = stored

            received = _parse_dt(row.get("received_at"))
            source_errors = _source_errors(row)
            reason: str | None = None
            if received is None or (
                (now - received).total_seconds() > self.config.stale_seconds
            ):
                reason = "stale"
            elif source_errors:
                reason = "source_errors"
            status = "degraded" if reason else "ok"

            listed = 0
            awaiting_sync = 0
            for gate in _gates(row):
                approval_id = normalize_request_id(gate.get("approval_id"))
                approval = pending.get(approval_id) if approval_id else None
                if approval is None and approval_id in decided:
                    awaiting_sync += 1
                    continue
                entry = {**gate, "project": project, "project_status": status}
                if approval is not None:
                    entry.update(
                        options=list(APPROVAL_OPTIONS),
                        deadline=_iso(approval.expires_at),
                        decision_route="approval_service",
                        approval_id=approval.id,
                    )
                else:
                    entry.update(
                        options=list(REPOSITORY_OPTIONS),
                        deadline=gate.get("deadline"),
                        decision_route="repository",
                        approval_id=None,
                    )
                entry.setdefault("answer_hint", None)
                gates.append(entry)
                listed += 1

            projects.append(
                {
                    "project": project,
                    "status": status,
                    "reason": reason,
                    "collected_at": _iso(row.get("collected_at")),
                    "received_at": _iso(row.get("received_at")),
                    "gate_count": listed,
                    "decided_awaiting_sync": awaiting_sync,
                    "source_errors": source_errors,
                }
            )

        gates.extend(
            _orphan_gate(a) for a in pending.values() if a.id not in referenced
        )
        return {"generated_at": now.isoformat(), "gates": gates, "projects": projects}

    async def decide(
        self, request: GateDecisionRequest, *, decided_by: str
    ) -> dict[str, Any]:
        """Decide a gate through its approval request. Never writes a snapshot."""
        self._require_enrolled(request.project)
        rows = await self.db.query(TABLE, f"project=eq.{request.project}")
        gate = next(
            (g for r in rows for g in _gates(r) if g.get("gate_id") == request.gate_id),
            None,
        )
        if gate is None:
            raise GateNotFoundError(f"{request.project} {request.gate_id}")

        hint = gate.get("answer_hint")
        approval_id = normalize_request_id(gate.get("approval_id"))
        if approval_id is None:
            raise GateNotDecidableError("no_approval_request", hint)
        approval = await self.approvals.decide_request(
            approval_id, request.decision, decided_by=decided_by, reason=request.reason
        )
        if approval is None:
            raise GateNotDecidableError("approval_not_pending", hint)
        return {
            "success": True,
            "project": request.project,
            "gate_id": request.gate_id,
            "approval": {"request_id": approval.id, "status": approval.status},
        }


_gate_projection_service: GateProjectionService | None = None


def get_gate_projection_service() -> GateProjectionService:
    """Return the process-wide gate projection service."""
    global _gate_projection_service
    if _gate_projection_service is None:
        _gate_projection_service = GateProjectionService()
    return _gate_projection_service


def reset_gate_projection_service() -> None:
    """Drop the singleton (tests)."""
    global _gate_projection_service
    _gate_projection_service = None
