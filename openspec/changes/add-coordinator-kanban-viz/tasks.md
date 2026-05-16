# Tasks — add-coordinator-kanban-viz

> **Bootstrap note:** This change depends on `add-coordinator-task-status-renderer` having merged so the renderer's data contract is the canonical issue shape consumed by the frontend's generated types. If the renderer change is not yet merged at implementation start, `wp-contracts` SHALL stub the issue type from a pinned snapshot and `wp-frontend-skeleton` SHALL re-pin once the renderer lands.

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

- [ ] 2.7 Write test: NOTIFY emission wired into `IssueService.update_status` transaction path
  **Spec scenarios**: "NOTIFY emission is wired into existing transaction paths"
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

- [ ] 2.8 Checkpoint: confirm tests 2.1–2.7b RED
  **Dependencies**: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.7a, 2.7b

- [ ] 2.9 Implement `GET /sync-points/status` in `agent-coordinator/src/coordination_api.py` reusing `shared.check_no_active_agents()`
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

- [ ] 2.12 Implement `GET /events/work` SSE handler with Postgres `LISTEN` binding (use `sse-starlette` or equivalent); validate JWT from query string, redact `token=` from access logs, reject on signature/nonce/exp/aud mismatch
  **Spec scenarios**: "...Work Event Stream (SSE)" (all)
  **Design decisions**: D2
  **Dependencies**: 2.8, 2.11
  **Size**: L

- [ ] 2.13 Add NOTIFY emission to `IssueService.update_status` and `AuditService.append`
  **Spec scenarios**: "NOTIFY emission is wired into existing transaction paths"
  **Dependencies**: 2.8
  **Size**: M

- [ ] 2.14 Add backpressure coalescing (cap 100 events/sec/connection → snapshot) to SSE handler
  **Spec scenarios**: "Backpressure coalesces excessive events"
  **Dependencies**: 2.12
  **Size**: M

- [ ] 2.15 Confirm tests 2.1–2.7 GREEN
  **Dependencies**: 2.9, 2.10, 2.11, 2.12, 2.13, 2.14
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

- [ ] 3.9 Implement `useCoordinator()` hook that fetches `GET /issues?labels=...`, mints an SSE token via `POST /events/auth`, and subscribes to `GET /events/work?token=...`
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

- [ ] 4.6 Implement `<VendorSwimlanes>` component sourcing children from `agent_profiles.metadata.vendor` and most-recent `audit_log` row per vendor
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

- [ ] 6.1 Write test: saved view validates against `contracts/schemas/saved-view.json` and is written to `docs/kanban-viz/saved-views/<slug>.json`
  **Spec scenarios**: "Saved view is valid against the JSON schema", "Saved view file path is git-relative"
  **Dependencies**: 1.6

- [ ] 6.2 Write test: re-save under same slug overwrites and audit event records prior + new git_sha
  **Spec scenarios**: "Re-save under same name overwrites with audit trail"
  **Dependencies**: 1.6

- [ ] 6.3 Write test: save-view emits audit event under `docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json` with mandatory header and `class: reversible-write`
  **Spec scenarios**: "Save-view emits an audit event"
  **Design decisions**: D8
  **Dependencies**: 1.6

- [ ] 6.4 Write test: drag-to-Ready calls `PATCH /issues/<id>/labels` with `pending-approval` and emits reversible-write audit event
  **Spec scenarios**: "Drag-to-Ready sets pending-approval label"
  **Dependencies**: 1.6

- [ ] 6.5 Checkpoint: confirm tests 6.1–6.4 RED
  **Dependencies**: 6.1, 6.2, 6.3, 6.4

- [ ] 6.6 Implement `saveView()` function that writes the file and emits the audit event
  **Spec scenarios**: "Saved Views with Mandatory Artifact Header" (all)
  **Design decisions**: D7
  **Dependencies**: 6.5
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
