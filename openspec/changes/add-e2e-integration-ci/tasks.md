# Tasks: add-e2e-integration-ci

## 1. CI Infrastructure

- [ ] 1.1 Add `test-integration` job to `.github/workflows/ci.yml` with ParadeDB service container
  **Dependencies**: None
  **Files**: `.github/workflows/ci.yml`

- [ ] 1.2 Pin ParadeDB image version (`v0.22.2`) in `docker-compose.yml` and CI job
  **Dependencies**: None
  **Files**: `agent-coordinator/docker-compose.yml`, `.github/workflows/ci.yml`

- [ ] 1.3 Create DB readiness wait script
  **Dependencies**: None
  **Files**: `agent-coordinator/scripts/wait_for_db.py`

- [ ] 1.4 Verify migration auto-apply via `/docker-entrypoint-initdb.d` mount works in GitHub Actions
  **Dependencies**: 1.1
  **Files**: `.github/workflows/ci.yml`

## 2. DirectPostgresClient Integration Fixtures

- [ ] 2.1 Create `tests/integration/conftest_postgres.py` with asyncpg-based fixtures (pool, cleanup, transaction isolation)
  **Dependencies**: None
  **Files**: `agent-coordinator/tests/integration/conftest_postgres.py`

- [ ] 2.2 Add DirectPostgresClient lock integration tests
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/tests/integration/test_locks_postgres.py`

- [ ] 2.3 Add DirectPostgresClient work queue integration tests
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/tests/integration/test_work_queue_postgres.py`

- [ ] 2.4 Add DirectPostgresClient memory integration tests
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/tests/integration/test_memory_postgres.py`

## 3. E2E Test Coverage Extensions

- [ ] 3.1 Add E2E tests for memory store/recall endpoints
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/tests/e2e/test_memory_live.py`

- [ ] 3.2 Add E2E tests for handoff write/read endpoints
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/tests/e2e/test_handoffs_live.py`

- [ ] 3.3 Add E2E tests for work queue submit/claim/complete lifecycle
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/tests/e2e/test_work_queue_live.py`

- [ ] 3.4 Add E2E tests for audit trail logging and query
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/tests/e2e/test_audit_live.py`

## 4. Validation & Documentation

- [ ] 4.1 Run full CI pipeline including new integration job and verify green
  **Dependencies**: 1.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4
  **Files**: `.github/workflows/ci.yml`

- [ ] 4.2 Update `agent-coordinator` spec testing strategy section
  **Dependencies**: 4.1
  **Files**: `openspec/specs/agent-coordinator/spec.md`
