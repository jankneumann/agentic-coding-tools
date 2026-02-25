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

- `--mode <auto|cli|web>` (default: `auto`)
- `--http-url <url>` (for Web/Cloud verification)
- `--api-key <key>` (for Web/Cloud verification)

## Objectives

- Enable MCP coordinator access for Claude Codex CLI, Codex CLI, and Gemini CLI
- Enable HTTP coordinator access for Claude Web, Codex Cloud/Web, and Gemini Web/Cloud
- Verify capability detection contract used by integrated skills
- Confirm graceful standalone fallback when coordinator is unavailable

## Steps

### 1. Determine Setup Mode

```bash
MODE=auto
# Parse --mode from $ARGUMENTS when provided.
```

- `auto`: run both CLI and Web checks (recommended)
- `cli`: run MCP-only checks
- `web`: run HTTP-only checks

### 2. Validate Coordinator Runtime Prerequisites

Ensure coordinator runtime is reachable before agent setup:

```bash
# Coordinator API health (local default)
curl -s "http://localhost:${API_PORT:-8081}/health"

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

with environment variables for identity and database access (`AGENT_ID`, `AGENT_TYPE`, and backend credentials).

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

## Backend Note

Cloud deployment uses Railway with ParadeDB Postgres. See `docs/cloud-deployment.md` for setup and `agent-coordinator/railway.toml` for configuration.

## Output

- Mode executed (`cli`, `web`, or both)
- Per-runtime verification summary (transport + capability flags)
- Failure diagnostics and remediation steps (if any)
- Standalone fallback confirmation when coordinator is unavailable
