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
│ agent-coordinator FastAPI (existing, two new endpoints)               │
│                                                                        │
│  Existing (consumed unchanged):                                       │
│   GET /issues?labels=change:<id>          (issue list)                │
│   GET /audit/recent?change_id=<id>&n=N   (last-N audit rows)         │
│   GET /agents/active                       (heartbeat-fresh agents)   │
│   POST /work/submit                        (existing — used for       │
│                                             pending-approval flag)    │
│                                                                        │
│  New (added in this change):                                          │
│   GET /events/work?change_ids=<csv>       (SSE: transition, audit)   │
│   GET /sync-points/status                  (banner blockers)          │
│   GET /worktrees/active                    (registry projection)      │
└────────────────────────┬─────────────────────────────────────────────┘
                         ▼
                   Postgres (work_queue, audit_log, file_locks,
                            agent_profiles, agents)
                   .git-worktrees/.registry.json (read-only)

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

**Polling fallback.** If `EventSource` cannot establish a connection (rare in browsers; possible in Tauri's webview if a proxy strips the `Connection: keep-alive` header), the client falls back to polling `GET /issues?labels=...` and `GET /audit/recent?...` at 5s intervals. The fallback is invisible to the rest of the UI.

### D3: No JSON sidecar mirror of `work_queue` state

The temptation is to maintain a `docs/kanban-viz/state.json` that mirrors current board state, so the Kanban can render before reaching the coordinator. We reject this: it duplicates the source of truth, introduces a sync problem identical to the one `add-coordinator-task-status-renderer` was created to solve, and violates the codeviz storage-tier policy (work_queue state is mutable, queryable, and properly lives in Postgres).

The only on-disk artifacts the Kanban writes are **saved views** (small, diffable, user-curated → git-committed under `docs/kanban-viz/saved-views/`) and **audit events** (event-class, dated paths under `docs/kanban-viz/audit/<YYYY-MM-DD>/`). Both carry the codeviz mandatory artifact header; both are properly classified per the codeviz storage-tier policy.

### D4: Vendor swimlanes derived from `audit_log.agent_id` + `agent_profiles.metadata.vendor`

A work-package in vendor-diverse parallel-review mode forks N agents (`wp-review--claude`, `wp-review--gemini`, `wp-review--codex`). The coordinator's `agent_profiles.metadata.vendor` field already records the vendor for each. The swimlane component groups `audit_log` rows by `vendor` and renders the most-recent-row's `args_summary` as a one-line "what is this vendor doing now" string.

When a card's underlying work-package is *not* in vendor-diverse mode (single-agent run), the swimlanes collapse to a single lane labeled with the lone vendor.

### D5: Sync-point banner reuses `shared.check_no_active_agents()`

The active-agent guard for `/cleanup-feature`, `/merge-pull-requests`, and `/update-specs` is centralized in `skills/shared/check_no_active_agents.py` (per CLAUDE.md). The new `/sync-points/status` endpoint imports the same function — no logic duplication. The endpoint enumerates the three sync-point skills and returns a list of `{skill, blocked, blockers, suggested_actions}`.

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
| Open the board | `GET /issues?...` | read | auto-allowed |
| Subscribe to events for a change | `GET /events/work` | read | auto-allowed |
| Read sync-point status | `GET /sync-points/status` | read | auto-allowed |
| Save a view | write file under `docs/kanban-viz/saved-views/` | reversible-write | auto-allowed; audit emitted |
| Drag a Backlog card → Ready (set pending-approval flag) | `PATCH /issues/<id>/labels` to add `pending-approval` | reversible-write | auto-allowed for human operator; agent requires scoped session; audit emitted |
| Force-release a stale lock | `DELETE /locks/<file_path>` | destructive-write | per-action consent prompt; audit emitted |
| Kick a stale agent (sync-point banner action) | `POST /agents/<id>/kick` | destructive-write | per-action consent prompt; audit emitted |

Audit emission goes to `docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json` (event-class artifact, mandatory header).

The classifier is **not duplicated**; the frontend imports a small TypeScript translation of the centralized `skills/shared/op_reversibility.py` rules (reservation in codeviz). For v1, the classification table above is hard-coded in `apps/kanban-viz/src/lib/reversibility.ts` with a comment pointing to the shared module so the duplication is intentional and easy to converge once codeviz ships the shared classifier.

## Storage alignment with codeviz tier policy

Per `openspec/roadmaps/codeviz/proposal.md` lines 49–56:

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

**Subscription model.** The client opens one SSE connection with `change_ids=<csv>` query string. The server-side handler binds to a Postgres `LISTEN` channel (`work_queue_change`, `audit_log_append`) and filters payloads against the subscribed change-ids. NOTIFY emission is added to the existing transaction paths in `IssueService.update_status` and `AuditService.append`.

**Reconnection.** EventSource auto-reconnects on disconnect. The server emits an initial `event: snapshot` with the current state of all subscribed change-ids on each (re)connection so the client can reconcile without polling.

**Backpressure.** The server caps event emission at 100 events/sec per connection; excess events are coalesced into a single `event: snapshot` triggering a client-side full re-render. This bound is generous (the audit_log table sees ~5 rows/sec under heaviest observed load) but prevents pathological cases.

## Multi-vendor swimlane data flow

```
work_queue row { id, status: "running", parent_id: <wp-review-id> }
  ↓ (children)
agent_profiles { agent_id: "wp-review--claude", metadata.vendor: "claude" }
agent_profiles { agent_id: "wp-review--gemini", metadata.vendor: "gemini" }
agent_profiles { agent_id: "wp-review--codex",  metadata.vendor: "codex"  }
  ↓ (audit_log filter agent_id IN [...])
audit_log row { agent_id: "wp-review--claude", operation: "edit_file",
                args_summary: "src/foo.py", ts: "..." }  (most recent)
audit_log row { agent_id: "wp-review--gemini", operation: "run_pytest",
                args_summary: "skills/tests/", ts: "..." }
audit_log row { agent_id: "wp-review--codex",  operation: "post_finding",
                args_summary: "FINDING-002 sev=med", ts: "..." }
```

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

## Performance

- Initial board render: ≤500ms cold (one HTTP round-trip to `GET /issues?...` + render).
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
