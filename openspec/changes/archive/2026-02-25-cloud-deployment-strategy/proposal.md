# Change: cloud-deployment-strategy

## Why

The agent-coordinator has a complete local development setup (docker-compose + MCP) but no documented or implemented path for cloud deployment. Cloud agents (Claude Web/API, Codex Cloud) require the HTTP coordination API to be accessible over the internet, yet there's no Dockerfile, no hosting configuration, and no deployment guide.

Currently the local docker-compose runs three Supabase containers (Postgres, PostgREST, Realtime) and the Python services talk to PostgREST over HTTP. This is unnecessarily complex — all 22 PostgreSQL stored functions can be called directly via asyncpg (`DB_BACKEND=postgres`), making PostgREST and Realtime containers redundant.

This proposal standardizes on **ParadeDB Postgres** (a Postgres image that includes BM25 full-text search via `pg_search` and vector similarity search via `pgvector`) as the single database image for both local development and cloud deployment. This simplifies infrastructure to two services everywhere, opens the door for enhanced memory search capabilities, and deploys to Railway — consistent with existing project usage.

## Architecture Decision

### Evaluated and Rejected

**Supabase Cloud Postgres:** Adds PostgREST as an unnecessary middleman since the Python API layer _is_ the API. Free tier auto-pauses after 7 days. Supabase Auth is user-focused, not M2M. Would mean two vendors (Railway + Supabase) with cross-internet DB latency.

**Supabase-Only (Edge Functions + PostgREST):** Requires rewriting Python middleware in TypeScript/Deno. 2-second CPU limit per request. Cedar policy engine (`cedarpy`) can't run in Deno. 1-2 weeks effort for less functionality.

**Direct PostgREST (no API server):** No auth middleware, no audit logging, no guardrails enforcement. Shared service key means all agents get full DB access. Only suitable for trusted single-team environments.

### Chosen: Railway (Two Services) + ParadeDB Postgres

**Single vendor, single Postgres image, direct connections everywhere.**

```
CLOUD:
  Railway Project
  ├─ Service 1: ParadeDB Postgres
  │    └─ Private network: postgres://...@paradedb.railway.internal:5432/coordinator
  └─ Service 2: Coordination API (FastAPI + uvicorn)
       └─ DB_BACKEND=postgres, POSTGRES_DSN=<private network URL>
       └─ Public HTTPS endpoint for cloud agents

LOCAL:
  docker-compose.yml
  └─ ParadeDB Postgres (single container, port 54322)

  Native processes:
  ├─ python -m src.coordination_mcp   (MCP for local agents)
  └─ python -m src.coordination_api   (HTTP for testing)
       └─ DB_BACKEND=postgres, POSTGRES_DSN=postgres://...@localhost:54322/coordinator
```

**Why ParadeDB:**
- Drop-in Postgres replacement — all existing migrations work unchanged
- Includes `pg_search` (BM25 full-text search via Tantivy) and `pgvector` (vector similarity search)
- Enables Phase 2: enhanced memory search across summaries, details, and lessons using BM25 ranking and/or semantic vector similarity
- Same image runs locally and on Railway — true dev/prod parity

**Why two separate services (not one container):**
- Scale API workers independently from database
- Failure isolation — DB crash doesn't kill API and vice versa
- Railway native pattern — private network between services, each with own health checks
- Locally: Postgres in docker-compose, API runs natively (same as today, just simpler)

**Why `DB_BACKEND=postgres` everywhere (dropping PostgREST):**
- Direct asyncpg connections are faster than HTTP-over-PostgREST
- Eliminates PostgREST and Realtime containers from local docker-compose (3 → 1)
- The Python API layer already handles auth, audit, guardrails — PostgREST adds nothing
- `DB_BACKEND=postgres` with asyncpg is already fully implemented and tested

## What Changes

### Phase 1 Deliverables (Cloud Deployment)
- **Add** `agent-coordinator/Dockerfile` for the coordination API (multi-stage, `uv`, non-root)
- **Add** `agent-coordinator/.dockerignore`
- **Add** `agent-coordinator/railway.toml` for Railway deployment config
- **Replace** `agent-coordinator/docker-compose.yml` — simplify from 3 Supabase services to 1 ParadeDB Postgres service
- **Update** `agent-coordinator/src/coordination_api.py` — production uvicorn settings (workers, keep-alive, access log)
- **Update** `agent-coordinator/src/config.py` — new `ApiConfig` fields for production settings
- **Update** health endpoint — add DB connectivity check with 2s timeout
- **Add** `docs/cloud-deployment.md` — step-by-step Railway deployment guide
- **Update** `agent-coordinator/.env.example` — cloud deployment section, `DB_BACKEND=postgres` as default
- **Update** `skills/setup-coordinator/SKILL.md` — cloud URL configuration
- **Update** `scripts/coordination_bridge.py` — SSRF allowlist documentation for cloud URLs
- **Add** migration automation guidance (psql-based or GitHub Actions)
- **No breaking changes** to the API surface — all additions/simplifications

### Phase 2 Deliverables (Enhanced Memory Search — future, optional)
- **Add** ParadeDB extension setup migration (`CREATE EXTENSION pg_search; CREATE EXTENSION vector;`)
- **Update** `store_episodic_memory` stored function — generate BM25 index over summary/details/lessons
- **Add** vector embedding column to `memory_episodic` table
- **Update** `get_relevant_memories` stored function — BM25 ranked search and/or vector similarity
- **Update** `memory.py` service — support search_query parameter for hybrid retrieval
- **Result:** Agent recall quality dramatically improved via ranked full-text + semantic search

## Impact

### Affected Architecture Layers
- **Execution**: Cloud agents gain a reachable coordination endpoint
- **Coordination**: No logic changes — same service layer, direct Postgres instead of PostgREST
- **Trust**: API key auth preserved on coordination API
- **Governance**: Audit trail preserved

### Affected Specs
- `agent-coordinator` — new deployment requirements (delta spec)
  - File: `openspec/changes/cloud-deployment-strategy/specs/agent-coordinator/spec.md`

### Affected Code
| File | Change |
|------|--------|
| `agent-coordinator/Dockerfile` | New — multi-stage Python build for coordination API |
| `agent-coordinator/.dockerignore` | New — exclude tests, docs, caches |
| `agent-coordinator/railway.toml` | New — Railway deployment config |
| `agent-coordinator/docker-compose.yml` | Replace — ParadeDB single service (was 3 Supabase services) |
| `agent-coordinator/src/coordination_api.py` | Update — production uvicorn settings, enhanced health check |
| `agent-coordinator/src/config.py` | Update — new ApiConfig fields |
| `agent-coordinator/.env.example` | Update — cloud section, DB_BACKEND=postgres default |
| `scripts/coordination_bridge.py` | Update — cloud URL SSRF allowlist docs |
| `skills/setup-coordinator/SKILL.md` | Update — cloud setup instructions |
| `docs/cloud-deployment.md` | New — deployment guide |

### Rollback Plan
Phase 1 is additive except for the docker-compose simplification. To revert docker-compose: restore the previous 3-service Supabase configuration from git history and set `DB_BACKEND=supabase`. The Supabase backend remains in the codebase and is not removed.
