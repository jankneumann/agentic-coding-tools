# Tasks: Live Service Testing Pipeline

**Change ID**: `live-service-testing`

## Phase 1: TestEnvironment Protocol + Docker Stack (Core)

- [ ] 1.1 Write tests for TestEnvironment protocol and DockerStackEnvironment
  **Spec scenarios**: LST.1 (protocol definition), LST.2 (env vars return), LST.3 (wait_ready), LST.4 (idempotent teardown), LST.5 (port allocation), LST.6 (compose invocation), LST.7 (runtime detection), LST.8 (health checks), LST.9 (teardown compose+ports), LST.10 (project name)
  **Contracts**: contracts/test_environment_protocol.py
  **Design decisions**: D1 (Protocol not ABC), D3 (direct import over MCP)
  **Dependencies**: None

- [ ] 1.2 Create TestEnvironment protocol and DockerStackEnvironment implementation
  **Spec scenarios**: LST.1–LST.10
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for stack_launcher CLI (start/teardown/status subcommands)
  **Spec scenarios**: LST.34 (CLI start), LST.35 (CLI teardown), LST.36 (CLI status)
  **Design decisions**: D2 (.test-env handoff)
  **Dependencies**: 1.1

- [ ] 1.4 Create stack_launcher.py CLI
  **Spec scenarios**: LST.34–LST.36
  **Dependencies**: 1.2, 1.3

## Phase 2: Smoke Test Suite

- [ ] 2.1 Write smoke test: test_health.py
  **Spec scenarios**: LST.22 (parametrized), LST.23 (health+ready endpoints), LST.27 (timeout)
  **Dependencies**: None (tests are standalone, run against any base URL)

- [ ] 2.2 Write smoke test: test_auth.py
  **Spec scenarios**: LST.22 (parametrized), LST.24 (auth enforcement), LST.27 (timeout)
  **Dependencies**: None

- [ ] 2.3 Write smoke test: test_cors.py
  **Spec scenarios**: LST.22 (parametrized), LST.25 (CORS headers), LST.27 (timeout)
  **Dependencies**: None

- [ ] 2.4 Write smoke test: test_error_sanitization.py
  **Spec scenarios**: LST.22 (parametrized), LST.26 (no leaks), LST.27 (timeout)
  **Dependencies**: None

- [ ] 2.5 Write conftest.py for smoke tests with shared fixtures
  **Spec scenarios**: LST.22 (parametrized by env vars)
  **Dependencies**: None

## Phase 3: Seed Data + Migration Compatibility

- [ ] 3.1 Write tests for seed data validity (SQL syntax, idempotency, table coverage)
  **Spec scenarios**: LST.17 (table coverage), LST.18 (idempotency), LST.19 (minimum rows)
  **Dependencies**: None

- [ ] 3.2 Create seed.sql with representative test fixture data
  **Spec scenarios**: LST.17–LST.19
  **Dependencies**: 3.1

- [ ] 3.3 Write tests for migration compatibility on standard PostgreSQL (no ParadeDB extensions)
  **Spec scenarios**: LST.20 (graceful extension handling), LST.21 (warning log)
  **Dependencies**: None

- [ ] 3.4 Update migration scripts for ParadeDB extension graceful degradation
  **Spec scenarios**: LST.20–LST.21
  **Dependencies**: 3.3

## Phase 4: Neon Branch Environment

- [ ] 4.1 Write tests for NeonBranchEnvironment (branch create, seed strategies, teardown)
  **Spec scenarios**: LST.11 (branch creation), LST.12 (seed strategies), LST.13 (Neon-to-Neon), LST.14 (wait_ready), LST.15 (teardown), LST.16 (env var config)
  **Design decisions**: D4 (neonctl CLI over SDK), D5 (pg_dump custom format)
  **Dependencies**: 1.1 (TestEnvironment protocol)

- [ ] 4.2 Create NeonBranchEnvironment implementation
  **Spec scenarios**: LST.11–LST.16
  **Dependencies**: 4.1, 1.2

- [ ] 4.3 Write tests for pg_dump/pg_restore seeding path
  **Spec scenarios**: LST.12 (dump_restore strategy)
  **Design decisions**: D5 (custom format, exclude pg_search)
  **Dependencies**: 4.1

- [ ] 4.4 Implement pg_dump/pg_restore seeding in NeonBranchEnvironment
  **Spec scenarios**: LST.12 (dump_restore)
  **Dependencies**: 4.2, 4.3

## Phase 5: Phase Runner Scripts + Gate Integration

- [ ] 5.1 Write tests for phase_deploy.py (env selection, .test-env persistence, error handling)
  **Spec scenarios**: LST.28 (deploy args), LST.30 (failure handling)
  **Design decisions**: D2 (.test-env file)
  **Dependencies**: 1.1

- [ ] 5.2 Create phase_deploy.py
  **Spec scenarios**: LST.28, LST.30
  **Dependencies**: 1.2, 4.2, 5.1

- [ ] 5.3 Write tests for phase_smoke.py (env loading, pytest invocation, report generation)
  **Spec scenarios**: LST.29 (smoke runner), LST.33 (validation report format)
  **Design decisions**: D7 (validation-report.md format)
  **Dependencies**: 2.1–2.5

- [ ] 5.4 Create phase_smoke.py
  **Spec scenarios**: LST.29, LST.33
  **Dependencies**: 5.2, 5.3

- [ ] 5.5 Write tests for validation gate logic (soft gate skip, hard gate reject)
  **Spec scenarios**: LST.31 (soft gate), LST.32 (hard gate)
  **Design decisions**: D7 (report-based gating)
  **Dependencies**: None

- [ ] 5.6 Update implement-feature SKILL.md with soft gate step
  **Spec scenarios**: LST.31
  **Dependencies**: 5.4, 5.5

- [ ] 5.7 Update cleanup-feature SKILL.md with hard gate step
  **Spec scenarios**: LST.32
  **Dependencies**: 5.4, 5.5

## Phase 6: Integration Testing + Validation

- [ ] 6.1 Integration test: Docker stack launcher end-to-end (allocate → start → smoke → teardown)
  **Spec scenarios**: LST.5–LST.10, LST.28–LST.29
  **Dependencies**: 5.4

- [ ] 6.2 Integration test: Neon branch end-to-end (create → seed → smoke → teardown)
  **Spec scenarios**: LST.11–LST.16, LST.28–LST.29
  **Dependencies**: 5.4, 4.2

- [ ] 6.3 Integration test: Seed data applied and queryable on both Docker and Neon
  **Spec scenarios**: LST.17–LST.19
  **Dependencies**: 3.2, 6.1, 6.2

- [ ] 6.4 Validate migration compatibility on standard PostgreSQL (non-ParadeDB)
  **Spec scenarios**: LST.20–LST.21
  **Dependencies**: 3.4, 6.2
