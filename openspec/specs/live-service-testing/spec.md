# live-service-testing Specification

## Purpose
TBD - created by archiving change live-service-testing. Update Purpose after archive.
## Requirements
### Requirement: LST.1 TestEnvironment Protocol

The system SHALL define a `TestEnvironment` protocol with methods `start() → dict[str, str]`, `wait_ready(timeout_seconds: int = 120) → bool`, `teardown() → None`, and `env_vars() → dict[str, str]`. `start()` SHALL return environment variables sufficient to connect to all services (at minimum: `POSTGRES_DSN`, `API_BASE_URL`). `wait_ready()` SHALL poll health endpoints at 2-second intervals and return `True` when all services respond, or `False` after `timeout_seconds`. `teardown()` SHALL be idempotent and release all allocated resources.

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

#### Scenario: start failure raises RuntimeError
Given a TestEnvironment with missing prerequisites (no Docker, no Neon credentials)
When start() is called
Then RuntimeError is raised with a message identifying the missing prerequisite

#### Scenario: env_vars empty before start
Given a TestEnvironment that has not been started
When env_vars() is called
Then an empty dict is returned

### Requirement: LST.2 Docker Stack Environment

`DockerStackEnvironment` SHALL allocate ports via `port_allocator` before starting services. It SHALL detect the container runtime by probing for `docker` CLI first, then `podman` CLI, raising `RuntimeError` if neither is found. It SHALL invoke `<runtime> compose up -d` with environment variables from the port allocation `env_snippet`, setting `COMPOSE_PROJECT_NAME` to the allocation's project name. `wait_ready()` SHALL verify PostgreSQL responds to `pg_isready -h localhost -p <db_port>` AND the coordination API (if running) responds with HTTP 200 on `GET /health`. On teardown, it SHALL run `<runtime> compose down -v` then release ports via `port_allocator.release()`.

Note: The coordination API runs on the host (started separately or via the stack launcher), not inside Docker compose. Docker compose provides only PostgreSQL (and optionally OpenBao). Smoke tests that require the API assume it is started by the caller or by `phase_deploy.py`.

#### Scenario: Docker stack starts with allocated ports
Given Docker is available and port_allocator returns ports starting at 10000
When DockerStackEnvironment.start() is called
Then docker compose is invoked with AGENT_COORDINATOR_DB_PORT=10000 and COMPOSE_PROJECT_NAME set

#### Scenario: Docker stack health check succeeds
Given a running Docker stack with PostgreSQL listening
When wait_ready(timeout_seconds=120) is called
Then pg_isready returns 0 within timeout and wait_ready returns True

#### Scenario: Docker stack health check timeout
Given a Docker stack where PostgreSQL fails to start
When wait_ready(timeout_seconds=10) is called
Then wait_ready returns False after 10 seconds of polling

#### Scenario: Docker stack teardown releases resources
Given a running Docker stack with allocated ports
When teardown() is called
Then docker compose down -v is invoked and ports are released via port_allocator

#### Scenario: Podman auto-detection
Given Docker CLI is not found but Podman CLI is installed
When DockerStackEnvironment.start() is called
Then podman compose is used instead of docker compose

#### Scenario: No container runtime available
Given neither Docker nor Podman CLI is found on PATH
When DockerStackEnvironment.start() is called
Then RuntimeError is raised with message "No container runtime found. Install docker or podman."

#### Scenario: Port allocation conflict
Given port_allocator has no available port blocks (all sessions allocated)
When DockerStackEnvironment.start() is called
Then RuntimeError is raised with message identifying the port exhaustion

### Requirement: LST.3 Neon Branch Environment

`NeonBranchEnvironment` SHALL create ephemeral Neon branches via `neonctl branches create --output json` CLI command. It SHALL support two seeding strategies (`dump_restore` and `migrations`) selectable via a `seed_strategy` parameter. It SHALL support creating a branch from an existing Neon database when `source_branch_id` is provided (Neon-to-Neon branching). `wait_ready()` SHALL verify the branch endpoint accepts a `psql -c 'SELECT 1'` connection. For `migrations` strategy, readiness additionally requires all migration files applied without error. On teardown, it SHALL delete the branch via `neonctl branches delete`. It SHALL read `NEON_PROJECT_ID` and `NEON_API_KEY` from environment variables, raising `RuntimeError` if either is not set.

For `dump_restore` strategy: use `pg_dump --format=custom --no-owner --no-privileges --exclude-extension=pg_search` from the source database, then `pg_restore --no-owner --no-privileges` into the Neon branch. pgvector extension is supported on both ParadeDB and Neon.

#### Scenario: Neon branch creation with migrations seeding
Given NEON_PROJECT_ID and NEON_API_KEY are set
When NeonBranchEnvironment.start() is called with seed_strategy="migrations"
Then a new Neon branch is created, migrations are applied, and seed.sql is executed

#### Scenario: Neon branch creation with dump_restore seeding
Given NEON_PROJECT_ID, NEON_API_KEY are set, and a local ParadeDB is running
When NeonBranchEnvironment.start() is called with seed_strategy="dump_restore"
Then pg_dump --format=custom captures local DB and pg_restore applies it to the Neon branch

#### Scenario: Neon-to-Neon branching
Given source_branch_id is provided
When NeonBranchEnvironment.start() is called
Then the new branch is created from the source branch via neonctl branches create --parent

#### Scenario: Missing Neon credentials
Given NEON_PROJECT_ID is not set
When NeonBranchEnvironment.start() is called
Then a RuntimeError is raised with message "NEON_PROJECT_ID environment variable is required"

#### Scenario: Neon branch teardown
Given an active Neon branch
When teardown() is called
Then the ephemeral branch is deleted via neonctl branches delete

#### Scenario: neonctl command failure
Given NEON_API_KEY is invalid or expired
When NeonBranchEnvironment.start() is called
Then RuntimeError is raised with the neonctl stderr output included in the message

#### Scenario: Neon branch readiness check
Given a newly created Neon branch
When wait_ready(timeout_seconds=60) is called
Then psql -c 'SELECT 1' is polled at 2-second intervals until it succeeds or timeout

### Requirement: LST.4 Seed Data

A `seed.sql` file SHALL provide representative idempotent test fixture data using `INSERT ... ON CONFLICT DO NOTHING` for the 7 cleanable tables: `agent_sessions`, `file_locks`, `work_queue`, `memory_episodic`, `memory_working`, `memory_procedural`, and `handoff_documents`. Minimum data: 2 agent sessions, 1 active lock, 2 work queue items (1 pending, 1 claimed), and 1 entry per memory type (3 total: episodic, working, procedural), plus 1 handoff document.

#### Scenario: Seed data covers all tables
Given the seed.sql file
When parsed for INSERT statements
Then it contains inserts for agent_sessions, file_locks, work_queue, memory_episodic, memory_working, memory_procedural, and handoff_documents

#### Scenario: Seed data is idempotent
Given a database with seed data already applied
When seed.sql is executed again
Then no errors occur and row counts remain unchanged

#### Scenario: Seed data minimum row counts
Given an empty database with migrations applied
When seed.sql is executed
Then agent_sessions has >= 2 rows, file_locks >= 1, work_queue >= 2, memory_episodic >= 1, memory_working >= 1, memory_procedural >= 1, handoff_documents >= 1

### Requirement: LST.5 Migration Compatibility

Migration scripts SHALL gracefully handle missing ParadeDB-specific extensions (pg_search) on non-ParadeDB PostgreSQL using `DO $$ BEGIN CREATE EXTENSION IF NOT EXISTS ... EXCEPTION WHEN OTHERS THEN RAISE WARNING ... END $$` blocks. The migration runner SHALL log skipped extensions at WARNING level.

#### Scenario: Migrations on standard PostgreSQL
Given a standard PostgreSQL instance (no pg_search extension available)
When all 16 migrations are applied
Then migrations complete successfully with WARNING logs for skipped extensions

#### Scenario: Migrations on ParadeDB
Given a ParadeDB instance with pg_search available
When all 16 migrations are applied
Then all extensions are created without warnings

### Requirement: LST.6 Smoke Tests

Smoke test suite SHALL be parametrized by `API_BASE_URL` and `POSTGRES_DSN` environment variables with no hardcoded connection details. Tests: health endpoints (`GET /health` returns HTTP 200), auth enforcement (no credentials → 401/403, valid `X-API-Key` → 200, malformed credentials → 401), CORS (`OPTIONS` with `Origin` header returns `Access-Control-Allow-Origin` and `Access-Control-Allow-Methods` including GET and POST), and error sanitization (error responses do not contain patterns matching filesystem paths `/Users/|/home/|/var/`, Python tracebacks `Traceback \(most recent`, RFC 1918 IPs `10\.\d|172\.(1[6-9]|2\d|3[01])\.|192\.168\.`, or connection strings `postgresql://`). Each test SHALL have a 30-second `pytest.mark.timeout`.

#### Scenario: Health check smoke test
Given a running test environment with API_BASE_URL set
When GET {API_BASE_URL}/health is called
Then HTTP 200 is returned

#### Scenario: Auth enforcement — no credentials
Given a running test environment
When GET {API_BASE_URL}/api/v1/settings/prompts is called without X-API-Key header
Then HTTP 401 or 403 is returned

#### Scenario: Auth enforcement — valid credentials
Given a running test environment with a known API key
When GET {API_BASE_URL}/api/v1/settings/prompts is called with valid X-API-Key
Then HTTP 200 is returned

#### Scenario: CORS preflight smoke test
Given a running test environment
When OPTIONS {API_BASE_URL}/ is sent with Origin: http://localhost:5173
Then Access-Control-Allow-Origin and Access-Control-Allow-Methods headers are present in response

#### Scenario: Error sanitization smoke test
Given a running test environment
When GET {API_BASE_URL}/nonexistent-path-triggering-error is called
Then response body does not match patterns for filesystem paths, tracebacks, RFC 1918 IPs, or connection strings

### Requirement: LST.7 Phase Runner Scripts

`phase_deploy.py` SHALL accept `--env docker|neon` and `--seed-strategy dump_restore|migrations` arguments, create the appropriate `TestEnvironment`, call `start()` and `wait_ready()`, and persist env vars to a `.test-env` file (dotenv format). `phase_smoke.py` SHALL load env vars from `.test-env`, invoke `pytest` on the smoke test suite with those env vars, collect results, and append a `## Smoke Tests` section to `validation-report.md`. If `phase_deploy.py` fails (timeout, missing runtime), it SHALL exit with code 1 and write a JSON object to stderr: `{"error": "<message>", "env": "<docker|neon>", "phase": "deploy"}`.

#### Scenario: Deploy phase creates .test-env
Given Docker is available
When phase_deploy.py --env docker is invoked
Then a .test-env file is created with TEST_ENV_TYPE=docker and valid POSTGRES_DSN

#### Scenario: Smoke phase reads .test-env and runs tests
Given a valid .test-env file exists
When phase_smoke.py is invoked
Then pytest runs the smoke test suite with env vars from .test-env and appends results to validation-report.md

#### Scenario: Deploy failure produces structured error
Given Docker is not available and Neon is not configured
When phase_deploy.py is invoked
Then exit code is 1 and stderr contains JSON with "error", "env", and "phase" keys

#### Scenario: Smoke phase with missing .test-env
Given no .test-env file exists
When phase_smoke.py is invoked
Then exit code is 1 and stderr contains JSON error indicating missing .test-env

### Requirement: LST.8 Validation Gate

`/implement-feature` SHALL run `phase_deploy.py` + `phase_smoke.py` after implementation is complete (soft gate). If Docker/Neon is unavailable, it SHALL log a WARNING, write smoke status as `skipped` in `validation-report.md`, and continue. `/cleanup-feature` SHALL check `validation-report.md` for a `## Smoke Tests` section with `Status: pass`. If the section is missing, has `Status: skipped`, or has `Status: fail`, cleanup-feature SHALL re-run `phase_deploy.py` + `phase_smoke.py`. If the re-run also fails or no runtime is available, `/cleanup-feature` SHALL halt with an error (hard gate — no skip, no merge). The validation report SHALL record: environment type (docker/neon), ISO 8601 timestamp, duration, and individual test results.

#### Scenario: Soft gate in implement-feature — runtime unavailable
Given implementation is complete but Docker is unavailable and Neon is not configured
When the soft validation gate runs
Then a WARNING is logged, validation-report.md gets smoke status "skipped", and implementation proceeds

#### Scenario: Soft gate in implement-feature — smoke tests pass
Given implementation is complete and Docker is available
When the soft validation gate runs
Then smoke tests execute and validation-report.md gets smoke status "pass"

#### Scenario: Hard gate in cleanup-feature — report missing
Given validation-report.md has no Smoke Tests section
When cleanup-feature validation gate runs
Then phase_deploy + phase_smoke are executed

#### Scenario: Hard gate in cleanup-feature — re-run succeeds
Given validation-report.md had smoke status "fail" and Docker is available
When cleanup-feature validation gate re-runs phase_deploy + phase_smoke
Then smoke tests pass and merge proceeds

#### Scenario: Hard gate in cleanup-feature — re-run fails
Given validation-report.md had smoke status "fail" and re-run also fails
When cleanup-feature validation gate completes
Then merge is blocked with an error message listing failing tests

#### Scenario: Hard gate passes on successful smoke
Given validation-report.md has smoke status "pass" from a previous run
When cleanup-feature validation gate runs
Then merge proceeds without re-running smoke tests

### Requirement: LST.9 Stack Launcher CLI

`stack_launcher.py` SHALL be invocable standalone with subcommands: `start --env docker|neon [--seed-strategy dump_restore|migrations] [--timeout 120]`, `teardown` (reads `.test-env` to identify the running environment), and `status` (reports environment type, health, and uptime). If `teardown` is called with no `.test-env` file, it SHALL exit successfully with a message "No active test environment found" (idempotent).

#### Scenario: CLI start command
Given Docker is available
When stack_launcher.py start --env docker is invoked
Then the Docker stack starts and .test-env is written to the current directory

#### Scenario: CLI teardown command
Given a .test-env file exists with an active Docker stack
When stack_launcher.py teardown is invoked
Then the stack is stopped, ports released, and .test-env is removed

#### Scenario: CLI teardown without active environment
Given no .test-env file exists
When stack_launcher.py teardown is invoked
Then exit code is 0 and message "No active test environment found" is printed

#### Scenario: CLI status command
Given a running Docker stack with .test-env present
When stack_launcher.py status is invoked
Then output shows environment type, health status (healthy/unhealthy), and uptime in seconds

