# Extend Kanban Viz with PRs and Proposals

## Why

The board today projects exactly one entity — `work_queue` issues — and ignores
two equally important streams of in-flight work:

- **Unmerged pull requests** across all sources (OpenSpec, Codex, Jules,
  Dependabot, manual). The `merge-pull-requests` skill enumerates these
  off-band via `scripts/discover_prs.py`, but the viz never shows them — so
  "what's blocked on review?" requires leaving the board for `gh pr list`.
- **OpenSpec proposals that haven't been implemented yet**, sitting as
  directories under `openspec/changes/` minus the archive. There's no surface
  that distinguishes "drafted but no code yet" from "drafted and actively
  being implemented."

The result: the board answers "what's the coordinator running right now?" but
not "what's the *state of the whole feature pipeline?*" — which is the question
operators actually ask before deciding what to merge, what to start, and what
to chase. Three sources sharing a `change_id` means the data can be
cross-linked into a single "this OpenSpec change has a proposal, a PR open,
and a worktree running" view that makes the pipeline state legible at a glance.

## What Changes

### Coordinator (`agent-coordinator/`)
- **NEW** `GET /github/prs` — on-demand pull of unmerged PRs across all
  configured sources, sorted newest-first, with origin classification. Auth
  via existing API key; calls GitHub using a server-side PAT.
- **NEW** `GET /openspec/proposals` — enumerates `openspec/changes/*` excluding
  `archive/`, classified by implementation state derived from branch contents.
- Caching: 60-second in-memory cache per endpoint, with explicit cache-bust on
  `?refresh=true` (the SPA refresh button passes this).
- Configuration: NEW `GITHUB_PAT` env var (this change introduces it;
  `agent-coordinator/src/github_coordination.py` does not currently hold
  GitHub credential logic — see spec for the env-var contract). NEW
  `GITHUB_REPOS` env var (CSV, defaults to `jankneumann/agentic-coding-tools`
  when unset, per spec). Hosted on `coord.rotkohl.ai` only — local
  coordinators get 503 unless `GITHUB_PAT` is set.

### SPA (`apps/kanban-viz/`)
- **NEW** card model: `BoardCard = IssueCard | PRCard | ProposalCard`
  discriminated union, replacing the bare `Issue` array in `useCoordinator`.
- **NEW** `SourceSwimlanes` component, projecting cards into three rows
  (Issues / PRs / Proposals), reusing the visual pattern from
  `VendorSwimlanes`.
- **NEW** `RefreshButton` component in the header — triggers refetch of all
  three sources with `?refresh=true`. Shows last-refreshed-at timestamp.
- **NEW** PR origin filter — chip-style multi-select in the PR swimlane
  toolbar: `openspec / codex / jules / dependabot / renovate / manual`
  (six chips matching the contract `Origin` enum and the classifier's
  emitted-then-folded values). Selected origins persist via existing
  save-view mechanism.
- **NEW** Review-findings projection on PR cards — surfaces the latest review
  state (`changes_requested / approved / commented`) and reviewer count from
  the GitHub REST `/pulls/{n}/reviews` endpoint (server-side projection).
- **NEW** Same-`change_id` clustering — issues, PRs, and proposals sharing a
  `change_id` render a cross-row cluster badge (cards remain in their own
  swimlane rows; the badge surfaces the linkage and a click highlights all
  siblings). No card-collapse / single-merged-card behavior — see design D6.

### Documentation
- `docs/kanban-viz/README.md` — document new endpoints, env vars, refresh
  semantics.

### Out of Scope
- **No drag-to-merge.** Belongs to `/merge-pull-requests`.
- **No drag-to-archive.** Belongs to `/cleanup-feature` and
  `/openspec-archive-change`.
- **No agent dispatch from the board.** Belongs to `/implement-feature`.
- **No webhook/SSE for PRs in v1.** Refresh is user-triggered per D1.
- **No write actions in the new endpoints.** Read-only projections.

## Approaches Considered

### Approach A — Polymorphic cards + source swimlanes (Recommended)

Introduce `type BoardCard = IssueCard | PRCard | ProposalCard` as a
discriminated union with a `kind` field. The existing `useCoordinator` hook
gains two more data sources fetched in parallel. The `Board` component renders
a single `SourceSwimlanes` container with three rows (Issues / PRs /
Proposals), each row showing the same three columns. Refresh button at the
top-right triggers a parallel refetch of all three sources with
`?refresh=true`. Same-`change_id` cards collapse into a single cluster card.

**Pros**:
- TypeScript narrows naturally on `kind` — each card component handles only
  its own type, no `any` or type assertions.
- Per-kind status enums stay native (PR `open|review|approved|merged`,
  Proposal `drafted|in-impl|archived`) — no awkward forced mapping into the
  issue enum.
- Cluster collapse is the highest-value UX win: at a glance you can see
  "this change has a proposal, a PR open with changes requested, and a
  worktree in flight."
- Filter chips and review-findings projection compose cleanly on `PRCard`
  without polluting the issue type.
- Reuses the existing `VendorSwimlanes` visual pattern; no new layout
  primitives.

**Cons**:
- Larger type-system change than the alternatives — every consumer of `Issue`
  in the SPA either becomes `IssueCard` (renamed) or gets a narrowing guard.
- Three different status enums means three column-mapping functions, not one.
- Cluster collapse adds an interaction surface (expand/collapse, keyboard
  affordances) that needs accessibility care.

**Effort**: M (≈ 2 days SPA + ≈ 1 day coordinator endpoints + tests).

### Approach B — Three-tab interface, independent boards

Keep the existing `Issue` type unchanged. Add two sibling components
(`PRBoard`, `ProposalBoard`) each with their own status enum and column
mapping. A tab strip at the top of `App.tsx` switches between three boards.
Each tab has its own refresh button.

**Pros**:
- Lowest type-system risk — existing `Issue`/`Board`/`Column` code untouched.
- Each board can evolve independently without coupling.
- Smaller per-component blast radius if a single source has a bug.

**Cons**:
- **Loses the cross-source pipeline view.** Cannot see "this change is
  drafted, PR is open, worktree running" without flipping tabs and holding
  three change-ids in your head — which is the actual question the extension
  is meant to answer.
- Triplicates UI code: three independent `Board`/`Column`/swimlane
  hierarchies, three save-view shapes, three refresh implementations.
- Per-tab refresh fragments the mental model — refreshing one tab leaves
  others stale; users have to remember which is current.

**Effort**: M-L (more code, less cohesion).

### Recommendation

**Approach A.** The whole motivation for the extension — making
pipeline state legible — is realized by the cluster collapse, which Approach B
structurally cannot provide. The type-system cost is real but bounded
(~ 15 files in the SPA), and TypeScript's exhaustiveness checking on the
discriminated union turns into a long-term safety net for any future card
type (worktrees, long-running test runs, blocked sync points). User
answers to the four discovery questions (on-demand refresh, hosted-only,
filter-by-origin, branch-contents detection) all assume a single unified
surface and are natively supported by A; B would require all four to be
duplicated three times.

### Selected Approach

**Approach A — Polymorphic cards + source swimlanes.** Confirmed by user
at Gate 1. Load-bearing commitments derived from this selection:

- `BoardCard = IssueCard | PRCard | ProposalCard` discriminated union with
  a `kind: "issue" | "pr" | "proposal"` field is the canonical SPA card
  model. Every consumer of the existing `Issue` type is migrated to either
  `IssueCard` or a generic `BoardCard` consumer with `kind` narrowing.
- Per-kind status enums stay native; three column-mapping functions
  (`issueStatusToColumn`, `prStatusToColumn`, `proposalStatusToColumn`)
  replace the single existing one.
- `SourceSwimlanes` renders three rows × three columns. Cards sharing a
  `change_id` render a cross-row cluster badge (NOT a collapsed merged
  card — design D6 refined this from the initial proposal because the
  whole point is seeing all three states at once). Click highlights
  siblings across rows.
- One unified refresh action triggers parallel refetch of all three
  sources. No per-source refresh.
- Two new read-only coordinator endpoints (`GET /github/prs`,
  `GET /openspec/proposals`) with 60s in-memory cache and `?refresh=true`
  cache-bust.

Approach B (three independent tabs) is rejected and not carried forward;
no fallback or feature-flag escape hatch is built — if A proves
unworkable during implementation, a new proposal is filed.

## Decision Boundaries

- **D1 (data path):** Coordinator-mediated. Server-side PAT, single-tier auth,
  no CORS for GitHub from the browser. Confirmed by user.
- **D2 (refresh model):** User-triggered via refresh button, with 60s
  cache-coalescing on the server. No SSE for PR/proposal events in v1.
  Confirmed by user.
- **D3 (host):** `coord.rotkohl.ai` only. Local coordinators that don't have a
  PAT return 503 with a clear message. Confirmed by user.
- **D4 (PR ordering and filter):** Newest-first (`updated_at` descending),
  filterable by origin (`openspec / codex / jules / dependabot / manual`),
  review findings (latest state + reviewer count) projected on the card.
  Confirmed by user.
- **D5 (proposal `in-impl` detection):** The git branch
  `openspec/<change-id>` exists AND contains commits whose diff touches paths
  outside `openspec/changes/<change-id>/` (i.e., real code, not just planning
  artifacts). Confirmed by user.
- **D6 (cross-source clustering):** Cards sharing `change_id` render a
  non-collapsing cross-row cluster badge; click highlights siblings.
  Originally proposed as "collapse into single card" — refined to
  non-collapsing badge during design because collapsing destroys the
  side-by-side per-source visibility the change exists to create. See
  design.md D6 for full rationale.

## Open Questions for Implementation

- **GitHub PAT scope:** The PAT needs `repo:status` + `pull_requests:read`
  at minimum. Does the deployed coordinator already have one with this scope,
  or do we provision a new one as part of this change?
- **Repo allow-list:** Default to the agentic-coding-tools repo only, or
  read a `GITHUB_REPOS` env var so other Railway services can use the same
  coordinator?
- **Save-view shape evolution:** Existing saved views are issue-only. Do we
  silently extend the schema (new optional fields) or version it
  (`v1` / `v2`)?
- **Stale-PR window:** "All unmerged" includes years-old PRs. Acceptable, or
  apply a default `updated_at > now() - 90d` cap with a "show all" toggle?
