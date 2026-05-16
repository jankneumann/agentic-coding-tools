# Add Coordinator Kanban Visualization (MVP)

## Why

The coordinator already exposes a rich multi-agent state surface — `work_queue` (pending → claimed → running → completed lifecycle, labels, parent_id, metadata), `file_locks`, `audit_log`, `agent_profiles`, `operation_guardrails` — through 40+ FastAPI endpoints in `agent-coordinator/src/coordination_api.py`. None of it is visualized. Operators reason about live multi-agent execution by tailing logs, reading `tasks.md`, and grepping `.git-worktrees/.registry.json`. The cognitive load grows superlinearly with parallelism: by the time three vendor-diverse reviewers are running across two work packages with overlapping file locks and a sync-point gate is silently blocked by a stale heartbeat, the operator has lost the plot.

Storybloq (`storybloq.com`) demonstrates that a Kanban-style visualization of work state is a genuinely useful surface for AI-assisted development — but its data model is single-agent, file-watching, JSON-only. Our domain is strictly richer: parallel vendor-diverse execution, file locks, sync-point gates, work-package DAGs, audit-tracked guardrails. A naive port of Storybloq's Kanban would lose precisely the layers that make multi-agent observability worth building.

This proposal closes the gap with a deliberately narrow MVP: three columns, vendor swimlanes on in-flight cards, and a sync-point gate banner. These are the three views that *only* make sense on our substrate. Everything else (DAG view, time-slider, lock heatmap, cross-repo board, autopilot lane, write actions beyond approval-staging) is deferred to a follow-up so we ship a useful surface before iterating.

The MVP composes with two adjacent in-flight efforts rather than competing with them:

- **`add-coordinator-task-status-renderer`** — the renderer's data contract (`coordination_bridge.try_issue_list(labels=["change:<id>"])` returning issues with `metadata.task_key`, `metadata.change_id`, `assignee`, `status`) is exactly the read shape this UI needs. The Kanban consumes the same contract; the frontend's TypeScript issue type is generated from the same Pydantic model.
- **`openspec/roadmaps/codeviz/`** (PR #156) — codeviz establishes the JSON-canonical-on-disk + FalkorDB-as-derived-cache + storage-tier policy + reversibility taxonomy + mandatory artifact header convention. The Kanban adopts those conventions for its few persisted artifacts (saved views, audit events, future FalkorDB work-state nodes), so when codeviz Phase 0 lands the Kanban becomes a natural lens on the same substrate without a data-layer fork.

## What Changes

1. **New web app** at `apps/kanban-viz/` (Vite + React + TypeScript, no SSR). Reads coordinator FastAPI directly; no new backend service. Three columns: `Backlog` (status=pending), `In Flight` (status in [claimed, running]), `Done` (status=completed within last 24h).
2. **Vendor swimlanes** on each `In Flight` card. The card subdivides into mini-lanes per vendor (`claude`, `codex`, `gemini`, `chatgpt-pro`) when the underlying work-package is in vendor-diverse parallel-review mode. Each lane shows the most recent `audit_log` row for that `(change_id, agent_id, vendor)` triple as a "live activity" string ("editing `src/foo.py`", "running pytest", "awaiting review consensus").
3. **Sync-point gate banner** pinned to the top of the board. Polls `/sync-points/status` (new endpoint, see contracts) every 5s and surfaces blockers with the format: `🟡 /cleanup-feature blocked — 1 active agent (wp-backend, last heartbeat 2m ago). [Wait] [Force]`. The banner is the cure for the most common operator confusion ("why won't this merge?").
4. **New coordinator endpoint** `GET /sync-points/status` that returns blocker state for the three sync-point skills (`/merge-pull-requests`, `/update-specs`, `/cleanup-feature`), reusing the existing `shared.check_no_active_agents()` logic. Returns a JSON list of `{ skill, blocked, blockers: [{agent_id, last_heartbeat_iso}], suggested_actions: [...] }`.
5. **New coordinator endpoint** `GET /events/work` (Server-Sent Events). Pushes `WorkQueueEvent` payloads (`{event: "transition" | "audit", payload: ...}`) on every `work_queue.status` transition and every appended `audit_log` row scoped to subscribed change-ids. Falls back to the existing pull endpoints if the client cannot establish SSE.
6. **Saved views** as small JSON artifacts under `docs/kanban-viz/saved-views/<view-name>.json` carrying the codeviz mandatory artifact header (`schema_version`, `generated_at`, `git_sha`, `generator`). Reversible-write per codeviz reversibility taxonomy.
7. **Audit emission** to `docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json` for every reversible-write or destructive-write action the user performs from the UI (drag-to-approve, force-release lock). Event-class artifact, dated path, mandatory header.
8. **Tauri scaffold** under `apps/kanban-viz/src-tauri/` — `tauri.conf.json`, minimal `Cargo.toml`, no production build wired into CI in this change. The presence of the scaffold makes the eventual native-app wrap a follow-up of ~100 lines rather than a re-architecture.

## What Doesn't Change

- The coordinator's Postgres schema. No migrations. The two new endpoints read existing columns.
- `add-coordinator-task-status-renderer` and `tasks.md` rendering. The Kanban is a parallel view over the same coordinator state; the renderer continues to project that state into the markdown.
- `.git-worktrees/.registry.json` format. The Kanban reads it via a new read-only coordinator endpoint (`GET /worktrees/active` — proposed; see contracts). The registry stays the source of truth.
- FalkorDB. Not introduced in this change. A reservation block in design.md declares the work-state node/edge labels (`WorkPackage`, `Agent`, `Worktree`, `Lock`, `BLOCKED_ON`, `LOCKS_FILE`, `WORKING_IN`) so codeviz Phase 0 ingestion can adopt them without later renames, but no FalkorDB code ships in v1.
- Existing skills (`/plan-feature`, `/implement-feature`, `/cleanup-feature`, `/merge-pull-requests`). No skill consumes the Kanban; the Kanban consumes them via their coordinator-emitted state.
- The coordinator's authentication posture (currently API-key based for local dev). The Kanban uses the same key.

## Approaches Considered

### Approach 1: Local web app (Vite + React + TS) reading coordinator HTTP+SSE directly (Recommended)

A SPA at `apps/kanban-viz/` served on `localhost:<port>` for development; static-built assets for distribution. Reads coordinator HTTP for initial state and SSE for live updates. Tauri-readiness via a non-shipping `src-tauri/` scaffold that the operator can `cargo build` when desired.

**Pros:**
- Works in cloud sessions (browser → forwarded port), local dev, and as a Tauri-wrapped native app from the same codebase. The repo runs on Linux, Mac, and in cloud-harness containers; a single web codebase covers all three.
- No new backend; the coordinator FastAPI stays the single source of truth and the existing API-key auth applies unchanged.
- Composable with codeviz: the Kanban becomes one lens of the same SPA shell once codeviz lands its frontend.
- TypeScript types generated from coordinator Pydantic models (existing `agent-coordinator/scripts/generate_typescript.py` pattern, if present, otherwise straight Pydantic → `pydantic-to-typescript`) means schema drift is a build failure, not a runtime mystery.

**Cons:**
- Adds a Node toolchain to the repo (currently Python-dominant). Mitigated by scoping to `apps/kanban-viz/` with no cross-cutting impact and pinning Node via `.nvmrc`.
- SSE endpoint is new server code; needs careful per-change-id subscription filtering to avoid leaking unrelated state to a viewer who shouldn't see it. Mitigated by reusing the existing label/permission filter that `IssueService.list_issues` already enforces.
- Two view modes (browser + Tauri) means UI must avoid Tauri-only APIs in v1 paths. Mitigated by gating Tauri API calls behind a runtime feature detect.

**Effort:** **M** (~1500 lines: 600 frontend + 200 SSE endpoint + 150 sync-point endpoint + 200 worktree endpoint + 250 saved-views + ~100 Tauri scaffold)

### Approach 2: Mac-native Swift app (Storybloq style)

Native SwiftUI app distributed via App Store, watching coordinator HTTP and the on-disk artifact directories. Mirrors Storybloq's distribution model.

**Pros:**
- Best-in-class native UX, system tray, real OS notifications.
- Aligns with Storybloq's positioning (free Mac app).

**Cons:**
- **Cannot run in cloud sessions.** Cloud-harness operators (a primary user of this repo, including this very session) would have no Kanban. Disqualifying for v1.
- Single-platform; Linux operators excluded.
- Adds Swift to a Python+TS codebase — toolchain tax, no shared code with codeviz frontend.
- App-Store distribution is incompatible with iterating this repo's local-first ethos.

**Effort:** **L** (~3000 lines, plus Swift toolchain in CI)

### Approach 3: TUI-only (Textual-based terminal Kanban)

A Python `textual` app rendering the Kanban in the terminal. Reads the same coordinator endpoints over HTTP.

**Pros:**
- Works everywhere a terminal works, including SSH and cloud-harness sessions.
- Reuses the repo's Python toolchain; no Node, no Rust.
- Cheap to build (~400 lines).

**Cons:**
- TUI cannot render vendor swimlanes within a card legibly at typical terminal widths.
- No drag-to-approve interaction model; reduces the UI to read-only, losing one of the MVP's differentiators.
- Forces an eventual GUI rebuild when operators want a richer surface — duplicate maintenance.

**Effort:** **S** (~400 lines)

### Selected Approach

**Approach 1: Local web app (Vite + React + TS) reading coordinator HTTP+SSE directly.** Selected at Gate 1 (Direction Approval).

Discovery-question decisions baked in:
- **Live update mechanism**: Server-Sent Events from a new `/events/work` endpoint, falling back to polling at 5s if SSE is unavailable. WebSocket rejected for v1 — SSE is one-way (server → client) which matches the read-mostly UI and has no framing/extension complexity. SSE auth needs a dedicated mint-and-redeem handshake (`POST /events/auth` → short-lived JWT in URL) because browser `EventSource` cannot attach `Authorization` headers; see design.md D2 and contracts/README.md for the full flow and token-in-URL mitigations.
- **Persistence layer for saved views**: small JSON artifacts under `docs/kanban-viz/saved-views/<name>.json`, committed to git, carrying the codeviz mandatory header. No database; no FalkorDB in v1. Aligns with codeviz storage-tier policy: small + diffable + canonical → git.
- **TUI parity**: deferred to a follow-up. Approach 3 is good enough to revisit *after* the web app proves which views matter.
- **Tauri shell**: scaffold ships in v1, build does not. Reduces follow-up cost without committing to native distribution prematurely.

## Recommended: Approach 1

Approach 1 wins on three grounds:

1. **It works in the environments operators actually use.** Cloud-harness sessions, local Mac/Linux, and (eventually) Tauri-wrapped native — all from one codebase. Approach 2 is Mac-only; Approach 3 is read-only.
2. **It composes with codeviz.** The codeviz roadmap is building a SPA frontend on the same substrate. Sharing a Vite + React + TS toolchain from day one means the Kanban becomes one of codeviz's lenses, not a parallel app to maintain.
3. **It honors the data-source-of-truth invariant.** No new database, no JSON sidecar mirror of `work_queue`. The coordinator stays the source of truth; the Kanban is a thin projection. This is the same architectural choice the renderer skill made, and the same reason `tasks.md` becomes a hybrid document rather than a sidecar.

The main risks — Node toolchain in a Python repo, SSE endpoint complexity — are bounded by scope (Node only inside `apps/kanban-viz/`) and by reuse (SSE filtering is the existing `IssueService` label filter under a streaming response).

## Out of Scope

- **DAG view of work-packages.yaml.** Worth doing; not the most-frequent operator question. Defer to a follow-up that lands alongside or after codeviz Phase 0 (which adds the structural-graph substrate).
- **Audit-log time slider / time-travel.** Requires either FalkorDB (for efficient bi-temporal queries) or a costly client-side replay. Defer until codeviz lands FalkorDB ingestion.
- **File-lock heatmap.** Requires a path-tree component and additional `/locks/heatmap` endpoint. Useful, not load-bearing for v1.
- **Cross-repo board.** Coordinator is multi-repo capable, but the v1 Kanban scopes to a single repo (the one currently checked out). Cross-repo tab strip is a follow-up after the single-repo UX is validated.
- **Roadmap autopilot lane.** `autopilot-roadmap` is itself young; surfacing its state in the Kanban will follow once its event model stabilizes.
- **Write actions beyond drag-to-approve.** v1 surfaces three write actions: save-view (reversible-write), drag-Backlog-card-to-Ready (reversible-write, sets pending-approval flag for `/plan-feature` Gate 2), and force-release-lock (destructive-write, gated by per-action consent). All other writes (kick agent, cancel work-package, force-merge) are deferred.
- **WebSocket transport.** Reconsider only if SSE proves insufficient for a specific UX requirement. Not in v1.
- **Authentication beyond the coordinator's existing API key.** No multi-user RBAC, no SSO, no audit-by-user. v1 assumes single-operator use of the local coordinator.
- **Native Tauri distribution.** Scaffold ships; binary distribution does not. Operators who want a native app run `cargo build` from the scaffold; CI doesn't build, sign, or notarize anything.
- **FalkorDB ingestion of work-state nodes.** Schema labels and edge types are *reserved* in design.md so codeviz Phase 0 can adopt them, but no ingestion code ships in this change.
