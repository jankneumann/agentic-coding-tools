"""Agent profiles service for Agent Coordinator.

Provides configurable agent profiles with trust levels, operation restrictions,
and resource limits. Profiles are stored in the database with code-level defaults.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from .audit import get_audit_service
from .config import get_config
from .db import DatabaseClient, get_db


@dataclass
class AgentProfile:
    """Represents an agent profile with capabilities and constraints."""

    id: str
    name: str
    agent_type: str
    trust_level: int = 2
    allowed_operations: list[str] = field(default_factory=list)
    blocked_operations: list[str] = field(default_factory=list)
    max_file_modifications: int = 50
    max_execution_time_seconds: int = 300
    max_api_calls_per_hour: int = 1000
    network_policy: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentProfile":
        return cls(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            agent_type=data.get("agent_type", ""),
            trust_level=int(data.get("trust_level", 2)),
            allowed_operations=data.get("allowed_operations") or [],
            blocked_operations=data.get("blocked_operations") or [],
            max_file_modifications=int(data.get("max_file_modifications", 50)),
            max_execution_time_seconds=int(data.get("max_execution_time_seconds", 300)),
            max_api_calls_per_hour=int(data.get("max_api_calls_per_hour", 1000)),
            network_policy=data.get("network_policy") or {},
            enabled=data.get("enabled", True),
        )


@dataclass
class ProfileResult:
    """Result of a profile lookup."""

    success: bool
    profile: AgentProfile | None = None
    source: str | None = None  # 'assignment', 'default', or None
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProfileResult":
        profile = None
        if data.get("profile"):
            profile = AgentProfile.from_dict(data["profile"])
        return cls(
            success=data.get("success", False),
            profile=profile,
            source=data.get("source"),
            reason=data.get("reason"),
        )


@dataclass
class OperationCheck:
    """Result of an operation permission check."""

    allowed: bool
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationCheck":
        return cls(
            allowed=data.get("allowed", False),
            reason=data.get("reason"),
        )


class ProfilesService:
    """Service for managing agent profiles and enforcing access controls."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db
        self._cache: dict[str, tuple[AgentProfile, float]] = {}

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def get_profile(
        self,
        agent_id: str | None = None,
        agent_type: str | None = None,
    ) -> ProfileResult:
        """Get the profile for an agent.

        Checks explicit assignment first, then falls back to default by agent_type.
        Results are cached with configurable TTL.
        """
        config = get_config()
        agent_id = agent_id or config.agent.agent_id
        agent_type = agent_type or config.agent.agent_type

        # Check cache
        cache_key = f"{agent_id}:{agent_type}"
        if cache_key in self._cache:
            profile, cached_at = self._cache[cache_key]
            if time.monotonic() - cached_at < config.profiles.default_trust_level * 60:
                return ProfileResult(success=True, profile=profile, source="cache")

        result = await self.db.rpc(
            "get_agent_profile",
            {
                "p_agent_id": agent_id,
                "p_agent_type": agent_type,
            },
        )

        profile_result = ProfileResult.from_dict(result)

        # Cache successful lookups
        if profile_result.success and profile_result.profile:
            self._cache[cache_key] = (profile_result.profile, time.monotonic())

        return profile_result

    async def check_operation(
        self,
        operation: str,
        agent_id: str | None = None,
        agent_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> OperationCheck:
        """Check if an agent is allowed to perform an operation.

        Args:
            operation: The operation to check (e.g., 'acquire_lock', 'complete_work')
            agent_id: Agent ID (default: from config)
            agent_type: Agent type (default: from config)
            context: Additional context for the check (e.g., file count)

        Returns:
            OperationCheck indicating whether the operation is allowed
        """
        config = get_config()

        if not config.profiles.enforce_resource_limits:
            return OperationCheck(allowed=True, reason="enforcement_disabled")

        profile_result = await self.get_profile(agent_id, agent_type)

        if not profile_result.success or not profile_result.profile:
            # No profile found — use default trust level
            return OperationCheck(
                allowed=True,
                reason="no_profile_default_allow",
            )

        profile = profile_result.profile

        # Check blocked operations
        if operation in profile.blocked_operations:
            return OperationCheck(
                allowed=False,
                reason=f"operation_blocked: {operation}",
            )

        # Check allowed operations (if specified, must be in list)
        if profile.allowed_operations and operation not in profile.allowed_operations:
            return OperationCheck(
                allowed=False,
                reason=f"operation_not_in_allowlist: {operation}",
            )

        # Check resource limits
        if context:
            files_modified = context.get("files_modified", 0)
            if files_modified >= profile.max_file_modifications:
                return OperationCheck(
                    allowed=False,
                    reason="resource_limit_exceeded: "
                    f"max_file_modifications={profile.max_file_modifications}",
                )

        return OperationCheck(allowed=True)

    async def _log_denial(
        self,
        agent_id: str,
        operation: str,
        reason: str,
    ) -> None:
        """Log an operation denial to audit trail."""
        try:
            await get_audit_service().log_operation(
                agent_id=agent_id,
                operation="profile_denial",
                parameters={"denied_operation": operation},
                result={"reason": reason},
                success=True,
            )
        except Exception:
            pass


# Global service instance
_profiles_service: ProfilesService | None = None


def get_profiles_service() -> ProfilesService:
    """Get the global profiles service instance."""
    global _profiles_service
    if _profiles_service is None:
        _profiles_service = ProfilesService()
    return _profiles_service
