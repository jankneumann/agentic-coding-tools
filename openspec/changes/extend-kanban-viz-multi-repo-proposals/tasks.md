# Tasks — extend-kanban-viz-multi-repo-proposals

Test-first ordering. Each task is sized XS (≤30min) / S (≤2hr) / M (≤4hr) / L (≤1 day); none XL. Checkpoint markers (`✓ CHECKPOINT`) every 2–3 implementation tasks signal natural commit boundaries.

## Section 1 — Coordinator: source descriptor parsing + warmup

- [ ] 1.1 (S) Write failing pytest `agent-coordinator/tests/test_openspec_sources.py::test_parse_sources_cases` covering: empty `OPENSPEC_SOURCES` → empty list; single local; single github; mixed; lowercase normalization of `<owner>/<repo>` portion; invalid entries (`bogus:foo`, `github:not_a_repo`, `local:`) → `ParseWarning` + 503 escalation. Reference spec scenarios "OPENSPEC_SOURCES unset", "mixes local and github sources", "Invalid OPENSPEC_SOURCES entry fails closed", "Owner/repo casing is normalized to lowercase".
  **Dependencies:** None

- [ ] 1.2 (M) Implement `agent-coordinator/src/openspec_sources.py` containing the `SourceDescriptor` dataclass and `parse_sources(env_val: str) -> tuple[list[SourceDescriptor], list[ParseWarning]]`. Make 1.1 pass.
  **Dependencies:** 1.1

- [ ] 1.3 (S) Write failing pytest `test_openspec_sources.py::test_derive_local_repo` for `derive_local_repo(path: Path)`: (a) repo with `origin` set to `https://github.com/JanK/Repo.git` returns `("jank/repo", None)`; (b) repo with SSH-style remote `git@github.com:owner/repo.git` returns `("owner/repo", None)`; (c) repo with no origin returns `("local/<basename>", warning_str)`; (d) origin parse fails returns `("local/<basename>", warning_str)`. The `local/` prefix on the basename fallback (R1-004) preserves owner/repo shape so the result passes the regex used by GITHUB_REPOS, hidden_repos saved-view validation, and the namespaced cluster key. Reference spec scenario "Repo derivation falls back to basename with warning".
  **Dependencies:** 1.2

- [ ] 1.4 (S) Implement `derive_local_repo` in `openspec_sources.py` using `subprocess.run(["git", "remote", "get-url", "origin"], cwd=path, timeout=2)` + a regex parser for both HTTPS and SSH GitHub URL forms. Make 1.3 pass.
  **Dependencies:** 1.3

- [ ] 1.5 ✓ CHECKPOINT — `agent-coordinator/.venv/bin/python -m pytest agent-coordinator/tests/test_openspec_sources.py -v` exits 0; commit as `feat(openspec-sources): source descriptor parsing + local repo derivation`.
  **Dependencies:** 1.2, 1.4

## Section 2 — Coordinator: hybrid cache + boot warmup

- [ ] 2.1 (M) Write failing pytest `test_openspec_sources.py::test_warm_local_sources` exercising: warm 2 local sources (fixture `tmp_path` git repos) → cache populated; second call without invalidation returns cached; `invalidate_local_walk_cache()` forces re-walk on next call. Use freezegun or monkeypatched clock for deterministic cache-age assertions.
  **Dependencies:** 1.5

- [ ] 2.2 (L) Implement `warm_local_sources`, `get_or_walk_local`, `invalidate_local_walk_cache` in `openspec_sources.py`. Walk produces the same per-change record shape that PR #211's filesystem walker emits (so the existing parsing reuses unchanged). Make 2.1 pass.
  **Dependencies:** 2.1

- [ ] 2.3 ✓ CHECKPOINT — full `test_openspec_sources.py` green; commit as `feat(openspec-sources): hybrid cache local-eager warmup`.
  **Dependencies:** 2.2

## Section 3 — Coordinator: GitHub-source fetcher

- [ ] 3.1 (M) Write failing pytest `agent-coordinator/tests/test_github_openspec_fetcher.py::test_fetch_proposals_basic` with mocked `httpx.AsyncClient`: source has 3 changes; assert 3 ProposalCards returned, all with `repo` set to lowercase source, `proposal_path` is the github web URL form (sourced from the `html_url` field, NOT manually concatenated), `has_branch` reflects the branches API result. Cover the "GitHub-source ProposalCard has github URL in proposal_path" and "GitHub-source branch-existence probe used for in-impl detection" spec scenarios.
  **Dependencies:** 1.5

- [ ] 3.1a (S) Write failing pytest `test_github_openspec_fetcher.py::test_rest_field_shape_adapter` using a recorded `/contents` fixture (file at `agent-coordinator/tests/fixtures/github_contents_openspec_changes.json`). Asserts: only `type == "dir"` entries are processed; `archive/` is excluded by name; the `proposal.md` title comes from base64-decoded `content`; `proposal_path` equals the `html_url`. This is the analogue of PR #211's `test_github_rest_adapter.py` field-shape regression sentinel — addresses the `from_rest_pr`-style gotcha called out in the spec.
  **Dependencies:** 1.5

- [ ] 3.2 (M) Write failing pytest `test_github_openspec_fetcher.py::test_budget_cap` — fixture with 80 changes + default cap 50 → returns 50 + `github_budget_exceeded` warning naming "30 changes truncated"; with `OPENSPEC_SOURCES_GITHUB_CAP=100` → returns all 80, no warning. Covers spec scenarios "Source within budget", "Source exceeds budget", "Budget cap configurable via env var".
  **Dependencies:** 3.1

- [ ] 3.3 (M) Write failing pytest `test_github_openspec_fetcher.py::test_degraded_modes` — 404 → `github_404` warning, no exception bubbles; 401/403 → `github_pat_denied` warning; timeout → `github_timeout` warning. Covers spec scenarios "Source timeout produces github_timeout warning".
  **Dependencies:** 3.1

- [ ] 3.4 (L) Implement `agent-coordinator/src/github_openspec_fetcher.py` with `fetch_proposals_from_github(source, pat, budget)` async function. Reuses `httpx.AsyncClient`, same auth header pattern as `github_prs_api.py`. Per-source request counter. Per-source 10s timeout. The fetcher MUST source `proposal_path` from the `html_url` field of the `/contents/openspec/changes/{change_id}/proposal.md` response (not concatenated by hand), MUST filter `/contents/openspec/changes` to `type == "dir"` entries excluding `archive/`, and MUST base64-decode `content` for H1 title extraction. Make 3.1–3.3 pass.
  **Dependencies:** 3.1a, 3.2, 3.3

- [ ] 3.5 ✓ CHECKPOINT — `test_github_openspec_fetcher.py` green; commit as `feat(github-openspec): REST fetcher with budget cap + degraded modes`.
  **Dependencies:** 3.4

## Section 4 — Coordinator: endpoint integration

- [ ] 4.1 (M) Write failing pytest `agent-coordinator/tests/test_openspec_proposals_api.py::test_multi_source_fan_out` using FastAPI `TestClient`: `OPENSPEC_SOURCES = "local:/tmp/repo-a,github:owner/b"` with mocked httpx; assert response contains proposals from both, `source: "mixed"` if local is fresh AND github is cached, `cache_age_seconds` is max of contributors. Covers spec scenarios "Mixed source freshness", "GitHub source cached lazily", "refresh=true busts both".
  **Dependencies:** 2.3, 3.5

- [ ] 4.2 (S) Write failing pytest `test_openspec_proposals_api.py::test_all_sources_fail` — all sources unreachable → `200 OK`, `proposals: []`, `_warnings` non-empty. Covers "All sources fail" scenario.
  **Dependencies:** 4.1

- [ ] 4.3 (S) Write failing pytest `test_openspec_proposals_api.py::test_github_pat_missing_mixed_mode` — mixed-mode config with `GITHUB_PAT` unset → 503 with `github_pat_missing`. Local-only config without PAT continues to serve.
  **Dependencies:** 4.1

- [ ] 4.4 (L) Update `agent-coordinator/src/openspec_proposals_api.py` to drive the multi-source flow described in design.md. Boot hook calls `warm_local_sources` once; request handler combines local + github results + warnings. **CRITICAL — implicit-local-source rule:** when `OPENSPEC_SOURCES` is unset OR empty, synthesize a single implicit `local:.` source pointing at the coordinator's own checkout (i.e., the path returned by `_get_repo_root()` per PR #211). This MUST derive `ProposalCard.repo` via `derive_local_repo`, so single-source coordinators continue to cluster PR↔Proposal cross-row by namespaced key (PR cards always carry `repo`; without the implicit source, ProposalCard.repo would be null and the mixed-null splitting rule would break clustering). Make 4.1–4.3 pass.
  **Dependencies:** 4.2, 4.3

- [ ] 4.4a (S) Add pytest `test_openspec_proposals_api.py::test_implicit_local_source_unset_env` covering: `OPENSPEC_SOURCES` unset → response proposals all have `repo` derived from the coordinator's own origin (NOT null); cross-row clustering with a PR sharing the same repo + change_id forms a cluster. Asserts the implicit-local-source rule explicitly so a regression cannot silently break PR #211 clustering.
  **Dependencies:** 4.4

- [ ] 4.5 ✓ CHECKPOINT — full coordinator test suite green (the PR #211 baseline — `test_github_classifier.py`, `test_github_rest_adapter.py`, `test_github_prs_api.py`, `test_openspec_proposals_api.py`, `test_kanban_viz_saved_views.py` — must remain green alongside the new multi-source tests). Capture the green test count at the START of this work-package's worktree and verify the same count + new tests pass at checkpoint; do NOT hardcode a count number in this checkpoint description. Commit as `feat(openspec-proposals): multi-source fan-out + degraded mode`.
  **Dependencies:** 4.4

## Section 5 — Coordinator: saved-view schema extension

- [ ] 5.1 (S) Write failing pytest `agent-coordinator/tests/test_kanban_viz_saved_views.py::test_hidden_repos_validates` covering: saved view with `hidden_repos: ["jankneumann/scratch"]` validates; pre-existing saved view without the field still validates; saved view with `hidden_repos: ["not_a_valid_entry"]` fails validation with a clear error. Covers spec scenarios "Saved view with hidden_repos validates" and "Pre-existing saved view continues to validate".
  **Dependencies:** None

- [ ] 5.2 (XS) Extend `agent-coordinator/src/schemas/kanban_viz/saved-view.json` with optional `hidden_repos: array<string>` under `view`, items matching `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`. Make 5.1 pass.
  **Dependencies:** 5.1

- [ ] 5.3 ✓ CHECKPOINT — schema validator green on round-trip via `PUT /kanban-viz/saved-views/{slug}` then `GET`; commit as `feat(saved-view): hidden_repos field`.
  **Dependencies:** 5.2

## Section 6 — Contracts: OpenAPI + TS types update

- [ ] 6.1 (S) Extend `openspec/changes/extend-kanban-viz-multi-repo-proposals/contracts/openapi/v1.yaml` with: new `OPENSPEC_SOURCES` documentation in the endpoint description; new `repo`/`change_id_namespaced` fields on `ProposalCard`; new `_warnings` array shape on `ProposalListResponse`; new `source: "live" | "cache" | "mixed"` enum extension; new 503 error code `openspec_sources_invalid`.
  **Dependencies:** None (contract changes are spec-derived)

- [ ] 6.2 (S) Update `openspec/changes/extend-kanban-viz-multi-repo-proposals/contracts/generated/types.ts`: add `repo: string | null` and `change_id_namespaced: string | null` to `ProposalCard`; add `repo?: string | null` to `IssueCard`; add `_warnings?: SourceWarning[]` to `ProposalListResponse`; extend `source` enum to include `"mixed"`. Verify with `cd apps/kanban-viz && npm run typecheck`.
  **Dependencies:** 6.1

- [ ] 6.3 ✓ CHECKPOINT — both contract files updated; commit as `feat(contracts): multi-repo proposal fields + warnings + source mixed`.
  **Dependencies:** 6.2

## Section 7 — SPA: type extension + repo derivation

- [ ] 7.1 (S) Write failing vitest `apps/kanban-viz/src/lib/__tests__/derive-issue-repo.test.ts` with the 4 spec scenarios for `deriveIssueRepo(labels)`: matching label → derived value; no match → null; multiple matches → first wins + console.warn; mixed case → lowercased.
  **Dependencies:** 6.3

- [ ] 7.2 (S) Implement `deriveIssueRepo` in `apps/kanban-viz/src/lib/coordinator-types.ts` (or a sibling utils file under `src/lib/`; do NOT import from `openspec/changes/.../contracts/` — `tsconfig.json` has `"include": ["src"]` so the SPA cannot resolve files outside `apps/kanban-viz/src/`). The in-change `contracts/generated/types.ts` is the spec source of truth; the SPA's `coordinator-types.ts` is the runtime copy that gets edited. Add `repo?: string | null` to the `IssueCard` interface AND `repo: string | null`, `change_id_namespaced: string | null` to the `ProposalCard` interface. Make 7.1 pass.
  **Dependencies:** 7.1

- [ ] 7.3 (S) Write failing vitest `apps/kanban-viz/src/lib/__tests__/cluster-key.test.ts` for the cluster key resolution: same-repo cluster uses namespaced key; cross-repo same change_id does NOT cluster; all-null-repo falls back to bare; mixed null/non-null splits. Covers spec scenarios under "Namespaced Cluster Key Resolution".
  **Dependencies:** 7.2

- [ ] 7.4 (M) Refactor `clusterBoardCards` inside `apps/kanban-viz/src/hooks/useBoardCards.ts` (CONFIRMED file location — PR #211 co-located the function in the hook, NOT a standalone `src/lib/clusterBoardCards.ts`) to use `getClusterKey(card)` + the mixed-null splitting rule. Update the existing PR #211 cluster tests at `apps/kanban-viz/src/hooks/__tests__/useBoardCards.test.ts` in lock-step (don't move them). Make 7.3 pass without regressing PR #211 cluster behavior — the all-null fallback path must still group cards as before.
  **Dependencies:** 7.3

- [ ] 7.5 ✓ CHECKPOINT — vitest green for `derive-issue-repo`, `cluster-key`, AND the existing PR #211 cluster tests; commit as `feat(kanban-viz): repo derivation + namespaced cluster key`.
  **Dependencies:** 7.2, 7.4

## Section 8 — SPA: RepoBadge + hook wiring

- [ ] 8.1 (S) Write failing vitest `apps/kanban-viz/src/components/__tests__/RepoBadge.test.tsx`: renders short form by default; tooltip shows full `<owner>/<repo>`; `aria-label` includes the qualifier; same repo produces same color across renders; null repo renders nothing.
  **Dependencies:** 7.5

- [ ] 8.2 (S) Implement `apps/kanban-viz/src/components/RepoBadge.tsx` with hash-to-HSL color derivation (deterministic, no randomization). Make 8.1 pass.
  **Dependencies:** 8.1

- [ ] 8.3 (M) Wire `RepoBadge` into `Card.tsx` (the PR #211 issue renderer at `apps/kanban-viz/src/components/Card.tsx` — there is no `IssueCardView`), `PRCardView.tsx`, and `ProposalCardView.tsx`. Update `useBoardCards` to call `deriveIssueRepo` on each issue post-fetch (before clustering, so the namespaced cluster key sees the derived value). Vitest assertion: a card with `repo: "x/y"` renders the badge; a card with `repo: null` does not.
  **Dependencies:** 8.2, 7.5

- [ ] 8.4 ✓ CHECKPOINT — SPA test suite green: the PR #211 baseline tests (Card / Board / useCoordinator / VendorSwimlanes / App / e2e.integration) must remain green alongside the new multi-repo tests. Capture the green test count at the START of this work-package's worktree and verify the same count + new tests pass at checkpoint; do NOT hardcode a count number in this checkpoint description (the post-rebase count may differ slightly from the count reported by PR #211's IMPL_REVIEW). Commit as `feat(kanban-viz): RepoBadge + multi-repo hook integration`.
  **Dependencies:** 8.3

## Section 9 — SPA: hidden_repos UX + partial-result chip

- [ ] 9.1 (S) Write failing vitest `apps/kanban-viz/src/components/__tests__/HiddenReposToggle.test.tsx`: chip group renders one entry per unique repo on board; clicking a chip toggles hidden state; persisted via saved view round-trip; hidden cards excluded from row totals and from cluster computation.
  **Dependencies:** 8.4

- [ ] 9.2 (M) Implement `HiddenReposToggle.tsx` component + wire to saved-view persistence (extend the existing saveView module to include `hidden_repos`). Make 9.1 pass.
  **Dependencies:** 9.1

- [ ] 9.3 (S) Write failing vitest extending `SourceSwimlanes.test.tsx`: when `proposalsResponse._warnings.length > 0`, the Proposals row renders a partial-result chip with warning chrome; clicking the chip surfaces the list of failed sources.
  **Dependencies:** 8.4

- [ ] 9.4 (S) Update `SourceSwimlanes.tsx` to render the partial-result chip per 9.3. Make the test pass.
  **Dependencies:** 9.3

- [ ] 9.5 ✓ CHECKPOINT — full SPA suite green including new hidden-repo and partial-result tests; commit as `feat(kanban-viz): hidden_repos toggle + partial-result chip`.
  **Dependencies:** 9.2, 9.4

## Section 10 — Integration test + docs

- [ ] 10.1 (M) Extend `apps/kanban-viz/src/__tests__/e2e.integration.test.tsx` with a multi-source mocked fixture: `GET /openspec/proposals` returns proposals from 2 distinct `repo` values + `_warnings` array; `GET /issues/list` returns issues with `repo:<owner>/<repo>` labels. Assert: all 3 rows render with repo badges; same-repo cluster forms across rows; cross-repo same-change_id does NOT cluster; partial-result chip appears; hidden_repos filter hides matching cards.
  **Dependencies:** 9.5

- [ ] 10.2 (S) Update `docs/kanban-viz/README.md` with: `OPENSPEC_SOURCES` syntax, hybrid cache semantics, `repo:` label convention, RepoBadge UX, `hidden_repos` saved-view field, `_warnings` partial-result chip behavior, `OPENSPEC_SOURCES_GITHUB_CAP` env var, cross-link to PR #211 `GITHUB_REPOS` section.
  **Dependencies:** 10.1

- [ ] 10.3 (XS) Run `openspec validate extend-kanban-viz-multi-repo-proposals --strict` — must exit 0. Fix any spec drift.
  **Dependencies:** 10.2

- [ ] 10.4 (XS) Run `agent-coordinator/.venv/bin/python skills/validate-packages/scripts/validate_work_packages.py --check-overlap openspec/changes/extend-kanban-viz-multi-repo-proposals/work-packages.yaml` — must exit 0 with all 6 checks pass.
  **Dependencies:** 10.3

- [ ] 10.5 ✓ CHECKPOINT — full validation chain green: openspec --strict + validate-packages + coordinator pytest + SPA vitest + typecheck. Commit as `test(integration): multi-repo board + docs updates`.
  **Dependencies:** 10.3, 10.4

## Section 11 — Deploy preconditions (ops handoff)

- [ ] 11.1 (S) On coord.rotkohl.ai, set `OPENSPEC_SOURCES=local:/app/openspec,github:jankneumann/newsletter-aggregator,github:jankneumann/agentic-assistant` (or whatever owned repos are in scope). Verify the boot warmup completes within 5 seconds and no `_warnings` are emitted at boot.

- [ ] 11.2 (S) Verify PAT scope on coord.rotkohl.ai covers `Contents: Read` on every configured github source (the PR endpoint already needs `Pull requests: Read`; this adds `Contents: Read` for the directory listing). Hit `GET /openspec/proposals` once and confirm proposals from EACH configured source appear without `github_403`/`github_404` warnings.

- [ ] 11.3 (S) Smoke test the SPA at coord.rotkohl.ai: refresh shows proposals from all configured repos; RepoBadge renders with stable colors; cross-repo same-change_id does NOT cluster; hidden_repos saves and restores.

- [ ] 11.4 ✓ CHECKPOINT — deployed and operationally live; the personal-coordinator multi-repo flow is end-to-end visible.
