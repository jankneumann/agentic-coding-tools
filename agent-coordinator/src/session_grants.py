"""Session-scoped permission grants for zero-standing-permissions model."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .db import DatabaseClient, get_db


@dataclass
class PermissionGrant:
    """A session-scoped permission grant."""

    id: str
    session_id: str
    agent_id: str
    operation: str
    justification: str | None
    granted_at: datetime
    expires_at: datetime | None
    approved_by: str | None


class SessionGrantService:
    """Manage session-scoped permission grants."""

    def __init__(self, db: DatabaseClient | None = None) -> None:
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def request_grant(
        self,
        session_id: str,
        agent_id: str,
        operation: str,
        justification: str | None = None,
    ) -> PermissionGrant:
        """Request a session-scoped permission grant."""
        grant_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        await self.db.insert("session_permission_grants", {
            "id": grant_id,
            "session_id": session_id,
            "agent_id": agent_id,
            "operation": operation,
            "justification": justification,
            "granted_at": now.isoformat(),
        })

        return PermissionGrant(
            id=grant_id,
            session_id=session_id,
            agent_id=agent_id,
            operation=operation,
            justification=justification,
            granted_at=now,
            expires_at=None,
            approved_by=None,
        )

    async def get_active_grants(self, session_id: str) -> list[PermissionGrant]:
        """Get all active grants for a session."""
        rows = await self.db.query(
            "session_permission_grants",
            query_params=f"session_id=eq.{session_id}&order=granted_at.asc",
        )
        return [self._row_to_grant(r) for r in rows]

    async def has_grant(self, session_id: str, operation: str) -> bool:
        """Check if a session has a specific grant."""
        rows = await self.db.query(
            "session_permission_grants",
            query_params=f"session_id=eq.{session_id}&operation=eq.{operation}",
        )
        return len(rows) > 0

    async def revoke_grants(self, session_id: str) -> int:
        """Revoke all grants for a session. Returns count revoked."""
        rows = await self.db.query(
            "session_permission_grants",
            query_params=f"session_id=eq.{session_id}",
        )
        count = len(rows)
        if count > 0:
            await self.db.delete(
                "session_permission_grants",
                match={"session_id": session_id},
            )
        return count

    def _row_to_grant(self, row: dict[str, Any]) -> PermissionGrant:
        return PermissionGrant(
            id=str(row["id"]),
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            operation=row["operation"],
            justification=row.get("justification"),
            granted_at=_parse_dt(row.get("granted_at")) or datetime.now(UTC),
            expires_at=_parse_dt(row.get("expires_at")),
            approved_by=row.get("approved_by"),
        )


def _parse_dt(val: Any) -> datetime | None:
    """Parse a datetime value from various formats."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val).replace("Z", "+00:00"))


_session_grant_service: SessionGrantService | None = None


def get_session_grant_service() -> SessionGrantService:
    """Get the global session grant service instance."""
    global _session_grant_service
    if _session_grant_service is None:
        _session_grant_service = SessionGrantService()
    return _session_grant_service


def reset_session_grant_service() -> None:
    """Reset the global session grant service (for testing)."""
    global _session_grant_service
    _session_grant_service = None
