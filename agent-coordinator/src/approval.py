"""Approval queue service for human-in-the-loop authorization gates."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .db import DatabaseClient, get_db


@dataclass
class ApprovalRequest:
    """Represents an approval request in the queue."""

    id: str
    agent_id: str
    agent_type: str | None
    operation: str
    resource: str | None
    context: dict[str, Any]
    status: str  # pending, approved, denied, expired
    decided_by: str | None
    decided_at: datetime | None
    reason: str | None
    expires_at: datetime
    created_at: datetime


class ApprovalService:
    """Service for managing human-in-the-loop approval requests."""

    def __init__(self, db: DatabaseClient | None = None) -> None:
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def submit_request(
        self,
        agent_id: str,
        operation: str,
        *,
        agent_type: str | None = None,
        resource: str | None = None,
        context: dict[str, Any] | None = None,
        timeout_seconds: int = 3600,
    ) -> ApprovalRequest:
        """Submit an approval request. Returns the created request."""
        request_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=timeout_seconds)

        await self.db.insert(
            "approval_queue",
            {
                "id": request_id,
                "agent_id": agent_id,
                "agent_type": agent_type,
                "operation": operation,
                "resource": resource,
                "context": json.dumps(context or {}),
                "status": "pending",
                "expires_at": expires_at.isoformat(),
                "created_at": now.isoformat(),
            },
        )

        return ApprovalRequest(
            id=request_id,
            agent_id=agent_id,
            agent_type=agent_type,
            operation=operation,
            resource=resource,
            context=context or {},
            status="pending",
            decided_by=None,
            decided_at=None,
            reason=None,
            expires_at=expires_at,
            created_at=now,
        )

    async def check_request(self, request_id: str) -> ApprovalRequest | None:
        """Check the status of an approval request."""
        rows = await self.db.query(
            "approval_queue",
            f"id=eq.{request_id}",
        )
        if not rows:
            return None
        return self._row_to_request(rows[0])

    async def decide_request(
        self,
        request_id: str,
        decision: str,
        *,
        decided_by: str | None = None,
        reason: str | None = None,
    ) -> ApprovalRequest | None:
        """Approve or deny a pending request."""
        if decision not in ("approved", "denied"):
            raise ValueError(f"Invalid decision: {decision}")

        now = datetime.now(UTC)
        rows = await self.db.query(
            "approval_queue",
            f"id=eq.{request_id}&status=eq.pending",
        )
        if not rows:
            return None

        await self.db.update(
            "approval_queue",
            {"id": request_id},
            {
                "status": decision,
                "decided_by": decided_by,
                "decided_at": now.isoformat(),
                "reason": reason,
            },
        )

        request = self._row_to_request(rows[0])
        request.status = decision
        request.decided_by = decided_by
        request.decided_at = now
        request.reason = reason
        return request

    async def expire_stale_requests(self) -> int:
        """Expire pending requests past their timeout. Returns count expired."""
        now = datetime.now(UTC)
        rows = await self.db.query(
            "approval_queue",
            f"status=eq.pending&expires_at=lt.{now.isoformat()}",
        )
        count = 0
        for row in rows:
            await self.db.update(
                "approval_queue",
                {"id": row["id"]},
                {"status": "expired"},
            )
            count += 1
        return count

    async def list_pending(
        self,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequest]:
        """List pending approval requests."""
        filters = "status=eq.pending&order=created_at.asc"
        if agent_id:
            filters += f"&agent_id=eq.{agent_id}"
        rows = await self.db.query("approval_queue", filters)
        return [self._row_to_request(r) for r in rows[:limit]]

    def _row_to_request(self, row: dict[str, Any]) -> ApprovalRequest:
        ctx = row.get("context", {})
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        return ApprovalRequest(
            id=str(row["id"]),
            agent_id=row["agent_id"],
            agent_type=row.get("agent_type"),
            operation=row["operation"],
            resource=row.get("resource"),
            context=ctx,
            status=row["status"],
            decided_by=row.get("decided_by"),
            decided_at=_parse_dt(row.get("decided_at")),
            reason=row.get("reason"),
            expires_at=_parse_dt(row.get("expires_at")) or datetime.now(UTC),
            created_at=_parse_dt(row.get("created_at")) or datetime.now(UTC),
        )


def _parse_dt(val: Any) -> datetime | None:
    """Parse a datetime value from various formats."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val).replace("Z", "+00:00"))


# Module-level singleton
_approval_service: ApprovalService | None = None


def get_approval_service() -> ApprovalService:
    """Get the global approval service instance."""
    global _approval_service
    if _approval_service is None:
        _approval_service = ApprovalService()
    return _approval_service


def reset_approval_service() -> None:
    """Reset the global approval service (for testing)."""
    global _approval_service
    _approval_service = None
