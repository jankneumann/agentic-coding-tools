## ADDED Requirements

### Requirement: Hermetic E2E Test Orchestration for Kanban-viz

The system SHALL provide a single command that runs the kanban-viz end-to-end test suite in a hermetic, ephemeral environment, suitable for local development and future CI integration without modifying the operator's running coordinator stack.

The orchestrator SHALL:

- Generate cryptographically random API key and SSE signing key per invocation (no persisted shared secrets between runs).
- Bring up PostgreSQL and the coordinator-api service via `docker compose --profile api up -d --build`, injecting the ephemeral keys through the operator-facing env vars (`COORDINATOR_API_KEYS`, `COORDINATOR_SSE_SIGNING_KEY`).
- Poll the coordinator's `/health` endpoint until 200, with a configurable timeout (default 60 seconds).
- Invoke the vitest suite at `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx` against the local coordinator URL with the ephemeral key in env.
- Tear the Docker stack down on success, failure, or operator signal (SIGINT/SIGTERM), with volume removal by default to ensure subsequent runs start from a clean DB.

The orchestrator SHALL also support a `remote` target that runs the same vitest suite against an operator-supplied URL, with a safety guard requiring explicit `--allow-nonlocal` for any non-localhost target.

Exit codes SHALL be:
- `0` — all tests passed
- `1` — setup error (Docker unavailable, health probe timed out, missing required arg for remote target)
- `2` — tests ran but reported failure

#### Scenario: make e2e-kanban runs the full sweep

**WHEN** the operator runs `make e2e-kanban` from `agent-coordinator/` with Docker available
**THEN** PostgreSQL and the coordinator-api container SHALL start under the compose project
**AND** the coordinator-api container SHALL be configured with ephemeral keys not present in any persisted file
**AND** the vitest e2e suite SHALL execute against `http://localhost:8081` with the matching ephemeral API key
**AND** the stack SHALL be torn down with `docker compose --profile api down -v` after the suite completes
**AND** the orchestrator SHALL exit `0` if the suite passed, `2` if it failed

#### Scenario: Transition test asserts SSE event arrives within latency budget

**WHEN** the e2e suite runs against a coordinator with `COORDINATOR_SSE_SIGNING_KEY` configured
**THEN** the suite SHALL create an issue with a unique `change:<test-id>` label
**AND** SHALL mint an SSE token via `POST /events/auth`
**AND** SHALL open the SSE stream via `GET /events/work?change_ids=<test-id>&token=<jwt>`
**AND** SHALL drive a `pending → running` transition via `POST /issues/update`
**AND** SHALL receive a `transition` event with `work_queue_id` matching the created issue, `from="pending"`, `to="running"`
**AND** the round-trip latency from update-request to event-receipt SHALL be measured and logged
**AND** the latency SHALL be less than 2000 milliseconds (target: 200 milliseconds per add-coordinator-kanban-viz task 8.1)

#### Scenario: Operator interrupts mid-run

**WHEN** the operator sends SIGINT (Ctrl+C) while the orchestrator is running
**THEN** the orchestrator SHALL print a teardown message and tear down the Docker stack
**AND** SHALL exit with code 130 (POSIX convention for SIGINT termination)
**AND** SHALL not leave the Docker stack running in the background

#### Scenario: Non-localhost target requires explicit --allow-nonlocal

**WHEN** the operator invokes the orchestrator with `--target remote --url https://staging.example.com --api-key <key>` without `--allow-nonlocal`
**THEN** the orchestrator SHALL refuse to proceed
**AND** SHALL print an error explaining that the test mutates issues
**AND** SHALL exit with code 1
**AND** SHALL NOT attempt the health probe or vitest invocation

#### Scenario: SSE signing key unset on coordinator triggers graceful skip

**WHEN** the e2e suite runs against a coordinator where `COORDINATOR_SSE_SIGNING_KEY` is not configured
**AND** `POST /events/auth` returns 503 (fail-closed per design D11)
**THEN** the transition test SHALL print a console warning indicating the skip reason
**AND** SHALL return from the test body without an assertion failure
**AND** the rest of the suite SHALL continue to execute

---

### Requirement: Demo Data Seeding for the Kanban Board

The system SHALL provide a seed script that populates the coordinator work queue with a representative set of issues spanning every kanban column and every vendor swimlane, suitable for local development and operator demos.

The seed script SHALL:

- Use stdlib-only HTTP (no extra dependencies on the coordinator side).
- Plant issues tagged with a configurable `change:<change-id>` label so they appear on the board.
- Tag every seeded issue with a stable umbrella label (`seed:active`) and a per-run unique label (`seed:<run-id>`) so prior runs can be wiped without touching real coordinator work.
- Cover every `work_queue.status` value (`pending`, `blocked`, `claimed`, `running`, `completed`, `failed`) at least once.
- Cover every recognized vendor swimlane (`claude`, `codex`, `gemini`) plus a no-vendor row.
- Support a `--reset` mode that closes every issue tagged `seed:active` via `POST /issues/close`.

The seed script SHALL NOT promise to populate `claimed_by` / `claimed_at` / `completed_at` columns, since those are populated only by `/work/claim` and `/work/complete`, not by `/issues/update`. The script's docstring SHALL document this limitation.

#### Scenario: Seed populates every column

**WHEN** the operator runs `seed_kanban_board.py --api-key <key> --change-id demo-kanban`
**THEN** the coordinator work queue SHALL contain at least one issue in each of: `pending`, `blocked`, `claimed`, `running`, `completed`, `failed` status
**AND** each seeded issue SHALL carry the label `change:demo-kanban`
**AND** each seeded issue SHALL carry both `seed:active` and a per-run `seed:<run-id>` label
**AND** running the kanban-viz frontend against the coordinator SHALL render cards in each of the three columns (Backlog, In Flight, Done)

#### Scenario: --reset wipes prior seeded rows

**WHEN** the operator runs `seed_kanban_board.py --reset` after a prior seed run
**THEN** every issue tagged with `seed:active` SHALL be closed via `POST /issues/close`
**AND** the script SHALL print the count of issues closed
**AND** non-seeded issues (without the `seed:active` label) SHALL remain unaffected

#### Scenario: Idempotent re-seed leaves multiple distinct runs queryable

**WHEN** the operator runs `seed_kanban_board.py` twice in succession without `--reset`
**THEN** the coordinator SHALL contain two distinct sets of seeded issues, each with a different `seed:<run-id>` label
**AND** both sets SHALL share the `seed:active` umbrella label
**AND** a subsequent `--reset` SHALL close both sets together

---

### Requirement: Coordinator Compose Surface for SSE Signing Key

The coordinator-api Docker Compose service SHALL accept `COORDINATOR_SSE_SIGNING_KEY` as an operator-configurable environment variable.

The compose service SHALL use an empty-default interpolation pattern (`${COORDINATOR_SSE_SIGNING_KEY:-}`) so that:

- When the host environment does not set the variable, the container receives an empty string.
- When the container receives an empty string, `event_stream._get_signing_key()` treats it as unset and `POST /events/auth` returns 503 (fail-closed posture from design D11 of `add-coordinator-kanban-viz`).
- When the host environment sets the variable to a non-empty value, the container receives that value and SSE authentication is enabled.

This preserves the invariant that SSE is opt-in: no accidental enablement with a known default key, no silent degradation of the fail-closed posture.

#### Scenario: Empty default produces fail-closed SSE

**WHEN** an operator runs `docker compose --profile api up` without setting `COORDINATOR_SSE_SIGNING_KEY` in the host environment
**THEN** the coordinator-api container SHALL start successfully
**AND** `POST /events/auth` SHALL return 503 with body containing `error` set to a fail-closed message
**AND** `GET /events/work?token=<anything>` SHALL also return 503

#### Scenario: Operator-set value flows through

**WHEN** an operator runs `COORDINATOR_SSE_SIGNING_KEY="$(openssl rand -hex 32)" docker compose --profile api up`
**THEN** the coordinator-api container SHALL start with that value in its environment
**AND** `POST /events/auth` with a valid `Authorization: Bearer` header and a non-empty `change_ids` body SHALL return 200 with a `token` field
**AND** `GET /events/work?change_ids=<id>&token=<jwt>` SHALL accept the connection and stream events

#### Scenario: Orchestrator-supplied ephemeral key enables full e2e

**WHEN** `make e2e-kanban` is run
**THEN** the orchestrator SHALL set `COORDINATOR_SSE_SIGNING_KEY` to a freshly-generated 64-hex-character value
**AND** the value SHALL be unique per invocation (different across consecutive runs)
**AND** the resulting container SHALL accept `/events/auth` requests for the duration of the test run
**AND** the value SHALL NOT be persisted to disk after teardown
