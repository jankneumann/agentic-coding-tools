# Cloud Deployment Guide

Deploy the Agent Coordination API to Railway with ParadeDB Postgres.

## Architecture

```
                     ┌──────────────────┐
                     │  Railway Project  │
                     │                  │
                     │  ParadeDB        │
                     │  (private net)   │
                     │       ▲          │
                     │       │ POSTGRES_DSN
                     │       │          │
                     │  Coordination    │
                     │  API (FastAPI)   │
                     │       ▲          │
                     └───────┼──────────┘
                             │ HTTPS + X-API-Key
                ┌────────────┼────────────┐
                │            │            │
         Claude Code    Claude Code     Codex
         (local/MCP)    (web/remote)   (cloud)
```

- **Local agents** use MCP over stdio (no HTTP, no API key needed)
- **Cloud agents** use HTTPS with `X-API-Key` header authentication
- Both share the same Postgres state (locks, memory, work queue)

## Prerequisites

- [Railway account](https://railway.app)
- `psql` CLI (for database migration)
- Repository connected to Railway (or pushed to GitHub)

## 1. Create Railway Project

1. Go to [railway.app/new](https://railway.app/new)
2. Create a new empty project

## 2. Add ParadeDB Postgres Service

1. In the project, click **+ New** > **Docker Image**
2. Enter image: `paradedb/paradedb`
3. Configure the service:
   - **Volume**: Add a persistent volume mounted at `/var/lib/postgresql/data`
   - **Environment variables**:
     ```
     POSTGRES_PASSWORD=<generate-strong-password>
     POSTGRES_DB=coordinator
     POSTGRES_LISTEN_ADDRESSES=*
     ```
   > **Important:** `POSTGRES_LISTEN_ADDRESSES=*` is required for private networking. Without it, Postgres only listens on `127.0.0.1` inside the container. Railway's TCP proxy works (it connects from within the container), but private network traffic arrives on the container's external interface and will be refused.
4. Deploy the service and note the **internal hostname** (e.g., `paradedb.railway.internal`)

## 3. Apply Database Migrations

Connect to the Railway Postgres instance via `psql` and apply migrations in order:

```bash
# Get the public connection string from Railway dashboard (Settings > Networking > Public URL)
RAILWAY_DB_URL="postgresql://postgres:<password>@<public-host>:<port>/coordinator"

# Apply migrations in order
for f in agent-coordinator/supabase/migrations/*.sql; do
  echo "Applying $f..."
  psql "$RAILWAY_DB_URL" -f "$f"
done
```

Alternatively, use a one-liner:

```bash
ls agent-coordinator/supabase/migrations/*.sql | sort | xargs -I {} psql "$RAILWAY_DB_URL" -f {}
```

### GitHub Actions Migration (Optional)

Add a workflow step to apply migrations on deploy:

```yaml
- name: Apply migrations
  run: |
    for f in agent-coordinator/supabase/migrations/*.sql; do
      psql "${{ secrets.RAILWAY_DB_URL }}" -f "$f"
    done
```

## 4. Add Coordination API Service

1. In the project, click **+ New** > **GitHub Repo** (or Docker)
2. Connect your repository
3. Set the root directory or Dockerfile path: `agent-coordinator/Dockerfile`
   (Railway reads `railway.toml` automatically for build config)

## 5. Configure Environment Variables

Set these in the Coordination API service settings:

| Variable | Value | Required |
|----------|-------|----------|
| `POSTGRES_DSN` | `postgresql://postgres:<password>@<service>.railway.internal:5432/coordinator?sslmode=disable` | Yes |
| `DB_BACKEND` | `postgres` | Yes |
| `COORDINATION_API_KEYS` | Comma-separated API keys (generate with `openssl rand -hex 32`) | Yes |
| `COORDINATION_API_KEY_IDENTITIES` | JSON mapping keys to agent identities (see below) | Yes |
| `API_WORKERS` | Number of uvicorn workers (default: 1) | No |
| `API_TIMEOUT_KEEP_ALIVE` | Keep-alive timeout in seconds (default: 5, set to 65 for Railway) | No |
| `API_ACCESS_LOG` | Enable access logging: `true` or `false` | No |

### API Key Identities Example

```json
{
  "abc123...": {"agent_id": "claude-web-1", "agent_type": "claude_web"},
  "def456...": {"agent_id": "codex-cloud-1", "agent_type": "codex_cloud"}
}
```

## 6. Private Networking

Railway services communicate over a private network. The `POSTGRES_DSN` should use the **internal hostname** (not the public URL) for lower latency and no egress charges.

**Required DSN format** — append `?sslmode=disable` because Railway's private network does not terminate TLS:

```
postgresql://postgres:<password>@<postgres-service>.railway.internal:5432/coordinator?sslmode=disable
```

Without `sslmode=disable`, asyncpg attempts an SSL handshake that the private network can't complete, causing a connection timeout.

The Coordination API is exposed publicly via Railway's HTTPS URL (e.g., `https://your-app.railway.app`).

For stable custom domain access through Cloudflare, see [Cloudflare Domain Setup](cloudflare-setup.md).

## 7. Verify Deployment

### Health Check

```bash
curl -s "https://your-app.railway.app/health"
# Expected: {"status": "ok", "db": "connected", "version": "0.2.0"}
```

### Capability Detection

```bash
# Set SSRF allowlist for cloud URL
export COORDINATION_ALLOWED_HOSTS="your-app.railway.app"

python3 skills/coordination-bridge/scripts/coordination_bridge.py detect \
  --http-url "https://your-app.railway.app" \
  --api-key "<your-api-key>"
```

### Setup Coordinator

Run the setup-coordinator skill with `--mode web` to verify cloud connectivity:

```bash
# In your agent runtime
/setup-coordinator --mode web --http-url https://your-app.railway.app --api-key <key>
```

## 8. Configure Agent Environments

Once the coordinator is deployed and verified, configure each agent CLI to connect.

### Quick Setup

Generate all configuration and push to Railway in one command:

```bash
cd agent-coordinator
make cloud-setup DOMAIN=coord.yourdomain.com RAILWAY=1
```

This generates API keys, writes `.env.cloud` (local agent env vars), auto-detects the Railway API service, and pushes `COORDINATION_API_KEYS` + `COORDINATION_API_KEY_IDENTITIES` via the Railway CLI. Then:

```bash
source .env.cloud          # activate in current shell
make hooks-setup           # install lifecycle hooks
make cloud-verify DOMAIN=coord.yourdomain.com   # test connectivity
```

Prerequisites for `RAILWAY=1`: Railway CLI installed, authenticated (`railway login`), and linked (`railway link`). Without `RAILWAY=1`, the script prints the values for manual dashboard entry.

To persist across shell sessions, add to `~/.zshrc` or `~/.bashrc`:

```bash
source /path/to/agent-coordinator/.env.cloud
```

This sets the shared coordinator URL and provides per-agent aliases:

```bash
ccc          # launches 'claude' with claude-local coordinator key
ccodex       # launches 'codex' with codex-local coordinator key
cgemini      # launches 'gemini' with gemini-local coordinator key
```

Each alias overrides `COORDINATION_API_KEY` with the agent-specific key so the coordinator can distinguish agents in audit logs and apply the correct trust level.

### Connection Modes

There are two ways local agents can connect to the Railway coordinator:

| Mode | Transport | Local agent connects to | DB exposed? | Tool integration |
|------|-----------|------------------------|-------------|-----------------|
| **MCP + Railway DB** | MCP (stdio) | Railway Postgres (public TCP) | Yes | Native — 30+ `mcp__coordination__*` tools |
| **HTTP** | HTTPS | Railway API (public HTTPS) | No | Via coordination bridge (auto-detected) |

**Recommendation: HTTP for all agents.** It keeps the database on Railway's private network (no public TCP port), works through any firewall, and provides centralized audit logging. The latency difference (~50ms vs ~1ms) is negligible for coordination operations. Use MCP + direct DB only for local-only development with Docker Postgres.

### 8a. Generate API Keys

Generate one key per agent (or per agent type):

```bash
# One key per cloud agent
CLAUDE_KEY=$(openssl rand -hex 32)
CODEX_KEY=$(openssl rand -hex 32)

echo "Claude: $CLAUDE_KEY"
echo "Codex:  $CODEX_KEY"
```

Set these on the Railway service as `COORDINATION_API_KEYS` (comma-separated) and `COORDINATION_API_KEY_IDENTITIES` (JSON map):

```bash
# Railway environment variables
COORDINATION_API_KEYS=<claude-key>,<codex-key>
COORDINATION_API_KEY_IDENTITIES={"<claude-key>":{"agent_id":"claude-remote","agent_type":"claude_code"},"<codex-key>":{"agent_id":"codex-remote","agent_type":"codex"}}
```

### 8b. Claude Code (CLI — HTTP mode, recommended)

Set environment variables so the coordination bridge uses HTTP to the Railway API:

```bash
export COORDINATION_API_URL="https://your-app.railway.app"
export COORDINATION_API_KEY="<claude-key>"
export COORDINATION_ALLOWED_HOSTS="your-app.railway.app"
```

Skills auto-detect HTTP transport when these are set. To verify:

```bash
python3 skills/coordination-bridge/scripts/check_coordinator.py \
  --url "https://your-app.railway.app"
```

### 8c. Claude Code (CLI — MCP mode, local dev)

For local development with Docker Postgres (no Railway needed):

```bash
cd agent-coordinator
make claude-mcp-setup   # Uses localhost DSN by default
```

To use MCP with the Railway database (direct public TCP — exposes DB port):

```bash
cd agent-coordinator
make claude-mcp-setup \
  POSTGRES_DSN="postgresql://postgres:<password>@<public-host>:<port>/coordinator"
```

This registers the MCP server in `~/.claude.json` with the Railway DSN. Claude Code gets native `mcp__coordination__*` tools via stdio, but connects to the shared Railway database.

### 8d. Claude Code (Web / Remote)

Claude Code `--remote` sessions and web-based agents always use HTTP:

```bash
export COORDINATION_API_URL="https://your-app.railway.app"
export COORDINATION_API_KEY="<claude-key>"
export COORDINATION_ALLOWED_HOSTS="your-app.railway.app"
```

### 8e. Codex (CLI)

For HTTP mode (recommended), set the same environment variables:

```bash
export COORDINATION_API_URL="https://your-app.railway.app"
export COORDINATION_API_KEY="<codex-key>"
export COORDINATION_ALLOWED_HOSTS="your-app.railway.app"
```

For MCP mode (local dev), register the MCP server and lifecycle hooks:

```bash
cd agent-coordinator
make codex-mcp-setup    # Registers MCP server (localhost DSN by default)
make hooks-setup        # Installs SessionStart/Stop/End hooks
```

### 8f. Codex (Cloud / Remote)

Codex cloud exec sessions connect via HTTP. Set in the execution environment:

```bash
export COORDINATION_API_URL="https://your-app.railway.app"
export COORDINATION_API_KEY="<codex-key>"
export COORDINATION_ALLOWED_HOSTS="your-app.railway.app"
```

### Environment Variable Reference

| Variable | Where to set | Purpose |
|----------|-------------|---------|
| `COORDINATION_API_URL` | Agent runtime | Coordinator HTTP base URL |
| `COORDINATION_API_KEY` | Agent runtime | API key for `X-API-Key` header |
| `COORDINATION_ALLOWED_HOSTS` | Agent runtime | SSRF allowlist (hostname without scheme) |
| `COORDINATION_API_KEYS` | Railway service | Comma-separated accepted keys |
| `COORDINATION_API_KEY_IDENTITIES` | Railway service | JSON map: key → agent identity |

**Fallback variable names** (checked in order): `COORDINATION_API_URL` → `COORDINATOR_HTTP_URL` → `AGENT_COORDINATOR_API_URL`. Use the primary name for new setups.

## 9. Local Development

For local development, use ParadeDB via docker-compose:

```bash
cd agent-coordinator
docker compose up -d

# Set environment
export DB_BACKEND=postgres
export POSTGRES_DSN=postgresql://postgres:postgres@localhost:54322/postgres

# Run the API
python3 agent-coordinator/run_mcp.py
```

## Troubleshooting

### Connection Timeout on Private Network
- **`POSTGRES_LISTEN_ADDRESSES=*`** must be set on the ParadeDB service. Without it, Postgres listens only on `localhost` inside the container. The public TCP proxy still works (it proxies from within the container), but private network traffic arrives on the container's external network interface and times out.
- **`?sslmode=disable`** must be appended to `POSTGRES_DSN`. Railway's private network does not support TLS; asyncpg's default SSL handshake will hang until timeout.
- Verify both services are in the **same Railway project and environment** — private DNS only resolves within the same environment.

### Connection Refused
- Verify the Postgres service is running in Railway dashboard
- Check `POSTGRES_DSN` uses the correct internal hostname
- Ensure the Coordination API service can reach the Postgres service on the private network

### Migration Errors
- Apply migrations in filename order (000, 001, 002, ...)
- Check for missing extensions: ParadeDB includes `pg_search` and `pgvector` by default
- If a migration fails, check if it was already partially applied

### API Key Issues
- `COORDINATION_API_KEYS` must contain the exact key used by the client
- Key identities JSON must be valid (use a JSON validator)
- Check Railway logs for 401/403 errors

### Health Check Shows "degraded"
- The `/health` endpoint always returns HTTP 200 (for Railway liveness) but reports DB status in the response body
- `{"status": "degraded", "db": "unreachable"}` means the API is running but can't reach Postgres
- Verify `POSTGRES_DSN` uses the correct internal hostname
- Check Railway Postgres service health in the dashboard

### Health Check Returns "service unavailable"
- Railway's proxy can't reach the app — the container isn't listening on the expected port
- The Dockerfile must bind to `0.0.0.0` (not `::`) — Railway's proxy uses IPv4
- Verify `$PORT` is used: the CMD should include `--port ${PORT:-8081}`

### SSRF Blocking Cloud URL
- Add Railway hostname to `COORDINATION_ALLOWED_HOSTS` environment variable
- Format: comma-separated hostnames without scheme or port
- Exact host: `COORDINATION_ALLOWED_HOSTS=your-app.railway.app`
- Wildcard: `COORDINATION_ALLOWED_HOSTS=*.yourdomain.com` (matches all subdomains)
- Mixed: `COORDINATION_ALLOWED_HOSTS=*.yourdomain.com,your-app.railway.app`

## Related Documentation

- [Cloud Session Hooks & Network Configuration](cloud-session-hooks.md) — How hooks, permissions, and egress allowlists work in cloud/remote Claude Code sessions
- [Cloudflare Domain Setup](cloudflare-setup.md) — Custom domain routing via Cloudflare
