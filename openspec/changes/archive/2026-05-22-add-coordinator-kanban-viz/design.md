# Design — Coordinator Kanban Visualization (MVP)

## Goals and non-goals

**Goal.** Make multi-agent coordinator state legible at a glance — operators should be able to answer "what's running, who's stuck, why won't this merge" in under five seconds without leaving the board.

**Non-goal.** Replacing logs, replacing the coordinator HTTP API as a scripting surface, replacing `tasks.md` as the change-scoped narrative artifact, or building the full codeviz frontend ahead of codeviz. The Kanban is a small, dedicated lens on `work_queue` + `audit_log` + `file_locks` + `.git-worktrees/.registry.json`; everything broader (graph, time-travel, lock heatmap, cross-repo) is deferred.

## Architecture at a glance

```
┌──────────────────────────────────────────────────────────────────────┐
│ Browser (or Tauri shell — same React app)                              │
│                                                                        │
│  apps/kanban-viz/src/                                                  │
│  ├─ Board (3 columns: Backlog / In Flight / Done)                      │
│  ├─ Card (with vendor swimlane component when in-flight)               │
│  ├─ SyncPointBanner (pinned top)                                       │
│  ├─ SavedViewsDrawer                                                   │
│  └─ EventStream (SSE connection, polling fallback)                     │
└────────────────────────┬─────────────────────────────────────────────┘
                         │ HTTPS / SSE
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ agent-coordinator FastAPI (existing, nine new endpoints — see D9+D10) │
│                                                                        │
│  Existing (consumed unchanged):                                       │
│   POST /issues/list                        (issue list with labels    │
│                                             filter — coordinator uses │
│                                             POST-with-body, not       │
│                                             GET-with-query)           │
│   GET /audit                               (audit rows; query-string  │
│                                             scoped via existing       │
│                                             AuditService.query)       │
│   GET /discovery/agents                    (active agents per         │
│                                             heartbeat-recency)        │
│   POST /work/submit                        (existing — used for       │
│                                             pending-approval flag)    │
│                                                                        │
│  New (added in this change):                                          │
│   POST /events/auth                        (mint short-lived JWT)     │
│   GET /events/work?change_ids=<csv>&token=…(SSE: transition, audit)  │
│   GET /sync-points/status                  (banner blockers)          │
│   GET /worktrees/active                    (registry projection)      │
│   PATCH /issues/{id}/labels                (drag-to-Ready writes)     │
│   DELETE /locks/{file_path:path}           (force-release lock)       │
│   POST /agents/{agent_id}/kick             (sync-point banner kick)   │
└────────────────────────┬─────────────────────────────────────────────┘
                         ▼
                   Postgres (work_queue, audit_log, file_locks,
                            agent_sessions, agent_profiles,
                            agent_profile_assignments)
                   .git-worktrees/.registry.json (read/write via
                                                  worktree.py for kick)

(Disk artifacts written by the frontend, served via a tiny static-file
 endpoint or git-committed directly:)
   docs/kanban-viz/saved-views/<name>.json     (mandatory header)
   docs/kanban-viz/audit/<YYYY-MM-DD>/<id>.json (mandatory header,
                                                  event-class)
```

The frontend never bypasses the coordinator. The coordinator never imports from the frontend. The boundary is the OpenAPI surface plus the SSE event payload schema (both specified in `contracts/README.md`).

## Decisions

### D1: Web app at `apps/kanban-viz/`, not under `agent-coordinator/`

The frontend lives in a sibling top-level directory, not nested inside the coordinator's Python package. Reasons: (1) different toolchain (Node vs uv-managed Python) shouldn't pollute coordinator install paths; (2) codeviz will eventually share this directory tree as `apps/codeviz-viz/` or merge into `apps/viz/` — establishing the `apps/` convention now is cheaper than relocating later; (3) a static-build artifact in `apps/kanban-viz/dist/` is cleanly servable from anywhere (including the Tauri shell) without coordinator coupling.

### D2: Server-Sent Events, not WebSocket, for live updates

Live updates flow one direction (server → client). SSE is HTTP/1.1-native, traverses proxies cleanly, and has a tiny client surface (`new EventSource(url)`). WebSocket adds bidirectional framing, ping/pong, and reconnection complexity for no UX benefit on a read-mostly board.

SSE has a known auth-surface gap: browser `EventSource` cannot attach arbitrary headers (HTML Living Standard exposes only `withCredentials`), so the API-key `Authorization: Bearer` flow used by the other endpoints does NOT carry over. We mint a short-lived single-use JWT via `POST /events/auth` and pass it as `?token=<jwt>` on the `EventSource` URL. Mitigations (log redaction, `Referrer-Policy: no-referrer`, server-side nonce store, key separation) are specified in `contracts/README.md` under the `GET /events/work` section. WebSocket would not change this: any browser auth handshake on a stream channel hits the same headers-on-handshake limitation.

The single SSE endpoint (`GET /events/work?change_ids=<csv>`) emits two event kinds:

```
event: transition
data: {"work_queue_id": "...", "from": "claimed", "to": "running",
       "agent_id": "wp-backend", "ts": "2026-05-15T10:42:13Z"}

event: audit
data: {"audit_id": "...", "agent_id": "wp-backend", "operation": "edit_file",
       "args_summary": "src/foo.py +42 -8", "ts": "2026-05-15T10:42:14Z"}
```

The client maintains a per-change-id subscription set; the server filters at emit time using the existing `IssueService` label filter applied to the underlying `work_queue` row.

**Polling fallback.** If `EventSource` cannot establish a connection (rare in browsers; possible in Tauri's webview if a proxy strips the `Connection: keep-alive` header), the client falls back to polling the existing coordinator read endpoints at 5s intervals: `POST /issues/list` (the coordinator uses POST-with-body for the labels-filtered list, not GET-with-query) and `GET /audit?since=<iso>&change_id=<id>&limit=<n>` (extended endpoint — see below). The fallback is invisible to the rest of the UI.

**Audit-endpoint extension required.** The current `GET /audit` handler (`coordination_api.py:1146`) accepts only `agent_id`, `operation`, and `limit`; `AuditService.query` likewise has no `since` or `change_id` filter. This change adds both filters (as a small precursor task in scope) so the polling fallback is implementable. The `change_id` filter joins to `work_queue` via the audit row's `parameters` JSONB column (which records the change_id on every relevant call site) or, where not present, falls back to the `agent_id` → `agent_sessions.change_id` mapping. The `since` filter is a simple `created_at >= $N` predicate. The extension keeps the existing query shape backward-compatible (all new params optional, default to no filter).

### D3: No JSON sidecar mirror of `work_queue` state

The temptation is to maintain a `docs/kanban-viz/state.json` that mirrors current board state, so the Kanban can render before reaching the coordinator. We reject this: it duplicates the source of truth, introduces a sync problem identical to the one `add-coordinator-task-status-renderer` was created to solve, and violates the codeviz storage-tier policy (work_queue state is mutable, queryable, and properly lives in Postgres).

The only on-disk artifacts the Kanban writes are **saved views** (small, diffable, user-curated → git-committed under `docs/kanban-viz/saved-views/`) and **audit events** (event-class, dated paths under `docs/kanban-viz/audit/<YYYY-MM-DD>/`). Both carry the codeviz mandatory artifact header; both are properly classified per the codeviz storage-tier policy.

### D4: Vendor swimlanes derived from `agent_id` suffix (canonical) with `agent_sessions.agent_type` as secondary cross-check

A work-package in vendor-diverse parallel-review mode forks N agents whose `agent_id`s follow the established `<wp>--<vendor>` convention (`wp-review--claude`, `wp-review--gemini`, `wp-review--codex` per CLAUDE.md "branch naming" rule).

**Schema reality check.** Earlier revisions of this design proposed `agent_profiles.metadata.vendor` as the per-agent source-of-truth. That is wrong: `agent_profiles` is a profile-**template** table keyed by a unique `name` (one row per profile like `claude_code_default`), with `agent_profile_assignments` mapping `agent_id → profile_id`. There is no per-agent `metadata` column anywhere in the live schema. Active per-agent rows live in `agent_sessions` (extended by `database/migrations/003_agent_discovery.sql`) and carry `agent_type` (e.g. `claude_code`, `codex`, `gemini`) plus `capabilities[]`, `status`, `last_heartbeat`. The vendor design uses these existing per-agent columns; it does NOT require a new column.

**Vendor-extraction precedence (specified to avoid runtime ambiguity):**
1. **Canonical:** parse the suffix after `--` from `agent_id` and validate against the closed set `{claude, codex, gemini, chatgpt-pro}`. The naming convention is enforced by the parallel-review dispatchers, so a missing or malformed suffix already indicates an off-convention agent that should not appear as a vendor lane.
2. **Cross-check (degrade gracefully):** if the suffix-parsed vendor disagrees with `agent_sessions.agent_type` (mapped: `claude_code → claude`, `codex → codex`, `gemini → gemini`, `claude_api → chatgpt-pro` only if explicitly configured), prefer the `agent_id` suffix and emit a warning row in `audit_log` for operator investigation. Disagreement is a signal of dispatcher bug, not a normal case.
3. **Fallback for unmatched suffixes:** render under a generic `other` lane rather than crash.

Note that `agent_sessions.metadata` is **not** a column today (003 only adds `capabilities`, `status`, `last_heartbeat`, `current_task`). Introducing a new column would be a schema migration — explicitly out of scope for this change.

The swimlane component groups `audit_log` rows by extracted vendor and renders the most-recent-row's `args_summary` as a one-line "what is this vendor doing now" string. When a card's underlying work-package is *not* in vendor-diverse mode (single-agent run), the swimlanes collapse to a single lane labeled with the lone vendor.

**Replaces previous test 2.0a (which referenced a non-existent column).** The new wp-coord-endpoints verification test (still numbered 2.0a) asserts that for every recent `audit_log.agent_id` matching `<wp>--<vendor>`, the suffix-parsed vendor matches the in-set value, AND `agent_sessions.agent_type` for that `agent_id` (if a session row exists) maps to the same vendor under the table above. The test exercises real data, not a hypothetical column.

### D5: Sync-point banner reuses `skills.shared.active_agents.check_no_active_agents()`

The active-agent guard for `/cleanup-feature`, `/merge-pull-requests`, and `/update-specs` is centralized in `skills/shared/active_agents.py` (per CLAUDE.md; the canonical filename is `active_agents.py`, the function inside it is `check_no_active_agents()`). The new `/sync-points/status` endpoint imports the same function — no logic duplication. The endpoint enumerates the three sync-point skills and returns a list of `{skill, blocked, blockers, suggested_actions}`.

**Import path from the coordinator.** The coordinator is a Python package living next to `skills/`; the new endpoint resolves `skills/shared/active_agents.py` via a sys.path-anchored helper introduced by this change (mirroring how `worktree.py` is imported from coordinator-side scripts). The endpoint MUST NOT vendor or copy the function, and MUST NOT depend on a separate worktree path — the import is by relative module path under the shared-skills installation.

`suggested_actions` is opinionated: when blockers exist, the endpoint returns `["wait", "kick:<agent_id>"]`. The frontend renders these as buttons. `kick` is destructive-write; clicking it surfaces a per-operation consent prompt before issuing `POST /agents/<id>/kick` (existing endpoint).

### D6: Reservation block for FalkorDB work-state schema (no implementation in v1)

When codeviz Phase 0 lands FalkorDB ingestion, the Kanban's data should ingest naturally. To prevent a later rename pass, we **reserve** the following labels and edge types now in `docs/kanban-viz/falkordb-reservation.md`:

**Node labels reserved:**
- `WorkPackage` — one per `work_queue` row
- `Agent` — one per `agent_profiles` row
- `Vendor` — `claude`, `codex`, `gemini`, `chatgpt-pro`
- `Worktree` — one per `.git-worktrees/.registry.json` entry
- `Lock` — one per `file_locks` row
- `SyncPoint` — `cleanup-feature`, `merge-pull-requests`, `update-specs`
- `AuditEvent` — one per `audit_log` row

**Edge types reserved:**
- `CLAIMED_BY` (WorkPackage → Agent)
- `BLOCKED_ON` (WorkPackage → WorkPackage)
- `LOCKS_FILE` (Agent → File)  *(File node from codeviz)*
- `WORKING_IN` (Agent → Worktree)
- `RAN_BY` (AuditEvent → Agent)
- `BLOCKS_SYNCPOINT` (Agent → SyncPoint)
- `IMPLEMENTS_TASK` (WorkPackage → Symbol)  *(Symbol node from codeviz)*

Codeviz Phase 0 ingestion can adopt these without coordination overhead. The Kanban does not write to FalkorDB in v1.

### D7: Saved views as committed JSON with mandatory artifact header

A "saved view" captures: column filter (e.g., `change_id IN [...]`), grouping (e.g., `group by vendor`), sort, and selected card. Stored at `docs/kanban-viz/saved-views/<view-name>.json`:

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-15T10:42:13Z",
  "git_sha": "<commit at save time>",
  "generator": "kanban-viz@0.1.0",
  "view": {
    "name": "Active reviews — security",
    "columns": {"Backlog": {...}, "In Flight": {...}, "Done": {...}},
    "filters": {"change_ids": ["..."], "vendors": ["claude", "gemini"]},
    "grouping": "vendor",
    "sort": {"key": "claimed_at", "dir": "desc"}
  }
}
```

Reversible-write per codeviz reversibility taxonomy: creating a view is auto-allowed (operator is human or scoped-session agent), deleting is reversible (the file is recoverable from git history). Overwriting an existing view's content with a different definition is also reversible-write — the prior content is in git.

### D8: Reversibility classification table for Kanban actions

Every action the UI exposes is classified per the codeviz `Operation Reversibility Taxonomy` and gated accordingly:

| UI action | Coordinator call | Class | Gating |
|---|---|---|---|
| Open the board | `POST /issues/list` (existing — coordinator uses POST-with-body for labels-filtered list) | read | auto-allowed |
| Subscribe to events for a change | `GET /events/work` | read | auto-allowed |
| Read sync-point status | `GET /sync-points/status` | read | auto-allowed |
| Save a view | write file under `docs/kanban-viz/saved-views/` | reversible-write | auto-allowed; audit emitted |
| Drag a Backlog card → Ready (set pending-approval flag) | `PATCH /issues/<id>/labels` to add `pending-approval` | reversible-write | auto-allowed for human operator; agent requires scoped session; audit emitted |
| Force-release a stale lock | `DELETE /locks/<file_path>` | destructive-write | per-action consent prompt; audit emitted |
| Kick a stale agent (sync-point banner action) | `POST /agents/<id>/kick` | destructive-write | per-action consent prompt; audit emitted |

Audit emission goes to `docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json` (event-class artifact, mandatory header).

The classifier is **not duplicated**; the frontend imports a small TypeScript translation of the centralized `skills/shared/op_reversibility.py` rules (reservation in codeviz). For v1, the classification table above is hard-coded in `apps/kanban-viz/src/lib/reversibility.ts` with a comment pointing to the shared module so the duplication is intentional and easy to converge once codeviz ships the shared classifier.

### D9: Three new coordinator write endpoints required by v1 UI actions

The previous revision of this design treated `PATCH /issues/{id}/labels`, `DELETE /locks/{file_path}`, and `POST /agents/{agent_id}/kick` as if they were existing endpoints. They are not — `coordination_api.py` does not currently define them. They are introduced here, in this change, alongside the read endpoints, because:

- **`PATCH /issues/{id}/labels`** — adds/removes labels on a `work_queue` row. Wraps `IssueService.update` (existing) with a label-only update path. Reuses the existing labels JSONB column. Reversibility: reversible-write.
- **`DELETE /locks/{file_path:path}`** — force-releases a stale lock entry. The existing `LockService.release()` (in `agent-coordinator/src/locks.py:276–339`) delegates to the Postgres `release_lock(...)` RPC which enforces holder-only semantics, so it cannot be reused as-is for force-release. This change adds a sibling Python method `LockService.force_release(file_path) -> {released, prior_holder}` that runs an inline parameterized `DELETE FROM file_locks WHERE file_path=$1`, captures the prior holder for the audit row, and returns it. The holder-only check stays intact on the normal release path; force-release is a separate, explicitly-audited method. Reversibility: destructive-write.
- **`POST /agents/{agent_id}/kick`** — marks a stale agent's worktree-registry entry as dead so the sync-point gate (`/cleanup-feature`, `/merge-pull-requests`, `/update-specs`) stops blocking on it. **Semantics correction.** The previous revision said this endpoint should set `last_heartbeat = epoch` on `agent_discovery` and that `check_no_active_agents()` would then ignore the agent — both halves of that claim are wrong:
  1. There is no `agent_discovery` table. Coordinator discovery rows live in `agent_sessions` (extended by `database/migrations/003_agent_discovery.sql`), keyed by `id`/`agent_id` with `last_heartbeat`/`status` columns.
  2. `skills.shared.active_agents.check_no_active_agents()` does NOT read coordinator tables. It reads `.git-worktrees/.registry.json` (see `skills/shared/active_agents.py`, `REGISTRY_RELATIVE_PATH`). Writing to `agent_sessions` would therefore have zero effect on the sync-point banner.

  **Corrected implementation.** The endpoint request body MUST include `change_id` (registry is keyed by `(change_id, agent_id)`; reject with 422 if absent). It then clears the agent's entry from `.git-worktrees/.registry.json` by shelling out to `python3 skills/worktree/scripts/worktree.py teardown <change_id> --agent-id <agent_id> --force` (or equivalently invoking its `teardown` library function in-process if the coordinator and worktree scripts share an interpreter). The `--force` flag on `teardown` does not exist today and is added as a precursor task (2.13c0 in tasks.md) to this endpoint. It additionally updates `agent_sessions.status = 'disconnected'` and `last_heartbeat = epoch` so the coordinator's own discovery view also stops listing the agent as active. The endpoint emits an `audit_log` row capturing both side effects, and the response body includes `{"registry_cleared": bool, "agent_sessions_updated": bool, "held_locks": list[str]}` so the UI can surface partial-failure cases and locks still held. Reversibility: destructive-write.

  **Cleanup contract.** Force-kicking does NOT release file locks held by the kicked agent; the operator must additionally force-release each lock through `DELETE /locks/{file_path:path}` or accept that the locks expire on the normal TTL. The endpoint's response includes `held_locks: list[str]` so the UI can surface the locks-still-held case and prompt for follow-up.

Each endpoint reuses an existing service module; no duplicated transaction logic is introduced. The endpoints are added to `wp-coord-endpoints` (Phase 2) rather than scoped to a separate work-package because they share the same locks (coord-endpoints file set) and the same reviewer.

## Storage alignment with codeviz tier policy

Per `openspec/roadmaps/codeviz/proposal.md` "Mandatory artifact header" (proposal lines 88 and 109; the previous reference to "lines 49–56" was incorrect — those lines describe a different topic):

| Artifact | Tier | Path | Diffable? |
|---|---|---|---|
| Saved views | Git (committed) | `docs/kanban-viz/saved-views/<name>.json` | Yes |
| Audit events from UI actions | Event-artifact dated path (committed-but-bounded) | `docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json` | Yes; 90-day retention |
| FalkorDB reservation doc | Linkage (committed) | `docs/kanban-viz/falkordb-reservation.md` | Yes |
| Frontend build artifacts | Local cache (.gitignored) | `apps/kanban-viz/dist/`, `apps/kanban-viz/node_modules/` | No |
| Tauri build artifacts | Local cache (.gitignored) | `apps/kanban-viz/src-tauri/target/` | No |
| Per-session SSE state | In-memory, never persisted | n/a | n/a |

CI lint (codeviz Phase 0 `artifact-classification` capability) will refuse PRs that commit anything from the local-cache row. The Kanban's `.gitignore` entries prevent the common accidents (`dist/`, `node_modules/`, Tauri's `target/`).

## Live update protocol details

**Subscription model.** The client opens one SSE connection with `change_ids=<csv>` query string. The server-side handler registers callbacks on the existing `agent-coordinator/src/event_bus.py` multi-channel LISTEN/NOTIFY bus via `EventBusService.on_event(channel, callback)` (the canonical API surface — there is no `subscribe()` method; do not invent one):

- The **existing `coordinator_task` channel** carries `work_queue` mutations (this change does not need to add a new channel for transitions — the bus already covers it; the SSE handler just translates `CoordinatorEvent` payloads into the `event: transition` SSE wire format).
- A **new `coordinator_audit` channel** is added by this change for `audit_log` appends. This is a small extension: append `"coordinator_audit"` to `event_bus.CHANNELS`, add the matching trigger on `audit_log` mirroring the existing `work_queue` trigger pattern, and add a one-line NOTIFY call in `AuditService.log_operation` (the public method that delegates to `_insert_audit_entry`; there is no `AuditService.append` — earlier revisions used that name in error) so the bus stays the single emission point.

The SSE handler is a thin per-connection filter/serializer in front of the bus, not a parallel LISTEN/NOTIFY implementation. Server-side filtering against `change_ids` happens in the SSE handler after the bus dispatches the event to its callback.

**Reconnection.** EventSource auto-reconnects on disconnect. The server emits an initial `event: snapshot` with the current state of all subscribed change-ids on each (re)connection so the client can reconcile without polling.

**Backpressure.** The server caps event emission at 100 events/sec per connection; excess events are coalesced into a single `event: snapshot` triggering a client-side full re-render. This bound is generous (the audit_log table sees ~5 rows/sec under heaviest observed load) but prevents pathological cases.

## Multi-vendor swimlane data flow

```
work_queue row { id, status: "running", parent_id: <wp-review-id> }
  ↓ (children — child work_queue rows or sibling audit_log entries
     scoped by parent_id and/or labels)
agent_sessions { agent_id: "wp-review--claude", agent_type: "claude_code", ... }
agent_sessions { agent_id: "wp-review--gemini", agent_type: "gemini",      ... }
agent_sessions { agent_id: "wp-review--codex",  agent_type: "codex",       ... }
  ↓ (vendor extracted from agent_id suffix; agent_type cross-checked per D4)
  ↓ (audit_log filter agent_id IN [...])
audit_log row { agent_id: "wp-review--claude", operation: "edit_file",
                args_summary: "src/foo.py", ts: "..." }  (most recent)
audit_log row { agent_id: "wp-review--gemini", operation: "run_pytest",
                args_summary: "skills/tests/", ts: "..." }
audit_log row { agent_id: "wp-review--codex",  operation: "post_finding",
                args_summary: "FINDING-002 sev=med", ts: "..." }
```

`agent_profiles` rows are NOT in this path; they are profile templates assigned to the agent_id via `agent_profile_assignments`. The per-agent vendor is encoded in `agent_id` (parsed from the suffix) and `agent_sessions.agent_type` (recorded by `register_agent_session()`).

The frontend renders three mini-lanes on the parent card, each showing the one-line `args_summary` with the vendor's color and the relative timestamp (`12s ago`).

When the parent work-package transitions to `completed`, the swimlanes collapse into a consensus indicator (✓ if review consensus reached, ✗ if conflicting findings) sourced from the existing `parallel-infrastructure` consensus synthesizer's output. v1 surfaces only the binary indicator; v2 will offer click-through to the per-finding consensus matrix.

## Sync-point banner data sources

```
GET /sync-points/status returns:
[
  { "skill": "cleanup-feature",
    "blocked": true,
    "blockers": [{"agent_id": "wp-backend", "last_heartbeat_iso": "2026-05-15T10:40:13Z"}],
    "suggested_actions": ["wait", "kick:wp-backend"] },
  { "skill": "merge-pull-requests", "blocked": false, "blockers": [], "suggested_actions": [] },
  { "skill": "update-specs",       "blocked": false, "blockers": [], "suggested_actions": [] }
]
```

The handler calls `shared.check_no_active_agents()` once, then iterates the three sync-point skills. The function already returns the blocker list with heartbeat timestamps; the new endpoint is a thin projection.

When the banner shows zero blockers, it collapses to a one-line green status (`✓ all sync-points clear`).

## Tauri-readiness checklist

The scaffold ships in v1; the production build does not. The scaffold consists of:

- `apps/kanban-viz/src-tauri/Cargo.toml` — Tauri 2.x dependencies pinned
- `apps/kanban-viz/src-tauri/tauri.conf.json` — window config, allowlist (`http: { request: true }` for coordinator, all other capabilities denied)
- `apps/kanban-viz/src-tauri/src/main.rs` — minimal `fn main() { tauri::Builder::default().run(...) }`
- `apps/kanban-viz/src-tauri/.gitignore` — `target/`

CI does not build, sign, or notarize a Tauri binary in this change. A follow-up change adds the production build pipeline. The scaffold's correctness is verified by a single test: `cargo check` succeeds in the scaffold directory.

This mirrors the `agentic-content-analyzer` Tauri integration (referenced in `proposal.md`'s "What Changes" section #8) without committing to the full distribution stack.

## Frontend persistence boundary (D10)

### D10: Coordinator file-write endpoints for saved views and audit emission

Earlier revisions said the frontend writes `docs/kanban-viz/saved-views/<slug>.json` and `docs/kanban-viz/audit/<YYYY-MM-DD>/<id>.json` "via a tiny static-file endpoint or git-committed directly". Neither is achievable from a browser:

- A Vite-served browser app has no filesystem access (the dev server is read-only from the browser's perspective; production-built assets are stateless).
- "git-committed directly" cannot mean a `git commit` from the browser — there is no path from a `fetch()` to a repo commit without a server intermediary.
- Tauri-only filesystem APIs would work but would mean the saved-views and audit-emission features are absent in the browser path, contradicting "every feature accessible in the UI ... SHALL function" (Frontend Packaging requirement, browser scenario).

**Decision.** Introduce two small coordinator endpoints in this change that own the disk writes, keeping the "frontend never bypasses the coordinator" invariant honored:

- **`PUT /kanban-viz/saved-views/{slug}`** — upserts a saved-view JSON file at `<repo-root>/docs/kanban-viz/saved-views/{slug}.json`. The coordinator validates the body against the saved-view JSON schema (declared in `contracts/README.md`), stamps the mandatory artifact header server-side (`schema_version`, `generated_at`, `git_sha`, `generator: kanban-viz@<version>`), writes atomically via tmp-file + rename, and returns the resulting file path. The repo-root is resolved via a NEW `COORDINATOR_WORKDIR_ROOT` config setting added by this change to `agent-coordinator/src/config.py` (default: `Path(__file__).resolve().parents[2]`, i.e. the repo root when running from the source tree; explicit env var when running in Docker). Path-safety: every resolved write path is checked to stay within the configured root, otherwise 400. The coordinator does not trust client-supplied paths. Reversibility: reversible-write (the prior file content is in git).
- **`POST /kanban-viz/audit`** — appends a UI-emitted audit event under `<repo-root>/docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json`. Uses the same `COORDINATOR_WORKDIR_ROOT` resolution as the saved-views endpoint. Same header-stamping, same atomic-write, same path-sanitization rules. Reversibility: event-class artifact, not user-mutated.

Both endpoints:

- Are authenticated with the existing `X-Coordinator-API-Key` header (same as every other write endpoint).
- Reject slugs / run-ids that do not match `^[a-z0-9][a-z0-9-]{0,63}$` to prevent path traversal.
- Reject when the resolved directory escapes `COORDINATOR_WORKDIR_ROOT` (400 with diagnostic message). `COORDINATOR_WORKDIR_ROOT` itself defaults to the source-tree repo root and can be overridden by env var; it is NOT a pre-existing setting and is added by this change (see config.py addition in 2.13d/2.13e dependencies).
- Emit an `audit_log` row capturing the operation and the resulting file path.

This adds two endpoints to the change scope (now nine new endpoints total — 4 read in D2/D9 surrounding context: `GET /sync-points/status`, `GET /worktrees/active`, `GET /events/work` (SSE), `POST /events/auth`; 3 write in D9: `PATCH /issues/{id}/labels`, `DELETE /locks/{file_path}`, `POST /agents/{agent_id}/kick`; 2 file-write in D10: `PUT /kanban-viz/saved-views/{slug}`, `POST /kanban-viz/audit`), but each is a thin wrapper around `pathlib` plus the existing audit-log machinery. The alternative — a separate "kanban-viz local CLI helper" — is more code and only works on the operator's local machine, defeating the cloud-harness use case.

**Tauri path.** When running under Tauri, the frontend can short-circuit these two endpoints and use Tauri's `fs.writeTextFile` directly. The runtime feature-detect chooses between the two paths. The on-disk format is identical, so saved views authored in either path are interoperable.

## Auth posture (D11)

### D11: Browser-to-coordinator authentication and SSE token mint

The MVP retains the coordinator's existing API-key-based auth model — no JWTs except for the SSE handshake, no per-operator identity layer, no OAuth/SSO. This is a deliberate v1 scope choice: the Kanban targets the same single-operator use case the coordinator already serves.

**How the browser obtains the API key.**
- **Local dev (`localhost:5173` → `localhost:8081`).** The Vite dev server reads `VITE_COORDINATOR_API_KEY` from `.env.local` (gitignored) at build time and bakes it into the client bundle. The dev-bundle is not distributed.
- **Cloud-harness operator.** The deployed coordinator is gated behind the harness's own auth wall (Tailscale / VPN / per-session forwarded port). The operator's browser session obtains the API key via a small login page (`/auth/login` — out of scope for this change, deferred to a follow-up) OR via a manually-pasted key in a local `localStorage` slot that the frontend reads at boot. v1 accepts the manual-paste pattern because it has zero new server surface; the follow-up adds the login page.
- **Tauri shell.** Tauri's keychain integration stores the key; the React app reads it via a Tauri command.

**SSE token mint (`POST /events/auth`).** Browsers' `EventSource` cannot attach an `Authorization` header. The frontend exchanges its API key (sent in a regular `Authorization: Bearer` header on `POST /events/auth`) for a short-lived JWT (`aud=events`, `exp` ≤ 300s, fresh `nonce`, bound to the requested `change_ids`), passes it as `?token=<jwt>` on the `EventSource` URL. The coordinator validates the JWT on every received event, rejects on aud/exp/nonce/change_ids mismatch, and logs the request with the `token=` parameter redacted. JWT signing key:

- v1: a `COORDINATOR_SSE_SIGNING_KEY` env var (32-byte secret); rotation is manual.
- Follow-up: integrate with the existing OpenBao seeding flow used for other coordinator secrets.

**No per-operator audit identity in v1.** The audit_log `agent_id` for actions originating from the Kanban UI is recorded as the API-key identity (existing `COORDINATION_API_KEY_IDENTITIES` mapping), not an individual human. Per-human attribution is out of scope; revisit when SSO lands.

**Destructive-action consent in v1 is UI-side only.** `DELETE /locks/{file_path}` and `POST /agents/{agent_id}/kick` accept bare authenticated requests at the server. Server-side per-operation consent (e.g. an `X-Consent-Token` minted by the UI prior to dispatch) is intentionally deferred to v1.1; it would require either a second round-trip (mint-token → dispatch) or a server-side rate-limited consent register, both of which expand v1 scope without changing the security posture for the actual v1 attack model (single trusted operator behind a harness auth wall). The two mitigations that DO ship in v1 are: (a) every destructive action emits an audit row regardless of UI consent path (per scenarios in spec.md §"Operation reversibility taxonomy"), and (b) the per-operation consent prompt is enforced by the UI (per spec.md scenarios "Kick action requires consent" and "Force-release lock requires consent"). Operators driving the coordinator from scripts/curl bypass the UI prompt by design — they accept the destructive semantics directly. A follow-up change (`add-coordinator-consent-tokens`) adds server-side consent tokens once a v1.1 use case justifies the surface increase.

## CORS posture (D12)

### D12: CORS allow-list for Kanban origins

The Kanban frontend runs at a different origin than the coordinator:

- **Local dev:** Vite at `http://localhost:5173`, coordinator at `http://localhost:8081`.
- **Cloud-harness:** Vite-built static assets served from any same-origin static host (or directly from Tauri's `tauri://localhost`); coordinator at the harness-configured URL (`https://coord.<domain>` typical).

The existing FastAPI app has no CORS middleware wired in; this change adds one with a strict allow-list:

- `Access-Control-Allow-Origin`: `http://localhost:5173` (dev) + the values of a new `COORDINATOR_CORS_ALLOWED_ORIGINS` env var (CSV) so cloud deployments configure their own origin.
- `Access-Control-Allow-Methods`: `GET, POST, PATCH, DELETE, OPTIONS` (covers the existing read endpoints plus D9 write endpoints).
- `Access-Control-Allow-Headers`: `Authorization, X-Coordinator-API-Key, X-API-Key, Content-Type` (the legacy `X-API-Key` header stays in the allow-list because `verify_api_key` keeps accepting it for backward compatibility per task 2.13z).
- `Access-Control-Allow-Credentials`: `false` (the API key travels in a header, not a cookie; no credentials to share).
- `Access-Control-Max-Age`: `600` (preflight cache).
- The SSE endpoint (`GET /events/work`) requires no special CORS handling beyond the above because `EventSource` does not preflight; the `change_ids` and `token` query params are part of the URL.

Tauri's `tauri://localhost` is added to the allow-list when Tauri builds ship (deferred to a follow-up); v1 covers browser-dev and cloud-harness only.

## Performance

- Initial board render: ≤500ms cold (one HTTP round-trip to `POST /issues/list` + render).
- SSE event-to-DOM latency: ≤200ms (event emission → client receives → re-render).
- Sync-point status poll: 5s interval; ≤100ms server-side computation.
- Audit emission file write: synchronous, ≤50ms (writes are small and infrequent — driven by user action).
- SSE backpressure threshold: 100 events/sec/connection (D2).
- Saved-view file write: ≤50ms.

## Open Questions

1. **Should the SSE endpoint require an explicit `Last-Event-ID` for resume, or is the client-side snapshot reconciliation sufficient?** Default: snapshot-only (simpler, no per-event durable ordering required). Revisit if reconnection storms cause visible UI flicker.
2. **What is the right column for "blocked" tasks** — keep them in `In Flight` with a chip, or break out a fourth column `Blocked`? v1: keep in `In Flight` with a `⛔ blocked on T2` chip per the renderer's existing convention. Operators reading both `tasks.md` and the Kanban see the same blocker semantics.
3. **Where does the saved-views directory live for changes that touch many repos?** v1 scopes to the current repo's `docs/kanban-viz/saved-views/`. Cross-repo views are deferred to the cross-repo follow-up.
4. **Tauri allowlist scope.** v1 allows only `http.request` to the configured coordinator URL. If operators want native notifications when sync-points clear, the allowlist needs `notification.show`. Defer until the request appears.
5. **Cost/budget surfacing (Langfuse traces per change).** Discussed in the parent comparison thread; not in v1 scope. The audit-event family already has the data Langfuse-aggregated cost would derive from. Surface in v2 once the "saved view" component proves which aggregations operators actually want pinned.
