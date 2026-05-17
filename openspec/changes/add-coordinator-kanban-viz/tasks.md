# Tasks — add-coordinator-kanban-viz

> **Bootstrap note:** This change builds on `add-coordinator-task-status-renderer` (archived `2026-05-16-add-coordinator-task-status-renderer`). The renderer's data contract — issue rows with `metadata.task_key`, `metadata.change_id`, `assignee`, `status` — is the canonical issue shape consumed by the frontend's generated types. The archive path is `openspec/changes/archive/2026-05-16-add-coordinator-task-status-renderer/contracts/README.md`.

## Phase 1 — Contracts (wp-contracts)

- [ ] 1.1 Document the three new HTTP endpoints (`/sync-points/status`, `/worktrees/active`, `/events/work`) in `contracts/README.md`
  **Spec scenarios**: coordinator-kanban-viz "New Coordinator Endpoint — Sync-Point Status", "...Worktree Active Projection", "...Work Event Stream (SSE)"
  **Design decisions**: D2 (SSE), D5 (sync-point reuses shared)
  **Dependencies**: None
  **Size**: M

- [ ] 1.2 Author SSE event JSON schemas under `contracts/schemas/events/` (`transition.json`, `audit.json`, `snapshot.json`)
  **Spec scenarios**: "Live Update via SSE with Polling Fallback" (transition propagation, snapshot on reconnect)
  **Design decisions**: D2
  **Dependencies**: 1.1
  **Size**: S

- [ ] 1.3 Author saved-view JSON schema under `contracts/schemas/saved-view.json`
  **Spec scenarios**: "Saved Views with Mandatory Artifact Header"
  **Design decisions**: D7 (saved-view format)
  **Dependencies**: 1.1
  **Size**: S

- [ ] 1.4 Author audit-event JSON schema under `contracts/schemas/audit-event.json`
  **Spec scenarios**: "Reversibility-Classified UI Actions" (save-view audit, force-release consent)
  **Design decisions**: D8 (reversibility table)
  **Dependencies**: 1.1
  **Size**: S

- [ ] 1.5 Author FalkorDB reservation linkage doc at `docs/kanban-viz/falkordb-reservation.md` mirroring the contracts/README.md reservation table
  **Design decisions**: D6 (FalkorDB reservation, no implementation)
  **Dependencies**: 1.1
  **Size**: XS

- [ ] 1.6 Checkpoint: run `openspec validate add-coordinator-kanban-viz --strict`; review contracts/README.md against spec scenarios
  **Dependencies**: 1.1, 1.2, 1.3, 1.4, 1.5

## Phase 2 — Coordinator endpoints (wp-coord-endpoints)

- [ ] 2.1 Write test: `GET /sync-points/status` returns three rows alphabetical by skill
  **Spec scenarios**: "...Sync-Point Status — Endpoint returns one row per sync-point"
  **Contracts**: contracts/README.md (`/sync-points/status` payload)
  **Design decisions**: D5
  **Dependencies**: 1.6
  **Size**: S

- [ ] 2.2 Write test: `/sync-points/status` blocker rows include `kick:<agent_id>` suggested actions
  **Spec scenarios**: "Suggested actions match blocker count"
  **Dependencies**: 1.6
  **Size**: S

- [ ] 2.3 Write test: `GET /worktrees/active` filters stale entries (heartbeat > 1h) but preserves pinned
  **Spec scenarios**: "Endpoint omits stale worktrees", "Pinned worktrees are not filtered as stale"
  **Dependencies**: 1.6
  **Size**: S

- [ ] 2.4 Write test: `GET /events/work` rejects empty `change_ids` with 400
  **Spec scenarios**: SSE subscription scoping (contracts/README.md)
  **Dependencies**: 1.6
  **Size**: S

- [ ] 2.5 Write test: `GET /events/work` emits `event: snapshot` on connection
  **Spec scenarios**: "Reconnection emits a snapshot"
  **Dependencies**: 1.6
  **Size**: M

- [ ] 2.6 Write test: `GET /events/work` filters by subscribed change-ids server-side
  **Spec scenarios**: "Subscription filters server-side by change-id"
  **Dependencies**: 1.6
  **Size**: M

- [ ] 2.0a Write test: vendor extraction from real data: for every `audit_log.agent_id` in the last 24h matching `<wp>--<vendor>` with `<vendor> ∈ {claude,codex,gemini,chatgpt-pro}`, the suffix-parsed vendor is in-set AND (when an `agent_sessions` row exists for that `agent_id`) `agent_sessions.agent_type` maps to the same vendor per the D4 table (`claude_code → claude`, `codex → codex`, `gemini → gemini`, `claude_api → chatgpt-pro` only if so configured). The previous formulation of this test referenced `agent_profiles.metadata.vendor`, which does not exist as a per-agent column — see D4 for the schema reality check.
  **Spec scenarios**: "Vendor Swimlanes on In-Flight Cards" (vendor source-of-truth verification)
  **Design decisions**: D4
  **Dependencies**: 1.6
  **Size**: S

- [ ] 2.7 Write test: SSE handler subscribes to existing `EventBusService` channel `coordinator_task` and dispatches a `transition` SSE event when `IssueService.update` commits a `work_queue` mutation
  **Spec scenarios**: "NOTIFY emission flows through the existing event bus"
  **Dependencies**: 1.6
  **Size**: M

- [ ] 2.7c Write test: new channel `coordinator_audit` is registered on `event_bus.CHANNELS`, its trigger fires on `audit_log` inserts, and SSE handler dispatches a corresponding `audit` SSE event
  **Spec scenarios**: "New coordinator_audit channel is wired into AuditService.append"
  **Dependencies**: 1.6
  **Size**: M

- [ ] 2.7d Write test: `PATCH /issues/{id}/labels` adds and removes labels, returns 200 with updated row, emits an `audit_log` entry
  **Spec scenarios**: "PATCH /issues/{id}/labels adds and removes labels"
  **Design decisions**: D9
  **Dependencies**: 1.6
  **Size**: S

- [ ] 2.7e Write test: `DELETE /locks/{file_path}` force-releases lock held by a different agent, returns `prior_holder_agent_id`, emits an `audit_log` entry
  **Spec scenarios**: "DELETE /locks/{file_path} force-releases a stale lock"
  **Design decisions**: D9
  **Dependencies**: 1.6
  **Size**: S

- [ ] 2.7f Write test: `POST /agents/{agent_id}/kick` clears the agent's entry from `.git-worktrees/.registry.json` (via the worktree teardown helper) AND updates `agent_sessions.status='disconnected'` and `last_heartbeat=epoch`; returns 200 with body `{registry_cleared, agent_sessions_updated, held_locks}`; emits an `audit_log` entry; and a subsequent `check_no_active_agents()` call returns the agent as not-active. Add a second test scenario asserting that file_locks held by the kicked agent are NOT auto-released and ARE surfaced in `held_locks`.
  **Spec scenarios**: "POST /agents/{agent_id}/kick clears worktree registry and updates session", "POST /agents/{agent_id}/kick does NOT auto-release file locks"
  **Design decisions**: D9
  **Dependencies**: 1.6
  **Size**: M

- [ ] 2.7a Write test: `POST /events/auth` mints a JWT with `aud=events`, `exp` within `ttl=300s`, fresh `nonce`, requires `Authorization: Bearer` header
  **Spec scenarios**: contracts/README.md — `GET /events/work` "Auth handshake"
  **Dependencies**: 1.6
  **Size**: M

- [ ] 2.7b Write test: `GET /events/work` rejects requests with missing / expired / wrong-aud / replayed-nonce / change_ids-mismatched JWT (401, stream not opened); access log captures the request line with `token=` redacted
  **Spec scenarios**: contracts/README.md — `GET /events/work` "Auth handshake", "Token-in-URL mitigations"
  **Dependencies**: 1.6
  **Size**: M

- [ ] 2.7g Write test: `PUT /kanban-viz/saved-views/{slug}` writes a saved view to `<WORKDIR_ROOT>/docs/kanban-viz/saved-views/{slug}.json` with server-stamped mandatory artifact header; rejects slugs not matching `^[a-z0-9][a-z0-9-]{0,63}$` with 400; rejects resolved paths escaping `WORKDIR_ROOT` with 400; emits an `audit_log` row.
  **Spec scenarios**: "PUT /kanban-viz/saved-views/{slug} writes a saved view", "Slug with directory traversal is rejected"
  **Design decisions**: D10
  **Dependencies**: 1.6
  **Size**: M

- [ ] 2.7h Write test: `POST /kanban-viz/audit` appends a UI audit event under `<WORKDIR_ROOT>/docs/kanban-viz/audit/<YYYY-MM-DD>/<run_id>.json`; date directory derived server-side from `generated_at` (UTC); same anti-traversal validation as saved-views; emits an `audit_log` row.
  **Spec scenarios**: "POST /kanban-viz/audit appends a UI audit event"
  **Design decisions**: D10
  **Dependencies**: 1.6
  **Size**: M

- [ ] 2.7i Write test: CORS preflight for `PATCH /issues/{id}/labels` from `http://localhost:5173` succeeds with the expected `Access-Control-*` headers (origin, methods include PATCH, headers include `Authorization, X-Coordinator-API-Key, Content-Type`, max-age=600, credentials=false). Preflight from `http://evil.example/` returns response WITHOUT `Access-Control-Allow-Origin` for that origin (browser blocks; server need not additionally reject).
  **Spec scenarios**: "Allowed origin receives CORS headers", "Disallowed origin is blocked client-side"
  **Design decisions**: D12
  **Dependencies**: 1.6
  **Size**: S

- [ ] 2.7j Write test (fail-closed): coordinator booted with `COORDINATOR_SSE_SIGNING_KEY` unset MUST 503 every `POST /events/auth` and `GET /events/work` request; no JWT is minted; the SSE handler refuses to open the stream. Test by spinning up the API with the env var explicitly stripped.
  **Spec scenarios**: "SSE token signing key absent fails closed"
  **Design decisions**: D11
  **Dependencies**: 1.6
  **Size**: S

- [ ] 2.8 Checkpoint: confirm tests 2.0a, 2.1–2.7j RED
  **Dependencies**: 2.0a, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.7a, 2.7b, 2.7c, 2.7d, 2.7e, 2.7f, 2.7g, 2.7h, 2.7i, 2.7j

- [ ] 2.9 Implement `GET /sync-points/status` in `agent-coordinator/src/coordination_api.py` importing `check_no_active_agents` from `skills/shared/active_agents.py` (canonical filename — NOT `check_no_active_agents.py`)
  **Spec scenarios**: "...Sync-Point Status" (all)
  **Design decisions**: D5
  **Dependencies**: 2.8
  **Size**: S

- [ ] 2.10 Implement `GET /worktrees/active` in `coordination_api.py` reading the registry via existing `worktree.py list` JSON output
  **Spec scenarios**: "...Worktree Active Projection" (all)
  **Dependencies**: 2.8
  **Size**: S

- [ ] 2.11 Implement `POST /events/auth` JWT-mint endpoint (header-authenticated; short-lived single-use token bound to `aud=events`, `change_ids`, server-stored `nonce`)
  **Spec scenarios**: contracts/README.md — `GET /events/work` "Auth handshake"
  **Design decisions**: D2
  **Dependencies**: 2.8
  **Size**: M

- [ ] 2.12 Implement `GET /events/work` SSE handler by registering callbacks on the existing `EventBusService` via `event_bus.on_event(channel="coordinator_task", callback=...)` and `event_bus.on_event(channel="coordinator_audit", callback=...)` — do NOT open a parallel Postgres `LISTEN` connection (the contract forbids it and the bus is the single emission point). Use `sse-starlette` or equivalent for the streaming response. Validate JWT from the query string, redact `token=` from access logs, reject on signature/nonce/exp/aud/change_ids mismatch.
  **Spec scenarios**: "...Work Event Stream (SSE)" (all)
  **Design decisions**: D2, "Live update protocol details"
  **Dependencies**: 2.8, 2.11
  **Size**: L

- [ ] 2.13 Add a new `coordinator_audit` LISTEN/NOTIFY channel to `event_bus.CHANNELS`, install the matching Postgres trigger on `audit_log`, and wire `AuditService.append` to emit through the bus. Do NOT add a parallel NOTIFY pathway; the existing `coordinator_task` channel already covers `work_queue` mutations.
  **Spec scenarios**: "NOTIFY emission flows through the existing event bus", "New coordinator_audit channel is wired into AuditService.append"
  **Dependencies**: 2.8
  **Size**: M

- [ ] 2.13a Implement `PATCH /issues/{id}/labels` in `coordination_api.py`, wrapping `IssueService.update` with a labels-only update path
  **Spec scenarios**: "PATCH /issues/{id}/labels adds and removes labels"
  **Design decisions**: D9
  **Dependencies**: 2.8
  **Size**: S

- [ ] 2.13b Implement `DELETE /locks/{file_path:path}` in `coordination_api.py`, calling `locks.release_lock(..., force=True)` and emitting an audit row capturing the prior holder
  **Spec scenarios**: "DELETE /locks/{file_path} force-releases a stale lock"
  **Design decisions**: D9
  **Dependencies**: 2.8
  **Size**: S

- [ ] 2.13c Implement `POST /agents/{agent_id}/kick` in `coordination_api.py`: (a) invoke `skills/worktree/scripts/worktree.py teardown <change_id> --agent-id <id> --force` (or in-process equivalent) to remove the agent's `.git-worktrees/.registry.json` entry — this is the only path that affects `check_no_active_agents()` since the guard reads the on-disk registry, NOT a database table; (b) `UPDATE agent_sessions SET status='disconnected', last_heartbeat='epoch' WHERE agent_id=$1` for coordinator-side discovery; (c) return `{registry_cleared, agent_sessions_updated, held_locks}` so the UI can surface partial failures and locks still held; (d) emit an audit row capturing both side effects.
  **Spec scenarios**: "POST /agents/{agent_id}/kick clears worktree registry and updates session", "POST /agents/{agent_id}/kick does NOT auto-release file locks"
  **Design decisions**: D9
  **Dependencies**: 2.8
  **Size**: S

- [ ] 2.13d Implement `PUT /kanban-viz/saved-views/{slug}` in `coordination_api.py`: validate slug against `^[a-z0-9][a-z0-9-]{0,63}$`; resolve path under the configured `WORKDIR_ROOT`; reject paths escaping the root; stamp the mandatory artifact header server-side; write atomically via tmp-file + rename; emit an `audit_log` row.
  **Spec scenarios**: "PUT /kanban-viz/saved-views/{slug} writes a saved view"
  **Design decisions**: D10
  **Dependencies**: 2.8
  **Size**: M

- [ ] 2.13e Implement `POST /kanban-viz/audit` in `coordination_api.py`: same slug/run-id validation, same `WORKDIR_ROOT` resolution, same atomic-write semantics; derive the date subdirectory server-side from the stamped `generated_at`; emit an `audit_log` row.
  **Spec scenarios**: "POST /kanban-viz/audit appends a UI audit event"
  **Design decisions**: D10
  **Dependencies**: 2.8
  **Size**: M

- [ ] 2.13f Wire FastAPI CORS middleware in `coordination_api.py` with the D12 configuration: `allow_origins` = union of `http://localhost:5173` and `COORDINATOR_CORS_ALLOWED_ORIGINS` env CSV; `allow_methods=[GET, POST, PATCH, DELETE, OPTIONS]`; `allow_headers=[Authorization, X-Coordinator-API-Key, Content-Type]`; `allow_credentials=False`; `max_age=600`.
  **Spec scenarios**: "Allowed origin receives CORS headers", "Disallowed origin is blocked client-side"
  **Design decisions**: D12
  **Dependencies**: 2.8
  **Size**: S

- [ ] 2.13g Add a SQL migration under `agent-coordinator/database/migrations/` (next sequential number) installing a NOTIFY trigger on `audit_log` that emits to the new `coordinator_audit` channel. Mirror the existing `trg_work_queue_notify` pattern in `015_notification_triggers.sql`; respect the `app.coordinator_internal = 'true'` skip flag for the same reason existing triggers do (avoids re-emitting during coordinator-driven inserts).
  **Spec scenarios**: contracts/README.md ("Database schema" sub-type, "One additive migration")
  **Design decisions**: design.md "Live update protocol details"
  **Dependencies**: 2.8
  **Size**: S

- [ ] 2.13h Add fail-closed startup check for `COORDINATOR_SSE_SIGNING_KEY`: if unset, both `POST /events/auth` and `GET /events/work` return 503 from a small dependency wired at startup. The check MUST short-circuit before any JWT decode runs.
  **Spec scenarios**: "SSE token signing key absent fails closed"
  **Design decisions**: D11
  **Dependencies**: 2.8
  **Size**: XS

- [ ] 2.14 Add backpressure coalescing (cap 100 events/sec/connection → snapshot) to SSE handler
  **Spec scenarios**: "Backpressure coalesces excessive events"
  **Dependencies**: 2.12
  **Size**: M

- [ ] 2.15 Confirm tests 2.0a, 2.1–2.7j GREEN
  **Dependencies**: 2.9, 2.10, 2.11, 2.12, 2.13, 2.13a, 2.13b, 2.13c, 2.13d, 2.13e, 2.13f, 2.13g, 2.13h, 2.14
  **Size**: XS

## Phase 3 — Frontend skeleton (wp-frontend-skeleton)

- [ ] 3.1 Scaffold `apps/kanban-viz/` with Vite + React + TypeScript; pin Node version in `.nvmrc`
  **Spec scenarios**: "Frontend Packaging" (structure)
  **Dependencies**: 1.6
  **Size**: S

- [ ] 3.2 Add `apps/kanban-viz/.gitignore` excluding `dist/`, `node_modules/`, `src-tauri/target/`
  **Spec scenarios**: "Frontend Packaging"
  **Dependencies**: 3.1
  **Size**: XS

- [ ] 3.3 Wire TypeScript type generation from coordinator Pydantic models into the build (build fails on stale types)
  **Contracts**: contracts/README.md (Frontend ↔ Coordinator Type Generation)
  **Dependencies**: 1.6
  **Size**: M

- [ ] 3.4 Write test (vitest): empty board renders the three-column structure with explicit empty-state copy in each
  **Spec scenarios**: "Empty column renders an explicit empty state"
  **Dependencies**: 3.1
  **Size**: S

- [ ] 3.5 Write test: card renders with title, change-id, assignee, relative timestamp from a fixture issue
  **Spec scenarios**: "Card shows minimum required fields"
  **Dependencies**: 3.1
  **Size**: S

- [ ] 3.6 Write test: status-to-column mapping bucketing (pending → Backlog, claimed/running → In Flight, completed-within-24h → Done)
  **Spec scenarios**: "Board renders cards bucketed by status"
  **Dependencies**: 3.1
  **Size**: S

- [ ] 3.7 Checkpoint: confirm tests 3.4–3.6 RED
  **Dependencies**: 3.4, 3.5, 3.6

- [ ] 3.8 Implement `Board`, `Column`, `Card` components against fixture data
  **Spec scenarios**: "Three-Column Kanban Board" (all)
  **Dependencies**: 3.7
  **Size**: M

- [ ] 3.9 Implement `useCoordinator()` hook that fetches `POST /issues/list` (body: `{labels: [...]}` — coordinator uses POST-with-body), mints an SSE token via `POST /events/auth` (sending `Authorization: Bearer <api-key>`), and subscribes to `GET /events/work?token=...`
  **Spec scenarios**: "Status transition propagates within 200ms", "Polling fallback engages on EventSource failure"
  **Design decisions**: D2
  **Dependencies**: 3.8, 2.15
  **Size**: M

- [ ] 3.10 Implement polling fallback inside `useCoordinator()` that engages on `EventSource` error
  **Spec scenarios**: "Polling fallback engages on EventSource failure"
  **Dependencies**: 3.9
  **Size**: S

- [ ] 3.11 Confirm tests 3.4–3.6 GREEN; add integration test wiring `useCoordinator()` against a mock SSE server
  **Dependencies**: 3.10
  **Size**: M

## Phase 4 — Vendor swimlanes (wp-frontend-swimlanes)

- [ ] 4.1 Write test: card with one child agent collapses to a single lane labeled with that vendor
  **Spec scenarios**: "Single-vendor card collapses swimlanes"
  **Dependencies**: 3.11
  **Size**: S

- [ ] 4.2 Write test: card with three vendor-diverse child agents renders three lanes sorted alphabetically
  **Spec scenarios**: "Vendor-diverse card renders one lane per vendor"
  **Dependencies**: 3.11
  **Size**: S

- [ ] 4.3 Write test: incoming `event: audit` for a swimlane-rendered agent updates only that lane within 200ms
  **Spec scenarios**: "Lane shows live activity update on SSE event"
  **Dependencies**: 3.11
  **Size**: M

- [ ] 4.4 Write test: completed vendor-diverse work-package collapses to consensus indicator (✓ or ✗)
  **Spec scenarios**: "Completed work-package collapses swimlanes to consensus indicator"
  **Dependencies**: 3.11
  **Size**: S

- [ ] 4.5 Checkpoint: confirm tests 4.1–4.4 RED
  **Dependencies**: 4.1, 4.2, 4.3, 4.4

- [ ] 4.6 Implement `<VendorSwimlanes>` component extracting per-child vendor from the `agent_id` suffix (canonical per D4) and grouping the most-recent `audit_log` row per vendor; agent type comes from `agent_sessions.agent_type` for the secondary cross-check
  **Spec scenarios**: "Vendor Swimlanes on In-Flight Cards" (all)
  **Design decisions**: D4 (swimlane derivation)
  **Dependencies**: 4.5
  **Size**: M

- [ ] 4.7 Implement consensus-indicator collapse using `parallel-infrastructure` consensus synthesizer output
  **Spec scenarios**: "Completed work-package collapses swimlanes to consensus indicator"
  **Dependencies**: 4.6
  **Size**: S

- [ ] 4.8 Confirm tests 4.1–4.4 GREEN
  **Dependencies**: 4.6, 4.7

## Phase 5 — Sync-point gate banner (wp-frontend-sync-banner)

- [ ] 5.1 Write test: banner collapses to single-line green status when all sync-points clear
  **Spec scenarios**: "All sync-points clear"
  **Dependencies**: 3.11

- [ ] 5.2 Write test: banner expands to one row per blocked sync-point with skill, blocker count, heartbeat age, action buttons
  **Spec scenarios**: "Single sync-point blocked by one agent"
  **Dependencies**: 3.11

- [ ] 5.3 Write test: clicking `Kick <agent_id>` surfaces consent prompt and only fires `POST /agents/<id>/kick` after confirm
  **Spec scenarios**: "Kick action requires consent"
  **Dependencies**: 3.11

- [ ] 5.4 Write test: kick action emits audit event regardless of confirm/decline outcome
  **Spec scenarios**: "Kick action requires consent" (audit emission)
  **Dependencies**: 3.11

- [ ] 5.5 Checkpoint: confirm tests 5.1–5.4 RED
  **Dependencies**: 5.1, 5.2, 5.3, 5.4

- [ ] 5.6 Implement `<SyncPointBanner>` component polling `/sync-points/status` every 5s and updating on relevant SSE events
  **Spec scenarios**: "Sync-Point Gate Banner" (all)
  **Design decisions**: D5
  **Dependencies**: 5.5
  **Size**: M

- [ ] 5.7 Implement `<ConsentPrompt>` component invoked by destructive-write actions
  **Spec scenarios**: "Kick action requires consent", "Force-release lock requires consent"
  **Design decisions**: D8
  **Dependencies**: 5.5
  **Size**: S

- [ ] 5.8 Confirm tests 5.1–5.4 GREEN
  **Dependencies**: 5.6, 5.7

## Phase 6 — Saved views and audit emission (wp-saved-views)

- [ ] 6.1 Write test: saved view validates against `contracts/schemas/saved-view.json` and the round-trip (frontend POSTs to `PUT /kanban-viz/saved-views/<slug>`, coordinator writes to `<WORKDIR_ROOT>/docs/kanban-viz/saved-views/<slug>.json`) yields a file containing the server-stamped mandatory header and the operator's view payload
  **Spec scenarios**: "Saved view is valid against the JSON schema", "Saved view file path is git-relative", "PUT /kanban-viz/saved-views/{slug} writes a saved view"
  **Dependencies**: 1.6

- [ ] 6.2 Write test: re-save under same slug overwrites and audit event records prior + new git_sha
  **Spec scenarios**: "Re-save under same name overwrites with audit trail"
  **Dependencies**: 1.6

- [ ] 6.3 Write test: save-view emits a UI audit event via `POST /kanban-viz/audit` (browser path) or Tauri `fs.writeTextFile` (Tauri path); the resulting file under `docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json` has the server-stamped mandatory header and `class: reversible-write`
  **Spec scenarios**: "Save-view emits an audit event", "POST /kanban-viz/audit appends a UI audit event"
  **Design decisions**: D8, D10
  **Dependencies**: 1.6

- [ ] 6.4 Write test: drag-to-Ready calls `PATCH /issues/<id>/labels` with `pending-approval` and emits reversible-write audit event
  **Spec scenarios**: "Drag-to-Ready sets pending-approval label"
  **Dependencies**: 1.6

- [ ] 6.5 Checkpoint: confirm tests 6.1–6.4 RED
  **Dependencies**: 6.1, 6.2, 6.3, 6.4

- [ ] 6.6 Implement `saveView()` function that POSTs to `PUT /kanban-viz/saved-views/{slug}` (browser path) and falls back to Tauri `fs.writeTextFile` (Tauri path); the coordinator endpoint owns the on-disk write so the function does NOT manipulate the filesystem from the browser
  **Spec scenarios**: "Saved Views with Mandatory Artifact Header" (all), "Tauri frontend bypasses coordinator file-write endpoints"
  **Design decisions**: D7, D10
  **Dependencies**: 6.5, 2.15
  **Size**: M

- [ ] 6.7 Implement `<SavedViewsDrawer>` UI for list/save/load
  **Dependencies**: 6.6
  **Size**: M

- [ ] 6.8 Implement drag-to-Ready interaction with reversible-write audit emission
  **Spec scenarios**: "Drag-to-Ready sets pending-approval label"
  **Dependencies**: 6.5
  **Size**: M

- [ ] 6.9 Implement reversibility classifier `apps/kanban-viz/src/lib/reversibility.ts` with the D8 table; comment pointing to `skills/shared/op_reversibility.py` (codeviz reservation)
  **Spec scenarios**: "Reversibility-Classified UI Actions"
  **Design decisions**: D8
  **Dependencies**: 6.5
  **Size**: S

- [ ] 6.10 Confirm tests 6.1–6.4 GREEN
  **Dependencies**: 6.6, 6.7, 6.8, 6.9

## Phase 7 — Tauri scaffold (wp-tauri-scaffold)

- [ ] 7.1 Scaffold `apps/kanban-viz/src-tauri/` with Tauri 2.x `Cargo.toml`, `tauri.conf.json` (allowlist `http.request` only, deny everything else), minimal `main.rs`, and `.gitignore` for `target/`
  **Spec scenarios**: "Frontend Packaging" (Tauri scaffold), "Tauri scaffold passes cargo check"
  **Design decisions**: design.md "Tauri-readiness checklist"
  **Dependencies**: 3.1
  **Size**: S

- [ ] 7.2 Write test: `cargo check` succeeds in `apps/kanban-viz/src-tauri/`
  **Spec scenarios**: "Tauri scaffold passes cargo check"
  **Dependencies**: 7.1
  **Size**: S

- [ ] 7.3 Add runtime feature-detect for Tauri APIs in `apps/kanban-viz/src/lib/runtime.ts`
  **Spec scenarios**: "Browser code paths run without Tauri APIs"
  **Dependencies**: 3.1
  **Size**: S

- [ ] 7.4 Write test: browser path of every UI surface (board, swimlanes, banner, save-view) functions without `@tauri-apps/api` import being evaluated
  **Spec scenarios**: "Browser code paths run without Tauri APIs"
  **Dependencies**: 7.3
  **Size**: M

- [ ] 7.5 Confirm tests 7.2 and 7.4 GREEN
  **Dependencies**: 7.2, 7.4

## Phase 8 — Integration, docs, and validation (wp-integration)

- [ ] 8.1 End-to-end test: launch coordinator + kanban-viz, seed fixture issues across statuses, drive a transition, assert UI updates within 200ms
  **Spec scenarios**: composite (board, swimlane update, sync-point banner, save-view audit)
  **Dependencies**: 2.15, 3.11, 4.8, 5.8, 6.10, 7.5
  **Size**: L

- [ ] 8.2 Confirm e2e test GREEN
  **Dependencies**: 8.1
  **Size**: XS

- [ ] 8.3 Update `docs/skills-catalogue.md` if the Kanban viz is to be discoverable from the skills index (probably listed under "frontends")
  **Dependencies**: 8.2
  **Size**: XS

- [ ] 8.4 Add `docs/kanban-viz/README.md` with dev-server instructions, coordinator URL config, Tauri scaffold disclaimer
  **Dependencies**: 8.2
  **Size**: S

- [ ] 8.5 Add a brief note to `CLAUDE.md` "Workflow" section if appropriate (the Kanban is an observability surface, not a skill)
  **Dependencies**: 8.2
  **Size**: XS

- [ ] 8.6 Final checkpoint: run `openspec validate add-coordinator-kanban-viz --strict`; run `python3 skills/validate-packages/scripts/validate_work_packages.py openspec/changes/add-coordinator-kanban-viz/work-packages.yaml`; run frontend test suite + coordinator endpoint tests
  **Dependencies**: 8.3, 8.4, 8.5
