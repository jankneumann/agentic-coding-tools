# Kanban Viz — Developer Guide

A real-time Kanban board for observing coordinator work-queue state.
Connects to the coordinator API over SSE for live updates.

The board projects three card types in three source swimlane rows:
- **Issues** — work-queue items from the coordinator
- **Pull Requests** — open GitHub PRs across configured repositories
- **Proposals** — unimplemented OpenSpec proposals from `openspec/changes/`

## Quick Start

```bash
cd apps/kanban-viz
npm install
npm run dev          # starts Vite dev server on http://localhost:5173
```

Configure the coordinator URL and API key via environment variables or the
`VITE_COORDINATOR_URL` / `VITE_API_KEY` prefix in a `.env.local` file:

```
VITE_COORDINATOR_URL=http://localhost:8000
VITE_API_KEY=your-api-key-here
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `VITE_COORDINATOR_URL` | yes | `http://localhost:8000` | Coordinator base URL |
| `VITE_API_KEY` | yes | — | Bearer API key |
| `VITE_CHANGE_IDS` | no | `""` | Comma-separated change IDs to filter issues |

### Coordinator-side (server env, not SPA)

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_PAT` | yes for PR rows | — | GitHub Personal Access Token with `repo:status` + `pull_requests:read` scopes. When unset, `GET /github/prs` returns 503. |
| `GITHUB_REPOS` | no | `jankneumann/agentic-coding-tools` | Comma-separated list of `<owner>/<repo>` repositories to enumerate open PRs from. |

## Auth

The board uses `Authorization: Bearer <api-key>` for every request (design D11).
The SSE stream uses a short-lived single-use JWT minted by `POST /events/auth`.

## Tauri Scaffold

`apps/kanban-viz/src-tauri/` contains a minimal Tauri 2.x scaffold.
It is **not built in CI** and has not been packaged for production.
To verify it compiles:

```bash
cd apps/kanban-viz/src-tauri
cargo check
```

The Tauri path uses `src/lib/runtime.ts` `isTauri()` to detect the runtime.
Filesystem writes (saved views, audit events) route through the coordinator
endpoint in browser mode and through `@tauri-apps/api/fs` in Tauri mode,
producing identical JSON output on both paths (design D10).

## Running Tests

```bash
cd apps/kanban-viz
npm test          # watch mode
npm test -- --run # single-pass (CI)
npm run typecheck # TypeScript strict check
```

## Coordinator Endpoints Used

| Endpoint | Purpose |
|---|---|
| `GET /sync-points/status` | Sync-point gate banner (polled every 5s) |
| `GET /worktrees/active` | Active worktree projection |
| `POST /events/auth` | Mint short-lived SSE token |
| `GET /events/work` | SSE stream (transition, audit, snapshot events) |
| `POST /issues/list` | Initial board fetch |
| `PATCH /issues/{id}/labels` | Drag-to-Ready sets `pending-approval` label |
| `POST /agents/{id}/kick` | Force-kick a blocked agent (consent-gated) |
| `PUT /kanban-viz/saved-views/{slug}` | Persist a saved view |
| `POST /kanban-viz/audit` | Append a UI audit event |
| `GET /github/prs` | All open GitHub PRs (classified by origin, with review summary) |
| `GET /openspec/proposals` | Active OpenSpec proposals (classified by impl state) |

## New Endpoints

### `GET /github/prs`

Returns all open pull requests across the configured `GITHUB_REPOS`.

**Response shape:**
```json
{
  "prs": [PRCard...],
  "generated_at_iso": "2026-06-10T12:00:00Z",
  "source": "live|cache",
  "cache_age_seconds": 0
}
```

- Sorted newest-first (`updated_at` descending).
- Origin classification: `openspec / codex / jules / dependabot / renovate / manual`.
- Each `PRCard` includes `review_summary` with `state`, `reviewer_count`, and `last_reviewed_at_iso`.
- **60-second in-memory cache.** Pass `?refresh=true` to bust the cache.
- Returns `503 {"error": "github_pat_missing"}` when `GITHUB_PAT` is unset.
- Returns `200 {"prs": []}` when no open PRs exist.

### `GET /openspec/proposals`

Returns every active OpenSpec proposal from `openspec/changes/` (excludes `archive/`).

**Response shape:**
```json
{
  "proposals": [ProposalCard...],
  "generated_at_iso": "2026-06-10T12:00:00Z",
  "source": "live|cache",
  "cache_age_seconds": 0
}
```

- `status: "drafted"` — proposal exists but no implementation branch with code changes.
- `status: "in-impl"` — branch `openspec/<change-id>` exists AND contains commits touching paths outside `openspec/changes/<change-id>/`.
- **60-second in-memory cache.** Pass `?refresh=true` to bust the cache.
- Returns `503 {"error": "git_unavailable"}` when the coordinator's runtime checkout has no `.git` directory (typical of Docker `COPY` layers that omit `.git`). The SPA shows a "feature unavailable in this deployment" chip on the Proposals row.

## Refresh Button

The board header includes a **Refresh** button that triggers a parallel refetch of all three sources with `?refresh=true`. While in flight, the button shows a spinner and is disabled to prevent double-submits. If any individual source fails, a per-row error chip is shown on that row only; other rows continue rendering successfully-refreshed data.

Each source displays its own last-refreshed-at timestamp in the row header (e.g. `updated 12s ago`).

## PR Origin Filter

The PR swimlane row toolbar includes a chip multi-select for filtering by origin: `OpenSpec / Codex / Jules / Dependabot / Renovate / Manual`. The default is all selected. Deselecting chips filters client-side — no network request is made. Selection persists via `localStorage["kanban-viz:pr-origins"]` in the default view, and via the `pr_origins` field in saved views.

## Cluster Badge

Cards sharing the same `change_id` across rows (Issue + PR + Proposal) render a cluster badge showing the number of related cards. Clicking the badge temporarily highlights all sibling cards (≥ 1.5s outline). Cards with `change_id = null` (e.g., Dependabot PRs) do not render a badge.

The badge has an `aria-label` describing the cluster: `"Part of cluster <change-id>; N related cards across rows"`.

## Saved View Schema

The saved-view JSON schema accepts two new optional fields under `view`:
- `pr_origins: string[]` — persisted PR origin filter selection.
- `hidden_rows: ("issues" | "prs" | "proposals")[]` — which source rows are hidden.

Pre-existing saved views without these fields continue to validate (both fields are optional).
