"""Memory service for Agent Coordinator.

Provides episodic and procedural memory for cross-session learning.
Memories are stored with relevance scoring and time-decay.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .config import get_config
from .db import DatabaseClient, get_db


@dataclass
class EpisodicMemory:
    """Represents an episodic memory entry."""

    id: str
    agent_id: str
    event_type: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    outcome: str | None = None
    lessons: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    relevance_score: float = 1.0
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EpisodicMemory":
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(
                str(data["created_at"]).replace("Z", "+00:00")
            )
        return cls(
            id=str(data["id"]),
            agent_id=data.get("agent_id", ""),
            event_type=data.get("event_type", ""),
            summary=data.get("summary", ""),
            details=data.get("details") or {},
            outcome=data.get("outcome"),
            lessons=data.get("lessons") or [],
            tags=data.get("tags") or [],
            relevance_score=float(data.get("relevance_score", 1.0)),
            created_at=created_at,
        )


@dataclass
class MemoryResult:
    """Result of a memory storage operation."""

    success: bool
    memory_id: str | None = None
    action: str | None = None  # 'created' or 'deduplicated'
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryResult":
        return cls(
            success=data.get("success", False),
            memory_id=str(data["memory_id"]) if data.get("memory_id") else None,
            action=data.get("action"),
            error=data.get("error"),
        )


@dataclass
class RecallResult:
    """Result of a memory recall operation."""

    memories: list[EpisodicMemory] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> "RecallResult":
        if not data or data == []:
            return cls(memories=[])
        if isinstance(data, list):
            return cls(memories=[EpisodicMemory.from_dict(m) for m in data])
        return cls(memories=[])


class MemoryService:
    """Service for agent memory operations."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def remember(
        self,
        event_type: str = "discovery",
        summary: str = "",
        details: dict[str, Any] | None = None,
        outcome: str | None = None,
        lessons: list[str] | None = None,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> MemoryResult:
        """Store an episodic memory.

        Args:
            event_type: Type of event ('error', 'success', 'decision', 'discovery', 'optimization')
            summary: Short description of what happened
            details: Additional structured data
            outcome: 'positive', 'negative', or 'neutral'
            lessons: Lessons learned from this event
            tags: Tags for filtering during recall
            agent_id: Agent storing the memory (default: from config)
            session_id: Session ID (default: from config)

        Returns:
            MemoryResult with memory_id and action ('created' or 'deduplicated')
        """
        config = get_config()

        result = await self.db.rpc(
            "store_episodic_memory",
            {
                "p_agent_id": agent_id or config.agent.agent_id,
                "p_session_id": session_id or config.agent.session_id,
                "p_event_type": event_type,
                "p_summary": summary,
                "p_details": details or {},
                "p_outcome": outcome,
                "p_lessons": lessons or [],
                "p_tags": tags or [],
            },
        )

        return MemoryResult.from_dict(result)

    async def recall(
        self,
        tags: list[str] | None = None,
        event_type: str | None = None,
        limit: int = 10,
        min_relevance: float = 0.0,
        agent_id: str | None = None,
    ) -> RecallResult:
        """Recall relevant memories.

        Args:
            tags: Filter by tags (memories matching ANY tag are returned)
            event_type: Filter by event type
            limit: Maximum number of memories to return
            min_relevance: Minimum relevance score threshold
            agent_id: Filter by agent (None for all agents)

        Returns:
            RecallResult with sorted memories (highest relevance first)
        """
        result = await self.db.rpc(
            "get_relevant_memories",
            {
                "p_agent_id": agent_id,
                "p_tags": tags or [],
                "p_event_type": event_type,
                "p_limit": limit,
                "p_min_relevance": min_relevance,
            },
        )

        return RecallResult.from_dict(result)


# Global service instance
_memory_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    """Get the global memory service instance."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
