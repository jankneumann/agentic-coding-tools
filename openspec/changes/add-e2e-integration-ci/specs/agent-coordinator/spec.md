## ADDED Requirements

### Requirement: CI Integration Tests Against Live Database

CI SHALL run integration tests against a live ParadeDB instance on every push to `main` and on pull requests. Integration tests SHALL validate the `DirectPostgresClient` (asyncpg) backend — the production database path.

- The CI pipeline SHALL include a `test-integration` job with a ParadeDB service container
- Migrations SHALL be auto-applied via `/docker-entrypoint-initdb.d` volume mount
- Integration tests SHALL use `DB_BACKEND=postgres` and `POSTGRES_DSN` environment variables
- Integration tests SHALL use transaction rollback for test isolation

#### Scenario: Integration tests run in CI on pull request

- **WHEN** a pull request is opened or pushed to
- **THEN** the `test-integration` CI job starts a ParadeDB service container
- **AND** runs `pytest -m "integration or e2e"` with `POSTGRES_DSN` set
- **AND** the job passes if all tests pass

#### Scenario: Test isolation via transaction rollback

- **WHEN** two DirectPostgresClient integration tests run sequentially
- **AND** the first test inserts data within a transaction
- **THEN** the transaction is rolled back after the first test
- **AND** the second test sees a clean database state

---

### Requirement: DirectPostgresClient Integration Test Coverage

Integration tests SHALL cover lock lifecycle, work queue lifecycle, and memory operations via `DirectPostgresClient` to validate JSONB serialization, UUID coercion, and array handling against real PostgreSQL.

- Lock integration tests SHALL cover acquire, release, conflict detection, TTL expiry, and concurrent acquire
- Work queue integration tests SHALL cover submit, claim, complete, and dependency tracking
- Memory integration tests SHALL cover store, recall, tag filtering, and deduplication

#### Scenario: Lock lifecycle via DirectPostgresClient

- **GIVEN** a running ParadeDB instance with migrations applied
- **WHEN** a lock is acquired, checked, and released via DirectPostgresClient
- **THEN** each operation succeeds with correct state transitions
- **AND** JSONB return values are correctly deserialized

#### Scenario: Work queue lifecycle via DirectPostgresClient

- **GIVEN** a running ParadeDB instance with migrations applied
- **WHEN** a task is submitted, claimed, and completed via DirectPostgresClient
- **THEN** each operation succeeds with correct state transitions

---

### Requirement: E2E HTTP API Test Coverage

E2E tests SHALL exercise the HTTP coordination API against a live database using FastAPI `TestClient`, covering health, locks, guardrails, memory, handoffs, work queue, and audit endpoints.

- E2E tests in CI SHALL use `DirectPostgresClient` via `DB_BACKEND=postgres`
- E2E tests SHALL validate request/response contracts for all major endpoints

#### Scenario: Memory store and recall via HTTP API

- **GIVEN** a running coordination API with live database
- **WHEN** a memory is stored via `POST /memory/store` and then recalled via `POST /memory/query`
- **THEN** the recall returns the stored memory with correct content and tags

#### Scenario: Handoff write and read via HTTP API

- **GIVEN** a running coordination API with live database
- **WHEN** a handoff document is written via `POST /handoffs/write` with list fields
- **THEN** the lists are correctly serialized as JSONB
- **AND** reading the handoff returns all fields intact

---

### Requirement: Database Readiness Verification

A readiness script SHALL verify database connectivity and migration completion before test execution, with a configurable timeout.

- The script SHALL verify PostgreSQL is accepting connections via `pg_isready`
- The script SHALL verify expected tables exist by querying `information_schema` or `pg_catalog`
- The script SHALL timeout after 60 seconds with a clear error message

#### Scenario: Readiness check passes

- **GIVEN** ParadeDB is running with all migrations applied
- **WHEN** the readiness script runs
- **THEN** it exits with code 0 within 10 seconds

#### Scenario: Readiness check fails on timeout

- **GIVEN** ParadeDB is not yet ready
- **WHEN** the readiness script polls for 60 seconds without success
- **THEN** it exits with a non-zero code and prints a diagnostic error message
