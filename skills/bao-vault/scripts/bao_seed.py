#!/usr/bin/env python3
"""Bootstrap seeding script for OpenBao.

Reads `.secrets.yaml` and `agents.yaml`, then populates OpenBao with:
- KV v2 secrets from `.secrets.yaml`
- AppRoles from `agents.yaml` (every agent declaring an `api_key`)
- Database secrets engine configuration (with --with-db-engine)

Usage:
    BAO_ADDR=http://localhost:8200 BAO_TOKEN=dev-root-token python bao-seed.py
    BAO_ADDR=http://localhost:8200 BAO_TOKEN=dev-root-token python bao-seed.py --dry-run
    BAO_ADDR=http://localhost:8200 BAO_TOKEN=dev-root-token python bao-seed.py --with-db-engine

Environment variables:
    BAO_ADDR: OpenBao server URL (required)
    BAO_TOKEN: Root/admin token for seeding (required)
    BAO_MOUNT_PATH: KV v2 mount path (default: "secret")
    BAO_SECRET_PATH: Secret data path (default: "coordinator")
    BAO_TOKEN_TTL: Token TTL for AppRoles in seconds (default: 3600)
    BAO_SECRETS_FILE: Path to the secrets YAML (default: ./.secrets.yaml)
    AGENTS_YAML: Path to agents.yaml (default: ./agents.yaml)
"""

from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openbao_credentials import PrincipalTopology, bootstrap_paths, project_principals

logger = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "openspec/changes/restructure-openbao-per-agent-secrets/contracts"
_SOURCE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ROLE = re.compile(r"^(agent|service)-[a-z][a-z0-9-]*$")
_PLACEHOLDER = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")


@dataclass(frozen=True)
class ReconciliationPlan:
    topology: PrincipalTopology
    agent_values: dict[str, str] = field(repr=False)
    vendor_values: dict[str, str] = field(repr=False)
    retained_internal: tuple[str, ...]
    bootstrap_dir: Path
    retired_agents: tuple[str, ...]
    legacy_role_aliases: dict[str, str]

    def preview(self) -> str:
        """Describe the whole mutation set without credential material."""
        lines = [f"mount: {self.topology.mount}"]
        for principal in self.topology.principals:
            lines.append(f"reconcile role {principal.role_name}, policy {principal.policy_name} ")
            lines.append(f"  read scope: {', '.join(principal.read_paths) or '(none)'}")
            lines.append(f"  bootstrap: {principal.role_name}.bundle.json")
        for name in sorted(self.agent_values):
            lines.append(f"reconcile agent path agents/{name}")
        for name in sorted(self.vendor_values):
            lines.append(f"reconcile vendor path vendors/{name}")
        for name in self.retired_agents:
            lines.append(f"retire owned agent role agent-{name}, policy agent-{name}, path agents/{name} after confirmed cutover")
        for name, alias in sorted(self.legacy_role_aliases.items()):
            lines.append(f"retire legacy role alias {alias} for {name} after confirmed cutover")
        lines.append("retire coordinator-read policy after confirmed cutover and internal role handoff")
        return "\n".join(lines)


def _read_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing input file: {path}")
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"input must be a mapping: {path}")
    return data


def _validate_schema(data: dict[str, Any], name: str) -> None:
    schema = json.loads((_SCHEMA_DIR / name).read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data))
    if errors:
        raise ValueError(f"{name}: {errors[0].message}")


def _protected_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("bootstrap directory must not be a symlink")
    if path.exists() and (not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700):
        raise ValueError("bootstrap directory must be mode 0700")
    if not path.parent.is_dir():
        raise ValueError("bootstrap directory parent does not exist")
    for filename in ("managed-state.json",):
        target = path / filename
        if target.is_symlink() or (target.exists() and (not target.is_file() or stat.S_IMODE(target.stat().st_mode) != 0o600)):
            raise ValueError(f"unsafe bootstrap destination: {filename}")


def _managed_state(path: Path) -> dict[str, Any]:
    state_path = path / "managed-state.json"
    if not state_path.exists():
        return {"version": 1, "agents": []}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("agents"), list):
        raise ValueError("invalid managed state")
    if any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name) for name in state["agents"]):
        raise ValueError("invalid managed agent name")
    return state


def plan_reconciliation(
    agents_path: Path, secrets_path: Path, migration_map_path: Path,
    bootstrap_dir: Path, mount_path: str = "secret", *,
    confirm_cutover: bool = False, internal_role_name: str | None = None,
) -> ReconciliationPlan:
    """Validate all local inputs and destinations without mutating Bao or disk."""
    registry = _read_mapping(agents_path)
    flat = _read_mapping(secrets_path)
    migration = _read_mapping(migration_map_path)
    _validate_schema(migration, "migration-map.schema.json")
    topology = project_principals(registry, mount=mount_path)
    _validate_schema(topology.to_dict(), "principal-topology.schema.json")
    keyed = {p.name for p in topology.principals if p.kind == "agent"}
    if set(migration["agents"]) != keyed or set(migration["vendors"]) != set(topology.vendors):
        raise ValueError("migration map must cover every keyed agent and declared vendor exactly")
    for name in keyed:
        declared = registry["agents"][name].get("api_key")
        match = _PLACEHOLDER.fullmatch(declared) if isinstance(declared, str) else None
        if match is None or migration["agents"][name] != match.group(1):
            raise ValueError(f"agent {name} source key disagrees with exact registry placeholder")
    sources = list(migration["agents"].values()) + list(migration["vendors"].values()) + migration["retained_internal"]
    if len(sources) != len(set(sources)):
        raise ValueError("duplicate source key in migration map")
    if set(sources) != set(flat):
        raise ValueError(f"missing or unaccounted source keys: {', '.join(sorted(set(sources) ^ set(flat)))}")
    if any(not isinstance(key, str) or not _SOURCE.fullmatch(key) for key in flat):
        raise ValueError("invalid flat source key")
    destination_sources = list(migration["agents"].values()) + list(migration["vendors"].values())
    if any(not isinstance(flat[key], str) or not flat[key] for key in destination_sources):
        raise ValueError("every agent or vendor destination must hold a nonempty string")
    _protected_directory(bootstrap_dir)
    prior = _managed_state(bootstrap_dir)
    retired = tuple(sorted(set(prior["agents"]) - keyed))
    aliases = migration.get("legacy_role_aliases", {})
    if set(aliases) - (keyed | set(retired)):
        raise ValueError("legacy role alias must belong to a mapped or owned agent")
    if len(set(aliases.values())) != len(aliases) or any(not _ROLE.fullmatch(alias) for alias in aliases.values()):
        raise ValueError("invalid or colliding legacy role alias")
    if set(aliases.values()) & {p.role_name for p in topology.principals}:
        raise ValueError("legacy role alias collides with projected role")
    if confirm_cutover and (not internal_role_name or not re.fullmatch(r"[a-z][a-z0-9-]*", internal_role_name)):
        raise ValueError("cutover requires explicit internal AppRole name")
    if internal_role_name in {p.role_name for p in topology.principals} or internal_role_name in aliases.values():
        raise ValueError("internal AppRole collides with managed role")
    for principal in topology.principals:
        paths = bootstrap_paths(bootstrap_dir, principal.role_name)
        for target in (paths.bundle, paths.session, paths.lock):
            if target.is_symlink() or (target.exists() and (not target.is_file() or stat.S_IMODE(target.stat().st_mode) != 0o600)):
                raise ValueError(f"unsafe bootstrap destination: {target.name}")
    return ReconciliationPlan(
        topology=topology,
        agent_values={name: flat[key] for name, key in migration["agents"].items()},
        vendor_values={name: flat[key] for name, key in migration["vendors"].items()},
        retained_internal=tuple(migration["retained_internal"]), bootstrap_dir=bootstrap_dir,
        retired_agents=retired, legacy_role_aliases=dict(aliases),
    )


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically replace a protected JSON file; never follow a destination symlink."""
    if path.is_symlink():
        raise ValueError(f"unsafe destination: {path.name}")
    descriptor, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(data, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _event(event: str, action: str, outcome: str, principal_id: str, resource: str) -> dict[str, Any]:
    value = {"version": 1, "event": event, "occurred_at": datetime.now(timezone.utc).isoformat(),
             "action": action, "outcome": outcome, "principal_id": principal_id, "resource": resource}
    _validate_schema(value, "openbao-event.schema.json")
    return value


def _login_internal(client: Any, role_id: str, secret_id: str) -> dict[str, Any]:
    try:
        response = client.auth.approle.login(role_id=role_id, secret_id=secret_id, use_token=False)
        auth = response["auth"]
        if not isinstance(auth.get("client_token"), str) or not auth["client_token"]:
            raise ValueError("missing token")
        return auth
    except Exception:
        raise ValueError("configured internal AppRole credentials cannot authenticate") from None


def _verify_internal_handoff(client: Any, mount: str, role_id: str, secret_id: str) -> None:
    """Prove configured credentials can read internal data with the new policy."""
    import hvac

    auth = _login_internal(client, role_id, secret_id)
    policies = auth.get("policies")
    if not isinstance(policies, list) or "coordinator-internal-read" not in policies or "coordinator-read" in policies:
        raise ValueError("internal token does not have isolated policy")
    try:
        reader = hvac.Client(url=client.url, token=auth["client_token"])
        try:
            result = reader.secrets.kv.v2.read_secret_version(
                path="coordinator", mount_point=mount, raise_on_deleted_version=True,
            )
            if not isinstance(result, dict) or not isinstance(result.get("data", {}).get("data"), dict):
                raise ValueError("invalid internal document")
        finally:
            reader.auth.token.revoke_self()
    except Exception:
        raise ValueError("internal credentials cannot read coordinator path under isolated policy") from None


def apply_reconciliation(
    client: Any, plan: ReconciliationPlan, *, confirm_cutover: bool = False,
    internal_role_name: str | None = None, audit: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Apply a validated plan, recording sanitized outcome for each mutation."""
    audit = audit or (lambda record: print(json.dumps(record, sort_keys=True)))
    if confirm_cutover and (not internal_role_name or not re.fullmatch(r"[a-z][a-z0-9-]*", internal_role_name)):
        raise ValueError("cutover requires explicit internal AppRole name")
    internal_role_id = os.environ.get("BAO_INTERNAL_ROLE_ID", "")
    internal_secret_id = os.environ.get("BAO_INTERNAL_SECRET_ID", "")
    if confirm_cutover and (not internal_role_id or not internal_secret_id):
        raise ValueError("cutover requires BAO_INTERNAL_ROLE_ID and BAO_INTERNAL_SECRET_ID")
    mounts = client.sys.list_mounted_secrets_engines()
    mounts = mounts.get("data", mounts) if isinstance(mounts, dict) else {}
    mount = mounts.get(f"{plan.topology.mount}/")
    if not isinstance(mount, dict) or mount.get("type") != "kv" or mount.get("options", {}).get("version") != "2":
        raise ValueError("configured mount is not KV-v2")
    if confirm_cutover:
        current_internal = client.auth.approle.read_role(role_name=internal_role_name)
        if not isinstance(current_internal, dict) or not isinstance(current_internal.get("data"), dict):
            raise ValueError("internal AppRole must exist before cutover")
        if current_internal["data"].get("secret_id_num_uses") != 0:
            raise ValueError("internal AppRole must have reusable SecretIDs for handoff")
        server_role_id = client.auth.approle.read_role_id(role_name=internal_role_name)["data"]["role_id"]
        if not hmac.compare_digest(server_role_id, internal_role_id):
            raise ValueError("configured internal RoleID does not match selected AppRole")
        roles_response = client.auth.approle.list_roles()
        role_names = roles_response.get("data", {}).get("keys") if isinstance(roles_response, dict) else None
        if not isinstance(role_names, list):
            raise ValueError("cannot enumerate AppRoles for safe cutover")
        owned_retirements = {f"agent-{name}" for name in plan.retired_agents} | set(plan.legacy_role_aliases.values())
        for role_name in role_names:
            role_response = client.auth.approle.read_role(role_name=role_name)
            policies = role_response.get("data", {}).get("token_policies") if isinstance(role_response, dict) else None
            if not isinstance(policies, list):
                raise ValueError("cannot inspect AppRole policies for safe cutover")
            if "coordinator-read" in policies and role_name not in owned_retirements and role_name != internal_role_name:
                raise ValueError(f"unexpected AppRole still uses coordinator-read: {role_name}")
        # The one credential proof runs after installing the isolated policy,
        # preserving finite-use SecretIDs and keeping shared-policy deletion gated.
    plan.bootstrap_dir.mkdir(mode=0o700, exist_ok=True)
    _protected_directory(plan.bootstrap_dir)
    def mutate(event: str, action: str, principal_id: str, resource: str, operation: Callable[[], Any]) -> Any:
        try:
            result = operation()
        except Exception:
            audit(_event(event, action, "failure", principal_id, resource))
            raise
        audit(_event(event, action, "success", principal_id, resource))
        return result

    auth_methods = client.sys.list_auth_methods()
    auth_methods = auth_methods.get("data", auth_methods) if isinstance(auth_methods, dict) else {}
    if "approle/" not in auth_methods:
        mutate("openbao.principal.created", "create",
               "spiffe://coordinator.rotkohl.ai/service/identity-reader", "role",
               lambda: client.sys.enable_auth_method("approle"))

    for principal in plan.topology.principals:
        policy = "".join(f'path "{path}" {{\n  capabilities = ["read"]\n}}\n' for path in principal.read_paths)
        if not policy:
            # Bao rejects an empty policy. A deny-only stanza grants no data path.
            policy = 'path "sys/health" {\n  capabilities = ["deny"]\n}\n'
        mutate("openbao.principal.updated", "update", principal.principal_id, "policy",
               lambda p=principal, hcl=policy: client.sys.create_or_update_policy(name=p.policy_name, policy=hcl))
        mutate("openbao.principal.updated", "update", principal.principal_id, "role",
               lambda p=principal: client.auth.approle.create_or_update_approle(
                   role_name=p.role_name, token_policies=[p.policy_name], token_period=f"{p.token_period_seconds}s",
                   token_num_uses=0, secret_id_num_uses=1))
    for name, value in sorted(plan.agent_values.items()):
        principal = next(p for p in plan.topology.principals if p.kind == "agent" and p.name == name)
        mutate("openbao.principal.updated", "update", principal.principal_id, "agent_path",
               lambda n=name, v=value: client.secrets.kv.v2.create_or_update_secret(path=f"agents/{n}", secret={"api_key": v}, mount_point=plan.topology.mount))
    gateway = plan.topology.by_id("spiffe://coordinator.rotkohl.ai/service/egress-gateway")
    for name, value in sorted(plan.vendor_values.items()):
        mutate("openbao.principal.updated", "update", gateway.principal_id, "vendor_path",
               lambda n=name, v=value: client.secrets.kv.v2.create_or_update_secret(path=f"vendors/{n}", secret={"api_key": v}, mount_point=plan.topology.mount))
    for principal in plan.topology.principals:
        role_id = client.auth.approle.read_role_id(role_name=principal.role_name)["data"]["role_id"]
        response = client.auth.approle.generate_secret_id(role_name=principal.role_name, wrap_ttl="300s")
        wrap = response["wrap_info"]
        bundle = {"version": 1, "principal_id": principal.principal_id, "role_name": principal.role_name,
                  "role_id": role_id, "wrapped_secret_id": {"token": wrap["token"],
                  "creation_path": wrap["creation_path"], "creation_time": wrap["creation_time"], "ttl_seconds": wrap["ttl"]}}
        expected = f"auth/approle/role/{principal.role_name}/secret-id"
        if wrap["creation_path"] != expected:
            audit(_event("openbao.bootstrap.rejected", "reject", "failure", principal.principal_id, "bootstrap"))
            raise ValueError("unexpected wrapping creation path")
        _validate_schema(bundle, "bootstrap-bundle.schema.json")
        mutate("openbao.bootstrap.issued", "issue", principal.principal_id, "bootstrap",
               lambda p=principal, b=bundle: _atomic_json(bootstrap_paths(plan.bootstrap_dir, p.role_name).bundle, b))
    if confirm_cutover:
        internal_policy = f'path "{plan.topology.mount}/data/coordinator" {{\n  capabilities = ["read"]\n}}\n'
        internal_id = "spiffe://coordinator.rotkohl.ai/service/identity-reader"
        mutate("openbao.principal.updated", "update", internal_id, "policy",
               lambda: client.sys.create_or_update_policy(name="coordinator-internal-read", policy=internal_policy))
        mutate("openbao.principal.updated", "update", internal_id, "role",
               lambda: client.auth.approle.create_or_update_approle(role_name=internal_role_name, token_policies=["coordinator-internal-read"]))
        _verify_internal_handoff(client, plan.topology.mount, internal_role_id, internal_secret_id)
        for name in plan.retired_agents:
            principal_id = f"spiffe://coordinator.rotkohl.ai/agent/{name}"
            mutate("openbao.principal.retired", "retire", principal_id, "role", lambda n=name: client.auth.approle.delete_role(role_name=f"agent-{n}"))
            mutate("openbao.principal.retired", "retire", principal_id, "policy", lambda n=name: client.sys.delete_policy(name=f"agent-{n}"))
            mutate("openbao.principal.retired", "retire", principal_id, "agent_path", lambda n=name: client.secrets.kv.v2.delete_metadata_and_all_versions(path=f"agents/{n}", mount_point=plan.topology.mount))
        for name, alias in sorted(plan.legacy_role_aliases.items()):
            principal_id = f"spiffe://coordinator.rotkohl.ai/agent/{name}"
            mutate("openbao.principal.retired", "retire", principal_id, "role", lambda r=alias: client.auth.approle.delete_role(role_name=r))
        mutate("openbao.principal.retired", "retire", internal_id, "policy", lambda: client.sys.delete_policy(name="coordinator-read"))
    current_agents = sorted(p.name for p in plan.topology.principals if p.kind == "agent")
    owned = current_agents if confirm_cutover else sorted(set(current_agents) | set(plan.retired_agents))
    _atomic_json(plan.bootstrap_dir / "managed-state.json", {"version": 1, "agents": owned})

def _default_config_path(env_name: str, filename: str) -> Path:
    """Resolve explicit configuration before a consumer-local default."""
    configured = os.environ.get(env_name)
    return Path(configured).expanduser() if configured else Path.cwd() / filename


def _get_client():  # type: ignore[no-untyped-def]
    """Create an hvac client authenticated with the root/admin token."""
    import hvac  # type: ignore[import-untyped]

    addr = os.environ.get("BAO_ADDR")
    token = os.environ.get("BAO_TOKEN")

    if not addr:
        print("ERROR: BAO_ADDR environment variable is required", file=sys.stderr)
        sys.exit(1)
    if not token:
        print("ERROR: BAO_TOKEN environment variable is required", file=sys.stderr)
        sys.exit(1)

    client = hvac.Client(url=addr, token=token)
    if not client.is_authenticated():
        print(
            f"ERROR: Authentication failed at {addr} — check BAO_TOKEN",
            file=sys.stderr,
        )
        sys.exit(1)

    return client


def seed_secrets(
    client,  # type: ignore[no-untyped-def]
    secrets_path: Path,
    mount_path: str,
    secret_path: str,
    dry_run: bool = False,
) -> None:
    """Write secrets from .secrets.yaml to OpenBao KV v2."""
    if not secrets_path.is_file():
        print(f"ERROR: {secrets_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(secrets_path) as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        print(f"ERROR: {secrets_path} is not a valid YAML mapping", file=sys.stderr)
        sys.exit(1)

    # Filter to string values only
    secrets = {k: v for k, v in data.items() if isinstance(v, str)}

    if dry_run:
        print(f"[DRY RUN] Would write {len(secrets)} secrets to {mount_path}/{secret_path}:")
        for key in sorted(secrets):
            print(f"  - {key}")
        return

    client.secrets.kv.v2.create_or_update_secret(
        path=secret_path,
        secret=secrets,
        mount_point=mount_path,
    )
    print(f"Wrote {len(secrets)} secrets to {mount_path}/{secret_path}:")
    for key in sorted(secrets):
        print(f"  - {key}")


def seed_approles(
    client,  # type: ignore[no-untyped-def]
    agents_path: Path,
    mount_path: str,
    secret_path: str,
    token_ttl: int,
    dry_run: bool = False,
) -> None:
    """Create AppRoles from agents.yaml for every agent declaring a key.

    The selector is ``api_key``, not ``transport``. ``get_api_key_identities()``
    already derives ``COORDINATION_API_KEY_IDENTITIES`` from any agent with a
    resolvable key regardless of transport (design D5), because an ``mcp`` agent
    still authenticates over HTTP — through the session hooks, through
    ``http_proxy`` when the local database is unreachable, and for every call
    when the coordinator is hosted rather than run as a local MCP server.
    Selecting AppRoles on ``transport == "http"`` here left that set narrower
    than the identity map it is supposed to back: an agent could hold an
    identity row whose key OpenBao was never told to serve.
    """
    if not agents_path.is_file():
        print(f"WARNING: {agents_path} not found — skipping AppRole creation", file=sys.stderr)
        return

    with open(agents_path) as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict) or "agents" not in data:
        print(f"WARNING: {agents_path} has no 'agents' section — skipping", file=sys.stderr)
        return

    keyed_agents = [
        (name, agent_data)
        for name, agent_data in data["agents"].items()
        if agent_data.get("api_key")
    ]

    if not keyed_agents:
        print("No agents declare an api_key — skipping AppRole creation")
        return

    # Policy granting read access to coordinator secrets (shared path for MVP)
    policy_name = "coordinator-read"
    policy_hcl = f'path "{mount_path}/data/{secret_path}" {{\n  capabilities = ["read"]\n}}\n'

    if dry_run:
        print(f"[DRY RUN] Would create policy '{policy_name}'")
        for name, adata in keyed_agents:
            role_id = adata.get("openbao_role_id", name)
            print(f"[DRY RUN] Would create AppRole '{role_id}' (agent: {name})")
        return

    # Create/update the shared read policy
    client.sys.create_or_update_policy(name=policy_name, policy=policy_hcl)
    print(f"Created policy: {policy_name}")

    # Enable AppRole auth if not already enabled
    auth_methods = client.sys.list_auth_methods()
    if "approle/" not in auth_methods:
        client.sys.enable_auth_method("approle")
        print("Enabled AppRole auth method")

    for name, agent_data in keyed_agents:
        role_id = agent_data.get("openbao_role_id", name)
        client.auth.approle.create_or_update_approle(
            role_name=role_id,
            token_policies=[policy_name],
            token_ttl=f"{token_ttl}s",
            token_max_ttl=f"{24 * 3600}s",
        )
        print(f"Created AppRole: {role_id} (agent: {name})")


def seed_db_engine(
    client,  # type: ignore[no-untyped-def]
    dry_run: bool = False,
) -> None:
    """Configure the database secrets engine for PostgreSQL.

    Sets up a connection to PostgreSQL and creates a role template for
    generating per-agent dynamic credentials.
    """
    if dry_run:
        print("[DRY RUN] Would enable database secrets engine at 'database/'")
        print("[DRY RUN] Would configure PostgreSQL connection from POSTGRES_DSN")
        print("[DRY RUN] Would create role 'coordinator-agent' (TTL: 1h, max: 24h)")
        return

    db_dsn = os.environ.get("POSTGRES_DSN")
    if not db_dsn:
        raise ValueError(
            "POSTGRES_DSN env var required for database secrets engine setup"
        )

    # Enable the database secrets engine if not already enabled
    secrets_engines = client.sys.list_mounted_secrets_engines()
    if "database/" not in secrets_engines:
        client.sys.enable_secrets_engine("database")
        print("Enabled database secrets engine")

    # Configure PostgreSQL connection — parse the DSN properly to extract
    # credentials and build a template URL with {{username}}/{{password}}
    # placeholders for OpenBao's database secrets engine.
    from urllib.parse import urlparse

    parsed = urlparse(db_dsn)
    db_username = parsed.username or "postgres"
    db_password = parsed.password or "postgres"

    if "{{username}}" in db_dsn:
        # Already a template URL, use as-is
        connection_url = db_dsn
    else:
        # Build template URL: strip existing credentials, insert placeholders
        host_port = parsed.hostname or "localhost"
        if parsed.port:
            host_port = f"{host_port}:{parsed.port}"
        db_name = parsed.path.lstrip("/") or "postgres"
        connection_url = f"postgresql://{{{{username}}}}:{{{{password}}}}@{host_port}/{db_name}"

    client.secrets.database.configure(
        name="coordinator-postgres",
        plugin_name="postgresql-database-plugin",
        connection_url=connection_url,
        allowed_roles=["coordinator-agent"],
        username=db_username,
        password=db_password,
    )
    print("Configured PostgreSQL connection: coordinator-postgres")

    # Create role template for per-agent dynamic credentials
    creation_statements = [
        "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';",
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{{name}}";',
    ]
    client.secrets.database.create_role(
        name="coordinator-agent",
        db_name="coordinator-postgres",
        creation_statements=creation_statements,
        default_ttl="1h",
        max_ttl="24h",
    )
    print("Created database role: coordinator-agent (TTL: 1h, max: 24h)")


def main() -> None:
    """Reconcile namespaced principal credentials from an explicit migration map."""
    parser = argparse.ArgumentParser(
        description="Provision per-principal OpenBao credentials from an explicit migration map."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to OpenBao",
    )
    parser.add_argument("--migration-map", type=Path, required=True,
                        help="Versioned mapping of flat source keys to agents and vendors")
    parser.add_argument("--bootstrap-dir", type=Path,
                        default=Path(os.environ.get("BAO_BOOTSTRAP_DIR", "")) if os.environ.get("BAO_BOOTSTRAP_DIR") else None,
                        help="Protected directory for principal bootstrap bundles")
    parser.add_argument("--confirm-cutover", action="store_true",
                        help="Retire only owned legacy agent access after explicit cutover")
    parser.add_argument("--internal-role-name", type=str,
                        help="Existing internal AppRole to isolate before shared policy retirement")
    parser.add_argument(
        "--secrets-path",
        type=Path,
        default=None,
        help="Path to .secrets.yaml (default: BAO_SECRETS_FILE or ./.secrets.yaml)",
    )
    parser.add_argument(
        "--agents-path",
        type=Path,
        default=None,
        help="Path to agents.yaml (default: AGENTS_YAML or ./agents.yaml)",
    )
    args = parser.parse_args()
    secrets_path = args.secrets_path or _default_config_path(
        "BAO_SECRETS_FILE", ".secrets.yaml"
    )
    agents_path = args.agents_path or _default_config_path("AGENTS_YAML", "agents.yaml")

    mount_path = os.environ.get("BAO_MOUNT_PATH", "secret")
    if args.bootstrap_dir is None:
        parser.error("--bootstrap-dir or BAO_BOOTSTRAP_DIR is required")
    plan = plan_reconciliation(
        agents_path, secrets_path, args.migration_map, args.bootstrap_dir, mount_path,
        confirm_cutover=args.confirm_cutover, internal_role_name=args.internal_role_name,
    )
    print(plan.preview())
    if not args.dry_run:
        apply_reconciliation(_get_client(), plan, confirm_cutover=args.confirm_cutover,
                             internal_role_name=args.internal_role_name)


if __name__ == "__main__":
    main()
