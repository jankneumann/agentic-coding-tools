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

For local development, multiple CLI agents (Claude, Codex, Gemini) each spawn their own MCP server process, all connecting to the same local ParadeDB. No cloud infrastructure needed.

For cross-environment coordination, local agents switch to the HTTP transport via `coordination_bridge.py` so the database is not publicly exposed.

## Arguments

`$ARGUMENTS` - Optional flags:

- `--profile <local|railway>` (default: read from `COORDINATOR_PROFILE` env var, fallback `local`)
- `--mode <auto|cli|web>` (default: `auto`)
- `--http-url <url>` (for HTTP verification)
- `--api-key <key>` (for HTTP verification)

## Objectives

- Load deployment profile (`local` or `railway`) and apply configuration
- Register MCP server with CLI agents (Claude Code, Codex CLI, Gemini CLI)
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
cd agent-coordinator

# Check for .secrets.yaml — copy from template if missing
if [ ! -f .secrets.yaml ]; then
  cp .secrets.yaml.example .secrets.yaml
  echo "Created .secrets.yaml from template — fill in real values before continuing."
fi

# Profile loading happens automatically via config.py when COORDINATOR_PROFILE is set
export COORDINATOR_PROFILE="$PROFILE"
```

Read `agents.yaml` to determine which agents need configuration:

- **MCP agents** (transport: mcp): generate vendor-specific MCP config via `get_mcp_env(agent_id)`
- **HTTP agents** (transport: http): derive `COORDINATION_API_KEY_IDENTITIES` via `get_api_key_identities()`

### 2. Validate Coordinator Runtime Prerequisites

#### Local profile

```bash
# Auto-start ParadeDB container if docker.auto_start is true in profile
# The docker_manager module handles: detect runtime → start container → health wait
cd agent-coordinator
python3 -c "
from src.docker_manager import start_container, wait_for_healthy
from src.profile_loader import load_profile
profile = load_profile('$PROFILE')
docker_cfg = profile.get('docker', {})
result = start_container(docker_cfg)
print(result)
if result.get('started') or result.get('already_running'):
    runtime = result.get('runtime', 'docker')
    name = docker_cfg.get('container_name', 'paradedb')
    healthy = wait_for_healthy(runtime, name)
    print(f'Healthy: {healthy}')
"

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

If health fails, fix runtime first (start `docker compose up -d` in `agent-coordinator/` for ParadeDB Postgres, then run the API with `DB_BACKEND=postgres`).

### 3. CLI Path (MCP) Setup and Verification

Run this section when mode is `auto` or `cli`.

#### 3a. Register MCP server with CLI agents

Use the Makefile targets to register with each CLI's native `mcp add` command:

```bash
cd agent-coordinator

# Register with all CLI agents at once
make mcp-setup

# Or register individually:
make claude-mcp-setup   # claude mcp add-json --scope user
make codex-mcp-setup    # codex mcp add --env ...
make gemini-mcp-setup   # gemini mcp add --scope user --env ...
```

Each target registers the coordination MCP server with:
- Absolute path to the venv Python binary (`.venv/bin/python -m src.coordination_mcp`)
- `DB_BACKEND=postgres` and `POSTGRES_DSN` pointing to local ParadeDB
- `AGENT_ID` and `AGENT_TYPE` for identity
- `COORDINATION_API_URL` and `COORDINATION_API_KEY` (optional) — enables HTTP proxy fallback when the local DB is unavailable
- Claude Code also gets `cwd` via `add-json` (Codex/Gemini don't need it — all file lookups use `Path(__file__)`)

Restart each CLI after registration to activate.

**HTTP proxy fallback**: When `POSTGRES_DSN` is unreachable at startup and `COORDINATION_API_URL` is set to a reachable coordinator (e.g., `https://coord.rotkohl.ai`), the MCP server automatically proxies tool calls through the HTTP API instead of the local database. Set `COORDINATION_ALLOWED_HOSTS` to allow remote hosts (e.g., `coord.rotkohl.ai`) past the SSRF allowlist. See `src/http_proxy.py` for details.

#### 3a.1. Install lifecycle hooks (status reporting & notifications)

Lifecycle hooks auto-register agents on session start, report status after each turn (heartbeat), and deregister on exit. They install at **user scope** so they work from any repo:

```bash
cd agent-coordinator

# Install for all agents at once
make hooks-setup

# Or individually:
make claude-hooks-setup      # Writes ~/.claude/hooks.json (SessionStart, Stop, SessionEnd)
make codex-hooks-setup       # Writes ~/.codex/hooks.json (SessionStart, Stop, SessionEnd)
make gemini-wrapper-install  # Symlinks gemini-coord to ~/.local/bin/
```

**How each agent gets lifecycle integration:**

| Agent | Mechanism | Events |
|-------|-----------|--------|
| Claude Code | `~/.claude/hooks.json` | SessionStart, Stop, SubagentStop, SessionEnd |
| Codex CLI | `~/.codex/hooks.json` | SessionStart, Stop, SessionEnd |
| Gemini CLI | `gemini-coord` wrapper | register → run → report → deregister |

Hook scripts use absolute paths to the coordinator's `scripts/` directory, so they resolve correctly regardless of the current working directory.

For Gemini, use `gemini-coord` instead of bare `gemini` to get coordinator integration:
```bash
gemini-coord "implement the auth module"
gemini-coord -p "fix the test" -y
```

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
gemini mcp list   # Should show: coordination → ✓ Connected
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

See `docs/cloud-deployment.md` for full Railway setup instructions.

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

The coordinator uses YAML-based deployment profiles (`agent-coordinator/profiles/`) with inheritance and `${VAR}` secret interpolation from `.secrets.yaml`. Profiles inject defaults into `os.environ` — existing env vars always win.

- `local.yaml`: MCP transport, Docker auto-start, ParadeDB on localhost
- `railway.yaml`: HTTP transport, Railway cloud deployment
- `base.yaml`: Shared defaults inherited by both

Agent identity is declared in `agent-coordinator/agents.yaml` — the single source of truth for agent type, trust level, transport, capabilities, and API key mapping.

## Backend Note

Cloud deployment uses Railway with ParadeDB Postgres. See `docs/cloud-deployment.md` for setup and `agent-coordinator/railway.toml` for configuration.

## Output

- Mode executed (`cli`, `web`, or both)
- Per-runtime verification summary (transport + capability flags)
- Failure diagnostics and remediation steps (if any)
- Standalone fallback confirmation when coordinator is unavailable
