# Tasks — extend-kanban-viz-prs-proposals

Test-first ordering. Each task is sized S (≤ 1 hour) / M (≤ 4 hours) / L (≤ 1 day). Tasks larger than L are split. Checkpoint markers (`✓ CHECKPOINT`) every 2-3 tasks signal natural commit boundaries and integration handoffs.

## Section 1 — Coordinator: classifier extraction (foundation)

- [ ] 1.1 (S) Write failing unit test in `agent-coordinator/tests/test_github_classifier.py` asserting `classify_pr({"headRefName": "openspec/foo", ...}) == {"origin": "openspec", "change_id": "foo"}`, plus cases for `claude/`, `dependabot/`, `renovate/`, codex-author, jules-labels (and Jules sub-types `sentinel/bolt/palette`), and the `other` fallback. Reuse the `_pr()` helper shape from `skills/tests/merge-pull-requests/test_classify.py` so fixtures stay in sync.

- [ ] 1.2 (M) Extract `classify_pr(pr: dict) -> dict` (returning `{"origin": str, "change_id": str | None}` — matching the existing surface in `discover_prs.py`), plus `JULES_PATTERNS`, `JULES_AUTHORS`, and helper rules from `skills/merge-pull-requests/scripts/discover_prs.py` into a new module `agent-coordinator/src/github_classifier.py`. Make 1.1 pass.

- [ ] 1.3 (S) Add a thin mapper `to_pr_card_origin(classifier_origin: str) -> Origin` in the same module: folds `sentinel | bolt | palette | jules → "jules"` and `other → "manual"` to match the six-value `PRCard.origin` enum in the contract. Direct passthrough for `openspec`, `codex`, `dependabot`, `renovate`. Unit-tested against all 9 classifier outputs.

- [ ] 1.4 (S) Update `skills/merge-pull-requests/scripts/discover_prs.py` to import `classify_pr`, `JULES_PATTERNS`, `JULES_AUTHORS` from `agent_coordinator.github_classifier` (via the existing skills-imports path) instead of redefining them. The skill SHALL continue to consume the raw `{"origin": ..., "change_id": ...}` dict (no `to_pr_card_origin` fold on the skill side — sub-types preserved for merge-strategy decisions). Existing skill tests SHALL still pass without modification.

✓ CHECKPOINT 1 — classifier is single-sourced (raw form for skill, folded form for kanban-viz endpoint) and exercised by both consumers.

## Section 2 — Coordinator: GET /github/prs endpoint

- [ ] 2.1 (M) Write failing pytest in `agent-coordinator/tests/test_github_prs_api.py` exercising the `Authentication Posture` 503 path: app boots without `GITHUB_PAT`, `GET /github/prs` returns 503 with body `{"error": "github_pat_missing"}`, and `httpx.AsyncClient` is never instantiated. Use FastAPI `TestClient` with monkeypatched env.

- [ ] 2.2 (M) Write failing pytest exercising the cache TTL: with `GITHUB_PAT` set and `httpx` mocked, two requests within 60s return identical `prs` arrays and `source = "cache"` on the second; the mock is called exactly once. A third request with `?refresh=true` calls the mock again.

- [ ] 2.3 (M) Write failing pytest for the review-summary reducer in isolation (`reduce_reviews(reviews_payload) -> ReviewSummary`): covers the four scenarios from the spec (approve-then-changes-requested, no-reviews, dismissed-reviews-excluded, multi-reviewer).

- [ ] 2.4 (L) Implement `agent-coordinator/src/github_prs_api.py` containing: PAT-gated GitHub REST client (`httpx.AsyncClient`), per-PR review fetch with `asyncio.gather` capped at 20 concurrent, classifier integration via `github_classifier.classify_pr` AND `to_pr_card_origin` for the `PRCard.origin` fold, the in-process TTL cache with mutex (single-flight), `?refresh=true` cache-bust, and the response shape from the spec. Make 2.1–2.3 pass.

- [ ] 2.5 (S) Register the endpoint in `agent-coordinator/src/coordination_api.py` and add it to the existing kanban-viz auth dependency. Add minimal smoke pytest that the route is registered.

✓ CHECKPOINT 2 — `GET /github/prs` is wired, cached, and review-projected against unit fixtures.

## Section 3 — Coordinator: GET /openspec/proposals endpoint

- [ ] 3.1 (M) Write failing pytest in `agent-coordinator/tests/test_openspec_proposals_api.py` exercising the "drafted vs in-impl" detection. Fixture: a `tmp_path` git repo with three changes — one without a branch, one with branch whose diff stays inside the proposal dir, one with branch touching `coordinator/foo.py`. Assert statuses `drafted`, `drafted`, `in-impl` respectively.

- [ ] 3.2 (S) Write failing pytest asserting archive entries are excluded: a directory `openspec/changes/archive/old-thing/proposal.md` SHALL NOT appear in the response.

- [ ] 3.3 (S) Write failing pytest asserting malformed proposals are skipped with a warning: a directory missing `proposal.md` SHALL be omitted, response status SHALL remain 200, a warning SHALL be logged.

- [ ] 3.4 (M) Write failing pytest for cache TTL parity with `/github/prs` (60s, `?refresh=true` bust, `source` field).

- [ ] 3.5 (L) Implement `agent-coordinator/src/openspec_proposals_api.py`: enumerate `openspec/changes/*` excluding `archive/`, parse H1 title, derive timestamps from `git log`, branch-existence + `git rev-list --count` probe for `code_changes_outside_proposal`, the TTL cache, the response shape from the spec. Make 3.1–3.4 pass.

- [ ] 3.6 (S) Register endpoint in `coordination_api.py` with the same auth dependency.

✓ CHECKPOINT 3 — both new coordinator endpoints are merged, tested, and unblocked for SPA work.

## Section 4 — Contracts: OpenAPI + TS types

Sections 4.1 and 4.2 are pre-shipped on the planning branch as
`openspec/changes/extend-kanban-viz-prs-proposals/contracts/openapi/v1.yaml`
and `.../contracts/generated/types.ts`. The implementer's job is to
(a) keep them in sync if any task below shifts a field, and (b) decide
whether to promote them to `agent-coordinator/contracts/` permanently
(persistent contract) or leave under the change directory until archive
(per-change contract). Default: promote in this PR — see 4.3.

- [ ] 4.1 (S) Verify the in-change OpenAPI at `openspec/changes/extend-kanban-viz-prs-proposals/contracts/openapi/v1.yaml` covers both new paths, the request/response schemas (`PRCard`, `ProposalCard`, error shapes), and the `?refresh` query parameter. Reference the existing API-key security scheme. Patch if endpoints below diverged.

- [ ] 4.2 (S) Verify the in-change generated TS at `.../contracts/generated/types.ts` is the typed superset of the existing `Issue` interface plus `PRCard`, `ProposalCard`, `BoardCard`. Patch if 5.x rename below diverges.

- [ ] 4.3 (S) Promote both files to `agent-coordinator/contracts/openapi/v1.yaml` and `apps/kanban-viz/contracts/generated/types.ts` (or whichever path the existing repo already uses — see `architecture.config.yaml`). Update SPA imports in 5.x to consume from this canonical location. Verify with `npm run typecheck` from `apps/kanban-viz/` and `openspec validate --strict`.

✓ CHECKPOINT 4 — contracts are the single source of truth; the SPA cannot drift from the coordinator without a type error.

## Section 5 — SPA: type model refactor

- [ ] 5.1 (M) Write failing vitest in `apps/kanban-viz/src/lib/__tests__/column-mapping.test.ts` covering the three column-mapping functions: `issueStatusToColumn` (preserve existing behavior), `prStatusToColumn`, `proposalStatusToColumn`. Include the strict-mode exhaustiveness assertion (type-level test using `never`).

- [ ] 5.2 (L) Rename `Issue` → `IssueCard` (with `kind: "issue"` field), add `PRCard`, `ProposalCard`, and `BoardCard` union to `coordinator-types.ts` (or import from contracts per 4.2). Rename `statusToColumn` → `issueStatusToColumn`. Implement `prStatusToColumn`, `proposalStatusToColumn`. Make 5.1 pass.

- [ ] 5.3 (M) Update every existing consumer of `Issue` in `apps/kanban-viz/src/` to consume `IssueCard` (rename + `kind` narrowing). `npm run typecheck` SHALL pass.

✓ CHECKPOINT 5 — SPA type model is polymorphic; existing behavior preserved.

## Section 6 — SPA: useBoardCards hook and cluster computation

- [ ] 6.1 (M) Write failing vitest for `clusterBoardCards(cards)` pure function: given mixed cards with overlapping and unique `change_id`s, returns a `Map<change_id, BoardCard[]>` and annotates each card with `cluster_count: number | null`. Cards with `change_id = null` SHALL receive `cluster_count = null` and SHALL NOT appear in any cluster.

- [ ] 6.2 (L) Implement `useBoardCards` hook in `apps/kanban-viz/src/lib/useBoardCards.ts`: parallel fetch of `/issues/list`, `/github/prs`, `/openspec/proposals`, response shape narrowing, cluster computation, per-source `lastRefreshed` timestamps, refresh trigger that re-fetches with `?refresh=true`. Vitest unit tests for the parallel-fetch behavior (with one source erroring) and the refresh idempotency.

- [ ] 6.3 (S) Refactor existing `useCoordinator` to delegate the cards portion to `useBoardCards` while keeping the SSE subscription and sync-point polling intact.

✓ CHECKPOINT 6 — data hook is ready to feed UI components.

## Section 7 — SPA: SourceSwimlanes + RefreshButton

- [ ] 7.1 (M) Write failing React Testing Library test for `SourceSwimlanes`: given a card array with mixed kinds, asserts three rows render in the order Issues → PRs → Proposals, each row's header shows correct backlog/in-flight/done totals, and toggling a row chip hides that row's cards.

- [ ] 7.2 (L) Implement `SourceSwimlanes.tsx` reusing the visual language of `VendorSwimlanes`. Row visibility state syncs with the saved-view payload's optional `hidden_rows` field (D4).

- [ ] 7.3 (M) Write failing RTL test for `RefreshButton`: click triggers parallel refetch via the hook (mocked), button enters spinner state, returns idle when all three resolve, one source failing surfaces a per-row error chip without blocking other rows.

- [ ] 7.4 (M) Implement `RefreshButton.tsx`. Wire to `useBoardCards.refresh()`.

✓ CHECKPOINT 7 — three-row board renders end-to-end with on-demand refresh.

## Section 8 — SPA: PR filter + cluster badge + per-card views

- [ ] 8.1 (S) Write failing RTL test for `PROriginFilter`: chips for the six origins render, deselecting a chip filters the PR row, no network request fires.

- [ ] 8.2 (S) Write failing test that selection persists across SPA reload via `localStorage["kanban-viz:pr-origins"]` and via the saved-view `pr_origins` field.

- [ ] 8.3 (M) Implement `PROriginFilter.tsx` plus the localStorage + saved-view persistence.

- [ ] 8.4 (M) Write failing RTL test for `ClusterBadge`: cards sharing change_id render the badge with correct count; click highlights siblings ≥ 1.5s; cards with `change_id = null` do NOT render a badge; badge `aria-label` describes the cluster.

- [ ] 8.5 (M) Implement `ClusterBadge.tsx` and integrate into card renderers.

- [ ] 8.6 (M) Implement `PRCardView.tsx` (with review-summary chrome — `approved` success, `changes_requested` warning, `commented`/`none` neutral) and `ProposalCardView.tsx` (status chip + branch indicator). Both include the `ClusterBadge` per 8.5.

✓ CHECKPOINT 8 — full feature visible in the browser; manual smoke against coord.rotkohl.ai.

## Section 9 — Integration test + docs + cleanup

- [ ] 9.1 (M) Extend `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx` to mock the two new endpoints and assert all three rows render, refresh re-fetches all three, PR filter narrows the PR row, cluster badge highlights siblings. Verify with `npm test -- --run`.

- [ ] 9.2 (S) Update `docs/kanban-viz/README.md`: add `GET /github/prs` and `GET /openspec/proposals` to the endpoints table; document `GITHUB_PAT` env var; document refresh-button semantics and 60s cache; document cluster badge interaction.

- [ ] 9.3 (S) Add `GITHUB_PAT=` (commented placeholder) to the coordinator's `.env.example` if one exists; if not, leave a note in the README.

- [ ] 9.4 (S) Run `openspec validate extend-kanban-viz-prs-proposals --strict`. Fix any validation failures.

- [ ] 9.5 (S) Run the full coordinator + SPA test suites (`uv run pytest -m "not e2e and not integration"` in `agent-coordinator/`; `npm test -- --run` in `apps/kanban-viz/`). Both SHALL pass.

✓ CHECKPOINT 9 — feature is complete, tested, documented, and OpenSpec-valid. Ready for `/validate-feature` and PR.

## Section 10 — Deploy prerequisites (out of code scope; ops handoff)

- [ ] 10.1 (S) Confirm a GitHub PAT with `repo:status + pull_requests:read` scopes is available for the coord.rotkohl.ai deploy. If not, file an issue to provision one — block deploy until resolved.

- [ ] 10.2 (S) Add `GITHUB_PAT` to the Railway/coord.rotkohl.ai env. Verify `/github/prs` returns 200 in the deployed environment, not 503.

- [ ] 10.3 (S) Smoke-test the SPA at coord.rotkohl.ai: refresh button triggers all three sources, cluster badges appear on the current change-ids, PR filter narrows correctly.

✓ CHECKPOINT 10 — deployed and operationally live.
