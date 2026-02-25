# Tasks: cloud-deployment-strategy (Phase 1)

## Task 1: Simplify docker-compose to ParadeDB single service
**Spec:** ParadeDB Local Development Environment
**Files:** `agent-coordinator/docker-compose.yml`
**Description:** Replace the current 3-service Supabase docker-compose (Postgres + PostgREST + Realtime) with a single ParadeDB Postgres service:
- Image: `paradedb/paradedb:latest` (Postgres + pg_search + pgvector)
- Port: `${AGENT_COORDINATOR_DB_PORT:-54322}:5432`
- Environment: `POSTGRES_PASSWORD`, `POSTGRES_DB`
- Volume: Mount `supabase/migrations/*.sql` at `/docker-entrypoint-initdb.d/` for auto-migration
- Health check: `pg_isready` every 5s
- Remove PostgREST and Realtime services entirely
- Remove JWT secret configuration (no longer needed without PostgREST)
- Preserve the bootstrap migration (`000_bootstrap.sql`) which creates schemas and roles
**Parallel zone:** Independent

## Task 2: Update .env.example for postgres-first defaults
**Spec:** Cloud Deployment Guide, SSRF Allowlist Documentation
**Files:** `agent-coordinator/.env.example`
**Description:** Update environment example:
- Change default `DB_BACKEND` to `postgres` (was `supabase`)
- Add local dev section: `POSTGRES_DSN=postgresql://postgres:postgres@localhost:54322/postgres`
- Add cloud deployment section with Railway examples:
  - `POSTGRES_DSN=postgresql://...@paradedb.railway.internal:5432/coordinator`
  - `COORDINATION_API_KEYS=<generated-key>`
  - `COORDINATION_API_KEY_IDENTITIES={"key1": {"agent_id": "cloud-agent-1", "agent_type": "cloud_agent"}}`
- Add `COORDINATION_ALLOWED_HOSTS` example for Railway hostnames
- Keep Supabase section as "Legacy / Alternative" with clear note
**Parallel zone:** Independent

## Task 3: Create production Dockerfile
**Spec:** Production Container Image
**Files:** `agent-coordinator/Dockerfile`
**Description:** Create a multi-stage Dockerfile:
- Build stage: `python:3.12-slim` + install `uv` via pip, `uv sync --all-extras`
- Runtime stage: `python:3.12-slim` with only installed packages copied
- Install `asyncpg` (required for `DB_BACKEND=postgres`)
- Entrypoint: `uvicorn src.coordination_api:app --host 0.0.0.0 --port ${API_PORT:-8081}`
- Expose port 8081
- Non-root user (`appuser`) for security
- Set `DB_BACKEND=postgres` as default ENV
**Parallel zone:** Independent

## Task 4: Add .dockerignore
**Spec:** Production Container Image
**Files:** `agent-coordinator/.dockerignore`
**Description:** Create `.dockerignore` to exclude:
- `tests/`, `docs/`, `node_modules/`, `.git/`, `__pycache__/`
- `.env`, `.env.example` (secrets come from Railway env vars)
- `supabase/` (migrations applied separately via psql)
- `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`
- `docker-compose.yml` (local dev only)
**Parallel zone:** Independent

## Task 5: Add production uvicorn settings
**Spec:** Production Server Settings
**Files:** `agent-coordinator/src/coordination_api.py`, `agent-coordinator/src/config.py`
**Description:** Add configurable production settings:
- `API_WORKERS` env var (default: 1) — uvicorn worker count
- `API_TIMEOUT_KEEP_ALIVE` env var (default: 5) — keep-alive timeout in seconds
- `API_ACCESS_LOG` env var (default: false) — access log toggle
- Update `config.py` `ApiConfig` dataclass with new fields
- Update the `main()` entry point to pass these settings to `uvicorn.run()`
**Parallel zone:** Independent — only modifies coordination_api.py and config.py

## Task 6: Enhance health check with DB connectivity
**Spec:** Health Check with Database Connectivity
**Files:** `agent-coordinator/src/coordination_api.py`
**Description:** Update `/health` endpoint:
- Attempt a lightweight DB query (`SELECT 1` via asyncpg or db.rpc)
- Return `{"status": "ok", "db": "connected", "version": "0.2.0"}` on success (HTTP 200)
- Return `{"status": "degraded", "db": "unreachable", "version": "0.2.0"}` on failure (HTTP 503)
- Add 2-second timeout to prevent health check from hanging
- Catch connection errors gracefully
**Parallel zone:** Can be developed alongside Task 5 (different function in same file)

## Task 7: Add Railway deployment configuration
**Spec:** Railway Deployment Configuration
**Files:** `agent-coordinator/railway.toml`
**Description:** Create Railway config for the API service:
- Build: Docker (use Dockerfile from Task 3)
- Health check: `GET /health` every 30s, 5s timeout
- Document the two-service setup in comments:
  - Service 1: ParadeDB Postgres (add via Railway dashboard using `paradedb/paradedb` Docker image)
  - Service 2: Coordination API (this Dockerfile, connect via `POSTGRES_DSN` on private network)
- List required env vars: `POSTGRES_DSN`, `DB_BACKEND=postgres`, `COORDINATION_API_KEYS`, `COORDINATION_API_KEY_IDENTITIES`
**Depends on:** Task 3

## Task 8: Write cloud deployment guide
**Spec:** Cloud Deployment Guide
**Files:** `docs/cloud-deployment.md`
**Description:** Step-by-step guide covering:
1. **Prerequisites**: Railway account, `psql` CLI
2. **Create Railway project**: New project with two services
3. **ParadeDB Postgres setup**: Add Docker service with `paradedb/paradedb` image, configure volume, set credentials
4. **Database migration**: Connect via `psql` and apply migrations in order, or use a migration script
5. **Coordination API setup**: Connect repo, set Dockerfile path to `agent-coordinator/Dockerfile`, configure env vars
6. **Private networking**: Set `POSTGRES_DSN` using Railway internal hostname
7. **API key provisioning**: Generate keys, configure `COORDINATION_API_KEYS` and `COORDINATION_API_KEY_IDENTITIES`
8. **Verification**: Call `/health` endpoint, run `setup-coordinator --mode web`
9. **Local development**: `docker compose up -d` for ParadeDB, set `DB_BACKEND=postgres` and `POSTGRES_DSN`
10. **Troubleshooting**: Connection refused, migration errors, API key issues
**Depends on:** Tasks 1-7 (needs final configs to document accurately)

## Task 9: Update setup-coordinator skill for cloud
**Spec:** Setup-Coordinator Cloud Support
**Files:** `skills/setup-coordinator/SKILL.md`
**Description:** Add cloud deployment section:
- Document setting `COORDINATION_API_URL` to Railway HTTPS URL
- Document API key configuration for cloud agents
- Add cloud-specific verification steps
- Update local setup to reference `DB_BACKEND=postgres` and ParadeDB docker-compose
- Add troubleshooting for cloud connectivity issues
**Parallel zone:** Independent — different file from all other tasks

## Task 10: Update coordination bridge SSRF docs
**Spec:** SSRF Allowlist Documentation
**Files:** `scripts/coordination_bridge.py`
**Description:**
- Add comments documenting `COORDINATION_ALLOWED_HOSTS` configuration for Railway cloud URLs
- Document the SSRF allowlist format (comma-separated hostnames)
- Add example: `COORDINATION_ALLOWED_HOSTS=your-app.railway.app,your-app-production.up.railway.app`
**Parallel zone:** Independent

## Parallelization Plan

```
Task 1  (docker-compose)   ─┐
Task 2  (.env.example)      │
Task 3  (Dockerfile)        │──→ Task 7 (railway.toml) ──→ Task 8 (deployment guide)
Task 4  (.dockerignore)     │
Task 5  (uvicorn settings)  │
Task 6  (health check)      │
Task 9  (setup skill)       │  (independent)
Task 10 (bridge SSRF docs)  ┘  (independent)
```

Tasks 1-6, 9, 10 can all be developed in parallel.
Task 7 depends on Task 3 (needs Dockerfile).
Task 8 depends on Tasks 1-7 (documents the complete setup).
