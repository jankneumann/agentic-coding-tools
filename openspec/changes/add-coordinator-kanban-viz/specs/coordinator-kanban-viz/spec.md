## ADDED Requirements

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

When an `In Flight` card represents a work-package whose children include multiple agents with distinct `agent_profiles.metadata.vendor` values, the card SHALL render mini-lanes — one per distinct vendor — showing the most recent `audit_log` row for that vendor's agent.

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

When `EventSource` cannot establish a connection (browser restriction, proxy stripping `Connection: keep-alive`, Tauri webview limitation), the frontend SHALL transparently fall back to polling `GET /issues?labels=...` and `GET /audit/recent?...` at 5-second intervals.

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
**THEN** the client SHALL transparently fall back to polling `GET /issues?labels=...` at 5-second intervals
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

The endpoint SHALL reuse `shared.check_no_active_agents()` for blocker detection — the logic MUST NOT be duplicated.

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

The endpoint SHALL bind to Postgres `LISTEN` channels (`work_queue_change`, `audit_log_append`) and SHALL filter payloads server-side against the subscription's change-id set.

The endpoint SHALL emit an initial `event: snapshot` on connection.

#### Scenario: Subscription filters server-side by change-id

**WHEN** a client subscribes with `change_ids=add-foo,add-bar` AND a `work_queue` transition occurs for change-id `add-baz`
**THEN** the client SHALL NOT receive an event for the `add-baz` transition
**AND** server-side filter logging SHALL record the suppression for observability

#### Scenario: NOTIFY emission is wired into existing transaction paths

**WHEN** `IssueService.update_status` commits a transaction
**THEN** a `work_queue_change` NOTIFY SHALL fire as part of the same transaction
**AND** the SSE handler SHALL receive the payload via its `LISTEN` subscription

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
