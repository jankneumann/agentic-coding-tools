"""Deterministic projection of registry identities into exact Bao scopes.

The projection accepts either the raw ``agents.yaml`` mapping or an object with
``agents`` and ``credential_vendors`` attributes. It has no IO or credentials.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

_SLUG = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_MOUNT = re.compile(r"^[a-z][a-z0-9-]*$")
_PREFIX = "spiffe://coordinator.rotkohl.ai"


class ProjectionError(ValueError):
    """Registry cannot be projected into a unique, least-privilege topology."""


@dataclass(frozen=True)
class Principal:
    kind: str
    principal_id: str
    role_name: str
    policy_name: str
    read_paths: tuple[str, ...]
    token_period_seconds: int = 3600
    name: str | None = None
    agent_kv_path: str | None = None
    vendor_credentials: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["read_paths"] = list(self.read_paths)
        if self.kind == "agent":
            value["vendor_credentials"] = list(self.vendor_credentials)
        else:
            for key in ("name", "agent_kv_path", "vendor_credentials"):
                value.pop(key)
        return value


@dataclass(frozen=True)
class PrincipalTopology:
    mount: str
    vendors: tuple[str, ...]
    principals: tuple[Principal, ...]
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "mount": self.mount,
            "vendors": list(self.vendors),
            "principals": [principal.to_dict() for principal in self.principals],
        }

    def by_id(self, principal_id: str) -> Principal:
        for principal in self.principals:
            if principal.principal_id == principal_id:
                return principal
        raise KeyError(principal_id)


def agent_principal_id(name: str) -> str:
    if not _SLUG.fullmatch(name):
        raise ProjectionError("invalid agent name")
    return f"{_PREFIX}/agent/{name}"


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def project_principals(registry: Any, mount: str = "secret") -> PrincipalTopology:
    """Project keyed agents and two service principals from the registry.

    Each vendor must be declared in ``credential_vendors``; policy/catalog
    vendor labels never confer credential read access.
    """
    if not isinstance(mount, str) or not _MOUNT.fullmatch(mount):
        raise ProjectionError("invalid KV-v2 mount")
    catalog = _field(registry, "credential_vendors")
    if not isinstance(catalog, (list, tuple)):
        raise ProjectionError("credential_vendors catalog is required")
    if len(catalog) != len(set(catalog)) or any(
        not isinstance(v, str) or not _SLUG.fullmatch(v) for v in catalog
    ):
        raise ProjectionError("invalid or duplicate credential vendor")
    vendors = tuple(sorted(catalog))
    raw_agents = _field(registry, "agents")
    if isinstance(raw_agents, Mapping):
        agents = list(raw_agents.items())
    elif isinstance(raw_agents, (list, tuple)):
        agents = [(_field(agent, "name"), agent) for agent in raw_agents]
    else:
        raise ProjectionError("agents mapping is required")
    names: set[str] = set()
    principals: list[Principal] = []
    all_agent_paths: list[str] = []
    used_vendors: set[str] = set()
    for name, agent in agents:
        if not isinstance(name, str) or not _SLUG.fullmatch(name) or name in names:
            raise ProjectionError("invalid or duplicate agent name")
        names.add(name)
        if _field(agent, "openbao_role_id") is not None:
            raise ProjectionError("manual openbao_role_id is forbidden")
        api_key = _field(agent, "api_key")
        if api_key is not None and (not isinstance(api_key, str) or not api_key):
            raise ProjectionError("invalid agent API key declaration")
        has_api_key = api_key is not None
        declared = _field(agent, "vendor_credentials", None)
        if has_api_key and declared is None:
            raise ProjectionError("keyed agent requires explicit vendor_credentials")
        if declared is None:
            declared = []
        if not isinstance(declared, (list, tuple)) or any(
            not isinstance(v, str) or v not in vendors for v in declared
        ) or len(declared) != len(set(declared)):
            raise ProjectionError("invalid, duplicate, or undeclared vendor credential")
        agent_vendors = tuple(sorted(declared))
        if not has_api_key:
            if agent_vendors:
                raise ProjectionError("keyless agent cannot declare vendor credentials")
            continue
        used_vendors.update(agent_vendors)
        agent_path = f"{mount}/data/agents/{name}"
        all_agent_paths.append(agent_path)
        principals.append(Principal(
            kind="agent",
            name=name,
            principal_id=agent_principal_id(name),
            role_name=f"agent-{name}",
            policy_name=f"agent-{name}",
            agent_kv_path=f"agents/{name}",
            vendor_credentials=agent_vendors,
            read_paths=(agent_path,) + tuple(
                f"{mount}/data/vendors/{vendor}" for vendor in agent_vendors
            ),
        ))
    principals.sort(key=lambda principal: principal.name or "")
    principals.extend((
        Principal(
            kind="identity_reader",
            principal_id=f"{_PREFIX}/service/identity-reader",
            role_name="service-identity-reader",
            policy_name="service-identity-reader",
            read_paths=tuple(sorted(all_agent_paths)),
        ),
        Principal(
            kind="egress_gateway",
            principal_id=f"{_PREFIX}/service/egress-gateway",
            role_name="service-egress-gateway",
            policy_name="service-egress-gateway",
            read_paths=tuple(f"{mount}/data/vendors/{vendor}" for vendor in sorted(used_vendors)),
        ),
    ))
    for attribute in ("principal_id", "role_name", "policy_name"):
        values = [_field(p, attribute) for p in principals]
        if len(values) != len(set(values)):
            raise ProjectionError(f"duplicate projected {attribute}")
    return PrincipalTopology(mount=mount, vendors=vendors, principals=tuple(principals))
