#!/usr/bin/env python3
"""Generate cloud coordinator configuration for all agent environments.

Creates a .env.cloud file with local agent env vars and optionally
pushes server-side env vars to Railway via the CLI.

Usage:
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com --railway
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com \
        --railway-service agentic-coordinator
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com \
        --railway --claude-key <key> --verify

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
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

AGENTS = [
    # Local CLI agents using HTTP instead of MCP
    {
        "id": "claude-local",
        "type": "claude_code",
        "key_flag": "claude_local_key",
        "label": "Claude (local)",
    },
    {
        "id": "codex-local",
        "type": "codex",
        "key_flag": "codex_local_key",
        "label": "Codex (local)",
    },
    {
        "id": "gemini-local",
        "type": "gemini",
        "key_flag": "gemini_local_key",
        "label": "Gemini (local)",
    },
    # Cloud/remote agents
    {
        "id": "claude-remote",
        "type": "claude_code",
        "key_flag": "claude_remote_key",
        "label": "Claude (remote)",
    },
    {
        "id": "codex-remote",
        "type": "codex",
        "key_flag": "codex_remote_key",
        "label": "Codex (remote)",
    },
    {
        "id": "gemini-remote",
        "type": "gemini",
        "key_flag": "gemini_remote_key",
        "label": "Gemini (remote)",
    },
]


def generate_key() -> str:
    return secrets.token_hex(32)


def build_identities(keys: dict[str, str]) -> dict[str, dict[str, str]]:
    identities: dict[str, dict[str, str]] = {}
    for agent in AGENTS:
        key = keys.get(agent["key_flag"])
        if key:
            identities[key] = {"agent_id": agent["id"], "agent_type": agent["type"]}
    return identities


def write_env_file(domain: str, keys: dict[str, str], output: Path) -> None:
    url = f"https://{domain}"
    lines = [
        "# Cloud coordinator configuration",
        f"# Generated for domain: {domain}",
        "#",
        "# Usage: source this file, or add to ~/.zshrc / ~/.bashrc",
        "",
        f'export COORDINATION_API_URL="{url}"',
        f'export COORDINATION_ALLOWED_HOSTS="{domain}"',
        f'export COORDINATOR_URL="{url}"',
        "",
    ]
    lines.append("# Per-agent keys (uncomment the one matching your agent)")
    for agent in AGENTS:
        key = keys.get(agent["key_flag"])
        if key:
            lines.append(f'# export COORDINATION_API_KEY="{key}"  # {agent["id"]}')
    local_claude_key = keys.get("claude_local_key", "")
    if local_claude_key:
        lines.append("")
        lines.append("# Default: local Claude Code CLI")
        lines.append(f'export COORDINATION_API_KEY="{local_claude_key}"')
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
    url = f"https://{domain}/health"
    print(f"\nVerifying: GET {url}")
    try:
        req = Request(url)
        if api_key:
            req.add_header("X-API-Key", api_key)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Cloud coordinator setup")
    parser.add_argument("--domain", required=True, help="Coordinator domain")
    parser.add_argument("--claude-local-key", help="Claude local CLI key (generated if omitted)")
    parser.add_argument("--codex-local-key", help="Codex local CLI key (generated if omitted)")
    parser.add_argument("--gemini-local-key", help="Gemini local CLI key (generated if omitted)")
    parser.add_argument("--claude-remote-key", help="Claude remote/web key (generated if omitted)")
    parser.add_argument("--codex-remote-key", help="Codex cloud key (generated if omitted)")
    parser.add_argument("--gemini-remote-key", help="Gemini cloud key (generated if omitted)")
    parser.add_argument("--railway", action="store_true", help="Push env vars to Railway")
    parser.add_argument("--railway-service", help="Railway service name (auto-detected if omitted)")
    parser.add_argument("--verify", action="store_true", help="Test /health after setup")
    parser.add_argument("--output", default=str(PROJECT_DIR / ".env.cloud"))
    args = parser.parse_args()

    use_railway = args.railway or args.railway_service is not None
    domain = args.domain.removeprefix("https://").removeprefix("http://").rstrip("/")

    keys = {
        "claude_local_key": args.claude_local_key or generate_key(),
        "codex_local_key": args.codex_local_key or generate_key(),
        "gemini_local_key": args.gemini_local_key or generate_key(),
        "claude_remote_key": args.claude_remote_key or generate_key(),
        "codex_remote_key": args.codex_remote_key or generate_key(),
        "gemini_remote_key": args.gemini_remote_key or generate_key(),
    }

    identities = build_identities(keys)
    all_keys = ",".join(keys[a["key_flag"]] for a in AGENTS if keys.get(a["key_flag"]))
    identities_json = json.dumps(identities, separators=(",", ":"))

    output_path = Path(args.output)
    write_env_file(domain, keys, output_path)

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
    for agent in AGENTS:
        key = keys.get(agent["key_flag"], "")
        flag = agent["key_flag"].replace("_", "-")
        src = "(provided)" if getattr(args, agent["key_flag"]) else "(generated)"
        print(f"   {agent['label']:<20s} {key[:12]}...  {src}")
        print(f"     --{flag} {key}")

    print("\n4. Install hooks: make hooks-setup")

    if args.verify:
        ok = verify_connectivity(domain, keys["claude_local_key"])
        print("\n[ok] Healthy" if ok else "\n[fail] Unreachable")
        if not ok:
            sys.exit(1)
    print()


if __name__ == "__main__":
    main()
