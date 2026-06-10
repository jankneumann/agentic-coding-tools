# Design — extend-kanban-viz-prs-proposals

## Context

The existing kanban-viz SPA at `apps/kanban-viz/` projects exactly one entity (`work_queue` issues) and is backed by a small set of coordinator endpoints documented in `docs/kanban-viz/README.md`. Two adjacent streams of in-flight work — open GitHub PRs and unimplemented OpenSpec proposals — are completely invisible from the board. Operators currently context-switch to `gh pr list` and `openspec list` to answer the question "what's the state of the whole pipeline?"

This change extends the existing system rather than replacing it. The existing Issue projection, sync-point banner, vendor swimlanes, save-views, SSE stream, and CORS posture all remain unchanged. We add two read-only HTTP endpoints to the coordinator, evolve the SPA card model into a discriminated union, and add three new UX primitives: source swimlanes, a refresh button, and cross-source cluster badges.

## Goals / Non-Goals

### Goals

- Make pipeline state legible at a glance: for any active `change_id`, the operator can see "proposal exists, branch is in-impl, PR is open with changes_requested" without leaving the board.
- Keep the data path consistent with existing patterns: server-side credential, single-tier API-key auth, no browser→GitHub calls.
- Preserve TypeScript strict-mode guarantees through the polymorphic refactor.
- Single-source the PR classification logic with the existing `discover_prs.py` skill — no parallel implementations.

### Non-Goals

- **No write actions on PRs or proposals.** No drag-to-merge, drag-to-archive, drag-to-dispatch. The board projects state; write skills (`/merge-pull-requests`, `/cleanup-feature`, `/implement-feature`) remain authoritative.
- **No SSE for PR or proposal events.** Refresh is user-triggered. The existing `/events/work` stream stays issue-only.
- **No per-source backend.** Both new endpoints live in the existing coordinator FastAPI app — no microservice split.
- **No webhook ingestion.** GitHub webhook receivers are out of scope; we pull on demand.
- **No GitHub App.** The PAT is sufficient for the read scopes we need; App migration is a follow-up if/when write actions land.

## Decision Boundaries (from proposal Gate 1)

### D1 — Data path: coordinator-mediated, server-side PAT

The coordinator holds a `GITHUB_PAT` env var and calls the GitHub REST API on behalf of the browser. The browser never sees a GitHub token.

**Why:** The kanban-viz existing auth posture is single-tier API-key Bearer. Browser-side GitHub calls would require either a CORS proxy or a public PAT — both worse. A server-side PAT lets us reuse the existing auth middleware unchanged.

**Alternative considered:** GitHub App with installation token. Rejected for v1 — installation tokens are short-lived and require token-refresh middleware we don't yet need. Migrate when write actions land.

### D2 — Refresh model: on-demand pull with 60s in-memory cache

`GET /github/prs` and `GET /openspec/proposals` each maintain an in-process cache (60s TTL). The SPA refresh button passes `?refresh=true` to bust the cache. Background prefetch / polling is not implemented.

**Why:** User intent at Gate 1 was "on-demand pull… refresh button in the UX." 60s cache is a single-flight guard against operator double-clicks and against the existing 5s sync-point polling becoming a thundering-herd vector if we later wire it.

**Cache structure:** single-process `dict[str, tuple[float, dict]]` keyed by endpoint name. No Redis, no shared state. If coordinator runs multiple workers behind a load balancer, each worker caches independently — acceptable for v1 because the board is single-tenant per operator and the underlying GitHub API has its own rate limits anyway.

**Cache invalidation across writes:** none in v1 (we have no write actions yet). When `/merge-pull-requests` lands a merge in a future change, it will need to publish a NOTIFY that the coordinator catches to invalidate the `/github/prs` cache. Out of scope here.

### D3 — Host: coord.rotkohl.ai only; local coordinators 503

The endpoint reads `GITHUB_PAT` at request time and responds 503 when unset. Local development coordinators that don't have a PAT continue to work for all existing endpoints; only the two new endpoints are 503.

**Why:** The user explicitly scoped the hosting to coord.rotkohl.ai. We don't want to ship default credentials, nor force every dev to manage a PAT.

**Implementation note:** the 503 path SHALL include a structured `{error: "github_pat_missing"}` body so the SPA can surface a clear "feature unavailable locally" chip on the PR row rather than a generic network error.

### D4 — PR ordering, filter, review findings

- Sort: `updated_at` descending (newest-touched first), server-side.
- Filter: client-side multi-select over the loaded array. Six origin values from `discover_prs.py`'s classifier.
- Findings: `review_summary = {state, reviewer_count, last_reviewed_at_iso}` projected server-side via the last-non-dismissed-review-per-reviewer reduction.

**Why:** Newest-first is the operator's natural mental model ("what changed since I last looked"). Client-side filter keeps the cache hit rate high — re-filtering doesn't refetch. Server-side findings reduction avoids leaking the GitHub reviews payload to the browser.

**Implementation note on filter persistence:** the existing save-view mechanism is JSON-shaped under `kanban_viz_files.py`. We extend the view payload schema with optional `pr_origins: string[]` and `hidden_rows: ("issues" | "prs" | "proposals")[]` fields. Optional + additive → no view-version bump needed; old views remain valid.

### D5 — Proposal `in-impl` detection: branch exists AND code outside proposal

A proposal is `in-impl` when both:
1. A branch named `openspec/<change-id>` exists locally OR in the configured remote.
2. The branch's diff vs. `main` includes at least one path outside `openspec/changes/<change-id>/`.

**Why:** The user's explicit answer was "Presence of code in git-branch (more than just planning artifacts)." This is the simplest implementation that captures that intent. A drafted-but-untouched proposal has no branch; a planning-only branch has the branch but its diff is confined to the change directory; a real in-flight implementation has commits elsewhere.

**Edge cases:**
- Multiple branches (`openspec/<id>--<wp>` agent branches): we look only at the parent feature branch `openspec/<id>`. Agent branches are merged into the feature branch during integration; if the merge hasn't happened, the feature branch may still have no out-of-proposal commits even though work-package agents do. Acceptable false-negative in v1; can revisit if it bites.
- `OPENSPEC_BRANCH_OVERRIDE` branches like `claude/<id>`: probe both `openspec/<id>` and `claude/<id>` and take the union.
- Squashed/merged branches: once a feature lands and is archived, the change directory moves under `archive/` and the projection naturally drops it. No special case needed.

**Implementation:** `git rev-list --count openspec/<id> ^main -- :^openspec/changes/<id>/` for the count of out-of-proposal commits. Wrap with `subprocess.run(check=False, timeout=5)` so a slow git invocation can't stall the request.

### D6 — Cluster: non-collapsing badge, not merged card

Cards remain in their per-source rows; each card sharing a `change_id` renders a cluster badge. Click highlights all siblings.

**Why:** The proposal initially considered "collapse cluster into one card." On reflection that destroys the very visibility the change is meant to add — the operator wants to see issue status, PR review state, and proposal status simultaneously, not behind a click. The badge gives cross-source linkage without hiding per-source detail.

**Rejected alternative:** collapsed cluster card with expand affordance. Rejected because the keyboard/screen-reader story for collapse-expand is heavier and the cross-source value is realized just as well by visual linking.

**Implementation:** the `useBoardCards` hook (new) computes a `Map<change_id, BoardCard[]>` once after fetch. Each card receives a `cluster_count: number | null` projection (null when count is 1 or change_id is null). The badge component reads `cluster_count` directly.

## Implementation Plan Outline

### Coordinator side

**New module: `agent-coordinator/src/github_classifier.py`**

Extract the classification rules from `skills/merge-pull-requests/scripts/discover_prs.py` into a pure function `classify_pr(pr: dict) -> dict` (returning `{"origin": str, "change_id": str | None}` — see PLAN_REVIEW R1 fix). Helper dependencies `safe_author` and `is_jules_author` are extracted from `_helpers.py` into the same module so the classifier is self-contained. The skill imports the new module instead of duplicating its logic. This is a refactor with zero behavioral change — covered by a unit test that runs the skill's existing test cases through the new entry point.

**Import path**: The coordinator publishes under the `src` package per `agent-coordinator/pyproject.toml` (`[tool.hatch.build.targets.wheel] packages=['src']` and tests use `from src.config import ...`). The classifier import is `from src.github_classifier import classify_pr`, NOT `from agent_coordinator.github_classifier import ...`. The skill's existing imports path goes through the established `skills-imports` shim (same approach as `src.shared.active_agents`).

**Critical adapter: `from_rest_pr(rest_payload: dict) -> dict`** (PLAN_REVIEW Round-1 CRITICAL finding). The classifier reads `gh`-CLI field names (`headRefName`, `body`, `title`, `labels[].name`, `author.login`, `createdAt`, `isDraft`, `url`), but the `GET /github/prs` endpoint fetches PRs via the REST API, which returns different field names (`head.ref`, `user.login`, `created_at`, `draft`, `html_url`). The adapter MUST be applied to every REST payload before `classify_pr` is called — without it, `headRefName` is empty and every PR falls through to `origin: "other"` / `change_id: null`. The adapter lives next to `classify_pr` (same module). The skill keeps feeding `gh`-CLI payloads directly because they're already in canonical shape.

**New endpoint: `GET /github/prs`** in a new module `agent-coordinator/src/github_prs_api.py`

- HTTP client: `httpx.AsyncClient` against `https://api.github.com/repos/<repo>/pulls?state=open` plus a per-PR `/reviews` call for review-summary projection. Batch the per-PR review calls with `asyncio.gather` (≤ 20 concurrent).
- Auth: `Authorization: Bearer <GITHUB_PAT>` header.
- Cache: in-process `dict[str, tuple[float, list]]`, mutex-protected for single-flight.
- 503 fail-closed on missing PAT.

**New endpoint: `GET /openspec/proposals`** in a new module `agent-coordinator/src/openspec_proposals_api.py`

- Read `openspec/changes/` from `Path(__file__).parent.parent.parent / "openspec" / "changes"`.
- For each non-archive subdirectory, parse `proposal.md` H1 + run `git rev-list --count`.
- Cache: same shape as `/github/prs`.
- No external dependencies.

**Deploy precondition (PLAN_REVIEW R2)**: This endpoint requires the coordinator's runtime checkout to contain (1) a `.git` directory with the `openspec/<id>` branches and an `origin/main` ref, AND (2) the `openspec/changes/` tree. Railway deploys built from Docker images typically `COPY` source without `.git`, which would silently make every proposal show as `drafted` (the branch-existence probe returns false). The Dockerfile for the coordinator MUST either bundle `.git` (via `COPY --from=git`) OR the deploy SHALL invoke `git fetch origin '+refs/heads/openspec/*:refs/remotes/origin/openspec/*'` on startup. The OpenSpec proposals endpoint SHALL detect missing `.git` at boot and fail closed with `503 {"error": "git_unavailable"}` — the SPA shows a clear "feature unavailable in this deployment" chip on the Proposals row, the same pattern as `GET /github/prs` on missing `GITHUB_PAT`.

**Routing:** register both endpoints in `agent-coordinator/src/coordination_api.py` alongside the existing kanban-viz endpoints. They share the same Bearer auth dependency.

### SPA side

**Type refactor (`src/lib/coordinator-types.ts`):**

- Rename `Issue` → `IssueCard`; add `kind: "issue"` field.
- Add `PRCard`, `ProposalCard` matching the spec field shapes.
- Add `type BoardCard = IssueCard | PRCard | ProposalCard`.
- Add `prStatusToColumn`, `proposalStatusToColumn`; rename `statusToColumn` → `issueStatusToColumn`.

**New hook (`apps/kanban-viz/src/hooks/useBoardCards.ts`):**

The hook lives in `src/hooks/`, NOT `src/lib/` — `src/lib/` is reserved for stateless utilities (types, runtime detection, saveView IO), while `src/hooks/` is where React state hooks live (this is where the existing `useCoordinator.ts` is). Original draft incorrectly placed it under `src/lib/`; correction per PLAN_REVIEW.

- Fetches the issue stream and the two new sources in parallel.
- **Multi-change issue semantics**: issues are fetched per-change-id in parallel and unioned client-side, NOT as one batched POST. The existing `fetchIssuesUnioned` helper in `useCoordinator.ts` already implements this; `useBoardCards` SHALL call it (or extract it to a shared helper) rather than implementing a one-shot batched POST that breaks multi-change boards. PR and proposal fetches are single-shot (no per-change-id partitioning).
- Returns `{cards: BoardCard[], byRow: {issues, prs, proposals}, clusters: Map<string, BoardCard[]>, lastRefreshed: {issues, prs, proposals}}`.
- Holds the refresh trigger (parallel refetch with `?refresh=true` on PR + proposal endpoints; the issues refetch goes through the same per-change union path).

**Issues stream coordination with existing SSE:** The existing `useCoordinator` keeps issues live via `GET /events/work` SSE — the initial `POST /issues/list` is followed by SSE-driven incremental updates (transition / audit / snapshot events). `useBoardCards.refresh()` triggers a fresh `POST /issues/list` (per-change union) that overwrites the in-memory issue array, then the SSE stream continues from that baseline. To avoid the SSE re-applying a stale event after refresh, the refresh action SHALL bump a `refreshGeneration` counter, and SSE event handlers SHALL ignore events whose generation predates the latest refresh. This is a classic "fence the stream" pattern; the SSE handshake doesn't need re-mint because the existing JWT remains valid.

**SPA component organization sanity check** (PLAN_REVIEW low-priority but worth fixing now): the existing components live under `src/components/`. New components added by this change SHALL follow that location, not `src/lib/` or `src/hooks/`. Specifically: `SourceSwimlanes.tsx`, `RefreshButton.tsx`, `PROriginFilter.tsx`, `ClusterBadge.tsx`, `PRCardView.tsx`, `ProposalCardView.tsx` all live in `src/components/`. Hooks (`useBoardCards.ts`) live in `src/hooks/`. Types and utils (`coordinator-types.ts`) live in `src/lib/`.

**New components:**

- `SourceSwimlanes.tsx` — three rows × three columns layout.
- `RefreshButton.tsx` — spinner-stateful button in the header.
- `PROriginFilter.tsx` — chip multi-select on the PR row toolbar.
- `PRCardView.tsx`, `ProposalCardView.tsx` — kind-specific renderers.
- `ClusterBadge.tsx` — badge with hover tooltip and click-to-highlight.

**Existing components updated:**

- `Board.tsx` swaps the bare `Issue[]` for `BoardCard[]` via the new hook and delegates to `SourceSwimlanes`.
- `IssueCardView` (the existing card renderer) is renamed and updated to consume `IssueCard` instead of `Issue`.
- `VendorSwimlanes` continues to render within the Issues row only.

### Tests

- Coordinator: pytest unit tests for the classifier, the review-summary reducer, the cache TTL behavior, the 503-on-missing-PAT path, the in-impl detection (with fixture git repos).
- Coordinator integration: a single end-to-end test that boots the FastAPI app and exercises both new endpoints with mocked `httpx` and a temp git repo.
- SPA: vitest unit tests for the three column-mapping functions, the cluster computation, and the filter persistence. React Testing Library tests for `SourceSwimlanes` totals, the cluster badge interaction, and the refresh-spinner state machine.
- SPA integration: extend `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx` to assert PR and proposal rows render against a fake coordinator.

## Risks and Mitigations

### R1 — GitHub API rate limits during cache stampede

The 60s cache hides most reads, but if a deploy restarts the coordinator with multiple operators hitting refresh simultaneously, we could burn through the 5000/hour authenticated quota. **Mitigation:** the single-flight mutex inside the cache means concurrent requests in the cache-miss window coalesce into one upstream call. Acceptable.

### R2 — discover_prs.py classifier drift

If we extract `classify_pr` into a shared module but the skill keeps its own copy synced manually, divergence will silently miscategorize PRs. **Mitigation:** the skill imports the module. We add a CI test that asserts no `classify_pr` definition exists in `discover_prs.py` itself.

### R3 — in-impl detection false negative on parallel-agent feature branches

A change actively being implemented by parallel work-package agents may show as `drafted` if the feature branch hasn't integrated agent commits yet. **Mitigation:** documented as a known limitation in the README. If this proves painful operationally, future change extends the probe to enumerate `openspec/<id>--*` branches and union their diffs.

### R4 — Cluster badge accessibility

Click-to-highlight is a non-standard interaction; screen-reader users may not perceive it. **Mitigation:** badge has `aria-label` describing the cluster ("Part of cluster extend-kanban-viz-prs-proposals; 3 related cards across rows"); click also opens a list panel reachable via keyboard.

### R5 — Stale 60s cache surprises operators who just opened a PR

Operator opens a PR in GitHub UI, switches to the board, expects to see it. The cached endpoint returns up to 60s stale data. **Mitigation:** the refresh button is one click. Acceptable. If it becomes a complaint, drop the cache to 15s.

### R6 — Per-PR `/reviews` fetch amplifies GitHub API consumption

The naive implementation issues one PR-list call plus one `/reviews` call per open PR. At 50 open PRs that's 51 calls per cache miss. With 60s TTL that's up to 60 misses/hour × 51 = **~3060 calls/hour** — well within the 5000/hour authenticated quota but uncomfortably close if multiple operators / multiple deploys share the PAT. **Mitigations** (in order of preference): (1) skip the `/reviews` fetch entirely for `is_draft == true` PRs (drafts have no review state worth surfacing); (2) use the GraphQL `pullRequests { reviews }` query to fold list + reviews into a single round trip; (3) if neither is in scope for v1, document the rate-limit risk in the README and emit a structured warning when the GitHub `X-RateLimit-Remaining` header drops below 500. v1 ships with (1) implemented and the GraphQL migration noted as a follow-up.

### R7 — `origin` enum mismatch between classifier and PRCard contract

`classify_pr` returns 9 distinct origin values (`openspec, codex, dependabot, renovate, sentinel, bolt, palette, jules, other`) but `PRCard.origin` in the contract is a 6-value enum (`openspec, codex, jules, dependabot, renovate, manual`). **Mitigation:** the endpoint applies `to_pr_card_origin` (folds Jules sub-types → `jules`, `other` → `manual`) before serializing. The skill (`discover_prs.py`) deliberately bypasses the fold and keeps the raw sub-types — they drive merge-strategy decisions that need finer granularity. The single-source-of-truth invariant is preserved: only the kanban-viz endpoint applies the fold, and the fold lives in the same module as the classifier so future drift is caught at code review.

## Open Questions Carried Forward to Implementation

- **GitHub PAT provisioning:** Does the deployed coordinator already have a PAT with `repo:status + pull_requests:read`, or do we provision one as part of merging this? Block the deploy step on confirming.
- **Repo allow-list:** Default to the agentic-coding-tools repo only. If we want multi-repo, read CSV from `GITHUB_REPOS` env var. Defer until a second repo asks.
- **Stale-PR window:** "All unmerged" with no upper time bound. For v1 ship as-is; revisit if the list grows past ~50 entries and visual noise becomes a problem.
- **Saved-view schema:** Extending with optional `pr_origins` and `hidden_rows` fields. Existing views silently default — no migration.
