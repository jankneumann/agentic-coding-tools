#!/usr/bin/env python3
"""Generate cloud coordinator configuration for all agent environments.

Creates a .env.cloud file with local agent env vars and optionally
pushes server-side env vars to Railway via the CLI.

The agent roster, the per-agent ``--<agent-name>-key`` flags, the identity
map, and the shell aliases are all derived from ``agents.yaml`` via
:func:`src.agents_config.load_agents_config` (design decision D7). There is
no roster in this file: adding a vendor harness to ``agents.yaml`` is the
only edit needed for it to show up here.

RETIREMENT: this script is scheduled for deletion in roadmap item **pca-03**
(``replace-static-api-keys-with-session-tokens``), when static per-agent API
keys are replaced by issued session tokens. Do not invest further in it —
fix bugs, but route new capability through the session-token work instead.

Usage:
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com --railway
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com \
        --railway-service agentic-coordinator
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com \
        --railway --claude-local-key <key> --verify

Then:
    source .env.cloud   # activate in current shell
    make hooks-setup    # install lifecycle hooks
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

# Importable both as `scripts/setup_cloud.py` (sys.path[0] is scripts/) and as
# a loaded module from the test suite.
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

try:
    from src.agents_config import load_agents_config  # noqa: E402
except ImportError as exc:  # pragma: no cover - operator environment guard
    raise SystemExit(
        f"Cannot load the agent registry ({exc}). This script now derives its roster "
        "from agents.yaml and needs the coordinator's dependencies. Run it as:\n"
        "    cd agent-coordinator && uv run python scripts/setup_cloud.py --domain <domain>"
    ) from exc


@dataclass(frozen=True)
class AgentSlot:
    """One registry agent, projected onto this script's CLI surface."""

    name: str
    type: str
    transport: str
    command: str | None  # cli.command, or None for agents without a `cli` section

    @property
    def key_flag(self) -> str:
        """argparse dest for this agent's key, e.g. ``claude_local_key``."""
        return key_flag_for(self.name)

    @property
    def cli_flag(self) -> str:
        """CLI flag for this agent's key, e.g. ``--claude-local-key``."""
        return cli_flag_for(self.name)


@dataclass(frozen=True)
class AliasSpec:
    """A shell alias wrapping one vendor CLI with an agent's coordinator key."""

    name: str
    slot: AgentSlot


def key_flag_for(agent_name: str) -> str:
    return f"{agent_name.replace('-', '_')}_key"


def cli_flag_for(agent_name: str) -> str:
    return f"--{key_flag_for(agent_name).replace('_', '-')}"


def load_roster(
    path: Path | None = None,
    *,
    secrets_path: Path | None = None,
) -> list[AgentSlot]:
    """Project ``agents.yaml`` onto the roster this script operates over."""
    return [
        AgentSlot(
            name=agent.name,
            type=agent.type,
            transport=agent.transport,
            command=agent.cli.command if agent.cli else None,
        )
        for agent in load_agents_config(path, secrets_path=secrets_path)
    ]


def default_key_slot(roster: list[AgentSlot]) -> AgentSlot | None:
    """The agent whose key becomes ``COORDINATION_API_KEY`` in ``.env.cloud``.

    Rule: the first local (``transport: mcp``) Claude Code agent — the shell
    that sources this file is, by construction, a local Claude Code session.
    Falls back to the first local agent, then to the first agent at all.
    """
    for slot in roster:
        if slot.type == "claude_code" and slot.transport == "mcp":
            return slot
    for slot in roster:
        if slot.transport == "mcp":
            return slot
    return roster[0] if roster else None


def derive_aliases(roster: list[AgentSlot]) -> list[AliasSpec]:
    """One alias per distinct vendor CLI command, named ``c<command>``.

    Only CLI-bearing agents (those with a ``cli`` section) get an alias, and
    only one per command: two agents sharing a command (``claude-local`` and
    ``claude-remote`` both run ``claude``) would otherwise emit two aliases of
    the same name, the second silently shadowing the first and handing the
    wrong key to the local CLI. The local (``transport: mcp``) agent wins,
    since an alias only ever runs in a local shell; registry order breaks any
    remaining tie.
    """
    chosen: dict[str, AgentSlot] = {}
    for slot in roster:
        if not slot.command:
            continue
        current = chosen.get(slot.command)
        if current is None or (current.transport != "mcp" and slot.transport == "mcp"):
            chosen[slot.command] = slot
    return [AliasSpec(name=f"c{command}", slot=slot) for command, slot in chosen.items()]


def generate_key() -> str:
    return secrets.token_hex(32)


def build_identities(
    roster: list[AgentSlot], keys: dict[str, str]
) -> dict[str, dict[str, str]]:
    """Build ``COORDINATION_API_KEY_IDENTITIES`` — ``{key: {agent_id, agent_type}}``."""
    identities: dict[str, dict[str, str]] = {}
    for slot in roster:
        key = keys.get(slot.key_flag)
        if key:
            identities[key] = {"agent_id": slot.name, "agent_type": slot.type}
    return identities


def write_env_file(
    domain: str, keys: dict[str, str], output: Path, roster: list[AgentSlot]
) -> None:
    url = f"https://{domain}"
    aliases = derive_aliases(roster)
    alias_names = ", ".join(alias.name for alias in aliases) or "(none)"
    default_slot = default_key_slot(roster)
    lines = [
        "# Cloud coordinator configuration",
        f"# Generated for domain: {domain}",
        "#",
        "# Roster derived from agents.yaml — do not hand-edit agent entries here.",
        "#",
        "# Usage: source this file, or add to ~/.zshrc / ~/.bashrc",
        f"#   Then use: {alias_names} aliases to launch with coordination",
        "",
        "# -- Shared coordinator settings --",
        f'export COORDINATION_API_URL="{url}"',
        f'export COORDINATION_ALLOWED_HOSTS="{domain}"',
        "",
        "# -- Cloudflare Access service token (edge auth) --",
        "# Required only when the coordinator is behind a Cloudflare Access",
        "# application (recommended for public deployments). Create a service",
        "# token in Zero Trust > Access > Service Tokens, then uncomment and fill",
        "# in the two values below. See docs/cloudflare-access-setup.md.",
        '# export CF_ACCESS_CLIENT_ID="<client-id>.access"',
        '# export CF_ACCESS_CLIENT_SECRET="<client-secret>"',
        "",
    ]

    default_key = keys.get(default_slot.key_flag, "") if default_slot else ""
    if default_slot and default_key:
        lines.append(f"# -- Default key ({default_slot.name}) --")
        lines.append(f'export COORDINATION_API_KEY="{default_key}"')
        lines.append("")

    lines.append("# -- CLI aliases (launch with per-agent coordinator key) --")
    for alias in aliases:
        key = keys.get(alias.slot.key_flag, "")
        if key:
            lines.append(
                f"alias {alias.name}='COORDINATION_API_KEY=\"{key}\" "
                f"{alias.slot.command}'  # {alias.slot.name}"
            )
    lines.append("")

    output.write_text("\n".join(lines) + "\n")


# -- Railway CLI integration --


def check_railway_cli() -> bool:
    if not shutil.which("railway"):
        print("  Error: 'railway' CLI not found.")
        return False
    result = subprocess.run(
        ["railway", "whoami", "--json"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print("  Error: Railway CLI not authenticated. Run: railway login")
        return False
    return True


def check_railway_linked() -> dict | None:
    result = subprocess.run(
        ["railway", "status", "--json"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def find_railway_services(status: dict) -> list[dict[str, str]]:
    services: list[dict[str, str]] = []
    for edge in status.get("services", {}).get("edges", []):
        node = edge.get("node", {})
        if node.get("name"):
            services.append({"id": node["id"], "name": node["name"]})
    return services


def detect_api_service(status: dict) -> str | None:
    """Auto-detect API service (has repo source, not image source)."""
    for env_edge in status.get("environments", {}).get("edges", []):
        env = env_edge.get("node", {})
        for svc_edge in env.get("serviceInstances", {}).get("edges", []):
            svc = svc_edge.get("node", {})
            source = svc.get("source", {})
            if source.get("repo") and not source.get("image"):
                return svc.get("serviceName")
    return None


def railway_set_variable(key: str, value: str, service: str) -> bool:
    result = subprocess.run(
        ["railway", "variable", "set", f"{key}={value}", "--service", service],
        capture_output=True, text=True, timeout=15,
    )
    return result.returncode == 0


def push_to_railway(service: str | None, all_keys: str, identities_json: str) -> bool:
    if not check_railway_cli():
        return False
    status = check_railway_linked()
    if not status:
        print("  Error: Not linked to a Railway project. Run: railway link")
        return False

    print(f"  Project: {status.get('name', 'unknown')}")
    env_name = "unknown"
    for env_edge in status.get("environments", {}).get("edges", []):
        env_node = env_edge.get("node", {})
        if env_node.get("name"):
            env_name = env_node["name"]
            break
    print(f"  Environment: {env_name}")

    if not service:
        service = detect_api_service(status)
        if service:
            print(f"  Auto-detected service: {service}")
        else:
            all_services = find_railway_services(status)
            print("  Error: Could not auto-detect API service.")
            if all_services:
                names = ", ".join(s["name"] for s in all_services)
                print(f"  Available services: {names}")
            return False
    else:
        print(f"  Target service: {service}")

    success = True
    for var_name, var_value in [
        ("COORDINATION_API_KEYS", all_keys),
        ("COORDINATION_API_KEY_IDENTITIES", identities_json),
    ]:
        ok = railway_set_variable(var_name, var_value, service)
        mark = "ok" if ok else "FAILED"
        display = var_value[:40] + "..." if len(var_value) > 40 else var_value
        print(f"  {var_name}: {display} [{mark}]")
        if not ok:
            success = False

    if success:
        print(f"  Env vars set on '{service}'. Service will redeploy automatically.")
    return success


# -- Verification --


def verify_connectivity(domain: str, api_key: str | None = None) -> bool:
    import os

    url = f"https://{domain}/health"
    print(f"\nVerifying: GET {url}")
    try:
        req = Request(url)
        req.add_header("User-Agent", "agentic-coding-tools/0.1")
        if api_key:
            req.add_header("X-API-Key", api_key)
        # Pass the Cloudflare Access edge when a service token is configured.
        cf_id = os.environ.get("CF_ACCESS_CLIENT_ID", "").strip()
        cf_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET", "").strip()
        if cf_id and cf_secret:
            req.add_header("CF-Access-Client-Id", cf_id)
            req.add_header("CF-Access-Client-Secret", cf_secret)
        with urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            print(f"  Status: {resp.status}")
            print(f"  Body:   {json.dumps(body)}")
            return resp.status == 200
    except URLError as e:
        print(f"  Failed: {e}")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


# -- Main --


def build_parser(roster: list[AgentSlot]) -> argparse.ArgumentParser:
    """Build the CLI, with one ``--<agent-name>-key`` flag per registry agent."""
    parser = argparse.ArgumentParser(description="Cloud coordinator setup")
    parser.add_argument("--domain", required=True, help="Coordinator domain")
    for slot in roster:
        parser.add_argument(
            slot.cli_flag,
            dest=slot.key_flag,
            help=f"{slot.name} ({slot.type}) key (generated if omitted)",
        )
    parser.add_argument("--railway", action="store_true", help="Push env vars to Railway")
    parser.add_argument("--railway-service", help="Railway service name (auto-detected if omitted)")
    parser.add_argument("--verify", action="store_true", help="Test /health after setup")
    parser.add_argument("--output", default=str(PROJECT_DIR / ".env.cloud"))
    return parser


def main() -> None:
    roster = load_roster()
    parser = build_parser(roster)
    args = parser.parse_args()

    use_railway = args.railway or args.railway_service is not None
    domain = args.domain.removeprefix("https://").removeprefix("http://").rstrip("/")

    keys = {
        slot.key_flag: getattr(args, slot.key_flag) or generate_key() for slot in roster
    }

    identities = build_identities(roster, keys)
    all_keys = ",".join(keys[s.key_flag] for s in roster if keys.get(s.key_flag))
    identities_json = json.dumps(identities, separators=(",", ":"))

    output_path = Path(args.output)
    write_env_file(domain, keys, output_path, roster)

    print("=" * 70)
    print("Cloud Coordinator Setup")
    print("=" * 70)

    print(f"\n1. Local env file: {output_path}")
    print(f"   Activate: source {output_path}")

    if use_railway:
        print("\n2. Railway environment variables:")
        push_to_railway(args.railway_service, all_keys, identities_json)
    else:
        print("\n2. Railway env vars (set in dashboard, or re-run with --railway):")
        print("   " + "-" * 60)
        print(f"   COORDINATION_API_KEYS={all_keys}")
        print(f"   COORDINATION_API_KEY_IDENTITIES={identities_json}")
        print("   " + "-" * 60)

    print("\n3. Per-agent API keys:")
    print(f"   {'Agent':<20s} {'Key':>14s}  Source")
    print(f"   {'-'*20} {'-'*14}  {'-'*10}")
    for slot in roster:
        key = keys.get(slot.key_flag, "")
        src = "(provided)" if getattr(args, slot.key_flag) else "(generated)"
        print(f"   {slot.name:<20s} {key[:12]}...  {src}")
        print(f"     {slot.cli_flag} {key}")

    print("\n4. Install hooks: make hooks-setup")

    if args.verify:
        default_slot = default_key_slot(roster)
        verify_key = keys.get(default_slot.key_flag) if default_slot else None
        ok = verify_connectivity(domain, verify_key)
        print("\n[ok] Healthy" if ok else "\n[fail] Unreachable")
        if not ok:
            sys.exit(1)
    print()


if __name__ == "__main__":
    main()
