#!/usr/bin/env python3
"""Generate cloud coordinator configuration for all agent environments.

Creates a .env.cloud file with local agent env vars and prints the
Railway service env vars that must be set in the dashboard.

Usage:
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com
    python3 scripts/setup_cloud.py --domain your-app.railway.app --verify
    python3 scripts/setup_cloud.py --domain coord.yourdomain.com \\
        --claude-key <key> --codex-key <key>

Then:
    source .env.cloud   # activate in current shell
    # or add to ~/.zshrc / ~/.bashrc for persistence
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

# Agent definitions: id, type, key-env-name
AGENTS = [
    {
        "id": "claude-remote", "type": "claude_code",
        "key_flag": "claude_key", "label": "Claude Code",
    },
    {"id": "codex-remote", "type": "codex", "key_flag": "codex_key", "label": "Codex"},
    {"id": "gemini-remote", "type": "gemini", "key_flag": "gemini_key", "label": "Gemini"},
]


def generate_key() -> str:
    """Generate a 32-byte hex API key."""
    return secrets.token_hex(32)


def build_identities(keys: dict[str, str]) -> dict[str, dict[str, str]]:
    """Build COORDINATION_API_KEY_IDENTITIES JSON from agent keys."""
    identities = {}
    for agent in AGENTS:
        key = keys.get(agent["key_flag"])
        if key:
            identities[key] = {"agent_id": agent["id"], "agent_type": agent["type"]}
    return identities


def write_env_file(domain: str, keys: dict[str, str], output: Path) -> None:
    """Write .env.cloud with shell-exportable variables."""
    url = f"https://{domain}"

    lines = [
        "# Cloud coordinator configuration",
        f"# Generated for domain: {domain}",
        "#",
        "# Usage: source this file, or add to ~/.zshrc / ~/.bashrc",
        "",
        "# Coordinator URL (used by coordination bridge and skills)",
        f'export COORDINATION_API_URL="{url}"',
        "",
        "# SSRF allowlist (required for coordination bridge)",
        f'export COORDINATION_ALLOWED_HOSTS="{domain}"',
        "",
        "# Alias used by report_status.py hook",
        f'export COORDINATOR_URL="{url}"',
        "",
    ]

    # Per-agent keys — the user picks which one to activate
    for agent in AGENTS:
        key = keys.get(agent["key_flag"])
        if key:
            lines.append(f"# {agent['label']} API key")
            lines.append(f"# export COORDINATION_API_KEY=\"{key}\"  # {agent['id']}")
            lines.append("")

    # Default to claude key
    claude_key = keys.get("claude_key", "")
    if claude_key:
        lines.append("# Active API key (uncomment the agent you're running as)")
        lines.append(f'export COORDINATION_API_KEY="{claude_key}"')
        lines.append("")

    output.write_text("\n".join(lines) + "\n")


def verify_connectivity(domain: str, api_key: str | None = None) -> bool:
    """Test /health endpoint on the coordinator."""
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate cloud coordinator config for all agent environments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--domain", required=True,
        help="Custom domain or Railway URL (e.g., coord.yourdomain.com)",
    )
    parser.add_argument("--claude-key", help="Claude Code API key (generated if omitted)")
    parser.add_argument("--codex-key", help="Codex API key (generated if omitted)")
    parser.add_argument("--gemini-key", help="Gemini API key (generated if omitted)")
    parser.add_argument(
        "--verify", action="store_true",
        help="Test /health after generating config",
    )
    parser.add_argument(
        "--output", default=str(PROJECT_DIR / ".env.cloud"),
        help="Output file path (default: agent-coordinator/.env.cloud)",
    )
    args = parser.parse_args()

    # Strip scheme if provided
    domain = args.domain.removeprefix("https://").removeprefix("http://").rstrip("/")

    # Resolve or generate keys
    keys = {
        "claude_key": args.claude_key or generate_key(),
        "codex_key": args.codex_key or generate_key(),
        "gemini_key": args.gemini_key or generate_key(),
    }

    # Build identity mapping
    identities = build_identities(keys)
    all_keys = ",".join(k for k in [keys["claude_key"], keys["codex_key"], keys["gemini_key"]] if k)

    # Write local env file
    output_path = Path(args.output)
    write_env_file(domain, keys, output_path)

    # Print results
    print("=" * 70)
    print("Cloud Coordinator Setup")
    print("=" * 70)

    print(f"\n1. Local env file written to: {output_path}")
    print(f"   Activate: source {output_path}")
    print("   Persist: add 'source' line to ~/.zshrc or ~/.bashrc")

    print("\n2. Railway service environment variables (set in dashboard):")
    print("   " + "-" * 60)
    print(f"   COORDINATION_API_KEYS={all_keys}")
    print("")
    identities_json = json.dumps(identities, separators=(",", ":"))
    print(f"   COORDINATION_API_KEY_IDENTITIES={identities_json}")
    print("   " + "-" * 60)

    print("\n3. Per-agent API keys:")
    for agent in AGENTS:
        key = keys.get(agent["key_flag"], "")
        provided = getattr(
            args, agent["key_flag"].replace("_key", "_key"), None,
        )
        generated = "(provided)" if provided else "(generated)"
        print(f"   {agent['label']:15s} ({agent['id']}): {key[:12]}... {generated}")

    print("\n4. Install lifecycle hooks (from agent-coordinator/):")
    print("   make hooks-setup")

    if args.verify:
        ok = verify_connectivity(domain, keys["claude_key"])
        if ok:
            print("\n✓ Coordinator is reachable and healthy")
        else:
            print("\n✗ Could not reach coordinator — check domain and deployment")
            sys.exit(1)

    print()


if __name__ == "__main__":
    main()
