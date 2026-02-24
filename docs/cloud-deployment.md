# Cloud Deployment Guide

Deploy the Agent Coordination API to Railway with ParadeDB Postgres.

## Architecture

```
Railway Project
├─ Service 1: ParadeDB Postgres
│    └─ Private network: postgres://...@<service>.railway.internal:5432/coordinator
└─ Service 2: Coordination API (FastAPI + uvicorn)
     └─ DB_BACKEND=postgres, POSTGRES_DSN=<private network URL>
     └─ Public HTTPS endpoint for cloud agents
```

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
     ```
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
| `POSTGRES_DSN` | `postgresql://postgres:<password>@<service>.railway.internal:5432/coordinator` | Yes |
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

Railway services communicate over a private network. The `POSTGRES_DSN` should use the **internal hostname** (not the public URL) for lower latency and no egress charges:

```
postgresql://postgres:<password>@<postgres-service>.railway.internal:5432/coordinator
```

The Coordination API is exposed publicly via Railway's HTTPS URL (e.g., `https://your-app.railway.app`).

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

python scripts/coordination_bridge.py detect \
  --http-url "https://your-app.railway.app" \
  --api-key "<your-api-key>"
```

### Setup Coordinator

Run the setup-coordinator skill with `--mode web` to verify cloud connectivity:

```bash
# In your agent runtime
/setup-coordinator --mode web --http-url https://your-app.railway.app --api-key <key>
```

## 8. Local Development

For local development, use ParadeDB via docker-compose:

```bash
cd agent-coordinator
docker compose up -d

# Set environment
export DB_BACKEND=postgres
export POSTGRES_DSN=postgresql://postgres:postgres@localhost:54322/postgres

# Run the API
python -m src.coordination_api
```

## Troubleshooting

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

### Health Check Returns 503
- The `/health` endpoint checks database connectivity
- Verify `POSTGRES_DSN` is correct and the database is accessible
- Check Railway Postgres service health in the dashboard

### SSRF Blocking Cloud URL
- Add Railway hostname to `COORDINATION_ALLOWED_HOSTS` environment variable
- Format: comma-separated hostnames without scheme or port
- Example: `COORDINATION_ALLOWED_HOSTS=your-app.railway.app`
