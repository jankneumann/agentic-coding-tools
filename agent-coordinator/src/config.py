"""Configuration management for Agent Coordinator.

Environment variables:
    SUPABASE_URL: Supabase project URL
    SUPABASE_SERVICE_KEY: Service role key for full access
    AGENT_ID: Identifier for this agent instance
    AGENT_TYPE: Type of agent (claude_code, codex, etc.)
    SESSION_ID: Optional session identifier
    LOCK_TTL_MINUTES: Default lock TTL (default: 120)
"""

import os
from dataclasses import dataclass, field


@dataclass
class SupabaseConfig:
    """Supabase connection configuration."""

    url: str
    service_key: str
    rest_prefix: str = "/rest/v1"  # Empty string for direct PostgREST connections

    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")

        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables required"
            )

        return cls(
            url=url,
            service_key=key,
            rest_prefix=os.environ.get("SUPABASE_REST_PREFIX", "/rest/v1"),
        )


@dataclass
class AgentConfig:
    """Agent identity configuration."""

    agent_id: str
    agent_type: str = "claude_code"
    session_id: str | None = None

    @classmethod
    def from_env(cls) -> "AgentConfig":
        agent_id = os.environ.get("AGENT_ID")
        if not agent_id:
            # Generate a default agent ID from process info
            import uuid

            agent_id = f"agent-{uuid.uuid4().hex[:8]}"

        return cls(
            agent_id=agent_id,
            agent_type=os.environ.get("AGENT_TYPE", "claude_code"),
            session_id=os.environ.get("SESSION_ID"),
        )


@dataclass
class LockConfig:
    """Lock behavior configuration."""

    default_ttl_minutes: int = 120
    max_ttl_minutes: int = 480  # 8 hours max

    @classmethod
    def from_env(cls) -> "LockConfig":
        return cls(
            default_ttl_minutes=int(os.environ.get("LOCK_TTL_MINUTES", "120")),
        )


@dataclass
class Config:
    """Complete configuration for Agent Coordinator."""

    supabase: SupabaseConfig
    agent: AgentConfig
    lock: LockConfig = field(default_factory=LockConfig.from_env)

    @classmethod
    def from_env(cls) -> "Config":
        """Load complete configuration from environment variables."""
        return cls(
            supabase=SupabaseConfig.from_env(),
            agent=AgentConfig.from_env(),
            lock=LockConfig.from_env(),
        )


# Global config instance (lazy-loaded)
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """Reset the global configuration (for testing)."""
    global _config
    _config = None
