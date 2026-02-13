"""Configuration management for Agent Coordinator.

Environment variables:
    SUPABASE_URL: Supabase project URL
    SUPABASE_SERVICE_KEY: Service role key for full access
    AGENT_ID: Identifier for this agent instance
    AGENT_TYPE: Type of agent (claude_code, codex, etc.)
    SESSION_ID: Optional session identifier
    LOCK_TTL_MINUTES: Default lock TTL (default: 120)
    DB_BACKEND: Database backend - "supabase" (default) or "postgres"
    POSTGRES_DSN: PostgreSQL connection string (when DB_BACKEND=postgres)
    POSTGRES_POOL_MIN: Minimum pool size (default: 2)
    POSTGRES_POOL_MAX: Maximum pool size (default: 10)
    GUARDRAILS_CACHE_TTL: Guardrail pattern cache TTL in seconds (default: 300)
    GUARDRAILS_CODE_FALLBACK: Use hardcoded patterns if DB unavailable (default: true)
    PROFILES_DEFAULT_TRUST: Default trust level for unregistered agents (default: 2)
    PROFILES_ENFORCE_LIMITS: Enforce resource limits (default: true)
    AUDIT_RETENTION_DAYS: Audit log retention in days (default: 90)
    AUDIT_ASYNC: Use async audit logging (default: true)
    NETWORK_DEFAULT_POLICY: Default network policy - "deny" or "allow" (default: deny)
    POLICY_ENGINE: Policy engine - "native" or "cedar" (default: native)
    POLICY_CACHE_TTL: Policy cache TTL in seconds (default: 300)
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
class PostgresConfig:
    """Direct PostgreSQL connection configuration."""

    dsn: str = ""  # e.g., "postgresql://user:pass@localhost:5432/coordinator"
    pool_min: int = 2
    pool_max: int = 10

    @classmethod
    def from_env(cls) -> "PostgresConfig":
        return cls(
            dsn=os.environ.get("POSTGRES_DSN", ""),
            pool_min=int(os.environ.get("POSTGRES_POOL_MIN", "2")),
            pool_max=int(os.environ.get("POSTGRES_POOL_MAX", "10")),
        )


@dataclass
class DatabaseConfig:
    """Database backend selection."""

    backend: str = "supabase"  # "supabase" or "postgres"
    postgres: PostgresConfig = field(default_factory=PostgresConfig)

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            backend=os.environ.get("DB_BACKEND", "supabase"),
            postgres=PostgresConfig.from_env(),
        )


@dataclass
class GuardrailsConfig:
    """Guardrails engine configuration."""

    patterns_cache_ttl_seconds: int = 300  # Refresh DB patterns every 5 min
    enable_code_fallback: bool = True  # Use hardcoded patterns if DB unavailable

    @classmethod
    def from_env(cls) -> "GuardrailsConfig":
        return cls(
            patterns_cache_ttl_seconds=int(
                os.environ.get("GUARDRAILS_CACHE_TTL", "300")
            ),
            enable_code_fallback=os.environ.get(
                "GUARDRAILS_CODE_FALLBACK", "true"
            ).lower()
            == "true",
        )


@dataclass
class ProfilesConfig:
    """Agent profiles configuration."""

    default_trust_level: int = 2  # Standard trust for unregistered agents
    enforce_resource_limits: bool = True

    @classmethod
    def from_env(cls) -> "ProfilesConfig":
        return cls(
            default_trust_level=int(
                os.environ.get("PROFILES_DEFAULT_TRUST", "2")
            ),
            enforce_resource_limits=os.environ.get(
                "PROFILES_ENFORCE_LIMITS", "true"
            ).lower()
            == "true",
        )


@dataclass
class AuditConfig:
    """Audit trail configuration."""

    retention_days: int = 90
    async_logging: bool = True  # Non-blocking audit inserts

    @classmethod
    def from_env(cls) -> "AuditConfig":
        return cls(
            retention_days=int(os.environ.get("AUDIT_RETENTION_DAYS", "90")),
            async_logging=os.environ.get("AUDIT_ASYNC", "true").lower() == "true",
        )


@dataclass
class NetworkPolicyConfig:
    """Network access policy configuration."""

    default_policy: str = "deny"  # "deny" or "allow" for unspecified domains

    @classmethod
    def from_env(cls) -> "NetworkPolicyConfig":
        return cls(
            default_policy=os.environ.get("NETWORK_DEFAULT_POLICY", "deny"),
        )


@dataclass
class PolicyEngineConfig:
    """Policy engine configuration (native or Cedar)."""

    engine: str = "native"  # "native" or "cedar"
    policy_cache_ttl_seconds: int = 300
    enable_code_fallback: bool = True

    @classmethod
    def from_env(cls) -> "PolicyEngineConfig":
        return cls(
            engine=os.environ.get("POLICY_ENGINE", "native"),
            policy_cache_ttl_seconds=int(
                os.environ.get("POLICY_CACHE_TTL", "300")
            ),
            enable_code_fallback=os.environ.get(
                "POLICY_CODE_FALLBACK", "true"
            ).lower()
            == "true",
        )


@dataclass
class Config:
    """Complete configuration for Agent Coordinator."""

    supabase: SupabaseConfig
    agent: AgentConfig
    lock: LockConfig = field(default_factory=LockConfig.from_env)
    database: DatabaseConfig = field(default_factory=DatabaseConfig.from_env)
    guardrails: GuardrailsConfig = field(default_factory=GuardrailsConfig.from_env)
    profiles: ProfilesConfig = field(default_factory=ProfilesConfig.from_env)
    audit: AuditConfig = field(default_factory=AuditConfig.from_env)
    network_policy: NetworkPolicyConfig = field(
        default_factory=NetworkPolicyConfig.from_env
    )
    policy_engine: PolicyEngineConfig = field(
        default_factory=PolicyEngineConfig.from_env
    )

    @classmethod
    def from_env(cls) -> "Config":
        """Load complete configuration from environment variables."""
        return cls(
            supabase=SupabaseConfig.from_env(),
            agent=AgentConfig.from_env(),
            lock=LockConfig.from_env(),
            database=DatabaseConfig.from_env(),
            guardrails=GuardrailsConfig.from_env(),
            profiles=ProfilesConfig.from_env(),
            audit=AuditConfig.from_env(),
            network_policy=NetworkPolicyConfig.from_env(),
            policy_engine=PolicyEngineConfig.from_env(),
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
