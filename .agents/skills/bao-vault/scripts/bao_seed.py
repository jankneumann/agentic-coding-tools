#!/usr/bin/env python3
"""Bootstrap seeding script for OpenBao.

Reads `.secrets.yaml` and `agents.yaml`, then populates OpenBao with:
- KV v2 secrets from `.secrets.yaml`
- AppRoles from `agents.yaml` (HTTP-transport agents only)
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
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

def _repo_root() -> Path:
    """Find the repository root via git, falling back to path traversal."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).parent,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    # Fallback: scripts/ → bao-vault/ → skills/ → repo root
    return Path(__file__).resolve().parent.parent.parent.parent


COORDINATOR_DIR = _repo_root() / "agent-coordinator"
DEFAULT_SECRETS_PATH = COORDINATOR_DIR / ".secrets.yaml"
DEFAULT_AGENTS_PATH = COORDINATOR_DIR / "agents.yaml"


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
    """Create AppRoles from agents.yaml for HTTP-transport agents."""
    if not agents_path.is_file():
        print(f"WARNING: {agents_path} not found — skipping AppRole creation", file=sys.stderr)
        return

    with open(agents_path) as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict) or "agents" not in data:
        print(f"WARNING: {agents_path} has no 'agents' section — skipping", file=sys.stderr)
        return

    http_agents = [
        (name, agent_data)
        for name, agent_data in data["agents"].items()
        if agent_data.get("transport") == "http"
    ]

    if not http_agents:
        print("No HTTP-transport agents found — skipping AppRole creation")
        return

    # Policy granting read access to coordinator secrets (shared path for MVP)
    policy_name = "coordinator-read"
    policy_hcl = f'path "{mount_path}/data/{secret_path}" {{\n  capabilities = ["read"]\n}}\n'

    if dry_run:
        print(f"[DRY RUN] Would create policy '{policy_name}'")
        for name, adata in http_agents:
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

    for name, agent_data in http_agents:
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
    db_dsn = os.environ.get(
        "POSTGRES_DSN",
        "postgresql://postgres:postgres@localhost:54322/postgres",
    )

    if dry_run:
        print("[DRY RUN] Would enable database secrets engine at 'database/'")
        print(f"[DRY RUN] Would configure PostgreSQL connection: {db_dsn}")
        print("[DRY RUN] Would create role 'coordinator-agent' (TTL: 1h, max: 24h)")
        return

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
    """Main entry point for bao-seed.py."""
    parser = argparse.ArgumentParser(
        description="Seed OpenBao with secrets and AppRoles from project config files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to OpenBao",
    )
    parser.add_argument(
        "--with-db-engine",
        action="store_true",
        help="Configure the database secrets engine for PostgreSQL",
    )
    parser.add_argument(
        "--secrets-path",
        type=Path,
        default=DEFAULT_SECRETS_PATH,
        help="Path to .secrets.yaml (default: agent-coordinator/.secrets.yaml)",
    )
    parser.add_argument(
        "--agents-path",
        type=Path,
        default=DEFAULT_AGENTS_PATH,
        help="Path to agents.yaml (default: agent-coordinator/agents.yaml)",
    )
    args = parser.parse_args()

    mount_path = os.environ.get("BAO_MOUNT_PATH", "secret")
    secret_path = os.environ.get("BAO_SECRET_PATH", "coordinator")
    token_ttl = int(os.environ.get("BAO_TOKEN_TTL", "3600"))

    if args.dry_run:
        print("=== DRY RUN MODE ===\n")
        client = None
    else:
        client = _get_client()

    # Step 1: Seed secrets from .secrets.yaml
    print("--- Seeding secrets ---")
    seed_secrets(client, args.secrets_path, mount_path, secret_path, dry_run=args.dry_run)
    print()

    # Step 2: Create AppRoles from agents.yaml
    print("--- Seeding AppRoles ---")
    seed_approles(
        client, args.agents_path, mount_path, secret_path, token_ttl, dry_run=args.dry_run
    )
    print()

    # Step 3: Configure database engine (optional)
    if args.with_db_engine:
        print("--- Configuring database secrets engine ---")
        seed_db_engine(client, dry_run=args.dry_run)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
