"""Network access policy service for Agent Coordinator.

Provides domain-level access control for agent network requests.
Policies are per-profile with global fallbacks.
"""

from dataclasses import dataclass
from typing import Any

from .config import get_config
from .db import DatabaseClient, get_db


@dataclass
class AccessDecision:
    """Result of a domain access check."""

    allowed: bool
    domain: str
    reason: str | None = None
    policy_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccessDecision":
        return cls(
            allowed=data.get("allowed", False),
            domain=data.get("domain", ""),
            reason=data.get("reason"),
            policy_id=str(data["policy_id"]) if data.get("policy_id") else None,
        )


class NetworkPolicyService:
    """Service for network access policy enforcement."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def check_domain(
        self,
        domain: str,
        agent_id: str | None = None,
    ) -> AccessDecision:
        """Check if an agent is allowed to access a domain.

        Args:
            domain: The domain to check (e.g., 'github.com')
            agent_id: Agent making the request (default: from config)

        Returns:
            AccessDecision with allowed status and reason
        """
        config = get_config()
        agent_id = agent_id or config.agent.agent_id

        try:
            result = await self.db.rpc(
                "is_domain_allowed",
                {
                    "p_agent_id": agent_id,
                    "p_domain": domain,
                },
            )
            return AccessDecision.from_dict(result)
        except Exception:
            # On error, apply default policy
            default_allowed = config.network_policy.default_policy == "allow"
            return AccessDecision(
                allowed=default_allowed,
                domain=domain,
                reason=f"default_policy:{config.network_policy.default_policy}",
            )


# Global service instance
_network_policy_service: NetworkPolicyService | None = None


def get_network_policy_service() -> NetworkPolicyService:
    """Get the global network policy service instance."""
    global _network_policy_service
    if _network_policy_service is None:
        _network_policy_service = NetworkPolicyService()
    return _network_policy_service
