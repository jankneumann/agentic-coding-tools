"""Policy engine for Agent Coordinator.

Provides a unified authorization interface with two backends:
- NativePolicyEngine: delegates to ProfilesService + NetworkPolicyService
- CedarPolicyEngine: uses cedarpy for Cedar-based authorization

Selected via POLICY_ENGINE env var ('native' or 'cedar').
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import get_config
from .db import DatabaseClient, get_db

import logging

logger = logging.getLogger(__name__)

# Read actions that all agents can perform
READ_ACTIONS = frozenset({
    "check_locks", "get_work", "recall", "discover_agents",
    "read_handoff", "query_audit",
})

# Write actions requiring trust_level >= 2
WRITE_ACTIONS = frozenset({
    "acquire_lock", "release_lock", "complete_work", "submit_work",
    "remember", "write_handoff", "check_guardrails",
})

# Admin actions requiring trust_level >= 3
ADMIN_ACTIONS = frozenset({
    "force_push", "delete_branch", "cleanup_agents",
})

# Known-allowed network domains (matches default Cedar policies)
ALLOWED_DOMAINS = frozenset({
    "github.com", "api.github.com", "raw.githubusercontent.com",
    "registry.npmjs.org", "pypi.org",
})


@dataclass
class PolicyDecision:
    """Result of a policy authorization check."""

    allowed: bool
    reason: str = ""
    policy_id: str | None = None
    diagnostics: list[str] = field(default_factory=list)

    @classmethod
    def allow(cls, reason: str = "permitted") -> "PolicyDecision":
        return cls(allowed=True, reason=reason)

    @classmethod
    def deny(cls, reason: str = "denied") -> "PolicyDecision":
        return cls(allowed=False, reason=reason)


@dataclass
class ValidationResult:
    """Result of validating a Cedar policy."""

    valid: bool
    errors: list[str] = field(default_factory=list)


class NativePolicyEngine:
    """Policy engine using native ProfilesService + NetworkPolicyService.

    This is the default engine that delegates to the existing
    profile-based authorization and network policy services.
    """

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def check_operation(
        self,
        agent_id: str,
        agent_type: str,
        operation: str,
        resource: str = "",
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Check if an operation is authorized using native profiles.

        Args:
            agent_id: Agent requesting authorization
            agent_type: Type of agent
            operation: Operation name (e.g., 'acquire_lock')
            resource: Target resource (file path, domain, etc.)
            context: Additional context (trust_level, files_modified, etc.)

        Returns:
            PolicyDecision indicating allowed/denied
        """
        from .profiles import get_profiles_service

        profiles = get_profiles_service()
        ctx = context or {}
        trust_level = ctx.get("trust_level")

        # If trust_level provided in context, use it directly
        # Otherwise try to get profile from DB
        if trust_level is None:
            try:
                profile_result = await profiles.get_profile(
                    agent_id=agent_id, agent_type=agent_type
                )
                if profile_result.success and profile_result.profile:
                    trust_level = profile_result.profile.trust_level
                else:
                    trust_level = get_config().profiles.default_trust_level
            except Exception:
                trust_level = get_config().profiles.default_trust_level

        # Suspended agents (trust 0) are denied all operations
        if trust_level == 0:
            decision = PolicyDecision.deny("agent_suspended: trust_level=0")
            await self._log_policy_decision(
                agent_id=agent_id,
                agent_type=agent_type,
                operation=operation,
                resource=resource,
                context=ctx,
                decision=decision,
                engine="native",
            )
            return decision

        # Check by action category
        if operation in READ_ACTIONS:
            decision = PolicyDecision.allow("read_permitted")
            await self._log_policy_decision(
                agent_id=agent_id,
                agent_type=agent_type,
                operation=operation,
                resource=resource,
                context=ctx,
                decision=decision,
                engine="native",
            )
            return decision

        if operation in WRITE_ACTIONS:
            if trust_level >= 2:
                decision = PolicyDecision.allow(
                    f"write_permitted: trust_level={trust_level}"
                )
                await self._log_policy_decision(
                    agent_id=agent_id,
                    agent_type=agent_type,
                    operation=operation,
                    resource=resource,
                    context=ctx,
                    decision=decision,
                    engine="native",
                )
                return decision
            decision = PolicyDecision.deny(
                f"write_denied: trust_level={trust_level} < 2"
            )
            await self._log_policy_decision(
                agent_id=agent_id,
                agent_type=agent_type,
                operation=operation,
                resource=resource,
                context=ctx,
                decision=decision,
                engine="native",
            )
            return decision

        if operation in ADMIN_ACTIONS:
            if trust_level >= 3:
                decision = PolicyDecision.allow(
                    f"admin_permitted: trust_level={trust_level}"
                )
                await self._log_policy_decision(
                    agent_id=agent_id,
                    agent_type=agent_type,
                    operation=operation,
                    resource=resource,
                    context=ctx,
                    decision=decision,
                    engine="native",
                )
                return decision
            decision = PolicyDecision.deny(
                f"admin_denied: trust_level={trust_level} < 3"
            )
            await self._log_policy_decision(
                agent_id=agent_id,
                agent_type=agent_type,
                operation=operation,
                resource=resource,
                context=ctx,
                decision=decision,
                engine="native",
            )
            return decision

        # Unknown operation — check via profile service
        try:
            check = await profiles.check_operation(
                agent_id=agent_id,
                operation=operation,
                context=ctx,
            )
            if check.allowed:
                decision = PolicyDecision.allow(
                    f"profile_permitted: {check.reason or operation}"
                )
            else:
                decision = PolicyDecision.deny(
                f"profile_denied: {check.reason or operation}"
            )
            await self._log_policy_decision(
                agent_id=agent_id,
                agent_type=agent_type,
                operation=operation,
                resource=resource,
                context=ctx,
                decision=decision,
                engine="native",
            )
            return decision
        except Exception:
            decision = PolicyDecision.deny(f"unknown_operation: {operation}")
            await self._log_policy_decision(
                agent_id=agent_id,
                agent_type=agent_type,
                operation=operation,
                resource=resource,
                context=ctx,
                decision=decision,
                engine="native",
            )
            return decision

    async def check_network_access(
        self,
        agent_id: str,
        domain: str,
    ) -> PolicyDecision:
        """Check network access using native NetworkPolicyService."""
        from .network_policies import get_network_policy_service

        service = get_network_policy_service()
        try:
            decision = await service.check_domain(
                domain=domain, agent_id=agent_id
            )
            if decision.allowed:
                return PolicyDecision.allow(
                    reason=decision.reason or "network_permitted"
                )
            return PolicyDecision.deny(
                reason=decision.reason or "network_denied"
            )
        except Exception as e:
            return PolicyDecision.deny(f"network_error: {e}")

    async def _log_policy_decision(
        self,
        agent_id: str,
        agent_type: str,
        operation: str,
        resource: str,
        context: dict[str, Any],
        decision: PolicyDecision,
        engine: str,
    ) -> None:
        """Best-effort policy decision audit logging."""
        try:
            from .audit import get_audit_service

            await get_audit_service().log_operation(
                agent_id=agent_id,
                agent_type=agent_type,
                operation="policy_decision",
                parameters={
                    "operation": operation,
                    "resource": resource,
                    "engine": engine,
                    "context": context,
                },
                result={
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "policy_id": decision.policy_id,
                    "diagnostics": decision.diagnostics,
                },
                success=True,
            )
        except Exception:
            logger.debug("Failed to audit policy decision", exc_info=True)


class CedarPolicyEngine:
    """Policy engine using Cedar (cedarpy) for authorization.

    Cedar provides a declarative policy language with PARC model
    (Principal/Action/Resource/Context). Policies are loaded from
    database with file fallback.

    Requires: pip install agent-coordinator[cedar]
    """

    def __init__(self, db: DatabaseClient | None = None):
        try:
            import cedarpy
            self._cedarpy = cedarpy
        except ImportError:
            raise ImportError(
                "cedarpy is required for Cedar policy engine. "
                "Install with: pip install agent-coordinator[cedar]"
            )

        self._db = db
        self._policies_cache: str | None = None
        self._policies_cache_time: float = 0.0
        self._schema_cache: str | None = None

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    def _load_default_policies(self) -> str:
        """Load default policies from cedar/default_policies.cedar."""
        # Try relative to this file's package
        candidates = [
            Path(__file__).parent.parent / "cedar" / "default_policies.cedar",
            Path("cedar") / "default_policies.cedar",
        ]
        for path in candidates:
            if path.exists():
                return path.read_text()
        raise FileNotFoundError(
            "Cannot find cedar/default_policies.cedar"
        )

    def _load_schema(self) -> str:
        """Load Cedar schema from file."""
        if self._schema_cache is not None:
            return self._schema_cache

        config = get_config()
        schema_path = config.policy_engine.schema_path

        if schema_path:
            path = Path(schema_path)
        else:
            path = Path(__file__).parent.parent / "cedar" / "schema.cedarschema"

        if path.exists():
            self._schema_cache = path.read_text()
            return self._schema_cache
        return ""

    async def _load_policies(self) -> str:
        """Load Cedar policies with caching.

        Tries database first, falls back to default file policies.
        """
        config = get_config()
        ttl = config.policy_engine.policy_cache_ttl_seconds
        now = time.monotonic()

        if (
            self._policies_cache is not None
            and (now - self._policies_cache_time) < ttl
        ):
            return self._policies_cache

        # Try loading from database
        try:
            rows = await self.db.query(
                "cedar_policies",
                "enabled=eq.true&order=priority.asc",
            )
            if rows:
                policies = "\n\n".join(
                    row["policy_text"] for row in rows
                )
                self._policies_cache = policies
                self._policies_cache_time = now
                return policies
        except Exception:
            pass

        # Fallback to file-based policies
        if config.policy_engine.enable_code_fallback:
            policies = self._load_default_policies()
            self._policies_cache = policies
            self._policies_cache_time = now
            return policies

        raise RuntimeError("No Cedar policies available")

    def _build_entity(
        self,
        agent_id: str,
        agent_type: str,
        trust_level: int,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Build Cedar entity list for authorization request."""
        ctx = context or {}
        entities: list[dict[str, Any]] = [
            {
                "uid": {"type": "Agent", "id": agent_id},
                "attrs": {
                    "trust_level": trust_level,
                    "agent_type": agent_type,
                    "session_id": ctx.get("session_id", ""),
                    "max_file_modifications": ctx.get(
                        "max_file_modifications", 100
                    ),
                    "max_execution_time_seconds": ctx.get(
                        "max_execution_time_seconds", 3600
                    ),
                },
                "parents": [{"type": "AgentType", "id": agent_type}],
            },
            {
                "uid": {"type": "AgentType", "id": agent_type},
                "attrs": {},
                "parents": [],
            },
        ]
        return entities

    def _build_resource_entity(
        self,
        resource: str,
        resource_type: str = "File",
    ) -> dict[str, Any]:
        """Build a resource entity."""
        if resource_type == "Domain":
            return {
                "uid": {"type": "Domain", "id": resource},
                "attrs": {"name": resource},
                "parents": [],
            }
        if resource_type == "Task":
            return {
                "uid": {"type": "Task", "id": resource or "default"},
                "attrs": {
                    "task_type": "general",
                    "priority": 5,
                },
                "parents": [],
            }
        return {
            "uid": {"type": "File", "id": resource or "unknown"},
            "attrs": {"path": resource},
            "parents": [],
        }

    def _determine_resource_type(self, operation: str) -> str:
        """Determine Cedar resource type based on operation."""
        if operation == "network_access":
            return "Domain"
        file_ops = {
            "acquire_lock", "release_lock", "check_locks",
            "force_push", "delete_branch",
        }
        if operation in file_ops:
            return "File"
        return "Task"

    async def check_operation(
        self,
        agent_id: str,
        agent_type: str,
        operation: str,
        resource: str = "",
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Check if an operation is authorized using Cedar.

        Args:
            agent_id: Agent requesting authorization
            agent_type: Type of agent
            operation: Operation name (Cedar action)
            resource: Target resource identifier
            context: Additional context (trust_level, etc.)

        Returns:
            PolicyDecision from Cedar evaluation
        """
        ctx = context or {}
        trust_level = ctx.get("trust_level", 1)

        try:
            policies = await self._load_policies()
        except Exception as e:
            decision = PolicyDecision.deny(f"policy_load_error: {e}")
            await self._log_policy_decision(
                agent_id=agent_id,
                agent_type=agent_type,
                operation=operation,
                resource=resource,
                context=ctx,
                decision=decision,
                engine="cedar",
            )
            return decision

        resource_type = self._determine_resource_type(operation)
        resource_entity = self._build_resource_entity(
            resource, resource_type
        )
        entities = self._build_entity(
            agent_id, agent_type, trust_level, ctx
        )
        entities.append(resource_entity)

        request = {
            "principal": f'Agent::"{agent_id}"',
            "action": f'Action::"{operation}"',
            "resource": f'{resource_type}::"{resource or "default"}"',
            "context": {},
        }

        try:
            response = self._cedarpy.is_authorized(
                request, policies, entities
            )
        except Exception as e:
            decision = PolicyDecision(
                allowed=False,
                reason=f"cedar_evaluation_error: {e}",
                diagnostics=[str(e)],
            )
            await self._log_policy_decision(
                agent_id=agent_id,
                agent_type=agent_type,
                operation=operation,
                resource=resource,
                context=ctx,
                decision=decision,
                engine="cedar",
            )
            return decision

        allowed = response.decision == self._cedarpy.Decision.Allow
        reason_parts: list[str] = []
        if hasattr(response, "diagnostics"):
            diag = response.diagnostics
            if hasattr(diag, "reasons") and diag.reasons:
                reason_parts.extend(str(r) for r in diag.reasons)
            if hasattr(diag, "errors") and diag.errors:
                reason_parts.extend(str(e) for e in diag.errors)

        decision = PolicyDecision(
            allowed=allowed,
            reason=f"cedar:{'allow' if allowed else 'deny'}",
            diagnostics=reason_parts,
        )
        await self._log_policy_decision(
            agent_id=agent_id,
            agent_type=agent_type,
            operation=operation,
            resource=resource,
            context=ctx,
            decision=decision,
            engine="cedar",
        )
        return decision

    async def check_network_access(
        self,
        agent_id: str,
        domain: str,
        agent_type: str = "unknown",
        trust_level: int = 1,
    ) -> PolicyDecision:
        """Check network access using Cedar policies.

        Maps to: is_authorized(Agent, Action::"network_access", Domain::domain)
        """
        return await self.check_operation(
            agent_id=agent_id,
            agent_type=agent_type,
            operation="network_access",
            resource=domain,
            context={"trust_level": trust_level},
        )

    def validate_policy(self, policy_text: str) -> ValidationResult:
        """Validate Cedar policy text against schema.

        Args:
            policy_text: Cedar policy text to validate

        Returns:
            ValidationResult with validity and any errors
        """
        try:
            schema = self._load_schema()
            result = self._cedarpy.validate_policies(policy_text, schema)
            if result.validation_passed:
                return ValidationResult(valid=True)
            return ValidationResult(
                valid=False,
                errors=[str(e) for e in result.errors],
            )
        except Exception as e:
            return ValidationResult(valid=False, errors=[str(e)])

    async def list_policies(self) -> list[dict[str, Any]]:
        """List all active Cedar policies from the database."""
        try:
            rows = await self.db.query(
                "cedar_policies",
                "order=priority.asc",
            )
            return [
                {
                    "id": row.get("id"),
                    "name": row.get("name", ""),
                    "enabled": row.get("enabled", True),
                    "priority": row.get("priority", 0),
                }
                for row in rows
            ]
        except Exception:
            return []

    def invalidate_cache(self) -> None:
        """Invalidate the policy cache, forcing reload on next check."""
        self._policies_cache = None
        self._policies_cache_time = 0.0

    async def _log_policy_decision(
        self,
        agent_id: str,
        agent_type: str,
        operation: str,
        resource: str,
        context: dict[str, Any],
        decision: PolicyDecision,
        engine: str,
    ) -> None:
        """Best-effort policy decision audit logging."""
        try:
            from .audit import get_audit_service

            await get_audit_service().log_operation(
                agent_id=agent_id,
                agent_type=agent_type,
                operation="policy_decision",
                parameters={
                    "operation": operation,
                    "resource": resource,
                    "engine": engine,
                    "context": context,
                },
                result={
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "policy_id": decision.policy_id,
                    "diagnostics": decision.diagnostics,
                },
                success=True,
            )
        except Exception:
            logger.debug("Failed to audit policy decision", exc_info=True)


# Global engine instance
_policy_engine: NativePolicyEngine | CedarPolicyEngine | None = None


def get_policy_engine() -> NativePolicyEngine | CedarPolicyEngine:
    """Get the global policy engine based on configuration.

    Returns NativePolicyEngine for POLICY_ENGINE=native (default),
    or CedarPolicyEngine for POLICY_ENGINE=cedar.
    """
    global _policy_engine
    if _policy_engine is None:
        config = get_config()
        engine = config.policy_engine.engine
        if engine == "cedar":
            _policy_engine = CedarPolicyEngine()
        else:
            _policy_engine = NativePolicyEngine()
    return _policy_engine


def reset_policy_engine() -> None:
    """Reset the global policy engine (for testing)."""
    global _policy_engine
    _policy_engine = None
