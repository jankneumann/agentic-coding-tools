# Design: add-e2e-integration-ci

## Context

The agent-coordinator has three database backends:
1. **SupabaseClient** — HTTP via PostgREST (legacy, used by existing integration tests)
2. **DirectPostgresClient** — asyncpg direct connections (production path, `DB_BACKEND=postgres`)
3. **Mock** — respx-based HTTP mocking (unit tests, always runs in CI)

Existing integration and E2E tests (15 tests across 5 files) only exercise the SupabaseClient path via PostgREST. The production deployment uses DirectPostgresClient, creating a coverage gap where type-level bugs (JSONB serialization, UUID coercion, array vs JSON) only surface in production.

CI currently has 5 jobs: `test`, `test-scripts`, `test-skills`, `validate-specs`, `formal-coordination`. None use Docker.

## Goals / Non-Goals

**Goals:**
- Run existing integration + E2E tests in CI against a real ParadeDB instance
- Add DirectPostgresClient integration test fixtures for the production DB path
- Extend E2E coverage to memory, handoffs, work queue, and audit endpoints
- Keep CI fast (target: <3 minutes for the integration job)
- Maintain backward compatibility with local `docker-compose up -d` workflow

**Non-Goals:**
- Adding PostgREST to CI (the production path is asyncpg, not PostgREST)
- Multi-container orchestration (coordinator API server is tested via TestClient, not Docker)
- Performance/load testing
- Browser/UI testing

## Decisions

### D1: ParadeDB service container in GitHub Actions

Use GitHub Actions `services:` to run ParadeDB as a sidecar. This is simpler than `docker-compose up` in CI and provides automatic lifecycle management.

```yaml
services:
  postgres:
    image: paradedb/paradedb:v0.22.2
    ports: ["54322:5432"]
    env:
      POSTGRES_PASSWORD: postgres
    options: >-
      --health-cmd "pg_isready -U postgres"
      --health-interval 5s
      --health-timeout 5s
      --health-retries 10
    volumes:
      - ${{ github.workspace }}/agent-coordinator/supabase/migrations:/docker-entrypoint-initdb.d
```

### D1b: Pin ParadeDB image version

Pin `paradedb/paradedb:v0.22.2` in both `docker-compose.yml` and CI to avoid version drift between local dev and CI. Uncontrolled `latest` pulls could introduce PostgreSQL behavior changes that cause flaky tests or mask real regressions. Version bumps should be explicit and intentional.

### D2: Test both DB backends

Run integration tests twice: once with `DB_BACKEND=postgres` (DirectPostgresClient) and once with the existing PostgREST fixtures (if PostgREST is available). Since PostgREST is not in CI, the PostgREST tests will continue to skip gracefully via `_is_supabase_running()`.

For CI, the primary validation target is `DirectPostgresClient` — the production backend.

### D3: Separate CI job, not added to existing `test` job

The integration job requires Docker services and has different failure semantics. Keeping it separate allows the fast unit test job to complete independently and avoids slowing down PR feedback for lint/type/unit issues.

### D4: DB readiness wait script

A Python script (`scripts/wait_for_db.py`) polls `pg_isready` and verifies migrations applied. This is more reliable than shell loops and provides clear error messages.

### D5: Test isolation via transaction rollback

New DirectPostgresClient integration tests use `BEGIN`/`ROLLBACK` per test for isolation instead of `TRUNCATE`. This is faster and avoids ordering dependencies.

## Alternatives Considered

### A1: docker-compose in CI instead of services

**Rejected**: GitHub Actions `services:` provides automatic lifecycle management, port mapping, and health checks. `docker-compose up` requires manual wait logic and cleanup.

### A2: Add PostgREST service to CI

**Rejected**: Production uses DirectPostgresClient (asyncpg). Testing PostgREST in CI would validate a non-production path. The existing PostgREST integration tests remain for local development.

### A3: Testcontainers library

**Rejected**: Adds a dependency and complexity. GitHub Actions services are simpler for a single PostgreSQL container.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| ParadeDB image pull time in CI | +30-60s to job | GitHub Actions caches Docker layers; image is ~300MB |
| Migration failures block CI | Integration job fails | `continue-on-error: false` with clear error messages |
| Flaky tests from timing | CI instability | Health check wait + transaction isolation |
| Volume mount for migrations | May not work with `services:` | Use `--mount` in options or copy step |

## Migration Plan

1. Add `test-integration` job to CI with ParadeDB service
2. Add DirectPostgresClient fixtures to `tests/integration/`
3. Add new E2E test files for uncovered services
4. Existing tests remain unchanged — PostgREST tests skip in CI, run locally
