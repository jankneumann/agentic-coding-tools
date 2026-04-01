# Tasks: Live Service Testing Pipeline

**Change ID**: `live-service-testing`

## Phase 1: TestEnvironment Protocol + Docker Stack (Core)

- [ ] 1.1 Write tests for TestEnvironment protocol and DockerStackEnvironment
  **Spec scenarios**: LST.1 (protocol conformance, start env vars, teardown idempotent, start failure, env_vars before start), LST.2 (allocated ports, health check success/timeout, teardown, podman detection, no runtime, port conflict)
  **Contracts**: contracts/test_environment_protocol.py
  **Design decisions**: D1 (Protocol not ABC), D3 (subprocess port_allocator import)
  **Dependencies**: None

- [ ] 1.2 Create TestEnvironment protocol and DockerStackEnvironment implementation
  **Spec scenarios**: LST.1, LST.2
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for stack_launcher CLI (start/teardown/status subcommands)
  **Spec scenarios**: LST.9 (CLI start, teardown, teardown without env, status)
  **Design decisions**: D2 (.test-env handoff)
  **Dependencies**: 1.1

- [ ] 1.4 Create stack_launcher.py CLI
  **Spec scenarios**: LST.9
  **Dependencies**: 1.2, 1.3

## Phase 2: Smoke Test Suite

- [ ] 2.1 Write smoke test: test_health.py
  **Spec scenarios**: LST.6 (health check)
  **Dependencies**: None (tests are standalone, run against any base URL)

- [ ] 2.2 Write smoke test: test_auth.py
  **Spec scenarios**: LST.6 (auth no credentials, auth valid, auth malformed)
  **Dependencies**: None

- [ ] 2.3 Write smoke test: test_cors.py
  **Spec scenarios**: LST.6 (CORS preflight)
  **Dependencies**: None

- [ ] 2.4 Write smoke test: test_error_sanitization.py
  **Spec scenarios**: LST.6 (error sanitization — path, traceback, IP, connection string patterns)
  **Dependencies**: None

- [ ] 2.5 Write conftest.py for smoke tests with shared fixtures
  **Spec scenarios**: LST.6 (parametrized by API_BASE_URL and POSTGRES_DSN)
  **Dependencies**: None

## Phase 3: Seed Data + Migration Compatibility

- [ ] 3.1 Write tests for seed data validity (SQL syntax, idempotency, table coverage)
  **Spec scenarios**: LST.4 (covers all 7 tables, idempotent, minimum row counts)
  **Dependencies**: None

- [ ] 3.2 Create seed.sql with representative test fixture data
  **Spec scenarios**: LST.4
  **Dependencies**: 3.1

- [ ] 3.3 Write tests for migration compatibility on standard PostgreSQL (no ParadeDB extensions)
  **Spec scenarios**: LST.5 (standard PostgreSQL, ParadeDB)
  **Dependencies**: None

- [ ] 3.4 Update migration scripts for ParadeDB extension graceful degradation
  **Spec scenarios**: LST.5
  **Dependencies**: 3.3

## Phase 4: Neon Branch Environment

- [ ] 4.1 Write tests for NeonBranchEnvironment (branch create, seed strategies, teardown)
  **Spec scenarios**: LST.3 (migrations seeding, dump_restore seeding, Neon-to-Neon, missing credentials, teardown, neonctl failure, readiness check)
  **Design decisions**: D4 (neonctl CLI over SDK), D5 (pg_dump custom format)
  **Dependencies**: 1.1 (TestEnvironment protocol)

- [ ] 4.2 Create NeonBranchEnvironment implementation
  **Spec scenarios**: LST.3
  **Dependencies**: 4.1, 1.2

- [ ] 4.3 Write tests for pg_dump/pg_restore seeding path
  **Spec scenarios**: LST.3 (dump_restore scenario — custom format, exclude pg_search)
  **Design decisions**: D5 (custom format, exclude pg_search)
  **Dependencies**: 4.1

- [ ] 4.4 Implement pg_dump/pg_restore seeding in NeonBranchEnvironment
  **Spec scenarios**: LST.3 (dump_restore)
  **Dependencies**: 4.2, 4.3

## Phase 5: Phase Runner Scripts + Gate Integration

- [ ] 5.1 Write tests for phase_deploy.py (env selection, .test-env persistence, error handling)
  **Spec scenarios**: LST.7 (deploy creates .test-env, deploy failure JSON error)
  **Design decisions**: D2 (.test-env file)
  **Dependencies**: 1.1

- [ ] 5.2 Create phase_deploy.py
  **Spec scenarios**: LST.7
  **Dependencies**: 1.2, 4.2, 5.1

- [ ] 5.3 Write tests for phase_smoke.py (env loading, pytest invocation, report generation)
  **Spec scenarios**: LST.7 (smoke reads .test-env, missing .test-env error)
  **Contracts**: contracts/validation_report_smoke.md
  **Design decisions**: D7 (validation-report.md format)
  **Dependencies**: 2.1–2.5

- [ ] 5.4 Create phase_smoke.py
  **Spec scenarios**: LST.7
  **Dependencies**: 5.2, 5.3

- [ ] 5.5 Write tests for validation gate logic (soft gate skip, hard gate reject, re-run)
  **Spec scenarios**: LST.8 (soft gate unavailable, soft gate pass, hard gate missing, hard gate re-run succeeds, hard gate re-run fails, hard gate passes)
  **Design decisions**: D7 (report-based gating)
  **Dependencies**: None

- [ ] 5.6 Update implement-feature SKILL.md with soft gate step
  **Spec scenarios**: LST.8 (soft gate)
  **Dependencies**: 5.4, 5.5

- [ ] 5.7 Update cleanup-feature SKILL.md with hard gate step
  **Spec scenarios**: LST.8 (hard gate with re-run logic)
  **Dependencies**: 5.4, 5.5

## Phase 6: Integration Testing + Validation

- [ ] 6.1 Integration test: Docker stack launcher end-to-end (allocate → start → smoke → teardown)
  **Spec scenarios**: LST.2 (full lifecycle), LST.7 (deploy+smoke), LST.9 (CLI)
  **Dependencies**: 5.4

- [ ] 6.2 Integration test: Neon branch end-to-end (create → seed → smoke → teardown)
  **Spec scenarios**: LST.3 (full lifecycle), LST.7 (deploy+smoke)
  **Dependencies**: 5.4, 4.2

- [ ] 6.3 Integration test: Seed data applied and queryable on both Docker and Neon
  **Spec scenarios**: LST.4 (row counts verifiable on live DB)
  **Dependencies**: 3.2, 6.1, 6.2

- [ ] 6.4 Validate migration compatibility on standard PostgreSQL (non-ParadeDB)
  **Spec scenarios**: LST.5 (standard PostgreSQL with WARNING logs)
  **Dependencies**: 3.4, 6.2
