---
name: setup-coordinator
description: Configure and verify coordinator access for CLI MCP and Web/Cloud HTTP runtimes
category: Coordination
tags: [coordinator, mcp, http, setup, parity]
triggers:
  - "setup coordinator"
  - "configure coordinator"
  - "coordinator setup"
  - "enable coordination"
  - "verify coordinator"
---

# Setup Coordinator

Configure coordinator access for local and cloud agent runtimes, verify capability detection, and capture fallback expectations.

## Transport Model

The coordinator has two transports — **MCP (stdio)** and **HTTP** — both backed by the same service layer and shared Postgres database. Coordination happens at the database level, not the transport level.

| Scenario | Transport | Database |
|----------|-----------|----------|
| Local (solo or multi-agent) | MCP (stdio) → direct Postgres | Local ParadeDB |
| Cloud agents | HTTP → Coordination API | Railway Postgres |
| Cross-environment (local + cloud) | Local: HTTP bridge, Cloud: HTTP | Railway Postgres |

For local development, multiple CLI agents (Claude, Codex) each spawn their own MCP server process, all connecting to the same local ParadeDB. No cloud infrastructure needed.

For cross-environment coordination, local agents switch to the HTTP transport via `coordination_bridge.py` so the database is not publicly exposed.

## Arguments

`$ARGUMENTS` - Optional flags:

- `--profile <local|railway>` (default: read from `COORDINATOR_PROFILE` env var, fallback `local`)
- `--mode <auto|cli|web>` (default: `auto`)
- `--http-url <url>` (for HTTP verification)
- `--api-key <key>` (for HTTP verification)
- `--coordinator-dir <path>` (optional external coordinator checkout for local
  MCP setup; fallback `COORDINATOR_DIR`)

Resolve `<skill-base-dir>` to the directory containing this loaded `SKILL.md`.
The HTTP path is fully portable and requires only the co-installed
`coordination-bridge` sibling. Local MCP registration is optional and requires
an explicitly configured external coordinator checkout; this skill never
assumes that `agent-coordinator/` was bundled into a consumer repository.

## Objectives

- Load deployment profile (`local` or `railway`) and apply configuration
- Register MCP server with CLI agents (Claude Code, Codex CLI)
- Configure HTTP access for cloud agents and cross-environment coordination
- Read `agents.yaml` to determine which agents to configure
- Verify capability detection contract used by integrated skills
- Confirm graceful standalone fallback when coordinator is unavailable

## Steps

### 1. Determine Profile and Setup Mode

```bash
PROFILE=local   # Parse --profile from $ARGUMENTS, or read COORDINATOR_PROFILE env var
MODE=auto       # Parse --mode from $ARGUMENTS when provided
```

- Profiles: `local` (MCP + Docker), `railway` (HTTP + cloud)
- Modes: `auto` (run both CLI and Web checks), `cli` (MCP only), `web` (HTTP only)

### 1a. Load Profile and Check Secrets

```bash
# Local source is required only when CLI/MCP checks are selected. Web mode is
# independently runnable from an installed skill through the public HTTP API.
COORDINATOR_DIR="${COORDINATOR_DIR:-}"
if [ "$MODE" != "web" ]; then
  if [ -z "$COORDINATOR_DIR" ] || [ ! -d "$COORDINATOR_DIR" ]; then
    echo "Local MCP setup requires --coordinator-dir or COORDINATOR_DIR." >&2
    echo "Use --mode web with COORDINATION_API_URL for a source-free setup." >&2
    exit 2
  fi

  if [ ! -f "$COORDINATOR_DIR/.secrets.yaml" ]; then
    cp "$COORDINATOR_DIR/.secrets.yaml.example" "$COORDINATOR_DIR/.secrets.yaml"
    echo "Created .secrets.yaml from template — fill in real values before continuing."
  fi
elif [ -z "${COORDINATION_API_URL:-}" ]; then
  echo "Web setup requires COORDINATION_API_URL." >&2
  exit 2
fi

# Profile loading happens automatically via config.py when COORDINATOR_PROFILE is set
export COORDINATOR_PROFILE="$PROFILE"
```

Read `agents.yaml` to determine which agents need configuration:

- **MCP agents** (transport: mcp): generate vendor-specific MCP config via `get_mcp_env(agent_id)`
- **Keyed agents** (any agent declaring `api_key`): derive `COORDINATION_API_KEY_IDENTITIES` via `get_api_key_identities()`. This is not restricted to `transport: http` — local harnesses hold coordinator keys too, for the session hooks, the `http_proxy` fallback, and hosted-coordinator deployments where every agent talks HTTP

### 2. Validate Coordinator Runtime Prerequisites

#### Local profile

```bash
# The coordinator checkout owns its compose contract. Invoke it through its
# public deployment surface instead of importing private src modules.
docker compose --project-directory "$COORDINATOR_DIR" \
  -f "$COORDINATOR_DIR/docker-compose.yml" up -d

# Coordinator API health
curl -s "http://localhost:${API_PORT:-8081}/health"
```

#### Railway profile

```bash
# Verify COORDINATION_API_URL resolves (from profile + secrets)
curl -s "$COORDINATION_API_URL/health"

# Bridge-level detection (HTTP contract)
python3 "<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py" detect
```

If health fails, fix the explicitly configured external runtime first (for
example, run its documented compose/API startup with `DB_BACKEND=postgres`).

### 3. CLI Path (MCP) Setup and Verification

Run this section when mode is `auto` or `cli`.

#### 3a. Register MCP server with CLI agents

Use the explicitly configured coordinator checkout's public setup targets to
register with each CLI's native `mcp add` command:

```bash
# Register with all CLI agents at once
make -C "$COORDINATOR_DIR" mcp-setup

# Or register individually:
make -C "$COORDINATOR_DIR" claude-mcp-setup
make -C "$COORDINATOR_DIR" codex-mcp-setup
```

Each target registers the coordination MCP server with:
- Absolute path to the venv Python binary (`.venv/bin/python -m src.coordination_mcp`)
- `DB_BACKEND=postgres` and `POSTGRES_DSN` pointing to local ParadeDB
- Provider-specific identity by default:
  - Claude Code: `AGENT_ID=claude-code-1`, `AGENT_TYPE=claude_code`
  - Codex CLI: `AGENT_ID=codex-1`, `AGENT_TYPE=codex`
- `COORDINATION_API_URL` and `COORDINATION_API_KEY` (optional) — enables HTTP proxy fallback when the local DB is unavailable
- Claude Code also gets `cwd` via `add-json` (Codex doesn't need it — all file lookups use `Path(__file__)`)

Pass `AGENT_ID=... AGENT_TYPE=...` to preserve the old behavior of using one
identity for every target, or pass `CLAUDE_AGENT_ID` or `CODEX_AGENT_ID` to
override one provider only.

Restart each CLI after registration to activate.

**HTTP proxy fallback**: When `POSTGRES_DSN` is unreachable at startup and `COORDINATION_API_URL` is set to a reachable coordinator (e.g., `https://coord.rotkohl.ai`), the MCP server automatically proxies tool calls through the HTTP API instead of the local database. Set `COORDINATION_ALLOWED_HOSTS` to allow remote hosts (e.g., `coord.rotkohl.ai`) past the SSRF allowlist. See `src/http_proxy.py` for details.

#### 3a.1. Install lifecycle hooks (status reporting & notifications)

Lifecycle hooks auto-register agents on session start, report status after each turn (heartbeat), and deregister on exit. They install at **user scope** so they work from any repo:

```bash
# Install for all agents at once
make -C "$COORDINATOR_DIR" hooks-setup

# Or individually:
make -C "$COORDINATOR_DIR" claude-hooks-setup
make -C "$COORDINATOR_DIR" codex-hooks-setup
```

**How each agent gets lifecycle integration:**

| Agent | Mechanism | Events |
|-------|-----------|--------|
| Claude Code | `~/.claude/settings.json` | SessionStart, Stop, SubagentStop, SessionEnd |
| Codex CLI | `~/.codex/hooks.json` | SessionStart, Stop |

Hook scripts use absolute paths under `$COORDINATOR_DIR/scripts/`, so they
resolve correctly regardless of the current working directory.
The installed Claude and Codex commands do not set `AGENT_ID`, `AGENT_TYPE`,
`COORDINATION_API_URL`, or `COORDINATION_API_KEY` inline. They inherit
`COORDINATION_API_URL` and `COORDINATION_API_KEY` from the current run
environment, and the coordinator resolves `agent_id` / `agent_type` from the
API-key identity mapping when the key is bound in server config.

#### 3a.2. Configure notifications (optional)

To receive push notifications (approvals, escalations, stale agents) set:

```bash
export NOTIFICATION_CHANNELS=gmail    # gmail, telegram, webhook (comma-separated)
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=you@gmail.com
export SMTP_PASSWORD=your-app-password
export NOTIFICATION_RECIPIENT_EMAIL=you@gmail.com
export NOTIFICATION_ALLOWED_SENDERS=you@gmail.com
```

Reply to notification emails to approve/deny, unblock escalations, or inject guidance. Omit `NOTIFICATION_CHANNELS` to disable.

#### 3b. Allow-list coordination tools in Claude Code permissions

After MCP registration, ensure all coordination tools are allow-listed so they don't trigger permission prompts during workflow execution:

```bash
# Check if mcp__coordination__* is already in settings.local.json
SETTINGS_FILE=".claude/settings.local.json"

if ! grep -q 'mcp__coordination__\*' "$SETTINGS_FILE" 2>/dev/null; then
  # Add the wildcard permission using python3 for safe JSON manipulation
  python3 -c "
import json, pathlib
p = pathlib.Path('$SETTINGS_FILE')
settings = json.loads(p.read_text()) if p.exists() else {}
perms = settings.setdefault('permissions', {}).setdefault('allow', [])
# Remove any individual mcp__coordination__ entries
perms[:] = [e for e in perms if not e.startswith('mcp__coordination__') or e == 'mcp__coordination__*']
perms.append('mcp__coordination__*')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(settings, indent=2) + '\n')
print('Added mcp__coordination__* to permissions allow-list')
"
else
  echo "mcp__coordination__* already in permissions"
fi
```

This replaces any individual coordination tool entries (e.g., `mcp__coordination__submit_work`) with the single wildcard `mcp__coordination__*`.

#### 3c. Verify MCP capabilities

Verify the MCP server is connected in each CLI:

```bash
claude mcp list   # Should show: coordination → ✓ Connected
codex mcp list    # Should show: coordination → enabled
```

Verify tool discovery includes coordinator tools:

- `acquire_lock`, `release_lock`
- `submit_work`, `get_work`, `complete_work`
- `write_handoff`, `read_handoff`
- `remember`, `recall`
- `check_guardrails`

Expected detection result in integrated skills:

- `COORDINATION_TRANSPORT=mcp`
- `COORDINATOR_AVAILABLE=true`
- `CAN_*` flags reflect discovered MCP tools

### 4. HTTP Path Setup and Verification

Run this section when mode is `auto` or `web`, or when local agents need to coordinate with cloud agents.

#### 4a. When to use HTTP

- **Cloud/web agents** that cannot run MCP stdio processes
- **Cross-environment coordination** where local and cloud agents share state — local agents switch to HTTP via `coordination_bridge.py` so the database is not publicly exposed

For local-only multi-agent coordination, MCP is sufficient — all agents connect to the same local ParadeDB.

#### 4b. Configure HTTP access

Set runtime secrets/env:

```bash
export COORDINATION_API_URL="https://your-app.railway.app"
export COORDINATION_API_KEY="<your-provisioned-api-key>"
# Allow Railway hosts in SSRF filter
export COORDINATION_ALLOWED_HOSTS="your-app.railway.app,your-app-production.up.railway.app"
```

Verify detection and capability flags:

```bash
curl -s "$COORDINATION_API_URL/health"
# Expected: {"status": "ok", "db": "connected", "version": "0.2.0"}

python3 "<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py" detect \
  --http-url "$COORDINATION_API_URL" \
  --api-key "$COORDINATION_API_KEY"
```

Expected detection result in integrated skills:

- `COORDINATION_TRANSPORT=http`
- `COORDINATOR_AVAILABLE=true`
- `CAN_*` flags reflect reachable HTTP endpoints for that credential scope

If only some endpoints are available, keep `COORDINATOR_AVAILABLE=true` and set missing capabilities to `false`.

For server deployment details, consult
`$COORDINATOR_DIR/docs/cloud-deployment.md` in the explicitly configured
external coordinator checkout.

### 5. Capability Summary and Hook Expectations

For the active runtime, summarize:

- Transport: `mcp`, `http`, or `none`
- Capability flags: `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`
- Which hooks will activate in each workflow skill

Hook activation rule:

- A hook runs only when its `CAN_*` flag is true.

### 6. Fallback and Troubleshooting

If setup fails (connectivity, auth, policy, or missing tools/endpoints):

- Report exact failing step and error
- Keep skill workflow in standalone mode (`COORDINATOR_AVAILABLE=false`, `COORDINATION_TRANSPORT=none`)
- Do not block feature workflow execution on coordinator setup failure

Common checks:

- API key validity (`X-API-Key` acceptance on write endpoints)
- Runtime network allowlist / egress restrictions
- MCP server process and env variables
- Coordinator `/health` reachability
- Railway health check failing: verify `POSTGRES_DSN` uses private network URL
- SSRF blocking cloud URL: add hostname to `COORDINATION_ALLOWED_HOSTS`
- API key rejected: verify `COORDINATION_API_KEYS` on server matches client key

## Profile Configuration

An external coordinator checkout uses YAML deployment profiles under
`$COORDINATOR_DIR/profiles/`, with inheritance and `${VAR}` secret
interpolation from `$COORDINATOR_DIR/.secrets.yaml`. Existing environment
variables win.

- `local.yaml`: MCP transport, Docker auto-start, ParadeDB on localhost
- `railway.yaml`: HTTP transport, Railway cloud deployment
- `base.yaml`: Shared defaults inherited by both

Agent identity is declared by `AGENTS_YAML` when set, otherwise by
`$COORDINATOR_DIR/agents.yaml` for explicitly configured local setup.

## Backend Note

Cloud deployment may use Railway with ParadeDB Postgres. Its deployment files
belong to the external coordinator service, not this installed skill. Use
`COORDINATION_API_URL` and `COORDINATION_API_KEY` to consume that service.

## Output

- Mode executed (`cli`, `web`, or both)
- Per-runtime verification summary (transport + capability flags)
- Failure diagnostics and remediation steps (if any)
- Standalone fallback confirmation when coordinator is unavailable
