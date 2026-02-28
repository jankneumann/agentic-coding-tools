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

Configure coordinator access for local CLI runtimes (MCP) and Web/Cloud runtimes (HTTP), verify capability detection, and capture fallback expectations.

## Arguments

`$ARGUMENTS` - Optional flags:

- `--profile <local|railway>` (default: read from `COORDINATOR_PROFILE` env var, fallback `local`)
- `--mode <auto|cli|web>` (default: `auto`)
- `--http-url <url>` (for Web/Cloud verification)
- `--api-key <key>` (for Web/Cloud verification)

## Objectives

- Load deployment profile (`local` or `railway`) and apply configuration
- Enable MCP coordinator access for Claude Codex CLI, Codex CLI, and Gemini CLI
- Enable HTTP coordinator access for Claude Web, Codex Cloud/Web, and Gemini Web/Cloud
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
python scripts/coordination_bridge.py detect
```

If health fails, fix runtime first (start `docker compose up -d` in `agent-coordinator/` for ParadeDB Postgres, then run the API with `DB_BACKEND=postgres`).

### 3. CLI Path (MCP) Setup and Verification

Run this section when mode is `auto` or `cli`.

#### 3a. Register MCP server in each CLI runtime

- Claude Codex CLI: configure `coordination_mcp` server (see `agent-coordinator/README.md`)
- Codex CLI: register the same MCP server in Codex MCP settings
- Gemini CLI: register the same MCP server in Gemini MCP settings

Use one canonical command target:

```text
python -m src.coordination_mcp
```

with environment variables from `agents.yaml` via `get_mcp_env(agent_id)`:

```bash
cd agent-coordinator
python3 -c "
from src.agents_config import get_mcp_env
env = get_mcp_env('claude-code-local')
for k, v in env.items():
    print(f'{k}={v}')
"
```

This generates `AGENT_ID`, `AGENT_TYPE`, and database connection settings for the MCP server registration.

#### 3b. Verify MCP capabilities

In each CLI runtime, verify tool discovery includes coordinator tools:

- `acquire_lock`, `release_lock`
- `submit_work`, `get_work`, `complete_work`
- `write_handoff`, `read_handoff`
- `remember`, `recall`
- `check_guardrails`

Expected detection result in integrated skills:

- `COORDINATION_TRANSPORT=mcp`
- `COORDINATOR_AVAILABLE=true`
- `CAN_*` flags reflect discovered MCP tools

### 4. Web/Cloud Path (HTTP) Setup and Verification

Run this section when mode is `auto` or `web`.

Set runtime secrets/env:

```bash
export COORDINATION_API_URL="<https://coord.example.com>"
export COORDINATION_API_KEY="<api-key>"
```

Verify detection and capability flags:

```bash
python scripts/coordination_bridge.py detect \
  --http-url "$COORDINATION_API_URL" \
  --api-key "$COORDINATION_API_KEY"
```

Expected detection result in integrated skills:

- `COORDINATION_TRANSPORT=http`
- `COORDINATOR_AVAILABLE=true`
- `CAN_*` flags reflect reachable HTTP endpoints for that credential scope

If only some endpoints are available, keep `COORDINATOR_AVAILABLE=true` and set missing capabilities to `false`.

#### Cloud Deployment (Railway)

For Railway-deployed coordinators, set the public HTTPS URL:

```bash
export COORDINATION_API_URL="https://your-app.railway.app"
export COORDINATION_API_KEY="<your-provisioned-api-key>"
# Allow Railway hosts in SSRF filter
export COORDINATION_ALLOWED_HOSTS="your-app.railway.app,your-app-production.up.railway.app"
```

Verify cloud connectivity:

```bash
curl -s "$COORDINATION_API_URL/health"
# Expected: {"status": "ok", "db": "connected", "version": "0.2.0"}

python scripts/coordination_bridge.py detect \
  --http-url "$COORDINATION_API_URL" \
  --api-key "$COORDINATION_API_KEY"
```

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
