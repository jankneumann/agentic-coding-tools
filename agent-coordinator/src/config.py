"""Configuration management for Agent Coordinator.

Environment variables:
    COORDINATOR_PROFILE: Active deployment profile (default: "local")
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
    API_HOST: HTTP API host (default: 0.0.0.0)
    API_PORT: HTTP API port (default: 8081)
    API_WORKERS: Number of uvicorn workers (default: 1)
    API_TIMEOUT_KEEP_ALIVE: Keep-alive timeout in seconds (default: 5)
    API_ACCESS_LOG: Enable uvicorn access logging (default: false)
    COORDINATION_API_KEYS: Comma-separated API keys for HTTP API auth
    COORDINATION_API_KEY_IDENTITIES: JSON mapping API keys to agent identities
    PORT_ALLOC_BASE: Base port for port allocator (default: 10000)
    PORT_ALLOC_RANGE: Port range per session (default: 100)
    PORT_ALLOC_TTL_MINUTES: Port allocation TTL in minutes (default: 120)
    PORT_ALLOC_MAX_SESSIONS: Maximum concurrent sessions (default: 20)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SupabaseConfig:
    """Supabase connection configuration."""

    url: str
    service_key: str
    rest_prefix: str = "/rest/v1"  # Empty string for direct PostgREST connections

    @classmethod
    def from_env(cls) -> SupabaseConfig:
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
    def from_env(cls) -> AgentConfig:
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
    def from_env(cls) -> LockConfig:
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
    def from_env(cls) -> PostgresConfig:
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
    def from_env(cls) -> DatabaseConfig:
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
    def from_env(cls) -> GuardrailsConfig:
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
    cache_ttl_seconds: int = 300  # Profile cache TTL

    @classmethod
    def from_env(cls) -> ProfilesConfig:
        return cls(
            default_trust_level=int(
                os.environ.get("PROFILES_DEFAULT_TRUST", "2")
            ),
            enforce_resource_limits=os.environ.get(
                "PROFILES_ENFORCE_LIMITS", "true"
            ).lower()
            == "true",
            cache_ttl_seconds=int(
                os.environ.get("PROFILES_CACHE_TTL", "300")
            ),
        )


@dataclass
class AuditConfig:
    """Audit trail configuration."""

    retention_days: int = 90
    async_logging: bool = True  # Non-blocking audit inserts

    @classmethod
    def from_env(cls) -> AuditConfig:
        return cls(
            retention_days=int(os.environ.get("AUDIT_RETENTION_DAYS", "90")),
            async_logging=os.environ.get("AUDIT_ASYNC", "true").lower() == "true",
        )


@dataclass
class NetworkPolicyConfig:
    """Network access policy configuration."""

    default_policy: str = "deny"  # "deny" or "allow" for unspecified domains

    @classmethod
    def from_env(cls) -> NetworkPolicyConfig:
        return cls(
            default_policy=os.environ.get("NETWORK_DEFAULT_POLICY", "deny"),
        )


@dataclass
class PolicyEngineConfig:
    """Policy engine configuration (native or Cedar)."""

    engine: str = "native"  # "native" or "cedar"
    policy_cache_ttl_seconds: int = 300
    enable_code_fallback: bool = True
    schema_path: str | None = None

    @classmethod
    def from_env(cls) -> PolicyEngineConfig:
        return cls(
            engine=os.environ.get("POLICY_ENGINE", "native"),
            policy_cache_ttl_seconds=int(
                os.environ.get("POLICY_CACHE_TTL", "300")
            ),
            enable_code_fallback=os.environ.get(
                "POLICY_CODE_FALLBACK", "true"
            ).lower()
            == "true",
            schema_path=os.environ.get("CEDAR_SCHEMA_PATH"),
        )


@dataclass
class OpenBaoConfig:
    """OpenBao (Vault-compatible) connection configuration.

    Environment variables:
        BAO_ADDR: OpenBao server URL (e.g., http://localhost:8200)
        BAO_ROLE_ID: AppRole role ID for authentication
        BAO_SECRET_ID: AppRole secret ID for authentication
        BAO_MOUNT_PATH: KV v2 mount path (default: "secret")
        BAO_SECRET_PATH: Secret data path (default: "coordinator")
        BAO_TIMEOUT: Connection timeout in seconds (default: 5)
        BAO_TOKEN_TTL: Token TTL in seconds (default: 3600)
    """

    addr: str = ""
    role_id: str = ""
    secret_id: str = ""
    mount_path: str = "secret"
    secret_path: str = "coordinator"
    timeout: int = 5
    token_ttl: int = 3600

    @classmethod
    def from_env(cls) -> OpenBaoConfig:
        return cls(
            addr=os.environ.get("BAO_ADDR", ""),
            role_id=os.environ.get("BAO_ROLE_ID", ""),
            secret_id=os.environ.get("BAO_SECRET_ID", ""),
            mount_path=os.environ.get("BAO_MOUNT_PATH", "secret"),
            secret_path=os.environ.get("BAO_SECRET_PATH", "coordinator"),
            timeout=int(os.environ.get("BAO_TIMEOUT", "5")),
            token_ttl=int(os.environ.get("BAO_TOKEN_TTL", "3600")),
        )

    def is_enabled(self) -> bool:
        """Return True when BAO_ADDR is set and non-empty."""
        return bool(self.addr)

    def create_client(self) -> Any:
        """Create an authenticated hvac.Client connected to OpenBao.

        Raises:
            RuntimeError: If OpenBao is not configured (BAO_ADDR not set).
            ValueError: If BAO_ROLE_ID or BAO_SECRET_ID is missing.
            ConnectionError: If the server is unreachable within the timeout.
        """
        if not self.is_enabled():
            raise RuntimeError("OpenBao is not configured")

        if not self.role_id:
            raise ValueError("BAO_ROLE_ID environment variable is required when BAO_ADDR is set")
        if not self.secret_id:
            raise ValueError(
                "BAO_SECRET_ID environment variable is required when BAO_ADDR is set"
            )

        import hvac

        try:
            client = hvac.Client(url=self.addr, timeout=self.timeout)
            client.auth.approle.login(role_id=self.role_id, secret_id=self.secret_id)
        except Exception as exc:
            # Distinguish connection errors from auth errors
            exc_str = str(exc)
            if "connect" in exc_str.lower() or "timeout" in exc_str.lower():
                raise ConnectionError(
                    f"OpenBao unreachable at {self.addr}: {exc}"
                ) from exc
            raise RuntimeError(
                f"OpenBao authentication failed at {self.addr} "
                f"(role_id={self.role_id!r}): {exc}"
            ) from exc

        if not client.is_authenticated():
            raise RuntimeError(
                f"OpenBao authentication failed at {self.addr} "
                f"(role_id={self.role_id!r}): client reports unauthenticated"
            )

        return client


@dataclass
class ObservabilityConfig:
    """OpenTelemetry observability configuration."""

    metrics_enabled: bool = False
    traces_enabled: bool = False
    prometheus_enabled: bool = False

    @classmethod
    def from_env(cls) -> ObservabilityConfig:
        return cls(
            metrics_enabled=os.environ.get("OTEL_METRICS_ENABLED", "false").lower() == "true",
            traces_enabled=os.environ.get("OTEL_TRACES_ENABLED", "false").lower() == "true",
            prometheus_enabled=os.environ.get("PROMETHEUS_ENABLED", "false").lower() == "true",
        )


@dataclass
class LangfuseConfig:
    """Langfuse observability configuration.

    Environment variables:
        LANGFUSE_ENABLED: Enable Langfuse tracing (default: false)
        LANGFUSE_PUBLIC_KEY: Project public key
        LANGFUSE_SECRET_KEY: Project secret key
        LANGFUSE_HOST: Langfuse server URL (default: http://localhost:3050)
        LANGFUSE_TRACE_API_REQUESTS: Trace coordinator HTTP API requests (default: true)
        LANGFUSE_DEBUG: Enable debug logging for Langfuse SDK (default: false)
    """

    enabled: bool = False
    public_key: str = ""
    secret_key: str = ""
    host: str = "http://localhost:3050"
    trace_api_requests: bool = True
    debug: bool = False

    @classmethod
    def from_env(cls) -> LangfuseConfig:
        return cls(
            enabled=os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true",
            public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-local-coding-agents"),
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-local-coding-agents"),
            host=os.environ.get("LANGFUSE_HOST", "http://localhost:3050"),
            trace_api_requests=os.environ.get(
                "LANGFUSE_TRACE_API_REQUESTS", "true"
            ).lower() == "true",
            debug=os.environ.get("LANGFUSE_DEBUG", "false").lower() == "true",
        )


@dataclass
class PortAllocatorConfig:
    """Port allocator configuration for parallel docker-compose stacks."""

    base_port: int = 10000
    range_per_session: int = 100
    ttl_minutes: int = 120
    max_sessions: int = 20

    @classmethod
    def from_env(cls) -> PortAllocatorConfig:
        return cls(
            base_port=int(os.environ.get("PORT_ALLOC_BASE", "10000")),
            range_per_session=int(os.environ.get("PORT_ALLOC_RANGE", "100")),
            ttl_minutes=int(os.environ.get("PORT_ALLOC_TTL_MINUTES", "120")),
            max_sessions=int(os.environ.get("PORT_ALLOC_MAX_SESSIONS", "20")),
        )


@dataclass
class ApiConfig:
    """HTTP API configuration."""

    host: str = "0.0.0.0"  # noqa: S104
    port: int = 8081
    api_keys: list[str] = field(default_factory=list)
    api_key_identities: dict[str, dict[str, str]] = field(default_factory=dict)
    workers: int = 1
    timeout_keep_alive: int = 5
    access_log: bool = False

    @classmethod
    def from_env(cls) -> ApiConfig:
        raw_keys = os.environ.get("COORDINATION_API_KEYS", "")
        api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

        raw_identities = os.environ.get("COORDINATION_API_KEY_IDENTITIES")
        identities: dict[str, dict[str, str]] = {}
        if raw_identities:
            try:
                identities = json.loads(raw_identities)
            except json.JSONDecodeError:
                identities = {}
        else:
            # Auto-populate from agents.yaml when no explicit env var is set.
            try:
                from src.agents_config import get_api_key_identities

                identities = get_api_key_identities()
            except FileNotFoundError:
                logger.debug("agents.yaml not found — skipping API key identity auto-population")
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Could not auto-populate API key identities from agents.yaml",
                    exc_info=True,
                )

        # When COORDINATION_API_KEYS is not set explicitly, derive the
        # allowlist from the auto-populated identity map so that keys
        # from agents.yaml are accepted without redundant env-var config.
        if not api_keys and identities:
            api_keys = list(identities.keys())

        return cls(
            host=os.environ.get("API_HOST", "0.0.0.0"),
            port=int(os.environ.get("API_PORT", "8081")),
            api_keys=api_keys,
            api_key_identities=identities,
            workers=int(os.environ.get("API_WORKERS", "1")),
            timeout_keep_alive=int(os.environ.get("API_TIMEOUT_KEEP_ALIVE", "5")),
            access_log=os.environ.get("API_ACCESS_LOG", "false").lower() == "true",
        )


@dataclass
class ApprovalConfig:
    """Approval gates configuration."""

    enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "APPROVAL_GATES_ENABLED", "false"
        ).lower()
        == "true"
    )
    default_timeout_seconds: int = field(
        default_factory=lambda: int(
            os.environ.get("APPROVAL_DEFAULT_TIMEOUT", "3600")
        )
    )
    auto_deny: bool = field(
        default_factory=lambda: os.environ.get(
            "APPROVAL_AUTO_DENY", "true"
        ).lower()
        == "true"
    )


@dataclass
class PolicySyncConfig:
    """Policy sync configuration."""

    enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "POLICY_SYNC_ENABLED", "false"
        ).lower()
        == "true"
    )
    reconnect_max_retries: int = field(
        default_factory=lambda: int(
            os.environ.get("POLICY_SYNC_MAX_RETRIES", "5")
        )
    )
    reconnect_backoff_seconds: float = field(
        default_factory=lambda: float(
            os.environ.get("POLICY_SYNC_BACKOFF", "1.0")
        )
    )


@dataclass
class RiskScoringConfig:
    """Risk scoring configuration."""

    enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "RISK_SCORING_ENABLED", "false"
        ).lower()
        == "true"
    )
    low_threshold: float = field(
        default_factory=lambda: float(
            os.environ.get("RISK_LOW_THRESHOLD", "0.3")
        )
    )
    high_threshold: float = field(
        default_factory=lambda: float(
            os.environ.get("RISK_HIGH_THRESHOLD", "0.7")
        )
    )
    violation_window_seconds: int = field(
        default_factory=lambda: int(
            os.environ.get("RISK_VIOLATION_WINDOW", "3600")
        )
    )


@dataclass
class SessionGrantsConfig:
    """Session grants configuration."""

    enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "SESSION_GRANTS_ENABLED", "false"
        ).lower()
        == "true"
    )
    require_justification: bool = field(
        default_factory=lambda: os.environ.get(
            "SESSION_GRANTS_REQUIRE_JUSTIFICATION", "true"
        ).lower()
        == "true"
    )


@dataclass
class Config:
    """Complete configuration for Agent Coordinator."""

    supabase: SupabaseConfig | None
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
    api: ApiConfig = field(default_factory=ApiConfig.from_env)
    port_allocator: PortAllocatorConfig = field(
        default_factory=PortAllocatorConfig.from_env
    )
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    policy_sync: PolicySyncConfig = field(default_factory=PolicySyncConfig)
    risk_scoring: RiskScoringConfig = field(default_factory=RiskScoringConfig)
    session_grants: SessionGrantsConfig = field(
        default_factory=SessionGrantsConfig
    )
    observability: ObservabilityConfig = field(
        default_factory=ObservabilityConfig.from_env
    )
    langfuse: LangfuseConfig = field(default_factory=LangfuseConfig.from_env)
    openbao: OpenBaoConfig = field(default_factory=OpenBaoConfig.from_env)
    active_profile: str | None = None
    transport: str = "none"
    _profile_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Config:
        """Load complete configuration from environment variables.

        When a ``profiles/`` directory exists, loads the active deployment
        profile first (injecting values into ``os.environ`` as defaults)
        before reading the individual config sections.
        """
        # Apply deployment profile (injects defaults into os.environ).
        from src.profile_loader import apply_profile

        try:
            profile_data = apply_profile()
        except (FileNotFoundError, ValueError) as exc:
            profile_name = os.environ.get("COORDINATOR_PROFILE", "local")
            raise RuntimeError(
                f"Failed to load profile '{profile_name}': {exc}"
            ) from exc

        db_backend = os.environ.get("DB_BACKEND", "supabase")
        try:
            supabase_config: SupabaseConfig | None = SupabaseConfig.from_env()
        except ValueError:
            if db_backend == "postgres":
                supabase_config = None
            else:
                raise

        active_profile: str | None = None
        transport = os.environ.get("COORDINATION_TRANSPORT", "none")
        if profile_data is not None:
            active_profile = os.environ.get("COORDINATOR_PROFILE", "local")

        return cls(
            supabase=supabase_config,
            agent=AgentConfig.from_env(),
            lock=LockConfig.from_env(),
            database=DatabaseConfig.from_env(),
            guardrails=GuardrailsConfig.from_env(),
            profiles=ProfilesConfig.from_env(),
            audit=AuditConfig.from_env(),
            network_policy=NetworkPolicyConfig.from_env(),
            policy_engine=PolicyEngineConfig.from_env(),
            api=ApiConfig.from_env(),
            port_allocator=PortAllocatorConfig.from_env(),
            openbao=OpenBaoConfig.from_env(),
            active_profile=active_profile,
            transport=transport,
            _profile_data=profile_data or {},
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
