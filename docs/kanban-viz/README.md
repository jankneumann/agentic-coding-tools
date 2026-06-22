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
| `GITHUB_PAT` | yes for PR rows | — | GitHub Personal Access Token with `repo:status` + `pull_requests:read` + `contents:read` scopes. When unset, `GET /github/prs` and any `github:` proposal sources return 503. |
| `GITHUB_REPOS` | no | `jankneumann/agentic-coding-tools` | Comma-separated list of `<owner>/<repo>` repositories to enumerate open PRs from. See [PR #211 GITHUB_REPOS section](#get-githubprs) for the parallel multi-repo idiom for the PR row. |
| `OPENSPEC_SOURCES` | no | _(implicit `local:.`)_ | Comma-separated list of OpenSpec proposal sources. Each entry is `local:<path>` (filesystem walk) or `github:<owner>/<repo>` (GitHub REST API). Empty = implicit `local:.` source pointing at the coordinator's own checkout (preserves PR #211 single-source behavior). Example: `local:/app/openspec,github:jankneumann/newsletter-aggregator,github:jankneumann/agentic-assistant`. |
| `OPENSPEC_SOURCES_GITHUB_CAP` | no | `50` | Maximum number of changes fetched per GitHub source per refresh. Raises a `github_budget_exceeded` warning (visible as a partial-result chip on the Proposals row) when exceeded. Raise this value for repos with more than ~20 in-flight changes. |

## Multi-Repository Support

The board surfaces work from multiple repositories in a single view.

### `OPENSPEC_SOURCES` — Proposals row

Configure `OPENSPEC_SOURCES` on the coordinator to aggregate OpenSpec proposals
from multiple repos:

```
OPENSPEC_SOURCES=local:/app/openspec,github:jankneumann/newsletter-aggregator,github:jankneumann/agentic-assistant
```

- `local:<path>` — walks the local filesystem at boot (fast, deterministic).
  The coordinator derives `repo` from `git remote get-url origin` (owner/repo
  lowercase). Falls back to `local/<basename>` with a warning log when origin
  parsing fails.
- `github:<owner>/<repo>` — fetches via GitHub REST API, lazily cached with a
  60-second TTL per source. Requires `GITHUB_PAT` with `contents:read` scope.

**Hybrid cache semantics:** local sources are walked eagerly at boot (sub-ms,
deterministic); GitHub sources are fetched lazily on first request with a 60s
TTL. `?refresh=true` busts both. The response field `source` reports
`"live"` | `"cache"` | `"mixed"` (at least one local + at least one cached
GitHub source). `cache_age_seconds` is the maximum age across all contributing
sources.

**Empty / unset `OPENSPEC_SOURCES`:** The coordinator synthesizes an implicit
`local:.` source pointing at its own checkout. This preserves PR #211's
single-source behavior and ensures `ProposalCard.repo` is always derived (so
PR↔Proposal cross-row clustering by `change_id` continues to work).

### `repo:` label convention — Issues row

To attribute Issues to a specific repo, add a label of the form
`repo:<owner>/<repo>` to the `work_queue` row. The SPA derives `IssueCard.repo`
client-side from the first matching label:

```
# Example label on a work-queue item:
repo:jankneumann/agentic-assistant
```

- Case is normalized to **lowercase** at derivation time (matches GitHub's
  case-insensitive behavior).
- **First-match-wins:** if an issue has multiple `repo:` labels, the first wins
  and a browser-console warning is logged naming the conflicting labels.
- Issues without any `repo:` label have `repo: null` and do not cluster
  cross-row with PRs or Proposals.

> **IMPORTANT — transition note for existing single-source coordinators:**
> Issues without `repo:<owner>/<repo>` labels have `repo: null` and will **NOT**
> cluster cross-row with PRs/Proposals (which always have non-null repo). This
> is intentional per spec D3 (mixed-null cluster split). To restore PR #211's
> cross-row clustering for existing issues, add `repo:<owner>/<repo>` labels via
> the coordinator's `PATCH /issues/{id}/labels` endpoint. Future automation
> could backfill these labels for a single-source coordinator; this is out of
> scope for the current change.
>
> The parallel multi-repo idiom for the PR row is configured via `GITHUB_REPOS`
> (see [PR row section](#get-githubprs) below).

### RepoBadge UX

Every card with a non-null `repo` field renders a small colored badge:

- **Short form:** basename of `<owner>/<repo>` (e.g. `myrepo` for
  `owner/myrepo`, `checkout` for `local/checkout`).
- **Tooltip:** hover shows the full `<owner>/<repo>` string.
- **Color:** deterministic per repo — same repo always produces the same HSL
  color (FNV-1a hash with [35%–55%] lightness range for readability).
- **Accessibility:** `aria-label="repository: <owner>/<repo>"`.

### Cluster key namespacing

Cards are clustered by `<repo>/<change_id>` (namespaced). This means:

- Same repo + same `change_id` → cluster forms across Issues / PRs / Proposals.
- **Different repos + same `change_id` → NO cluster** (intentional; prevents
  false visual links across unrelated repos).
- When ALL candidate cluster members have `repo: null` (pre-multi-repo data),
  the bare `change_id` is used as the fallback key (back-compat with PR #211).

### `hidden_repos` saved-view field

The saved-view schema accepts an optional `hidden_repos: string[]` field under
`view`:

```json
{
  "view": {
    "name": "Focus on agentic-assistant",
    "hidden_repos": ["jankneumann/agentic-coding-tools", "jankneumann/newsletter-aggregator"],
    "filters": {}
  }
}
```

The `HiddenReposToggle` chip group in the board header lists all repos visible
on the current board. Clicking a chip toggles its hidden state and persists via
the saved-view round-trip.

### `_warnings` partial-result chip

When one or more configured `OPENSPEC_SOURCES` are unreachable (e.g., GitHub
repo 404, PAT denied, timeout), the endpoint returns the surviving sources with
a `_warnings` array in the response. The SPA renders a **partial-result chip**
on the Proposals row header:

- Chip text: `⚠ Partial results (N sources failed)`.
- Clicking the chip expands a detail panel listing each failed source and its
  error code (`github_404`, `github_pat_denied`, `github_timeout`, etc.).
- Chip only shows for the latest refresh result; no sticky retention across
  requests.

This mirrors the per-row error chip pattern from PR #211's RefreshButton — same
UX vocabulary, different trigger.

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

The saved-view JSON schema accepts optional fields under `view`:
- `pr_origins: string[]` — persisted PR origin filter selection.
- `hidden_rows: ("issues" | "prs" | "proposals")[]` — which source rows are hidden.
- `hidden_repos: string[]` — which repos are hidden (multi-repo extension). Each
  entry is `<owner>/<repo>` matching the `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`
  pattern.

Pre-existing saved views without any of these fields continue to validate (all fields are optional).
