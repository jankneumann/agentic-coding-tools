# coordinator-kanban-viz Specification

## Purpose
TBD - created by archiving change add-coordinator-kanban-viz. Update Purpose after archive.
## Requirements
### Requirement: Three-Column Kanban Board

The system SHALL provide a web application at `apps/kanban-viz/` that renders coordinator work-queue state as a three-column Kanban board.

The columns SHALL be:

- `Backlog` — work-queue rows where `status = 'pending'`.
- `In Flight` — work-queue rows where `status IN ('claimed', 'running')`.
- `Done` — work-queue rows where `status = 'completed'` AND `completed_at >= now() - interval '24 hours'`.

Each card SHALL display: task title (`work_queue.title` or `metadata.task_key + title`), the change-id (from `labels` matching `change:<id>` or `metadata.change_id`), the assignee (`agent_id` of `claimed_by`), and a relative timestamp (claimed-at or completed-at depending on column).

#### Scenario: Board renders cards bucketed by status

**WHEN** the board mounts and the coordinator returns issues across all three statuses
**THEN** each `pending` issue SHALL appear in the `Backlog` column
**AND** each `claimed` or `running` issue SHALL appear in the `In Flight` column
**AND** each `completed` issue with `completed_at >= now() - 24h` SHALL appear in the `Done` column
**AND** issues completed earlier than 24h ago SHALL NOT appear on the board

#### Scenario: Card shows minimum required fields

**WHEN** a card renders for any issue
**THEN** the title, change-id, assignee (when set), and relative timestamp SHALL all be visible
**AND** missing optional fields (no assignee on a `pending` row) SHALL render as empty placeholders, not as crash points

#### Scenario: Empty column renders an explicit empty state

**WHEN** any column has zero matching issues
**THEN** the column SHALL render its empty-state copy (e.g., `No tasks in Backlog`)
**AND** SHALL NOT render a misleading skeleton/loader after the initial fetch resolves

---

### Requirement: Vendor Swimlanes on In-Flight Cards

When an `In Flight` card represents a work-package whose children include multiple agents with distinct vendor values (extracted per design.md D4: canonical source is the `agent_id` suffix after `--`; secondary cross-check is `agent_sessions.agent_type`), the card SHALL render mini-lanes — one per distinct vendor — showing the most recent `audit_log` row for that vendor's agent.

Each mini-lane SHALL display: the vendor name and color, a one-line summary of the latest operation (`audit_log.args_summary` truncated to one line), and a relative timestamp (`<n>s ago`, `<n>m ago`).

#### Scenario: Single-vendor card collapses swimlanes

**WHEN** a card represents a work-package with exactly one child agent
**THEN** the card SHALL render a single lane labeled with that agent's vendor
**AND** SHALL NOT render an N-lane structure with a single populated lane

#### Scenario: Vendor-diverse card renders one lane per vendor

**WHEN** a card represents a work-package with three child agents whose vendors are `claude`, `gemini`, and `codex`
**THEN** the card SHALL render exactly three mini-lanes
**AND** each lane SHALL display the most recent `audit_log` row for the agent of its vendor
**AND** lanes SHALL be sorted by vendor name in stable lexicographic order

#### Scenario: Lane shows live activity update on SSE event

**WHEN** the client receives an `event: audit` SSE payload for an agent currently rendered on a swimlane
**THEN** the affected lane SHALL update its summary text within 200ms
**AND** other lanes on the same card SHALL NOT re-render

#### Scenario: Completed work-package collapses swimlanes to consensus indicator

**WHEN** a card's underlying work-package transitions to `completed` AND the work-package was vendor-diverse
**THEN** the swimlanes SHALL collapse into a single consensus indicator (`✓` if review consensus is `agree`, `✗` if `conflict`)
**AND** the indicator SHALL source from the existing `parallel-infrastructure` consensus synthesizer's output

---

### Requirement: Sync-Point Gate Banner

A banner SHALL be pinned to the top of the board displaying the blocker state of the three sync-point skills (`/cleanup-feature`, `/merge-pull-requests`, `/update-specs`).

The banner SHALL poll `GET /sync-points/status` on a 5-second interval AND SHALL update on relevant SSE events.

When zero sync-points are blocked, the banner SHALL collapse to a single-line green status (`✓ all sync-points clear`).

When at least one sync-point is blocked, the banner SHALL expand to one row per blocked sync-point, each row showing the skill name, the blocker count, the most-stale blocker's heartbeat age, and action buttons.

#### Scenario: All sync-points clear

**WHEN** the `/sync-points/status` endpoint returns `blocked: false` for all three sync-points
**THEN** the banner SHALL render a single line with copy `✓ all sync-points clear`
**AND** SHALL NOT render per-skill rows or buttons

#### Scenario: Single sync-point blocked by one agent

**WHEN** the endpoint returns `cleanup-feature` as `blocked: true` with one blocker `wp-backend` whose `last_heartbeat_iso` was 2 minutes ago
**THEN** the banner SHALL render `🟡 /cleanup-feature blocked — 1 active agent (wp-backend, 2m ago).`
**AND** SHALL render two action buttons labeled `Wait` and `Kick wp-backend`

#### Scenario: Kick action requires consent

**WHEN** the operator clicks `Kick <agent_id>` on a sync-point banner row
**THEN** the UI SHALL surface a per-action consent prompt naming the agent and the destructive operation
**AND** the `POST /agents/<id>/kick` call SHALL ONLY fire after the operator confirms
**AND** an audit event SHALL be written to `docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json` with the mandatory artifact header regardless of confirmation outcome

---

### Requirement: Live Update via SSE with Polling Fallback

The frontend SHALL receive live coordinator state updates via Server-Sent Events from a new endpoint `GET /events/work?change_ids=<csv>`.

When `EventSource` cannot establish a connection (browser restriction, proxy stripping `Connection: keep-alive`, Tauri webview limitation), the frontend SHALL transparently fall back to polling the existing coordinator read endpoints `POST /issues/list` (labels-filtered list — coordinator uses POST-with-body, not GET-with-query) and `GET /audit` (with `since`, `change_id`, and `limit` query params via `AuditService.query`) at 5-second intervals.

The SSE endpoint SHALL emit two event kinds:

- `event: transition` — payload includes `work_queue_id`, `from`, `to`, `agent_id`, `ts`.
- `event: audit` — payload includes `audit_id`, `agent_id`, `operation`, `args_summary`, `ts`.

On (re)connection, the server SHALL emit a single `event: snapshot` containing the current state of subscribed change-ids before resuming live emission.

#### Scenario: Status transition propagates within 200ms

**WHEN** a coordinator transaction updates a `work_queue` row's status from `claimed` to `running` for a change-id the client has subscribed to
**THEN** the client SHALL receive an `event: transition` payload via SSE
**AND** the corresponding card SHALL move from its current column to the `In Flight` column within 200ms of the server-side transaction commit

#### Scenario: Reconnection emits a snapshot

**WHEN** the SSE connection drops and `EventSource` reconnects
**THEN** the server SHALL emit a single `event: snapshot` containing the current state of all subscribed change-ids
**AND** the client SHALL reconcile its local state against the snapshot rather than awaiting individual transition events for catch-up

#### Scenario: Polling fallback engages on EventSource failure

**WHEN** `EventSource` raises an error indicating the SSE connection cannot be established
**THEN** the client SHALL transparently fall back to polling `POST /issues/list` (with `labels` filter in the request body) at 5-second intervals
**AND** the polling fallback SHALL engage without surfacing an error to the user

#### Scenario: Backpressure coalesces excessive events

**WHEN** more than 100 events would be emitted to a single SSE connection within 1 second
**THEN** the server SHALL coalesce excess events and emit a single `event: snapshot` instead
**AND** the snapshot SHALL contain the post-coalesce state for all subscribed change-ids

---

### Requirement: Reversibility-Classified UI Actions

Every write action exposed by the UI SHALL be classified per the codeviz operation reversibility taxonomy (`read`, `reversible-write`, or `destructive-write`) AND gated accordingly.

`read` actions SHALL be auto-allowed for any caller.
`reversible-write` actions SHALL be auto-allowed for the human operator AND SHALL emit an audit event.
`destructive-write` actions SHALL require per-operation operator consent AND SHALL emit an audit event regardless of consent outcome.

The classification SHALL match the table in `design.md` decision D8.

#### Scenario: Save-view emits an audit event

**WHEN** the operator saves a view named `Active reviews — security`
**THEN** the file `docs/kanban-viz/saved-views/active-reviews-security.json` SHALL be written
**AND** an audit event SHALL be appended to `docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json` with `class: reversible-write` and `action: save-view`
**AND** the audit event SHALL carry the mandatory artifact header

#### Scenario: Force-release lock requires consent

**WHEN** the operator clicks `Force-release` on a stale file lock
**THEN** the UI SHALL surface a per-action consent prompt identifying the file path and the agent that holds the lock
**AND** the `DELETE /locks/<file_path>` call SHALL fire only after the operator confirms
**AND** the operator-confirm and the consent-decline outcomes SHALL each emit a distinct audit event

#### Scenario: Drag-to-Ready sets pending-approval label

**WHEN** the operator drags a Backlog card to a `Ready` drop zone
**THEN** the client SHALL `PATCH /issues/<id>/labels` to add the `pending-approval` label
**AND** the action SHALL be classified as `reversible-write`
**AND** an audit event SHALL be emitted; no consent prompt SHALL be required for the human operator

---

### Requirement: Saved Views with Mandatory Artifact Header

Saved views SHALL be persisted as JSON files under `docs/kanban-viz/saved-views/<view-name>.json`.

Each saved-view file SHALL carry the codeviz mandatory artifact header (`schema_version`, `generated_at`, `git_sha`, `generator`) at the top level.

The view payload SHALL include: name, columns config, filters (change-ids, vendors), grouping, and sort.

The directory SHALL be git-committed (small, diffable, canonical per the codeviz storage-tier policy).

#### Scenario: Saved view is valid against the JSON schema

**WHEN** the operator saves a view
**THEN** the resulting file SHALL validate against the JSON schema declared in `contracts/README.md`
**AND** the file SHALL be valid JSON

#### Scenario: Saved view file path is git-relative

**WHEN** the operator saves a view from any working directory
**THEN** the resulting file SHALL be written to `<repo-root>/docs/kanban-viz/saved-views/<slug>.json`
**AND** the slug SHALL be derived from the view name (lowercased, spaces → hyphens, non-alphanumeric stripped)

#### Scenario: Re-save under same name overwrites with audit trail

**WHEN** the operator saves a view whose slug matches an existing file
**THEN** the file SHALL be overwritten in place
**AND** an audit event SHALL identify both the prior `git_sha`-of-file and the new `git_sha`-at-save so reviewers can correlate

---

### Requirement: New Coordinator Endpoint — Sync-Point Status

The coordinator SHALL expose `GET /sync-points/status` returning the blocker state of the three sync-point skills.

The response SHALL be a JSON array with one object per sync-point skill, each containing: `skill` (string, one of `cleanup-feature`, `merge-pull-requests`, `update-specs`), `blocked` (boolean), `blockers` (array of `{agent_id, last_heartbeat_iso}`), and `suggested_actions` (array of strings, e.g., `["wait", "kick:wp-backend"]`).

The endpoint SHALL reuse `skills.shared.active_agents.check_no_active_agents()` (file: `skills/shared/active_agents.py`) for blocker detection — the logic MUST NOT be duplicated, and the coordinator MUST NOT vendor or copy the function.

#### Scenario: Endpoint returns one row per sync-point

**WHEN** a client invokes `GET /sync-points/status`
**THEN** the response SHALL contain exactly three objects, one per sync-point skill
**AND** the order SHALL be deterministic (alphabetical by `skill`)

#### Scenario: Suggested actions match blocker count

**WHEN** a sync-point has N blockers
**THEN** `suggested_actions` SHALL contain `"wait"` plus N entries of the form `"kick:<agent_id>"`
**AND** when N=0, `suggested_actions` SHALL be an empty array

---

### Requirement: New Coordinator Endpoint — Worktree Active Projection

The coordinator SHALL expose `GET /worktrees/active` returning a projection of `.git-worktrees/.registry.json` with stale entries filtered out (heartbeat older than 1 hour).

This endpoint exists so the frontend never reads the registry file directly — preserving the rule that the coordinator is the single point of access to coordination state.

#### Scenario: Endpoint omits stale worktrees

**WHEN** the registry contains 3 entries — two with heartbeat within 5 minutes, one with heartbeat 2 hours ago
**THEN** the endpoint response SHALL contain exactly 2 entries
**AND** the response SHALL NOT contain the 2-hours-stale entry

#### Scenario: Pinned worktrees are not filtered as stale

**WHEN** the registry contains a worktree whose heartbeat is 6 hours ago but `pinned: true`
**THEN** the endpoint response SHALL contain that entry
**AND** the entry SHALL include a `pinned: true` field so the UI can distinguish it

---

### Requirement: New Coordinator Endpoint — Work Event Stream (SSE)

The coordinator SHALL expose `GET /events/work?change_ids=<csv>` as a Server-Sent Events endpoint emitting `transition` and `audit` events filtered to the supplied change-ids.

The endpoint SHALL subscribe to the existing `agent-coordinator/src/event_bus.py` multi-channel LISTEN/NOTIFY bus (channel `coordinator_task` for work-queue transitions; a new channel `coordinator_audit`, added by this change, for `audit_log` appends). The endpoint SHALL filter payloads server-side against the subscription's change-id set after the bus dispatches each event.

The endpoint SHALL emit an initial `event: snapshot` on connection.

#### Scenario: Subscription filters server-side by change-id

**WHEN** a client subscribes with `change_ids=add-foo,add-bar` AND a `work_queue` transition occurs for change-id `add-baz`
**THEN** the client SHALL NOT receive an event for the `add-baz` transition
**AND** server-side filter logging SHALL record the suppression for observability

#### Scenario: NOTIFY emission flows through the existing event bus

**WHEN** `IssueService.update` commits a transaction that mutates a `work_queue` row
**THEN** the existing `coordinator_task` NOTIFY trigger on `work_queue` SHALL fire as part of the same transaction
**AND** `EventBusService` SHALL dispatch the payload to the SSE handler's subscribed callback

#### Scenario: New coordinator_audit channel is wired into AuditService.log_operation

**WHEN** `AuditService.log_operation` commits a row to `audit_log`
**THEN** a `coordinator_audit` NOTIFY SHALL fire as part of the same transaction
**AND** `EventBusService` SHALL dispatch the payload to the SSE handler's subscribed callback

---

### Requirement: New Coordinator Write Endpoints for UI Actions

The coordinator SHALL expose three write endpoints required by v1 UI actions: `PATCH /issues/{id}/labels`, `DELETE /locks/{file_path:path}`, and `POST /agents/{agent_id}/kick`. Each endpoint SHALL reuse an existing service module and SHALL emit an `audit_log` row for each call.

#### Scenario: PATCH /issues/{id}/labels adds and removes labels

**WHEN** a client calls `PATCH /issues/{id}/labels` with body `{"add": ["pending-approval"], "remove": []}` against a valid `work_queue` row
**THEN** the row's `labels` array SHALL contain `pending-approval`
**AND** the response status SHALL be 200
**AND** an `audit_log` row SHALL be appended capturing the action

#### Scenario: DELETE /locks/{file_path} force-releases a stale lock

**WHEN** a client calls `DELETE /locks/{file_path}` for an existing lock held by a different agent
**THEN** the lock SHALL be removed
**AND** an `audit_log` row SHALL be appended capturing the prior holder
**AND** the response SHALL include `prior_holder_agent_id` for forensics

#### Scenario: POST /agents/{agent_id}/kick clears worktree registry and updates session

**WHEN** a client calls `POST /agents/{agent_id}/kick` against an agent whose `.git-worktrees/.registry.json` entry exists and whose `agent_sessions` row is currently `status='active'`
**THEN** the agent's entry SHALL be removed from `.git-worktrees/.registry.json` (via `skills/worktree/scripts/worktree.py teardown --agent-id <id> --force` semantics, since `check_no_active_agents()` reads only the on-disk registry, NOT a database table)
**AND** the agent's `agent_sessions` row SHALL be updated with `status='disconnected'` and `last_heartbeat=epoch` so coordinator-side discovery views also stop listing the agent
**AND** subsequent calls to `check_no_active_agents()` SHALL NOT consider the agent active
**AND** the response body SHALL include `{registry_cleared: bool, agent_sessions_updated: bool, held_locks: list[str]}` so the UI can surface partial-failure and locks-still-held cases
**AND** an `audit_log` row SHALL be appended capturing both side effects

#### Scenario: POST /agents/{agent_id}/kick does NOT auto-release file locks

**WHEN** the kicked agent currently holds entries in `file_locks`
**THEN** the kick endpoint SHALL leave those `file_locks` rows in place (cleanup is the operator's responsibility via `DELETE /locks/{file_path:path}` or the existing TTL)
**AND** the response's `held_locks` array SHALL enumerate the file paths still locked

---

### Requirement: New Coordinator File-Write Endpoints for UI Persistence

The coordinator SHALL expose two file-write endpoints required by the v1 UI's saved-views and audit-emission features: `PUT /kanban-viz/saved-views/{slug}` and `POST /kanban-viz/audit`. These exist because the v1 UI is a browser app (with optional Tauri shell) that cannot itself write repo files; the coordinator owns the disk writes to preserve the "frontend never bypasses the coordinator" invariant (design.md D10).

Both endpoints SHALL:

- Require authentication via the existing `X-Coordinator-API-Key` / `Authorization: Bearer` header.
- Stamp the codeviz mandatory artifact header (`schema_version`, `generated_at`, `git_sha`, `generator: kanban-viz@<version>`) server-side; client-supplied header values SHALL be ignored.
- Validate the body against the corresponding JSON schema (saved-view schema for `PUT /kanban-viz/saved-views/{slug}`, audit-event schema for `POST /kanban-viz/audit`), declared in `contracts/README.md`.
- Reject `slug` / `run-id` values that do not match `^[a-z0-9][a-z0-9-]{0,63}$` (anti path-traversal).
- Resolve the on-disk path relative to a configured `WORKDIR_ROOT`; refuse if the resolved path escapes the configured root.
- Write atomically via `tmp-file + rename`.
- Append a row to `audit_log` capturing the operation, the resolved file path, and the `slug`/`run-id`.

#### Scenario: PUT /kanban-viz/saved-views/{slug} writes a saved view

**WHEN** a client calls `PUT /kanban-viz/saved-views/active-reviews-security` with a body matching the saved-view JSON schema
**THEN** the coordinator SHALL write the file to `<WORKDIR_ROOT>/docs/kanban-viz/saved-views/active-reviews-security.json`
**AND** the file SHALL carry the codeviz mandatory artifact header stamped server-side
**AND** the response SHALL include the resolved repo-relative path
**AND** an `audit_log` row SHALL capture `operation='kanban_viz.save_view'`, the slug, and the resolved path

#### Scenario: POST /kanban-viz/audit appends a UI audit event

**WHEN** a client calls `POST /kanban-viz/audit` with a body matching the audit-event JSON schema, including a `run_id`
**THEN** the coordinator SHALL append the file to `<WORKDIR_ROOT>/docs/kanban-viz/audit/<YYYY-MM-DD>/<run_id>.json` (date derived server-side from `generated_at`)
**AND** the file SHALL carry the codeviz mandatory artifact header stamped server-side
**AND** an `audit_log` row SHALL capture `operation='kanban_viz.audit'`, the `run_id`, and the resolved path

#### Scenario: Slug with directory traversal is rejected

**WHEN** a client calls `PUT /kanban-viz/saved-views/..%2Fpwned` or `PUT /kanban-viz/saved-views/foo/bar`
**THEN** the response SHALL be 400 Bad Request
**AND** no file SHALL be written
**AND** no `audit_log` row SHALL be appended

#### Scenario: Tauri frontend bypasses coordinator file-write endpoints

**WHEN** the frontend is running under a Tauri shell that has been granted filesystem capabilities
**THEN** the saved-view and audit-event files MAY be written directly via Tauri's `fs.writeTextFile` instead of the coordinator endpoints
**AND** the on-disk format SHALL be identical
**AND** the runtime feature-detect SHALL choose between paths based on the presence of the Tauri API

---

### Requirement: Authentication Posture for Kanban UI

The Kanban UI SHALL authenticate against the coordinator using the existing API-key model (`X-Coordinator-API-Key` / `Authorization: Bearer` header) on every HTTP call. No JWTs SHALL be introduced except for the SSE handshake (design.md D2 / D11). No per-operator identity, OAuth, or SSO SHALL be introduced in v1.

The frontend SHALL obtain its API key from one of three sources:

- Local dev: `VITE_COORDINATOR_API_KEY` baked at build time from a gitignored `.env.local`.
- Cloud-harness browser: manually pasted by the operator into a `localStorage` slot at first use (the harness's network-level auth wall is the primary defense; per-operator identity is deferred).
- Tauri shell: read from the OS keychain via a Tauri command.

The SSE handshake (`POST /events/auth` → short-lived JWT) SHALL use the API-key bearer header on the mint call. The minted JWT SHALL:

- Carry `aud=events`, `exp ≤ 300s`, a fresh single-use `nonce` stored server-side, and the requested `change_ids` bound into the payload.
- Be passed as the `?token=<jwt>` query parameter on the `EventSource` URL (browser `EventSource` cannot attach headers).
- Be validated on every received event; mismatches on aud/exp/nonce/change_ids SHALL reject the stream.
- Be redacted from coordinator access logs as `token=<redacted>`.

The JWT signing key SHALL be sourced from the `COORDINATOR_SSE_SIGNING_KEY` environment variable in v1; integration with OpenBao is a follow-up.

#### Scenario: Frontend reads API key from VITE env at build time

**WHEN** the frontend is built locally with `VITE_COORDINATOR_API_KEY=dev-key-001` in `.env.local`
**THEN** the built bundle SHALL include the key as a build-time constant
**AND** all coordinator calls (except `EventSource` URLs) SHALL include `Authorization: Bearer dev-key-001`

#### Scenario: SSE token signing key absent fails closed

**WHEN** the coordinator boots with `COORDINATOR_SSE_SIGNING_KEY` unset
**THEN** `POST /events/auth` SHALL respond 503 Service Unavailable with a clear error message
**AND** no JWT SHALL be minted
**AND** the `GET /events/work` endpoint SHALL also respond 503 on every request

#### Scenario: Audit identity in v1 is the API-key identity

**WHEN** the operator triggers a UI write action (drag-to-Ready, save-view, force-release lock, kick agent)
**THEN** the resulting `audit_log.agent_id` SHALL be the identity bound to the API key per `COORDINATION_API_KEY_IDENTITIES`
**AND** there SHALL be no per-human identity captured (deferred to a follow-up)

---

### Requirement: CORS Allow-List for Kanban Origins

The coordinator SHALL configure FastAPI's CORS middleware to allow requests from the Kanban frontend origins:

- `Access-Control-Allow-Origin`: the union of `http://localhost:5173` (Vite dev) AND the values of the new `COORDINATOR_CORS_ALLOWED_ORIGINS` env var (CSV) supplied by the deploy.
- `Access-Control-Allow-Methods`: `GET, POST, PATCH, DELETE, OPTIONS`.
- `Access-Control-Allow-Headers`: `Authorization, X-Coordinator-API-Key, X-API-Key, Content-Type` (the legacy `X-API-Key` header is included so backward-compatible callers can keep using it; see task 2.13z).
- `Access-Control-Allow-Credentials`: `false`.
- `Access-Control-Max-Age`: `600`.

Origins not in the allow-list SHALL receive responses without CORS headers (browser SHALL block on its side).

#### Scenario: Allowed origin receives CORS headers

**WHEN** a browser at `http://localhost:5173` issues a `PATCH /issues/{id}/labels` preflight `OPTIONS` request
**THEN** the response SHALL include `Access-Control-Allow-Origin: http://localhost:5173`
**AND** the response SHALL include `Access-Control-Allow-Methods` covering `PATCH`
**AND** the actual `PATCH` SHALL succeed when the API key is valid

#### Scenario: Disallowed origin is blocked client-side

**WHEN** a browser at `http://evil.example/` issues a `PATCH /issues/{id}/labels` preflight `OPTIONS` request
**THEN** the response SHALL NOT include `Access-Control-Allow-Origin: http://evil.example/`
**AND** the browser SHALL block the actual `PATCH` (the coordinator does not need to additionally reject — CORS is enforced client-side)

---

### Requirement: Frontend Packaging

The frontend SHALL be packaged at `apps/kanban-viz/` with the following structure:

- `apps/kanban-viz/package.json` — Vite + React + TypeScript dependencies
- `apps/kanban-viz/src/` — application code
- `apps/kanban-viz/public/` — static assets
- `apps/kanban-viz/src-tauri/` — Tauri scaffold (config + minimal `main.rs`); production build NOT wired into CI in this change
- `apps/kanban-viz/.gitignore` — excludes `dist/`, `node_modules/`, `src-tauri/target/`
- `apps/kanban-viz/README.md` — dev-server instructions, coordinator URL config, Tauri scaffold disclaimer

The frontend SHALL NOT depend on any Tauri-specific API on browser code paths; Tauri capabilities SHALL be feature-detected at runtime.

#### Scenario: Tauri scaffold passes cargo check

**WHEN** an operator runs `cargo check` from `apps/kanban-viz/src-tauri/`
**THEN** the scaffold SHALL compile without errors
**AND** the scaffold SHALL NOT trigger a full Tauri build in this verification

#### Scenario: Browser code paths run without Tauri APIs

**WHEN** the frontend boots in a browser (no Tauri runtime)
**THEN** every feature accessible in the UI (board, swimlanes, banner, save-view) SHALL function
**AND** no `@tauri-apps/api` import SHALL be evaluated at module load time on the browser path

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

### Requirement: Multi-Repository OpenSpec Sources Configuration

The coordinator SHALL read an optional `OPENSPEC_SOURCES` environment variable as a comma-separated list of source descriptors. Each entry SHALL match one of two prefixes:

- `local:<path>` — filesystem-walk source. `<path>` is an absolute or coordinator-relative path to a checkout containing an `openspec/changes/` directory.
- `github:<owner>/<repo>` — GitHub REST API source. The coordinator fetches `openspec/changes/` directory listings via the existing `GITHUB_PAT` (the same credential already used by `GET /github/prs`).

When `OPENSPEC_SOURCES` is unset or empty, the coordinator SHALL treat its own runtime checkout as an implicit `local:.` source — derive `repo` from the checkout's `git remote get-url origin` (lowercase-normalized to `<owner>/<repo>`), falling back to `local/<basename>` (the checkout's directory basename, prefixed with `local/` to preserve owner/repo shape) only when origin parsing fails. This preserves PR #211 wire shape (a single source) AND keeps `ProposalCard.repo` consistent with `PRCard.repo` (which PR #211 derives from `GITHUB_REPOS`), so cross-row clustering by change_id continues to work in single-source mode without forcing the all-null fallback path. `repo` SHALL be `null` only when origin parsing AND basename derivation both fail (an unreachable case in practice; covered by spec scenario "Repo derivation falls back to basename with warning").

The entry parser SHALL validate that `<path>` resolves to an existing directory for `local:` entries, AND that `<owner>/<repo>` matches `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` for `github:` entries (the same regex applied to `GITHUB_REPOS` in PR #211). An invalid entry SHALL cause the endpoint to respond `503` with body `{"error": "openspec_sources_invalid", "message": "<offending entry>"}` and NOT serve partial results from valid entries — failing closed matches the `github_repos_invalid` posture.

The parser SHALL normalize the `<owner>/<repo>` portion to lowercase (matching GitHub's case-insensitive lookup) before storing it in the source registry; the `repo` field on response cards SHALL likewise be lowercase.

#### Scenario: OPENSPEC_SOURCES unset uses implicit local source with derived repo

**WHEN** the coordinator boots with `OPENSPEC_SOURCES` unset AND its own checkout's `git remote get-url origin` returns `https://github.com/JanKneumann/agentic-coding-tools.git` AND a client calls `GET /openspec/proposals`
**THEN** the endpoint SHALL walk the coordinator's own `openspec/changes/` directory (preserving PR #211 wire shape)
**AND** every returned `ProposalCard` SHALL have `repo: "jankneumann/agentic-coding-tools"` (lowercase-normalized from origin)
**AND** `change_id_namespaced` SHALL equal `"jankneumann/agentic-coding-tools/<change-id>"`
**AND** PR #211 cross-row PR↔Proposal clustering by change_id SHALL continue to work because `PRCard.repo` (from `GITHUB_REPOS`) and `ProposalCard.repo` (from origin) lowercase-normalize to the same string for the coordinator's own repo

#### Scenario: OPENSPEC_SOURCES mixes local and github sources

**WHEN** the coordinator boots with `OPENSPEC_SOURCES="local:/repos/agentic-coding-tools,github:jankneumann/newsletter-aggregator"` AND a client calls `GET /openspec/proposals`
**THEN** the response SHALL contain proposals from BOTH sources, merged
**AND** the `repo` field SHALL distinguish them: local source proposals SHALL carry `repo: "jankneumann/agentic-coding-tools"` (resolved via `git remote get-url origin`), github source proposals SHALL carry `repo: "jankneumann/newsletter-aggregator"`

#### Scenario: Invalid OPENSPEC_SOURCES entry fails closed

**WHEN** `OPENSPEC_SOURCES = "local:/repos/valid,github:not_a_valid_entry"` AND a client calls `GET /openspec/proposals`
**THEN** the response status SHALL be `503`
**AND** the response body SHALL include `{"error": "openspec_sources_invalid"}`
**AND** the message SHALL name the offending entry
**AND** the endpoint SHALL NOT return proposals from the valid `local:` entry — fail closed

#### Scenario: Owner/repo casing is normalized to lowercase

**WHEN** `OPENSPEC_SOURCES = "github:JanKneumann/Newsletter-Aggregator"`
**THEN** the stored source SHALL be `github:jankneumann/newsletter-aggregator`
**AND** the response `ProposalCard.repo` field SHALL equal `"jankneumann/newsletter-aggregator"`

---

### Requirement: Hybrid Cache Strategy for Multi-Source Proposals

The endpoint SHALL apply a HYBRID cache strategy across local and github sources:

- **Local sources** SHALL be walked EAGERLY at coordinator boot and re-walked on `?refresh=true`. The walk result is cached in-process until the next boot or refresh; no TTL applies (filesystem walks are sub-millisecond per source and deterministic). EXCEPTION (R1-101): the implicit `local:.` source synthesized when `OPENSPEC_SOURCES` is unset retains PR #211's 60s TTL behavior for byte-identical observable behavior to single-source coordinators. Explicit `local:<path>` entries in `OPENSPEC_SOURCES` use the no-TTL rule above.
- **GitHub sources** SHALL be cached LAZILY per source with a 60-second TTL — the same TTL the PR #211 `GET /github/prs` endpoint uses. The first request to any github source triggers the fetch; subsequent requests within 60s return the cached result.
- **`?refresh=true`** SHALL bust BOTH the local re-walk cache (forcing a fresh filesystem walk for every local source) AND every github source's TTL slot (forcing fresh REST calls).

The cache SHALL coalesce concurrent requests to the same github source via a per-source mutex (single-flight pattern, matching `github_prs_api.py`). Local source re-walks are CPU-bound and short, so no mutex is required; concurrent walks are acceptable.

The response SHALL include `cache_age_seconds` as the MAXIMUM age across all source caches contributing to the response (worst-case freshness signal for the operator), and `source: "live" | "cache" | "mixed"` — `live` if all sources were freshly fetched, `cache` if all were from cache, `mixed` otherwise.

#### Scenario: Local sources warmed at boot

**WHEN** the coordinator boots with `OPENSPEC_SOURCES = "local:/repos/a,local:/repos/b"` AND a client immediately calls `GET /openspec/proposals`
**THEN** the response SHALL contain proposals from both local sources
**AND** no filesystem walk SHALL be triggered by the request — the boot warmup served the data
**AND** `cache_age_seconds` SHALL be ≈ time-since-boot (NOT > 60)

#### Scenario: GitHub source cached lazily after first request

**WHEN** the coordinator boots with `OPENSPEC_SOURCES = "github:owner/repo"` AND a client calls `GET /openspec/proposals` at T=0 and again at T=30 seconds without `?refresh=true`
**THEN** at T=0, exactly one GitHub REST call SHALL be made; the response `source` SHALL equal `"live"`
**AND** at T=30, ZERO GitHub REST calls SHALL be made; the response `source` SHALL equal `"cache"` and `cache_age_seconds` SHALL be approximately `30`

#### Scenario: refresh=true busts both local and github caches

**WHEN** a client calls `GET /openspec/proposals?refresh=true` while local sources have a stale walk AND github sources have a fresh cache
**THEN** every local source SHALL be re-walked
**AND** every github source SHALL be re-fetched
**AND** the response `source` SHALL equal `"live"`

#### Scenario: Mixed source freshness produces mixed source label

**WHEN** the response is assembled from one local source (last walked at boot OR since the previous `?refresh=true`; serves cached otherwise) and one github source still within its 60s TTL
**THEN** the response `source` SHALL equal `"mixed"`
**AND** `cache_age_seconds` SHALL be the MAX age across all contributing source caches (per design D2 / R1-009 — both local-since-walk and github-since-fetch ages are included in the comparison, so the local source can be the worst-case when its last walk pre-dates the github fetch)

---

### Requirement: Multi-Source ProposalCard Fields

The `ProposalCard` shape returned by `GET /openspec/proposals` SHALL be extended with the following fields:

- `repo` (string or null) — the `<owner>/<repo>` identifier of the source this proposal came from. For `github:` sources, this is the lowercase-normalized github source entry. For `local:` sources, this is derived from `git remote get-url origin` (parsed for `owner/repo`), falling back to `local/<basename>` (the checkout's directory basename, prefixed with `local/` to preserve owner/repo shape) if origin parsing fails (a warning is logged on fallback). When `OPENSPEC_SOURCES` is unset, the coordinator's own checkout is treated as an implicit `local:.` source, so `repo` is derived from its own `git remote get-url origin`. `repo` SHALL be `null` only when BOTH origin parsing AND basename derivation are unavailable (rare; e.g., container without git installed AND `Path.name` returns empty string — practically unreachable). This convergence keeps PR #211's cross-row clustering intact: `PRCard.repo` from `GITHUB_REPOS` and `ProposalCard.repo` from the same origin URL normalize to the same lowercase string.
- `change_id_namespaced` (string or null) — equal to `<repo>/<change-id>` when `repo` is non-null, otherwise `null`. Display and debug convenience: the cluster key is computed by the SPA's `getClusterKey` from `<repo>/<bare change_id>` directly (R1-005 + R1-106), NOT by reading this field. The field is included in the response for operator-side debugging and future use cases that need the namespaced form pre-computed.

All other `ProposalCard` fields from PR #211 SHALL be preserved unchanged: `kind`, `id`, `change_id`, `title`, `status`, `created_at_iso`, `updated_at_iso`, `proposal_path`, `has_tasks_md`, `has_design_md`, `has_spec_delta`, `has_branch`, `branch_name`, `code_changes_outside_proposal`.

For `github:` sources, the `proposal_path` SHALL be the github web URL to the `proposal.md` file (`https://github.com/<owner>/<repo>/blob/<branch>/openspec/changes/<change-id>/proposal.md`), NOT a local filesystem path. This lets the SPA render a "View on GitHub" link uniformly. For `local:` sources, `proposal_path` remains a repo-relative path as in PR #211.

For `github:` sources, the `has_branch` + `branch_name` + `code_changes_outside_proposal` fields SHALL be derived by checking the GitHub REST `/repos/{owner}/{repo}/branches/openspec/{change-id}` endpoint (or `claude/{change-id}` if the former 404s) and counting commits via `/repos/{owner}/{repo}/compare/<default_branch>...openspec/{change-id}` with a path filter. The default branch SHALL be resolved per-source by querying `GET /repos/{owner}/{repo}` and reading `default_branch` (R1-107); hardcoding `main` is rejected because configured sources may use `master` or a renamed default. When the branch doesn't exist, `has_branch: false` AND `code_changes_outside_proposal: 0` SHALL be returned.

**GitHub REST field-shape adapter contract:** The `/contents/openspec/changes` endpoint returns a JSON array of objects, each with at least `{name: string, path: string, sha: string, type: "file" | "dir", size: int, url: string, html_url: string, download_url: string | null}`. The fetcher SHALL:
- Filter to entries with `type == "dir"` (skip `archive/` aggregation directory by NAME exclusion).
- For each candidate change-id directory, issue a recursive `/contents/openspec/changes/{change_id}` call to detect `proposal.md`, `tasks.md`, `design.md`, and `specs/` presence — `/contents` does NOT return children-of-children in a single call.
- Treat 404 on `proposal.md` as "skip this directory" (not a hard error — operator may have a stray dir).
- Parse the H1 title from `proposal.md` by base64-decoding the `content` field (the `/contents` endpoint returns content base64-encoded when `Accept: application/vnd.github+json` is used; the `download_url` is an alternative but adds a second roundtrip).
- Build `proposal_path` from the `html_url` of the `proposal.md` entry (NOT manually concatenated — `html_url` is GitHub's canonical anchor and survives default-branch renames).

This adapter contract MUST be exercised by a fixture-driven pytest using a recorded `/contents` payload (analogous to PR #211's `test_github_rest_adapter.py`), to head off the `from_rest_pr`-style field-shape drift that surfaced in PR #211 CRITICAL review.

#### Scenario: ProposalCard from local source has lowercase repo and namespaced id

**WHEN** a local source at `/repos/agentic-coding-tools` is configured AND the repo's `git remote get-url origin` returns `https://github.com/JanKneumann/Agentic-Coding-Tools.git`
**THEN** every `ProposalCard` from that source SHALL have `repo: "jankneumann/agentic-coding-tools"` (lowercase)
**AND** for a change with `change_id: "foo"`, `change_id_namespaced` SHALL equal `"jankneumann/agentic-coding-tools/foo"`

#### Scenario: GitHub-source ProposalCard has github URL in proposal_path

**WHEN** a github source `github:jankneumann/newsletter-aggregator` is configured AND the repo has `openspec/changes/foo/proposal.md` on the default branch (`main`)
**THEN** the returned `ProposalCard.proposal_path` SHALL equal `"https://github.com/jankneumann/newsletter-aggregator/blob/main/openspec/changes/foo/proposal.md"`
**AND** the SPA SHALL render this as a clickable "View on GitHub" link (NOT as a local-path tooltip)

#### Scenario: GitHub-source branch-existence probe used for in-impl detection

**WHEN** a github source has `openspec/changes/bar/proposal.md` AND a branch named `openspec/bar` exists with 3 commits ahead of main, 2 of which touch `coordinator/foo.py`
**THEN** the returned `ProposalCard` SHALL have `has_branch: true`, `branch_name: "openspec/bar"`, `code_changes_outside_proposal: 2`, and `status: "in-impl"`

#### Scenario: Repo derivation falls back to basename with warning

**WHEN** a local source at `/repos/orphan-checkout` has NO git remote configured (or `git remote get-url origin` exits non-zero)
**THEN** the derived `repo` value SHALL be `"local/orphan-checkout"` (the basename of the checkout directory, prefixed with `local/` so the result always has owner/repo shape — R1-004 fix)
**AND** a warning-level log entry SHALL be emitted naming the source and the fallback reason
**AND** the response SHALL still return the proposals from that source — the fallback is non-fatal
**AND** the `local/<basename>` form SHALL satisfy the same `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` regex used by `GITHUB_REPOS` entries, `hidden_repos` saved-view validation, and namespaced cluster keys

---

### Requirement: Repo-Qualified IssueCard Attribution via Label Convention

The SPA SHALL derive `IssueCard.repo` client-side from the issue's `labels` array. The derivation rule:

1. Scan the labels array for the FIRST entry matching the pattern `^repo:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`.
2. Strip the `repo:` prefix.
3. Lowercase the remainder.
4. Use that value as `IssueCard.repo`.

If no matching label is found, `IssueCard.repo` SHALL equal `null`. The derivation SHALL be a pure function with no network or coordinator side effects.

The `work_queue` table SHALL NOT undergo a schema migration. The label convention reuses the existing `labels` array (already a `text[]` column). Skills and agents that want to attribute work to a specific repo write a `repo:<owner>/<repo>` label alongside their other labels using the existing `PATCH /issues/{id}/labels` endpoint.

The coordinator endpoint `GET /issues/list` response shape SHALL be UNCHANGED — the derivation happens entirely SPA-side. This preserves the contract for non-kanban-viz consumers of `/issues/list`.

The SPA SHALL display `IssueCard.repo === null` cards without a repo badge (they participate in clusters via the bare `change_id` fallback documented in the Namespaced Cluster Key requirement).

#### Scenario: Issue with repo label gets a derived repo field

**WHEN** an issue has `labels = ["repo:jankneumann/agentic-coding-tools", "priority:high"]`
**THEN** the SPA's derived `IssueCard.repo` SHALL equal `"jankneumann/agentic-coding-tools"`
**AND** the rendered card SHALL show the RepoBadge with that value

#### Scenario: Issue with no repo label has null repo

**WHEN** an issue has `labels = ["pending-approval", "priority:medium"]` AND no `repo:` prefix entry exists
**THEN** the SPA's derived `IssueCard.repo` SHALL equal `null`
**AND** the card SHALL NOT render a RepoBadge

#### Scenario: Issue with multiple repo labels uses the first

**WHEN** an issue has `labels = ["repo:jankneumann/a", "repo:jankneumann/b"]` (operator error or intentional cross-tagging)
**THEN** the SPA's derived `IssueCard.repo` SHALL equal `"jankneumann/a"` (first occurrence wins)
**AND** a warning SHALL be logged to the browser console naming the issue id and the conflicting labels

#### Scenario: Label casing is normalized to lowercase

**WHEN** an issue has `labels = ["repo:JanKneumann/Agentic-Coding-Tools"]` (mixed case)
**THEN** the derived `IssueCard.repo` SHALL equal `"jankneumann/agentic-coding-tools"` (lowercase)

---

### Requirement: Namespaced Cluster Key Resolution

The SPA's cluster computation function `clusterBoardCards` SHALL key clusters by `change_id_namespaced` (the form `<repo>/<change-id>`) for the standard path, AND SHALL fall back to bare `change_id` ONLY when EVERY card in a candidate cluster has `repo: null` (this is rare in practice — the coordinator derives `repo` from the local checkout even when `OPENSPEC_SOURCES` is unset; the fallback exists for the edge case where derivation fails for every contributing source). Note: the function lives inside `apps/kanban-viz/src/hooks/useBoardCards.ts` (the PR #211 file layout — it is not a standalone `apps/kanban-viz/src/lib/clusterBoardCards.ts`).

This means:

- Cards with non-null repos cluster only when their `<repo>/<change-id>` matches exactly. Two cards with `change_id: "fix-auth"` in DIFFERENT repos do NOT cluster (this is the safety guarantee).
- Cards with `repo: null` cluster by bare `change_id` — preserving PR #211's behavior for single-source coordinators.
- A cluster CANNOT mix repo-null and repo-non-null members. If a candidate cluster would mix them, the function SHALL split into separate clusters (the repo-null group, plus one cluster per distinct repo).

The fallback behavior SHALL be unit-tested against a fixture board containing both pre-multi-repo data (all `repo: null`) AND multi-repo data (all `repo` set) to confirm the back-compat path works without regressing PR #211 behavior.

A future "cross-repo cluster registry" extension (deferred — see proposal Open Questions) would add an OPTIONAL override layer that lets explicit `change_id_aliases` link cards across repos. The current requirement is structured so that registry can layer on without rewriting `clusterBoardCards`'s core key resolution.

#### Scenario: Same-repo cluster uses namespaced key

**WHEN** the board contains an `IssueCard` and a `PRCard` both with `repo: "jankneumann/agentic-coding-tools"` and `change_id: "add-langfuse-tracing"`
**THEN** they SHALL cluster together
**AND** each card's `cluster_count` SHALL equal `2`

#### Scenario: Same change_id across repos does NOT cluster

**WHEN** the board contains a `PRCard` with `repo: "jankneumann/agentic-coding-tools"` and `change_id: "fix-auth"`, AND a `PRCard` with `repo: "jankneumann/newsletter-aggregator"` and `change_id: "fix-auth"`
**THEN** they SHALL NOT cluster together
**AND** each card's `cluster_count` SHALL equal `1` (singleton — no badge rendered)

#### Scenario: All-null-repo cluster falls back to bare change_id

**WHEN** the board contains an `IssueCard`, `PRCard`, `ProposalCard` all with `repo: null` and `change_id: "foo"` (the rare degraded case where origin and basename derivation both failed on every contributing source — e.g., a minimal container without git, or a fixture-driven test)
**THEN** they SHALL cluster together via the bare `change_id` fallback
**AND** each card's `cluster_count` SHALL equal `3`
**AND** this fallback is primarily exercised by test fixtures; in production, the implicit-local-source rule keeps `ProposalCard.repo` non-null

#### Scenario: Mixed null and non-null repos split into separate clusters

**WHEN** the board contains an `IssueCard` with `repo: null, change_id: "foo"` and a `PRCard` with `repo: "x/y", change_id: "foo"`
**THEN** they SHALL NOT cluster together
**AND** the IssueCard's `cluster_count` SHALL equal `1`
**AND** the PRCard's `cluster_count` SHALL equal `1`

---

### Requirement: Per-Card Repo Badge Component

The SPA SHALL render a `RepoBadge` micro-component on `Card` (the existing `apps/kanban-viz/src/components/Card.tsx` issue renderer — PR #211 has no `IssueCardView`), `PRCardView`, and `ProposalCardView` whenever the card's `repo` field is non-null. The badge SHALL:

- Display the short form of the repo (the `<repo>` portion after the `/`) by default.
- On hover, show the full `<owner>/<repo>` as a tooltip.
- Use a deterministic per-repo color derived from a hash of the full `<owner>/<repo>` string (so the same repo always gets the same color across the board, helping operators visually group cards by repo).
- Be accessible — `aria-label` SHALL include the full `<owner>/<repo>` so screen readers don't lose the qualifier.

Cards with `repo: null` SHALL NOT render a RepoBadge. The visual treatment for repo-less cards SHALL remain identical to PR #211 (no behavioral regression for single-source boards).

The hash-to-color function SHALL be deterministic and seeded only by the repo string — no randomization, no per-session state. This makes the visual mapping stable across SPA reloads and across operators sharing the same board.

#### Scenario: RepoBadge renders short form with full tooltip

**WHEN** an `IssueCard` has `repo: "jankneumann/agentic-coding-tools"`
**THEN** the rendered DOM SHALL contain a RepoBadge with visible text `"agentic-coding-tools"`
**AND** the badge's title attribute (tooltip) SHALL equal `"jankneumann/agentic-coding-tools"`
**AND** the badge's `aria-label` SHALL equal `"Repository jankneumann/agentic-coding-tools"`

#### Scenario: Repo-null card omits badge entirely

**WHEN** a `PRCard` has `repo: null`
**THEN** the rendered card SHALL NOT contain any `RepoBadge` element
**AND** the card layout SHALL be visually identical to PR #211's PR card rendering

#### Scenario: Color stable across reloads

**WHEN** an `IssueCard` and `PRCard` both have `repo: "jankneumann/agentic-coding-tools"`
**THEN** their RepoBadges SHALL render with the IDENTICAL background color
**AND** the color SHALL be the same value on every page reload (deterministic, hash-seeded)

---

### Requirement: Hidden Repos Saved-View Field

The coordinator's saved-view JSON schema at `agent-coordinator/src/schemas/kanban_viz/saved-view.json` SHALL be extended with an optional `hidden_repos` field under `view`. The field SHALL be an array of `<owner>/<repo>` strings; cards whose `repo` matches any listed entry SHALL be hidden from the board (across all three rows).

The field SHALL be optional and additive — saved views written prior to this change (with no `hidden_repos`) SHALL continue to validate.

The SPA SHALL provide a UI affordance to toggle a repo's hidden state. A reasonable implementation: clicking a RepoBadge with a modifier key (Shift) hides that repo; a "Visible repos" header chip group exposes the full list of repos that have appeared on the current board with toggle state. The exact UI is left to implementation but the persistence path MUST be the `hidden_repos` saved-view field.

#### Scenario: Saved view with hidden_repos validates

**WHEN** the SPA writes a saved view with `view.hidden_repos = ["jankneumann/scratch-repo"]`
**THEN** the coordinator schema validator SHALL accept the document as valid
**AND** the round-trip via `PUT /kanban-viz/saved-views/{slug}` then `GET` SHALL preserve the field

#### Scenario: Pre-existing saved view continues to validate

**WHEN** a saved view written before this change (with no `hidden_repos`) is loaded
**THEN** the schema validator SHALL accept it
**AND** the SPA SHALL fall back to the default (no repos hidden)

#### Scenario: Hidden repo filters all three rows

**WHEN** the board contains 5 cards from `jankneumann/repo-a` and 3 cards from `jankneumann/repo-b` AND the active saved view has `hidden_repos: ["jankneumann/repo-b"]`
**THEN** only the 5 cards from `repo-a` SHALL be visible
**AND** the row totals SHALL exclude the hidden cards
**AND** cluster computation SHALL exclude hidden cards (no orphan badges referencing hidden siblings)

---

### Requirement: Degraded Multi-Source Mode

When `GET /openspec/proposals` fans out across multiple sources, the endpoint SHALL be resilient to individual source failures. The behavior:

- If a `local:` source path does not exist, walk fails, or has no `openspec/changes/` subdirectory: skip it, emit a `_warnings` entry, return `200 OK` with the surviving sources' proposals.
- If a `github:` source returns 404 (repo not found), 401/403 (PAT lacks access), 5xx (GitHub outage), or times out (per-source timeout 10s): skip it, emit a `_warnings` entry, return `200 OK` with the surviving sources' proposals.
- If ALL configured sources fail: return `200 OK` with `proposals: []` AND a `_warnings` array listing all failures. The SPA renders the Proposals row with an empty state + partial-result chip.

The `_warnings` array SHALL be top-level in the response (sibling to `proposals`), shaped as `Array<{source: string, error: string, status?: integer}>`. Each entry SHALL name the source string (e.g., `"github:jankneumann/repo-x"`) and an error code from the canonical `SourceWarningError` enum: `local_path_missing`, `local_walk_failed`, `github_404`, `github_pat_denied`, `github_timeout`, `github_5xx`, `github_budget_exceeded`. The HTTP status code SHALL be included on the `status` field where applicable. R1-105: PAT-denied responses (401/403) emit `github_pat_denied`, NOT `github_403` — the enum value is the source of truth. Unexpected exceptions during a github fetch (network errors, JSON parse failures, etc.) map to `github_5xx` as the catch-all github-side-fault bucket so the SPA can type-narrow on the contract enum.

The SPA's Proposals row SHALL render a partial-result chip (warning chrome, the same chrome `changes_requested` uses on PR cards) whenever `_warnings.length > 0`. The chip SHALL show on hover or click a list of the failed sources and their errors. This pattern mirrors the per-row error chip behavior already specified for the RefreshButton in PR #211 — same UX vocabulary, different trigger.

Sources MUST be retried independently on the NEXT request (no circuit breaker pinning a source as broken across requests). This keeps the operator's mental model simple: refresh = try everything again.

#### Scenario: One github source 404s, others succeed

**WHEN** `OPENSPEC_SOURCES = "local:/repos/a,github:jankneumann/nonexistent-repo,github:jankneumann/newsletter-aggregator"` AND `jankneumann/nonexistent-repo` returns 404
**THEN** the response status SHALL be `200`
**AND** `proposals` SHALL contain proposals from `local:/repos/a` and `github:jankneumann/newsletter-aggregator` ONLY
**AND** `_warnings` SHALL contain exactly one entry: `{source: "github:jankneumann/nonexistent-repo", error: "github_404", status: 404}`

#### Scenario: All sources fail returns empty with warnings

**WHEN** all configured sources fail (e.g., all `local:` paths missing AND all `github:` repos 404)
**THEN** the response status SHALL be `200`
**AND** `proposals` SHALL equal `[]`
**AND** `_warnings` SHALL contain one entry per failed source
**AND** the SPA Proposals row SHALL render an empty state with a warning chip

#### Scenario: Source timeout produces github_timeout warning

**WHEN** a `github:` source's REST request exceeds the per-source 10s timeout
**THEN** the response SHALL include `_warnings: [{source: "github:owner/repo", error: "github_timeout"}]`
**AND** the surviving sources' proposals SHALL still be returned
**AND** the failed source SHALL be retried on the next request (no circuit breaker)

---

### Requirement: GitHub API Request Budget Cap

Each `github:` source request SHALL impose a per-source budget cap of 50 CHANGES (proposals) per refresh — counted by number of returned `ProposalCard` entries, NOT by raw REST calls (R1-103 reconciliation: earlier draft conflated calls and changes). The implementation SHALL alphabetically sort the directory listing and stop processing additional changes once the 50th proposal is built. If a source has more than 50 changes, the endpoint SHALL emit a `_warnings` entry: `{source: "github:owner/repo", error: "github_budget_exceeded", message: "<N> changes truncated"}` where N is the count of changes beyond the cap.

This protects against runaway calls when a repo has many in-flight changes AND/OR when per-change-id branch-probe recursion expands the underlying REST-call count. 50 is the v1 default; the cap SHALL be configurable via the `OPENSPEC_SOURCES_GITHUB_CAP` env var (integer, default 50, recommended max 200 — a typical refresh issues 3-5 REST calls per change, so 200 changes ≈ 600-1000 calls, well below GitHub's hourly authenticated quota of 5000 which is SHARED across `GET /github/prs` and other coordinator endpoints using the same PAT — R1-108). Raising the cap higher requires accepting that one refresh can consume a meaningful share of the hourly quota.

The truncation behavior SHALL be deterministic: changes are sorted alphabetically by directory name before processing, so the same 50 changes are returned on every refresh until either the cap is raised or the repo's change set shrinks below the cap.

A future change MAY replace REST with a GraphQL batch query (one API call covering the full directory listing + branch state for N changes), which would remove the need for this cap. The cap MUST remain in place for the REST path regardless.

#### Scenario: Source within budget returns all changes

**WHEN** a github source has 30 changes in `openspec/changes/` AND the budget is 50
**THEN** all 30 changes SHALL be returned
**AND** no `github_budget_exceeded` warning SHALL be emitted

#### Scenario: Source exceeds budget returns truncated result

**WHEN** a github source has 80 changes AND the budget is 50
**THEN** the response SHALL include 50 proposals from that source (alphabetically first by `change_id`)
**AND** `_warnings` SHALL contain `{source: "github:owner/repo", error: "github_budget_exceeded", message: "30 changes truncated"}`

#### Scenario: Budget cap configurable via env var

**WHEN** `OPENSPEC_SOURCES_GITHUB_CAP = "100"` AND a github source has 80 changes
**THEN** all 80 changes SHALL be returned
**AND** no `github_budget_exceeded` warning SHALL be emitted

---

### Requirement: Documentation Updates for Multi-Repository Support

`docs/kanban-viz/README.md` SHALL be extended to document:

- `OPENSPEC_SOURCES` env var syntax, including both source type prefixes and the lowercase-normalization behavior.
- Hybrid cache strategy semantics (local at boot, github lazy 60s, refresh busts both).
- The `repo:<owner>/<repo>` label convention for issues — including the casing normalization rule and the "first match wins" tie-breaker.
- The RepoBadge visual treatment and `hidden_repos` saved-view field.
- The degraded-mode `_warnings` behavior and the Proposals row partial-result chip.
- The `OPENSPEC_SOURCES_GITHUB_CAP` env var and its default value.
- A cross-link to the PR #211 `GITHUB_REPOS` documentation so the parallel multi-repo pattern is discoverable from either entry point.

#### Scenario: README documents OPENSPEC_SOURCES alongside GITHUB_REPOS

**WHEN** an operator reads `docs/kanban-viz/README.md` after this change lands
**THEN** the "Environment Variables" section SHALL include `OPENSPEC_SOURCES` with syntax examples for both `local:` and `github:` entries
**AND** a cross-link SHALL point to the `GITHUB_REPOS` section to highlight the parallel pattern

