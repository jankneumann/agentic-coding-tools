# Specification: Live Service Testing

**Spec ID**: `live-service-testing`
**Version**: 1.0.0
**Change**: `live-service-testing`

## Overview

Infrastructure for mandatory live service testing in the validation pipeline, supporting both local Docker/Podman stacks and cloud Neon branches through a unified `TestEnvironment` abstraction.

## ADDED Requirements

### Requirement: LST.1 TestEnvironment Protocol

The system SHALL define a `TestEnvironment` protocol with methods `start() → dict[str, str]`, `wait_ready(timeout_seconds: int) → bool`, `teardown() → None`, and `env_vars() → dict[str, str]`. `start()` SHALL return environment variables sufficient to connect to all services (at minimum: `POSTGRES_DSN`, `API_BASE_URL`). `wait_ready()` SHALL poll health endpoints and return `True` when ready or `False` after timeout. `teardown()` SHALL be idempotent and release all allocated resources.

#### Scenario: Protocol conformance check
Given a class that implements start(), wait_ready(), teardown(), and env_vars()
When checked with isinstance(obj, TestEnvironment)
Then the check returns True

#### Scenario: start returns required env vars
Given a TestEnvironment implementation
When start() is called successfully
Then the returned dict contains "POSTGRES_DSN" and "API_BASE_URL" keys

#### Scenario: teardown is idempotent
Given a started TestEnvironment
When teardown() is called twice
Then no error is raised on the second call

### Requirement: LST.2 Docker Stack Environment

`DockerStackEnvironment` SHALL allocate ports via `port_allocator`, invoke `docker compose up -d` (or `podman compose up -d`) with the allocation env_snippet, auto-detect the container runtime, set `COMPOSE_PROJECT_NAME` from port allocation, verify PostgreSQL responds to `pg_isready` AND coordination API responds HTTP 200, and on teardown run `docker compose down -v` then release ports.

#### Scenario: Docker stack starts with allocated ports
Given Docker is available and port_allocator returns ports starting at 10000
When DockerStackEnvironment.start() is called
Then docker compose is invoked with AGENT_COORDINATOR_DB_PORT=10000 and COMPOSE_PROJECT_NAME set

#### Scenario: Docker stack health check
Given a running Docker stack
When wait_ready(timeout_seconds=120) is called
Then it polls pg_isready and API /health endpoint until both succeed or timeout

#### Scenario: Docker stack teardown releases resources
Given a running Docker stack with allocated ports
When teardown() is called
Then docker compose down -v is invoked and ports are released via port_allocator

#### Scenario: Podman auto-detection
Given Docker is not available but Podman is installed
When DockerStackEnvironment.start() is called
Then podman compose is used instead of docker compose

### Requirement: LST.3 Neon Branch Environment

`NeonBranchEnvironment` SHALL create ephemeral Neon branches via `neonctl` CLI, support two seeding strategies (`dump_restore` and `migrations`), support Neon-to-Neon branching via `source_branch_id`, verify branch accepts connections, delete branch on teardown, and read `NEON_PROJECT_ID` and `NEON_API_KEY` from environment variables.

#### Scenario: Neon branch creation with migrations seeding
Given NEON_PROJECT_ID and NEON_API_KEY are set
When NeonBranchEnvironment.start() is called with seed_strategy="migrations"
Then a new Neon branch is created, migrations are applied, and seed.sql is executed

#### Scenario: Neon branch creation with dump_restore seeding
Given NEON_PROJECT_ID, NEON_API_KEY are set, and a local ParadeDB is running
When NeonBranchEnvironment.start() is called with seed_strategy="dump_restore"
Then pg_dump captures local DB and pg_restore applies it to the Neon branch

#### Scenario: Neon-to-Neon branching
Given source_branch_id is provided
When NeonBranchEnvironment.start() is called
Then the new branch is created from the source branch (not from scratch)

#### Scenario: Missing Neon credentials
Given NEON_PROJECT_ID is not set
When NeonBranchEnvironment.start() is called
Then a RuntimeError is raised with a clear message about the missing variable

#### Scenario: Neon branch teardown
Given an active Neon branch
When teardown() is called
Then the ephemeral branch is deleted via neonctl

### Requirement: LST.4 Seed Data

A `seed.sql` file SHALL provide representative idempotent test fixture data (`INSERT ... ON CONFLICT DO NOTHING`) for all 7 cleanable tables, with at least 2 agent sessions, 1 active lock, 2 work queue items, and 1 memory entry per type.

#### Scenario: Seed data covers all tables
Given the seed.sql file
When parsed for INSERT statements
Then it contains inserts for agent_sessions, file_locks, work_queue, memory_episodic, memory_working, memory_procedural, and handoff_documents

#### Scenario: Seed data is idempotent
Given a database with seed data already applied
When seed.sql is executed again
Then no errors occur and row counts remain unchanged

### Requirement: LST.5 Migration Compatibility

Migration scripts SHALL gracefully handle missing ParadeDB-specific extensions (pg_search) on non-ParadeDB PostgreSQL. The migration runner SHALL log skipped extensions at WARNING level.

#### Scenario: Migrations on standard PostgreSQL
Given a standard PostgreSQL instance (no pg_search extension)
When all 16 migrations are applied
Then migrations complete successfully with WARNING logs for skipped extensions

### Requirement: LST.6 Smoke Tests

Smoke test suite SHALL be parametrized by `API_BASE_URL` and `POSTGRES_DSN`, with tests for health endpoints (200 + status JSON), auth enforcement (401 without creds, 200 with valid, 401 with garbage), CORS (preflight headers, origin rejection), and error sanitization (no path/traceback/IP leaks). All tests SHALL complete within 30 seconds each.

#### Scenario: Health check smoke test
Given a running test environment
When GET /health is called
Then HTTP 200 is returned

#### Scenario: Auth enforcement smoke test
Given a running test environment
When a request is made without credentials
Then HTTP 401 or 403 is returned

#### Scenario: CORS preflight smoke test
Given a running test environment
When an OPTIONS request is made with Origin header
Then Access-Control-Allow-Origin and Access-Control-Allow-Methods headers are present

#### Scenario: Error sanitization smoke test
Given a running test environment
When an error is triggered (e.g., request to nonexistent endpoint)
Then the response body does not contain filesystem paths, stack traces, or internal IPs

### Requirement: LST.7 Phase Runner Scripts

`phase_deploy.py` SHALL accept `--env docker|neon` and `--seed-strategy` arguments, create the appropriate `TestEnvironment`, and persist env vars to `.test-env`. `phase_smoke.py` SHALL load `.test-env`, run pytest on smoke tests, and generate a smoke section for `validation-report.md`. Deploy failures SHALL exit code 1 with structured JSON error.

#### Scenario: Deploy phase creates .test-env
Given Docker is available
When phase_deploy.py --env docker is invoked
Then a .test-env file is created with TEST_ENV_TYPE=docker and valid POSTGRES_DSN

#### Scenario: Smoke phase reads .test-env and runs tests
Given a valid .test-env file exists
When phase_smoke.py is invoked
Then pytest runs the smoke test suite with env vars from .test-env

#### Scenario: Deploy failure produces structured error
Given Docker is not available and Neon is not configured
When phase_deploy.py is invoked
Then exit code is 1 and stderr contains JSON with error details

### Requirement: LST.8 Validation Gate

`/implement-feature` SHALL run deploy+smoke after implementation (soft gate — warn and continue if unavailable). `/cleanup-feature` SHALL require smoke test pass before merge (hard gate — halt on failure). The validation report SHALL record environment type, timestamp, and individual test results.

#### Scenario: Soft gate in implement-feature
Given implementation is complete but Docker is unavailable
When the validation gate runs
Then a WARNING is logged and implementation proceeds with smoke status "skipped"

#### Scenario: Hard gate in cleanup-feature blocks merge
Given validation-report.md has smoke status "fail"
When cleanup-feature validation gate runs
Then merge is blocked with an error message

#### Scenario: Hard gate passes on successful smoke
Given validation-report.md has smoke status "pass"
When cleanup-feature validation gate runs
Then merge proceeds normally

### Requirement: LST.9 Stack Launcher CLI

`stack_launcher.py` SHALL be invocable standalone with `start --env docker|neon`, `teardown` (reads .test-env), and `status` subcommands.

#### Scenario: CLI start command
Given Docker is available
When stack_launcher.py start --env docker is invoked
Then the Docker stack starts and .test-env is written

#### Scenario: CLI teardown command
Given a .test-env file exists with an active Docker stack
When stack_launcher.py teardown is invoked
Then the stack is stopped and .test-env is removed

#### Scenario: CLI status command
Given a running Docker stack
When stack_launcher.py status is invoked
Then output shows the environment type, health status, and uptime
