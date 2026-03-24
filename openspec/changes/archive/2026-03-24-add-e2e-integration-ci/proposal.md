# Change: add-e2e-integration-ci

## Why

The agent-coordinator has 881 unit tests that pass in CI, but all integration and E2E tests are excluded (`-m "not e2e and not integration"`). These tests exist and work locally against Docker, but CI never spins up database services. This means:

1. **JSONB serialization bugs go undetected** — the `write_handoff` bug (fixed in `95374c2`) was a `DataError` from asyncpg that no unit test could catch because mocks don't enforce PostgreSQL type semantics.
2. **Migration regressions are invisible** — schema changes in `supabase/migrations/` are never validated against a running database in CI.
3. **The production DB backend (`DirectPostgresClient`) has zero CI coverage** — existing integration tests use `SupabaseClient` (PostgREST), but production uses asyncpg directly.

Adding Docker-based ParadeDB to the CI pipeline and running the existing test suites closes these gaps with minimal new test code.

## What Changes

- Add a new CI job `test-integration` that starts ParadeDB via Docker Compose and runs integration + E2E tests
- Add a `DirectPostgresClient` integration test fixture (`conftest_postgres.py`) so tests validate the production DB backend
- Extend existing E2E tests to cover services not yet tested (memory, handoffs, work queue, audit)
- Add a health-check wait script to ensure ParadeDB is ready before tests run
- Update `docker-compose.yml` with an explicit healthcheck for CI reliability

## Impact

- **Specs affected**: `agent-coordinator` (testing strategy section)
- **Code touchpoints**:
  - `.github/workflows/ci.yml` — new `test-integration` job
  - `agent-coordinator/docker-compose.yml` — healthcheck refinement
  - `agent-coordinator/tests/integration/conftest.py` — add asyncpg fixtures
  - `agent-coordinator/tests/integration/conftest_postgres.py` — new DirectPostgresClient fixtures
  - `agent-coordinator/tests/e2e/conftest.py` — add asyncpg-based E2E fixtures
  - `agent-coordinator/tests/e2e/test_*.py` — new E2E test files for uncovered services
  - `agent-coordinator/scripts/wait_for_db.py` — DB readiness script for CI
