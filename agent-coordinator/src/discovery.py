"""Agent discovery service for Agent Coordinator.

Provides agent registration, discovery, heartbeat monitoring,
and dead agent cleanup for multi-agent coordination.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .audit import get_audit_service
from .config import get_config
from .db import DatabaseClient, get_db


@dataclass
class AgentInfo:
    """Represents a discovered agent."""

    agent_id: str
    agent_type: str
    session_id: str
    capabilities: list[str] = field(default_factory=list)
    status: str = "active"
    current_task: str | None = None
    last_heartbeat: datetime | None = None
    started_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentInfo":
        def parse_dt(val: Any) -> datetime | None:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))

        return cls(
            agent_id=data["agent_id"],
            agent_type=data["agent_type"],
            session_id=data["session_id"],
            capabilities=data.get("capabilities", []),
            status=data.get("status", "active"),
            current_task=data.get("current_task"),
            last_heartbeat=parse_dt(data.get("last_heartbeat")),
            started_at=parse_dt(data.get("started_at")),
        )


@dataclass
class RegisterResult:
    """Result of agent registration."""

    success: bool
    session_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegisterResult":
        return cls(
            success=data["success"],
            session_id=data.get("session_id"),
        )


@dataclass
class DiscoverResult:
    """Result of agent discovery."""

    agents: list[AgentInfo]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiscoverResult":
        agents = [AgentInfo.from_dict(a) for a in data.get("agents", [])]
        return cls(agents=agents)


@dataclass
class HeartbeatResult:
    """Result of a heartbeat update."""

    success: bool
    session_id: str | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HeartbeatResult":
        return cls(
            success=data["success"],
            session_id=data.get("session_id"),
            error=data.get("error"),
        )


@dataclass
class CleanupResult:
    """Result of dead agent cleanup."""

    success: bool
    agents_cleaned: int = 0
    locks_released: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CleanupResult":
        return cls(
            success=data["success"],
            agents_cleaned=data.get("agents_cleaned", 0),
            locks_released=data.get("locks_released", 0),
        )


class DiscoveryService:
    """Service for agent discovery and lifecycle management."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def register(
        self,
        agent_id: str | None = None,
        agent_type: str | None = None,
        session_id: str | None = None,
        capabilities: list[str] | None = None,
        current_task: str | None = None,
    ) -> RegisterResult:
        """Register an agent session for discovery.

        Args:
            agent_id: Agent identifier (default: from config)
            agent_type: Type of agent (default: from config)
            session_id: Session identifier (default: from config)
            capabilities: List of agent capabilities
            current_task: Description of current task

        Returns:
            RegisterResult with session_id
        """
        config = get_config()

        result = await self.db.rpc(
            "register_agent_session",
            {
                "p_agent_id": agent_id or config.agent.agent_id,
                "p_agent_type": agent_type or config.agent.agent_type,
                "p_session_id": session_id or config.agent.session_id,
                "p_capabilities": capabilities or [],
                "p_current_task": current_task,
            },
        )

        reg_result = RegisterResult.from_dict(result)

        try:
            await get_audit_service().log_operation(
                agent_id=agent_id or config.agent.agent_id,
                agent_type=agent_type or config.agent.agent_type,
                operation="register_agent",
                parameters={"capabilities": capabilities or []},
                success=reg_result.success,
            )
        except Exception:
            pass

        return reg_result

    async def discover(
        self,
        capability: str | None = None,
        status: str | None = None,
    ) -> DiscoverResult:
        """Discover active agents with optional filtering.

        Args:
            capability: Filter by capability (e.g., 'coding', 'review')
            status: Filter by status ('active', 'idle', 'disconnected')

        Returns:
            DiscoverResult with list of matching agents
        """
        result = await self.db.rpc(
            "discover_agents",
            {
                "p_capability": capability,
                "p_status": status,
            },
        )

        return DiscoverResult.from_dict(result)

    async def heartbeat(
        self,
        session_id: str | None = None,
    ) -> HeartbeatResult:
        """Send a heartbeat to indicate the agent is still alive.

        Args:
            session_id: Session to heartbeat (default: from config)

        Returns:
            HeartbeatResult indicating success
        """
        config = get_config()

        try:
            result = await self.db.rpc(
                "agent_heartbeat",
                {
                    "p_session_id": session_id or config.agent.session_id,
                },
            )
        except Exception:
            return HeartbeatResult(success=False, error="database_unavailable")

        return HeartbeatResult.from_dict(result)

    async def cleanup_dead_agents(
        self,
        stale_threshold_minutes: int = 15,
    ) -> CleanupResult:
        """Clean up dead agents and release their locks.

        Args:
            stale_threshold_minutes: Minutes before an agent is considered dead

        Returns:
            CleanupResult with counts of cleaned agents and released locks
        """
        result = await self.db.rpc(
            "cleanup_dead_agents",
            {
                "p_stale_threshold": f"{stale_threshold_minutes} minutes",
            },
        )

        cleanup_result = CleanupResult.from_dict(result)

        try:
            await get_audit_service().log_operation(
                operation="cleanup_dead_agents",
                parameters={
                    "stale_threshold_minutes": stale_threshold_minutes
                },
                result={
                    "agents_cleaned": cleanup_result.agents_cleaned,
                    "locks_released": cleanup_result.locks_released,
                },
                success=cleanup_result.success,
            )
        except Exception:
            pass

        return cleanup_result


# Global service instance
_discovery_service: DiscoveryService | None = None


def get_discovery_service() -> DiscoveryService:
    """Get the global discovery service instance."""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = DiscoveryService()
    return _discovery_service
