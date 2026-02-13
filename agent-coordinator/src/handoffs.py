"""Handoff document service for Agent Coordinator.

Provides session continuity by persisting structured handoff documents
that agents can write at session end and read at session start.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from .config import get_config
from .db import DatabaseClient, get_db


@dataclass
class HandoffDocument:
    """Represents a handoff document for session continuity."""

    id: UUID
    agent_name: str
    session_id: str | None
    summary: str
    completed_work: list[str] = field(default_factory=list)
    in_progress: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HandoffDocument":
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(
                str(data["created_at"]).replace("Z", "+00:00")
            )

        return cls(
            id=UUID(str(data["id"])),
            agent_name=data["agent_name"],
            session_id=data.get("session_id"),
            summary=data["summary"],
            completed_work=data.get("completed_work", []),
            in_progress=data.get("in_progress", []),
            decisions=data.get("decisions", []),
            next_steps=data.get("next_steps", []),
            relevant_files=data.get("relevant_files", []),
            created_at=created_at,
        )


@dataclass
class WriteHandoffResult:
    """Result of writing a handoff document."""

    success: bool
    handoff_id: UUID | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WriteHandoffResult":
        handoff_id = None
        if data.get("handoff_id"):
            handoff_id = UUID(str(data["handoff_id"]))

        return cls(
            success=data["success"],
            handoff_id=handoff_id,
            error=data.get("error"),
        )


@dataclass
class ReadHandoffResult:
    """Result of reading handoff documents."""

    handoffs: list[HandoffDocument]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReadHandoffResult":
        handoffs = []
        for h in data.get("handoffs", []):
            handoffs.append(HandoffDocument.from_dict(h))
        return cls(handoffs=handoffs)


class HandoffService:
    """Service for managing handoff documents."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def write(
        self,
        summary: str,
        agent_name: str | None = None,
        session_id: str | None = None,
        completed_work: list[str] | None = None,
        in_progress: list[str] | None = None,
        decisions: list[str] | None = None,
        next_steps: list[str] | None = None,
        relevant_files: list[str] | None = None,
    ) -> WriteHandoffResult:
        """Write a handoff document for session continuity.

        Args:
            summary: Required summary of the session/work done
            agent_name: Agent writing the handoff (default: from config)
            session_id: Session identifier (default: from config)
            completed_work: List of completed work items
            in_progress: List of in-progress items
            decisions: List of decisions made
            next_steps: List of next steps
            relevant_files: List of relevant file paths

        Returns:
            WriteHandoffResult with handoff_id on success
        """
        config = get_config()

        try:
            result = await self.db.rpc(
                "write_handoff",
                {
                    "p_agent_name": agent_name or config.agent.agent_id,
                    "p_session_id": session_id or config.agent.session_id,
                    "p_summary": summary,
                    "p_completed_work": completed_work or [],
                    "p_in_progress": in_progress or [],
                    "p_decisions": decisions or [],
                    "p_next_steps": next_steps or [],
                    "p_relevant_files": relevant_files or [],
                },
            )
        except Exception:
            return WriteHandoffResult(success=False, error="database_unavailable")

        return WriteHandoffResult.from_dict(result)

    async def read(
        self,
        agent_name: str | None = None,
        limit: int = 1,
    ) -> ReadHandoffResult:
        """Read recent handoff documents.

        Args:
            agent_name: Filter by agent name (None for all agents)
            limit: Maximum number of handoffs to return (default: 1)

        Returns:
            ReadHandoffResult with list of handoff documents
        """
        result = await self.db.rpc(
            "read_handoff",
            {
                "p_agent_name": agent_name,
                "p_limit": limit,
            },
        )

        return ReadHandoffResult.from_dict(result)

    async def get_recent(
        self,
        limit: int = 5,
    ) -> list[HandoffDocument]:
        """Get recent handoff documents across all agents.

        Args:
            limit: Maximum number of handoffs to return

        Returns:
            List of recent handoff documents
        """
        handoffs = await self.db.query(
            "handoff_documents",
            f"order=created_at.desc&limit={limit}",
        )
        return [HandoffDocument.from_dict(h) for h in handoffs]


# Global service instance
_handoff_service: HandoffService | None = None


def get_handoff_service() -> HandoffService:
    """Get the global handoff service instance."""
    global _handoff_service
    if _handoff_service is None:
        _handoff_service = HandoffService()
    return _handoff_service
