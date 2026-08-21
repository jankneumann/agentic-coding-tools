#!/usr/bin/env python3
"""Additively mint coordinator API keys for a new agent host.

Unlike ``setup_cloud.py``, which regenerates every key it is not handed and
overwrites ``COORDINATION_API_KEYS`` / ``COORDINATION_API_KEY_IDENTITIES``
wholesale, this script *reads* the current Railway values, appends new
per-agent keys, and refuses to run if any pre-existing key or identity would
be dropped. Use it when adding a second machine (e.g. the GX10 box) without
rotating the keys already in use elsewhere.

Agent type, profile name, and CLI command are derived from the matching
``<vendor>-local`` entry in ``agents.yaml`` — nothing about vendors is
hardcoded here beyond the shell alias spellings.

Outputs (nothing is applied without --apply):
  1. an env file for the new host (0600) with per-agent aliases
  2. a shell script of ``railway variable set`` commands (0600), so full key
     material never lands in your shell history
  3. a SQL migration assigning each new agent_id to its profile, creating any
     profile agents.yaml references but the DB never seeded

Usage:
    # dry run — writes the three artifacts, touches nothing remote
    python3 scripts/add_agent_keys.py --host-label gx10 --domain coord.rotkohl.ai

    # same, and push both variables to Railway
    python3 scripts/add_agent_keys.py --host-label gx10 --domain coord.rotkohl.ai --apply

    # offline: supply current Railway values from a file instead of calling the CLI
    railway variable list --service api --json > /tmp/vars.json
    python3 scripts/add_agent_keys.py --host-label gx10 --domain coord.rotkohl.ai \
        --from-json /tmp/vars.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
AGENTS_YAML = PROJECT_DIR / "agents.yaml"
MIGRATIONS_DIR = PROJECT_DIR / "database" / "migrations"

# Reuse the Railway plumbing rather than reimplementing it. sys.path[0] is
# this script's directory, so the sibling module imports directly.
from setup_cloud import (  # noqa: E402
    check_railway_cli,
    check_railway_linked,
    detect_api_service,
    find_railway_services,
    generate_key,
)

KEYS_VAR = "COORDINATION_API_KEYS"
IDENTITIES_VAR = "COORDINATION_API_KEY_IDENTITIES"

# Profile rows the migrations actually seed (007 + 019 renames). Anything
# agents.yaml references outside this set has to be created before it can be
# assigned — see build_migration().
SEEDED_PROFILES = {
    "claude_code_local",
    "claude_code_remote",
    "claude_code_reviewer",
    "codex_local",
    "codex_remote",
    "gemini_local",
    "gemini_remote",
    "strands_local",
}

# Template row cloned when creating a missing <vendor>_local profile. Trust
# level and the operation list come from the live row so the new profiles
# inherit whatever later migrations added to it (e.g. 022's merge-queue ops).
PROFILE_TEMPLATE = "claude_code_local"

# Alias spellings match those written by setup_cloud.py's alias_map.
ALIAS_OVERRIDES = {"claude": "ccc", "codex": "ccodex"}

# Placeholder that agents.yaml uses for keys resolved at runtime; such an
# entry carries no usable key material and is not a rotation candidate.
INTERPOLATION_RE = re.compile(r"\$\{[^}]+\}")


# -- agents.yaml -------------------------------------------------------------


class AgentSpec:
    """Identity and CLI shape for one vendor, derived from agents.yaml."""

    def __init__(self, vendor: str, entry: dict[str, Any], host_label: str) -> None:
        self.vendor = vendor
        self.agent_id = f"{vendor}-{host_label}"
        self.agent_type = entry["type"]
        self.profile = entry.get("profile") or f"{self.agent_type}_local"
        cli = entry.get("cli") or {}
        self.command = cli.get("command") or vendor
        self.alias = ALIAS_OVERRIDES.get(vendor, f"c{self.command}")
        self.description = entry.get("description") or f"{vendor} worker"


def load_local_agents(host_label: str, vendors: list[str] | None) -> list[AgentSpec]:
    """Read <vendor>-local entries from agents.yaml into AgentSpecs."""
    if not AGENTS_YAML.exists():
        sys.exit(f"ERROR: {AGENTS_YAML} not found")
    raw = yaml.safe_load(AGENTS_YAML.read_text()) or {}
    agents = raw.get("agents") or {}

    available = {
        name.removesuffix("-local"): entry
        for name, entry in agents.items()
        if name.endswith("-local") and isinstance(entry, dict)
    }
    if not available:
        sys.exit("ERROR: no '<vendor>-local' entries found in agents.yaml")

    selected = vendors or sorted(available)
    unknown = [v for v in selected if v not in available]
    if unknown:
        sys.exit(
            f"ERROR: unknown vendor(s) {', '.join(unknown)}. "
            f"Available: {', '.join(sorted(available))}"
        )
    return [AgentSpec(v, available[v], host_label) for v in selected]


# -- Reading current Railway state -------------------------------------------


def parse_variable_payload(payload: Any) -> dict[str, str]:
    """Normalize the shapes `railway variable list --json` has shipped.

    Accepts a flat {KEY: value} map, {KEY: {"value": ...}}, or a list of
    {"name"/"key", "value"} records. Anything else is a hard error rather
    than a silent empty dict — an empty dict here would look exactly like
    "no variables set yet" and cause this script to clobber them.
    """
    if isinstance(payload, dict):
        out: dict[str, str] = {}
        for key, value in payload.items():
            if isinstance(value, dict):
                out[key] = str(value.get("value", ""))
            else:
                out[key] = "" if value is None else str(value)
        return out
    if isinstance(payload, list):
        out = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("key")
            if name:
                out[str(name)] = str(item.get("value", ""))
        return out
    raise ValueError(f"unrecognized variable payload of type {type(payload).__name__}")


def resolve_service(explicit: str | None) -> str:
    if explicit:
        return explicit
    if not check_railway_cli():
        sys.exit("ERROR: Railway CLI unavailable. Pass --railway-service and --from-json.")
    status = check_railway_linked()
    if not status:
        sys.exit("ERROR: not linked to a Railway project. Run: railway link")
    service = detect_api_service(status)
    if service:
        print(f"  Auto-detected service: {service}")
        return service
    names = ", ".join(s["name"] for s in find_railway_services(status)) or "(none)"
    sys.exit(f"ERROR: could not auto-detect API service. Available: {names}")


def railway_list_variables(service: str, environment: str | None) -> dict[str, str]:
    cmd = ["railway", "variable", "list", "--service", service, "--json"]
    if environment:
        cmd += ["--environment", environment]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        sys.exit(f"ERROR: {' '.join(cmd)} failed:\n{result.stderr.strip()}")
    try:
        return parse_variable_payload(json.loads(result.stdout))
    except (json.JSONDecodeError, ValueError) as exc:
        sys.exit(f"ERROR: could not parse Railway variables: {exc}")


def railway_set_variable(name: str, value: str, service: str, environment: str | None) -> bool:
    cmd = ["railway", "variable", "set", f"{name}={value}", "--service", service]
    if environment:
        cmd += ["--environment", environment]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"  {name}: FAILED — {result.stderr.strip()}")
    return result.returncode == 0


# -- Merge -------------------------------------------------------------------


def read_current(variables: dict[str, str]) -> tuple[list[str], dict[str, dict[str, str]]]:
    raw_keys = variables.get(KEYS_VAR, "")
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

    raw_identities = variables.get(IDENTITIES_VAR, "").strip()
    identities: dict[str, dict[str, str]] = {}
    if raw_identities:
        try:
            parsed = json.loads(raw_identities)
        except json.JSONDecodeError as exc:
            sys.exit(
                f"ERROR: {IDENTITIES_VAR} on Railway is not valid JSON ({exc}). "
                "Refusing to overwrite a value I cannot round-trip."
            )
        if not isinstance(parsed, dict):
            sys.exit(f"ERROR: {IDENTITIES_VAR} is not a JSON object")
        identities = parsed
    return keys, identities


def merge(
    existing_keys: list[str],
    existing_identities: dict[str, dict[str, str]],
    specs: list[AgentSpec],
    allow_rotate: bool,
) -> tuple[dict[str, str], list[str], dict[str, dict[str, str]]]:
    """Mint one key per spec and fold it into the existing allowlist and map.

    Returns (spec.agent_id -> new key, merged key list, merged identity map).
    """
    claimed = {
        identity.get("agent_id"): key
        for key, identity in existing_identities.items()
        if isinstance(identity, dict) and identity.get("agent_id")
    }
    collisions = [s.agent_id for s in specs if s.agent_id in claimed]
    if collisions and not allow_rotate:
        sys.exit(
            "ERROR: these agent_ids already have keys: "
            + ", ".join(collisions)
            + "\n  Pick a different --host-label, or pass --rotate to replace them "
            "(the old keys stop working the moment Railway redeploys)."
        )

    merged_keys = list(existing_keys)
    merged_identities = dict(existing_identities)
    minted: dict[str, str] = {}

    for spec in specs:
        if spec.agent_id in claimed:
            stale = claimed[spec.agent_id]
            merged_identities.pop(stale, None)
            merged_keys = [k for k in merged_keys if k != stale]
            print(f"  rotating {spec.agent_id}: retiring {stale[:12]}...")
        key = generate_key()
        minted[spec.agent_id] = key
        merged_keys.append(key)
        merged_identities[key] = {"agent_id": spec.agent_id, "agent_type": spec.agent_type}

    verify_additive(existing_keys, existing_identities, merged_keys, merged_identities, specs)
    return minted, merged_keys, merged_identities


def verify_additive(
    existing_keys: list[str],
    existing_identities: dict[str, dict[str, str]],
    merged_keys: list[str],
    merged_identities: dict[str, dict[str, str]],
    specs: list[AgentSpec],
) -> None:
    """Fail loud if the merge dropped or altered anything it should not have.

    This is the whole point of the script, so it is an assertion rather than a
    comment: a silently-truncated allowlist locks every other machine out of
    the coordinator, and the symptom (401 on every write) shows up far from
    the cause.
    """
    rotated = {s.agent_id for s in specs}
    surviving = set(merged_keys)

    for key in existing_keys:
        identity = existing_identities.get(key, {})
        if identity.get("agent_id") in rotated:
            continue  # deliberately retired above
        if key not in surviving:
            sys.exit(f"ABORT: merge would drop existing key {key[:12]}... — refusing to write")

    for key, identity in existing_identities.items():
        if identity.get("agent_id") in rotated:
            continue
        if merged_identities.get(key) != identity:
            sys.exit(f"ABORT: merge would alter identity for {key[:12]}... — refusing to write")

    if len(merged_keys) != len(set(merged_keys)):
        sys.exit("ABORT: merged key list contains duplicates")


# -- Artifacts ---------------------------------------------------------------


def write_secure(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o600)


def build_env_file(
    domain: str, host_label: str, specs: list[AgentSpec], minted: dict[str, str]
) -> str:
    default_spec = next((s for s in specs if s.vendor == "claude"), specs[0])
    lines = [
        f"# Coordinator configuration for host: {host_label}",
        f"# Generated by scripts/add_agent_keys.py for domain: {domain}",
        "#",
        "# Copy to the target host and source it from ~/.zshrc / ~/.bashrc.",
        "# Contains live key material — keep mode 0600, never commit.",
        "",
        "# -- Shared coordinator settings --",
        f'export COORDINATION_API_URL="https://{domain}"',
        f'export COORDINATION_ALLOWED_HOSTS="{domain}"',
        "",
        "# -- Cloudflare Access service token (edge auth) --",
        "# Required when the coordinator sits behind a Cloudflare Access",
        "# application: the API key authenticates at the origin, but the edge",
        "# rejects the request before it ever gets there. Check with:",
        f"#   curl -s -D - -o /dev/null https://{domain}/health",
        "# Look at the response HEADERS, not the status: 'server: cloudflare' plus a",
        "# 302 to *.cloudflareaccess.com => a service token is needed. 'server:",
        "# railway-hikari' => the request reaches the origin directly, nothing to do.",
        "# Do not use 'curl -I' here — that sends HEAD, and /health is registered",
        "# GET-only, so it answers 405 regardless of what sits in front of it.",
        "# Create a service token in Zero Trust > Access > Service Tokens.",
        '# export CF_ACCESS_CLIENT_ID="<client-id>.access"',
        '# export CF_ACCESS_CLIENT_SECRET="<client-secret>"',
        "",
        f"# -- Default key ({default_spec.agent_id}) --",
        f'export COORDINATION_API_KEY="{minted[default_spec.agent_id]}"',
        "",
        "# -- CLI aliases (launch each vendor under its own coordinator identity) --",
    ]
    for spec in specs:
        lines.append(
            f"alias {spec.alias}='COORDINATION_API_KEY=\"{minted[spec.agent_id]}\" "
            f"{spec.command}'  # {spec.agent_id}"
        )
    lines.append("")
    return "\n".join(lines)


def build_railway_script(
    service: str,
    environment: str | None,
    merged_keys: list[str],
    merged_identities: dict[str, dict[str, str]],
) -> str:
    env_flag = f" --environment {environment}" if environment else ""
    keys_csv = ",".join(merged_keys)
    identities_json = json.dumps(merged_identities, separators=(",", ":"), sort_keys=True)
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "# Generated by scripts/add_agent_keys.py — contains live key material.",
            "# Run once, then delete. Each 'set' triggers a Railway redeploy.",
            "set -euo pipefail",
            "",
            f"railway variable set '{KEYS_VAR}={keys_csv}' "
            f"--service {service}{env_flag}",
            "",
            f"railway variable set '{IDENTITIES_VAR}={identities_json}' "
            f"--service {service}{env_flag}",
            "",
        ]
    )


def next_migration_number() -> int:
    highest = 0
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = re.match(r"(\d+)_", path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def build_migration(number: int, host_label: str, specs: list[AgentSpec]) -> str:
    missing = sorted({s.profile for s in specs if s.profile not in SEEDED_PROFILES})

    lines = [
        f"-- Migration {number:03d}: profile assignments for the '{host_label}' host",
        "-- Dependencies: 007_agent_profiles.sql, 018_agent_profile_assignments.sql,",
        "--               019_standardize_profile_names.sql",
        "--",
        "-- get_profile() resolves an explicit agent_id assignment first and only",
        "-- then falls back to a type-based default (src/profiles.py:104). A new",
        "-- agent_id with no assignment therefore inherits whichever profile happens",
        "-- to sort first for its agent_type — the exact drift migration 018 was",
        "-- written to eliminate. Every agent_id in COORDINATION_API_KEY_IDENTITIES",
        "-- needs a row here.",
        "",
        "-- Fail loud rather than silently inserting nothing if the template row is",
        "-- absent: every INSERT below is a SELECT-driven copy, and a missing source",
        "-- row would make them all no-ops that still report success.",
        "DO $$",
        "BEGIN",
        "    IF NOT EXISTS (",
        f"        SELECT 1 FROM agent_profiles WHERE name = '{PROFILE_TEMPLATE}'",
        "    ) THEN",
        f"        RAISE EXCEPTION 'template profile {PROFILE_TEMPLATE} missing — "
        "apply migrations 007 and 019 first';",
        "    END IF;",
        "END $$;",
        "",
    ]

    if missing:
        lines += [
            "-- =============================================================================",
            "-- Create profiles agents.yaml references but no migration ever seeded",
            "-- =============================================================================",
            "-- agents.yaml names these under `profile:`, but 007/018/019 only seeded the",
            "-- claude_code_*, codex_*, gemini_* and strands_* rows. Cloned from",
            f"-- {PROFILE_TEMPLATE} so they inherit trust level and the operation list as",
            "-- later migrations extended it (e.g. 022's merge-queue operations), instead",
            "-- of pinning a copy that drifts.",
            "",
        ]
        for profile in missing:
            spec = next(s for s in specs if s.profile == profile)
            lines += [
                "INSERT INTO agent_profiles (",
                "    name, description, agent_type, trust_level,",
                "    allowed_operations, blocked_operations, max_file_modifications,",
                "    max_execution_time_seconds, max_api_calls_per_hour",
                ")",
                "SELECT",
                f"    '{profile}',",
                f"    'Local {spec.vendor} worker with full coordination access',",
                f"    '{spec.agent_type}',",
                "    trust_level, allowed_operations, blocked_operations,",
                "    max_file_modifications, max_execution_time_seconds, max_api_calls_per_hour",
                f"FROM agent_profiles WHERE name = '{PROFILE_TEMPLATE}'",
                "ON CONFLICT (name) DO NOTHING;",
                "",
            ]

    lines += [
        "-- =============================================================================",
        f"-- Assign each {host_label} agent_id to its profile",
        "-- =============================================================================",
        "",
    ]
    for spec in specs:
        lines += [
            "INSERT INTO agent_profile_assignments (agent_id, profile_id, assigned_by)",
            f"SELECT '{spec.agent_id}', id, 'add_agent_keys.py'",
            f"    FROM agent_profiles WHERE name = '{spec.profile}'",
            "ON CONFLICT (agent_id) DO UPDATE",
            "    SET profile_id = EXCLUDED.profile_id, assigned_at = now();",
            "",
        ]

    agent_id_list = ", ".join(f"'{s.agent_id}'" for s in specs)
    lines += [
        "-- =============================================================================",
        "-- Verify: every agent_id above resolved to a profile",
        "-- =============================================================================",
        "DO $$",
        "DECLARE",
        "    missing_count INT;",
        "BEGIN",
        "    SELECT count(*) INTO missing_count",
        f"    FROM unnest(ARRAY[{agent_id_list}]) AS expected(agent_id)",
        "    WHERE NOT EXISTS (",
        "        SELECT 1 FROM agent_profile_assignments a",
        "        WHERE a.agent_id = expected.agent_id",
        "    );",
        "    IF missing_count > 0 THEN",
        "        RAISE EXCEPTION",
        f"            '% of {len(specs)} {host_label} agents have no profile assignment',",
        "            missing_count;",
        "    END IF;",
        "END $$;",
        "",
    ]
    return "\n".join(lines)


# -- Main --------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Additively mint coordinator API keys for a new agent host",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host-label", required=True,
        help="Host suffix for agent ids, e.g. 'gx10' -> claude-gx10, codex-gx10",
    )
    parser.add_argument("--domain", required=True, help="Coordinator domain, e.g. coord.rotkohl.ai")
    parser.add_argument(
        "--vendors",
        help="Comma-separated vendors (default: every <vendor>-local in agents.yaml)",
    )
    parser.add_argument("--railway-service", help="Railway service name (auto-detected if omitted)")
    parser.add_argument("--environment", help="Railway environment (default: linked environment)")
    parser.add_argument(
        "--from-json",
        help="Read current Railway variables from this JSON file instead of calling the CLI",
    )
    parser.add_argument("--apply", action="store_true", help="Push merged variables to Railway")
    parser.add_argument(
        "--rotate", action="store_true",
        help="Replace keys for agent_ids that already exist (they stop working immediately)",
    )
    parser.add_argument("--env-output", help="Path for the host env file")
    parser.add_argument("--railway-output", help="Path for the railway-set shell script")
    parser.add_argument("--migration-output", help="Path for the SQL migration")
    args = parser.parse_args()

    host_label = args.host_label.strip().strip("-")
    if not host_label:
        sys.exit("ERROR: --host-label must not be empty")
    domain = args.domain.removeprefix("https://").removeprefix("http://").rstrip("/")
    vendors = [v.strip() for v in args.vendors.split(",") if v.strip()] if args.vendors else None

    specs = load_local_agents(host_label, vendors)

    print("=" * 70)
    print(f"Add coordinator keys for host '{host_label}'")
    print("=" * 70)

    print("\n1. Current Railway state")
    if args.from_json:
        payload = json.loads(Path(args.from_json).read_text())
        variables = parse_variable_payload(payload)
        service = args.railway_service or "<service>"
        print(f"   Read from {args.from_json}")
    else:
        service = resolve_service(args.railway_service)
        variables = railway_list_variables(service, args.environment)
    existing_keys, existing_identities = read_current(variables)
    print(f"   {KEYS_VAR}: {len(existing_keys)} key(s)")
    print(f"   {IDENTITIES_VAR}: {len(existing_identities)} identity/identities")
    for key, identity in sorted(existing_identities.items(), key=lambda kv: str(kv[1])):
        print(f"     {key[:12]}...  {identity.get('agent_id')} ({identity.get('agent_type')})")

    unmapped = [k for k in existing_keys if k not in existing_identities]
    if unmapped:
        print(
            f"   NOTE: {len(unmapped)} key(s) are in {KEYS_VAR} with no identity entry — "
            "they authenticate as agent_id=None. Preserved as-is."
        )

    print("\n2. Minting keys")
    minted, merged_keys, merged_identities = merge(
        existing_keys, existing_identities, specs, args.rotate
    )
    for spec in specs:
        print(
            f"   {spec.agent_id:<22s} {minted[spec.agent_id][:12]}...  "
            f"type={spec.agent_type} profile={spec.profile}"
        )
    print(f"   merged: {len(merged_keys)} key(s), {len(merged_identities)} identity/identities")

    env_path = Path(args.env_output or PROJECT_DIR / f".env.{host_label}")
    railway_path = Path(args.railway_output or PROJECT_DIR / f".railway-vars.{host_label}.sh")
    number = next_migration_number()
    migration_path = Path(
        args.migration_output
        or MIGRATIONS_DIR / f"{number:03d}_{host_label}_agent_profile_assignments.sql"
    )

    print("\n3. Artifacts")
    write_secure(env_path, build_env_file(domain, host_label, specs, minted))
    print(f"   {env_path}  (0600 — copy to the {host_label} host, then source it)")

    write_secure(
        railway_path,
        build_railway_script(service, args.environment, merged_keys, merged_identities),
    )
    print(f"   {railway_path}  (0600 — run once, then delete)")

    migration_path.write_text(build_migration(number, host_label, specs))
    print(f"   {migration_path}")

    print("\n4. Railway")
    if args.apply:
        if args.from_json and not args.railway_service:
            sys.exit("ERROR: --apply with --from-json also needs --railway-service")
        ok = True
        for name, value in [
            (KEYS_VAR, ",".join(merged_keys)),
            (IDENTITIES_VAR, json.dumps(merged_identities, separators=(",", ":"), sort_keys=True)),
        ]:
            pushed = railway_set_variable(name, value, service, args.environment)
            print(f"   {name}: {'ok' if pushed else 'FAILED'}")
            ok = ok and pushed
        if not ok:
            sys.exit(1)
        print(f"   Set on '{service}'. The service redeploys automatically.")
    else:
        print(f"   Dry run — nothing pushed. To apply:  bash {railway_path}")
        print("   (or re-run this script with --apply)")

    print("\n5. Next steps")
    print(f"   a. Apply the migration to the coordinator DB: {migration_path.name}")
    print(f"   b. Copy {env_path.name} to the {host_label} host and source it")
    print("   c. Verify from that host — this round-trips key -> identity -> profile:")
    print(f'      curl -H "X-API-Key: $COORDINATION_API_KEY" https://{domain}/profiles/me')
    print()


if __name__ == "__main__":
    main()
