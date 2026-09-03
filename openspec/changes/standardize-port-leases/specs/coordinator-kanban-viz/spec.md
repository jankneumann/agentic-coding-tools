## MODIFIED Requirements

### Requirement: Hermetic E2E Test Orchestration for Kanban-viz

The system SHALL provide a single command that runs the kanban-viz end-to-end test suite in a hermetic, ephemeral environment, suitable for local development and future CI integration without modifying the operator's running coordinator stack.

The orchestrator SHALL:

- Generate cryptographically random API key and SSE signing key per invocation (no persisted shared secrets between runs).
- Acquire a port lease through the shared `PortLease` client and bring up PostgreSQL and the coordinator-api service via `docker compose --profile api up -d --build` under the lease's `COMPOSE_PROJECT_NAME`, injecting the ephemeral keys through the operator-facing env vars (`COORDINATOR_API_KEYS`, `COORDINATOR_SSE_SIGNING_KEY`) and the leased ports through `AGENT_COORDINATOR_DB_PORT` and `AGENT_COORDINATOR_REST_PORT`.
- Poll the coordinator's `/health` endpoint at the leased REST port until 200, with a configurable timeout (default 60 seconds).
- Invoke the vitest suite at `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx` against `API_BASE_URL` from the lease env with the ephemeral key in env.
- Tear the Docker stack down and release the lease on success, failure, or operator signal (SIGINT/SIGTERM), with volume removal by default to ensure subsequent runs start from a clean DB.

The orchestrator SHALL also support a `remote` target that runs the same vitest suite against an operator-supplied URL, with a safety guard requiring explicit `--allow-nonlocal` for any non-localhost target.

Exit codes SHALL be:
- `0` — all tests passed
- `1` — setup error (Docker unavailable, lease unavailable, health probe timed out, missing required arg for remote target)
- `2` — tests ran but reported failure

#### Scenario: make e2e-kanban runs the full sweep
- **WHEN** the operator runs `make e2e-kanban` from `agent-coordinator/` with Docker available
- **THEN** PostgreSQL and the coordinator-api container SHALL start under the leased compose project
- **AND** the coordinator-api container SHALL be configured with ephemeral keys not present in any persisted file
- **AND** the vitest e2e suite SHALL execute against the leased `API_BASE_URL` with the matching ephemeral API key
- **AND** the stack SHALL be torn down with `docker compose --profile api down -v` and the lease released after the suite completes
- **AND** the orchestrator SHALL exit `0` if the suite passed, `2` if it failed

#### Scenario: Two sweeps run concurrently
- **WHEN** two operators or agents run `make e2e-kanban` on the same host at the same time
- **THEN** each run SHALL receive a distinct port block and compose project
- **AND** neither run SHALL fail with a port bind error

#### Scenario: Transition test asserts SSE event arrives within latency budget
- **WHEN** the e2e suite runs against a coordinator with `COORDINATOR_SSE_SIGNING_KEY` configured
- **THEN** the suite SHALL create an issue with a unique `change:<test-id>` label
- **AND** SHALL mint an SSE token via `POST /events/auth`
- **AND** SHALL open the SSE stream via `GET /events/work?change_ids=<test-id>&token=<jwt>`
- **AND** SHALL drive a `pending → running` transition via `POST /issues/update`
- **AND** SHALL receive a `transition` event with `work_queue_id` matching the created issue, `from="pending"`, `to="running"`
- **AND** the round-trip latency from update-request to event-receipt SHALL be measured and logged
- **AND** the latency SHALL be less than 2000 milliseconds (target: 200 milliseconds per add-coordinator-kanban-viz task 8.1)

#### Scenario: Operator interrupts mid-run
- **WHEN** the operator sends SIGINT (Ctrl+C) while the orchestrator is running
- **THEN** the orchestrator SHALL print a teardown message, tear down the Docker stack, and release the lease
- **AND** SHALL exit with code 130 (POSIX convention for SIGINT termination)

## ADDED Requirements

### Requirement: Kanban dev server honours the leased UI port

The kanban-viz dev server SHALL bind to the leased `UI_PORT` and address the coordinator at the leased `API_BASE_URL` when a lease env is present, and SHALL fall back to Vite's default port and `http://localhost:8081` only when neither variable is set.

#### Scenario: Dev server started from a lease env
- **WHEN** `npm run dev` runs with `UI_PORT=10004` and `VITE_COORDINATOR_URL=http://localhost:10001` in the environment
- **THEN** Vite SHALL listen on port 10004 with `strictPort` enabled
- **AND** the app SHALL call the coordinator at `http://localhost:10001`

#### Scenario: Dev server started without a lease env
- **WHEN** `npm run dev` runs with neither `UI_PORT` nor `VITE_COORDINATOR_URL` set
- **THEN** Vite SHALL use its default port
- **AND** the app SHALL call `http://localhost:8081`

#### Scenario: Leased UI origin is accepted by CORS
- **WHEN** the coordinator starts with `COORDINATOR_CORS_ALLOWED_ORIGINS` containing the leased `UI_ORIGIN`
- **THEN** a browser request from that origin SHALL receive a matching `Access-Control-Allow-Origin` header
- **AND** a request from an origin not in the list SHALL receive no such header
