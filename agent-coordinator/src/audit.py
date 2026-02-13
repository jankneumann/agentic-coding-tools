"""Audit trail service for Agent Coordinator.

Provides immutable, async logging of all coordination operations.
Audit entries are append-only — the database enforces immutability via triggers.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .config import get_config
from .db import DatabaseClient, get_db


@dataclass
class AuditEntry:
    """Represents an audit log entry."""

    id: str
    agent_id: str
    agent_type: str | None
    operation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None
    success: bool | None = None
    error_message: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEntry":
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(
                str(data["created_at"]).replace("Z", "+00:00")
            )
        return cls(
            id=str(data["id"]),
            agent_id=data["agent_id"],
            agent_type=data.get("agent_type"),
            operation=data["operation"],
            parameters=data.get("parameters") or {},
            result=data.get("result") or {},
            duration_ms=data.get("duration_ms"),
            success=data.get("success"),
            error_message=data.get("error_message"),
            created_at=created_at,
        )


@dataclass
class AuditResult:
    """Result of an audit logging operation."""

    success: bool
    entry_id: str | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditResult":
        return cls(
            success=data.get("success", False),
            entry_id=data.get("entry_id") or data.get("id"),
            error=data.get("error"),
        )


class AuditService:
    """Service for audit trail logging and querying."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def log_operation(
        self,
        agent_id: str | None = None,
        agent_type: str | None = None,
        operation: str = "",
        parameters: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        success: bool | None = None,
        error_message: str | None = None,
    ) -> AuditResult:
        """Log a coordination operation to the audit trail.

        When async_logging is enabled (default), this fires-and-forgets
        the insert to avoid blocking the caller.
        """
        config = get_config()
        agent_id = agent_id or config.agent.agent_id
        agent_type = agent_type or config.agent.agent_type

        data = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "operation": operation,
            "parameters": parameters or {},
            "result": result or {},
            "duration_ms": duration_ms,
            "success": success,
            "error_message": error_message,
        }

        if config.audit.async_logging:
            # Fire-and-forget: don't block the caller
            asyncio.create_task(self._insert_audit_entry(data))
            return AuditResult(success=True)
        else:
            return await self._insert_audit_entry(data)

    async def _insert_audit_entry(self, data: dict[str, Any]) -> AuditResult:
        """Insert an audit entry into the database."""
        try:
            row = await self.db.insert("audit_log", data)
            return AuditResult(success=True, entry_id=str(row.get("id", "")))
        except Exception as e:
            return AuditResult(success=False, error=str(e))

    async def query(
        self,
        agent_id: str | None = None,
        operation: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """Query audit log entries with optional filters."""
        query_parts = ["order=created_at.desc", f"limit={limit}"]

        if agent_id:
            query_parts.append(f"agent_id=eq.{agent_id}")
        if operation:
            query_parts.append(f"operation=eq.{operation}")
        if since:
            query_parts.append(f"created_at=gte.{since.isoformat()}")
        if until:
            query_parts.append(f"created_at=lte.{until.isoformat()}")

        query = "&".join(query_parts)
        rows = await self.db.query("audit_log", query)
        return [AuditEntry.from_dict(row) for row in rows]

    def timed(self, operation: str) -> "AuditTimer":
        """Create a context manager for timing and logging an operation."""
        return AuditTimer(self, operation)


class AuditTimer:
    """Context manager for timing operations and logging to audit trail."""

    def __init__(self, service: AuditService, operation: str):
        self.service = service
        self.operation = operation
        self._start: float = 0

    async def __aenter__(self) -> "AuditTimer":
        self._start = time.monotonic()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        duration_ms = int((time.monotonic() - self._start) * 1000)
        await self.service.log_operation(
            operation=self.operation,
            duration_ms=duration_ms,
            success=exc_type is None,
            error_message=str(exc_val) if exc_val else None,
        )


# Global service instance
_audit_service: AuditService | None = None


def get_audit_service() -> AuditService:
    """Get the global audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
