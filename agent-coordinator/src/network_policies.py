"""Network access policy service for Agent Coordinator.

Provides domain-level access control for agent network requests.
Policies are per-profile with global fallbacks.
"""

import hashlib
import ipaddress
import json
import re
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


class NetworkPolicyExportError(ValueError):
    """An exact-agent policy snapshot cannot be exported safely."""

    def __init__(self, reason: str, status_code: int = 422) -> None:
        self.reason = reason
        self.status_code = status_code
        super().__init__(reason)


_DNS_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_DNS_PATTERN = re.compile(rf"^(?:\*\.)?(?:{_DNS_LABEL}\.)+{_DNS_LABEL}$")
_RULE_KEYS = {
    "destination_kind",
    "destination_pattern",
    "port",
    "action",
    "priority",
    "scope",
    "policy_id",
}


def canonical_json_bytes(value: Any) -> bytes:
    """Encode contract JSON deterministically, rejecting ambiguous floats."""

    def reject_floats(item: Any) -> None:
        if isinstance(item, float):
            raise NetworkPolicyExportError("invalid policy export: floats are forbidden")
        if isinstance(item, dict):
            for child in item.values():
                reject_floats(child)
        elif isinstance(item, list):
            for child in item:
                reject_floats(child)

    reject_floats(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NetworkPolicyExportError(f"invalid policy export: {exc}") from exc


def _validate_rule(rule: Any) -> None:
    if not isinstance(rule, dict) or set(rule) != _RULE_KEYS:
        raise NetworkPolicyExportError("invalid policy export: malformed rule fields")
    kind = rule["destination_kind"]
    destination = rule["destination_pattern"]
    port = rule["port"]
    if kind not in {"dns", "ipv4", "ipv6"} or not isinstance(destination, str):
        raise NetworkPolicyExportError("invalid policy export: typed destination")
    if kind == "dns" and not _DNS_PATTERN.fullmatch(destination):
        raise NetworkPolicyExportError("invalid policy export: DNS destination")
    try:
        if kind == "ipv4" and ipaddress.ip_address(destination).version != 4:
            raise ValueError
        if kind == "ipv6":
            if not (destination.startswith("[") and destination.endswith("]")):
                raise ValueError
            if ipaddress.ip_address(destination[1:-1]).version != 6:
                raise ValueError
    except ValueError as exc:
        raise NetworkPolicyExportError("invalid policy export: IP destination") from exc
    if port is not None and (type(port) is not int or not 1 <= port <= 65535):
        raise NetworkPolicyExportError("invalid policy export: port")
    if rule["action"] not in {"allow", "deny"}:
        raise NetworkPolicyExportError("invalid policy export: action")
    if type(rule["priority"]) is not int:
        raise NetworkPolicyExportError("invalid policy export: priority")
    if rule["scope"] not in {"agent_profile", "global"}:
        raise NetworkPolicyExportError("invalid policy export: scope")
    if not isinstance(rule["policy_id"], str) or not rule["policy_id"]:
        raise NetworkPolicyExportError("invalid policy export: policy id")


def _validate_export(snapshot: Any, agent_id: str) -> dict[str, Any]:
    required = {
        "schema_version",
        "agent_id",
        "default_action",
        "rules",
        "policy_revision",
    }
    if not isinstance(snapshot, dict) or set(snapshot) != required:
        raise NetworkPolicyExportError("invalid policy export: malformed snapshot")
    if (
        snapshot["schema_version"] != 1
        or snapshot["agent_id"] != agent_id
        or snapshot["default_action"] != "deny"
        or not isinstance(snapshot["rules"], list)
        or not isinstance(snapshot["policy_revision"], str)
    ):
        raise NetworkPolicyExportError("invalid policy export: contract mismatch")
    for rule in snapshot["rules"]:
        _validate_rule(rule)
    return snapshot


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

    async def export_for_agent(self, agent_id: str) -> dict[str, Any]:
        """Return one atomic, exact-agent, default-deny policy snapshot."""

        if not agent_id.strip():
            raise NetworkPolicyExportError("agent_not_found", 404)
        try:
            result = await self.db.rpc("export_network_policy", {"p_agent_id": agent_id})
        except NetworkPolicyExportError:
            raise
        except Exception as exc:
            raise NetworkPolicyExportError("policy_storage_unavailable", 503) from exc
        if isinstance(result, dict) and result.get("success") is False:
            reason = str(result.get("reason") or "invalid_policy")
            status = (
                404
                if reason == "agent_not_found"
                else 409
                if reason
                in {
                    "profile_disabled",
                    "agent_unassigned",
                }
                else 422
            )
            raise NetworkPolicyExportError(reason, status)
        snapshot = _validate_export(result, agent_id)
        exported = dict(snapshot)
        exported["policy_digest"] = hashlib.sha256(canonical_json_bytes(snapshot)).hexdigest()
        return exported


# Global service instance
_network_policy_service: NetworkPolicyService | None = None


def get_network_policy_service() -> NetworkPolicyService:
    """Get the global network policy service instance."""
    global _network_policy_service
    if _network_policy_service is None:
        _network_policy_service = NetworkPolicyService()
    return _network_policy_service
