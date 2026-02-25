# Validation Report: cloud-deployment-strategy

**Date**: 2026-02-25 02:45:00
**Commit**: 62de284 (asyncpg fix re-validation)
**Branch**: openspec/cloud-deployment-strategy

## Phase Results

| Phase | Status | Details |
|-------|--------|---------|
| Deploy | PASS | ParadeDB container started, healthy in 1s, 23 tables migrated, API connected |
| Smoke | PASS | Health: ok, Auth: 401 on no/bad key, Lock acquire: 200, Memory store: 200, Guardrails: 200 |
| Spec Compliance | PASS | 6/6 scenarios verified (see below) |

## Spec Compliance Detail

| Requirement | Scenario | Result |
|-------------|----------|--------|
| Health Check with DB Connectivity | DB reachable → 200 with db: connected | PASS |
| ParadeDB Local Development | pg_isready succeeds | PASS |
| ParadeDB Local Development | Migrations applied (23 tables) | PASS |
| Production Server Settings | API starts with default workers | PASS |
| SSRF Allowlist | localhost accessible | PASS |
| asyncpg Write Endpoints | Lock acquire + Memory store return 200 | PASS |

## Findings During Validation

### Fixed (committed)
1. **Volume mount incompatibility** (97c027a): Postgres 18+ changed data directory structure. Fixed mount from `/var/lib/postgresql/data` to `/var/lib/postgresql`
2. **SupabaseConfig required even with DB_BACKEND=postgres** (97c027a): Made SupabaseConfig optional when using postgres backend
3. **Type safety in db.py** (97c027a): Added runtime guard for missing Supabase config
4. **asyncpg JSON serialization bug** (62de284): Write endpoints failed with 500 — two root causes:
   - `rpc()` returns JSONB as strings (not dicts) for function calls — added `json.loads()` on result
   - `insert()`/`update()` need dicts serialized to JSON strings for JSONB columns — added `_serialize_for_asyncpg()` (dicts only, not lists which are PostgreSQL arrays)

### Pre-existing (out of scope)
1. **SonarCloud CI failure**: Fails on this PR and PR #24 — pre-existing configuration issue.

## Result

**PASS** — Ready for `/cleanup-feature cloud-deployment-strategy`

All phases passed. asyncpg JSON serialization bug fully fixed and verified against live services.
