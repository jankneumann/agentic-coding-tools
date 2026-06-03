# Tasks: Ambient Continuous Review with a Self-Verifying Finding Ledger

## Phase 0: Extract refine-core (shared backbone)

- [ ] 0.1 Write characterization test for `convergence_loop.converge()` capturing
  current iterate/synthesize/fix/validate outputs on a fixture change [S]
  **Spec scenarios**: refine-loop (Convergence loop delegates to refine-core)
  **Design decisions**: D3 (behavior-preserving extraction)
  **Dependencies**: None
- [ ] 0.2 Write unit tests for the `refine-core` primitive surface (iterate,
  synthesize, fix, validate) [S]
  **Spec scenarios**: refine-loop (Independent caller consumes refine-core)
  **Dependencies**: None
- [ ] 0.3 Extract `refine_core.py` in `skills/parallel-infrastructure/scripts/`
  from the convergence-loop internals [M]
  **Spec scenarios**: refine-loop (Independent caller consumes refine-core)
  **Design decisions**: D3
  **Dependencies**: 0.2
- [ ] 0.4 Re-point `convergence_loop.converge()` to delegate to `refine-core`;
  confirm characterization test passes unchanged [S]
  **Spec scenarios**: refine-loop (Convergence loop delegates to refine-core)
  **Dependencies**: 0.1, 0.3
- [ ] 0.5 Checkpoint: run convergence + refine-core tests, review diff, verify
  scope (only parallel-infrastructure + autopilot scripts touched)

## Phase 1: Ambient continuous review

- [ ] 1.1 Write tests for `post-commit` hook behavior: enqueues on commit, exits
  0 fast, no-ops under kill-switch [S]
  **Spec scenarios**: ambient-review (Commit enqueues an ambient review),
  (Operator disables ambient review), (Default-on after install)
  **Design decisions**: D6 (hook resolution pattern)
  **Dependencies**: None
- [ ] 1.2 Write tests for the ambient review runner: single-vendor dispatch,
  findings validate against schema with `review_type: ambient`, read-only [S]
  **Spec scenarios**: ambient-review (Review runs asynchronously and
  single-vendor), (Ambient reviewer attempts no writes)
  **Contracts**: contracts/review-ledger.schema.json
  **Design decisions**: D4 (single-vendor, read-only)
  **Dependencies**: None
- [ ] 1.3 Add `ambient` to the `review_type` enum in
  `openspec/schemas/review-findings.schema.json` [XS]
  **Design decisions**: D4
  **Dependencies**: 1.2
- [ ] 1.4 Implement `.githooks/post-commit` mirroring the `post-merge` resolution
  pattern (env seam, venv python, fail-open) [S]
  **Spec scenarios**: ambient-review (Commit enqueues an ambient review)
  **Design decisions**: D6
  **Dependencies**: 1.1
- [ ] 1.5 Implement the ambient review runner (single-vendor dispatch via the
  ambient archetype; writes findings to the ledger) [M]
  **Spec scenarios**: ambient-review (Review runs asynchronously and
  single-vendor)
  **Design decisions**: D4
  **Dependencies**: 1.2, 1.3, 2.4
- [ ] 1.6 Wire the kill-switch (`REVIEW_AMBIENT=0` / config flag) and update the
  hook installer to register `post-commit` [S]
  **Spec scenarios**: ambient-review (Operator disables ambient review)
  **Dependencies**: 1.4
- [ ] 1.7 Checkpoint: run hook + runner tests, review diff, verify scope

## Phase 2: Durable finding ledger + compact

- [ ] 2.1 Write tests for ledger read/write: local-first source of truth, write
  succeeds offline, stable-id keying [M]
  **Spec scenarios**: review-ledger (Finding written to local ledger),
  (Best-effort coordinator sync)
  **Contracts**: contracts/review-ledger.schema.json
  **Design decisions**: D1 (local-first), D2 (stable id)
  **Dependencies**: None
- [ ] 2.2 Write tests for lifecycle transitions (`open`→`addressed`→`retired`)
  and for `compact` (stale retire, duplicate consolidation, live preserve) [M]
  **Spec scenarios**: review-ledger (New finding starts open), (Finding marked
  addressed), (Stale finding retired), (Duplicate findings consolidated),
  (Live finding preserved)
  **Design decisions**: D5 (compact reuses consensus matching)
  **Dependencies**: None
- [ ] 2.3 Author `contracts/review-ledger.schema.json` and a ledger-entry model [S]
  **Contracts**: contracts/review-ledger.schema.json
  **Design decisions**: D2
  **Dependencies**: 2.1
- [ ] 2.4 Implement the ledger library: local-first store, stable-id keying,
  best-effort coordinator sync (idempotent) [M]
  **Spec scenarios**: review-ledger (Finding written to local ledger),
  (Best-effort coordinator sync)
  **Design decisions**: D1, D2
  **Dependencies**: 2.1, 2.3
- [ ] 2.5 Implement `compact` re-verification reusing `consensus_synthesizer`
  matching for dedup; retire stale, consolidate duplicates, preserve live [M]
  **Spec scenarios**: review-ledger (Stale finding retired), (Duplicate findings
  consolidated), (Live finding preserved)
  **Design decisions**: D5
  **Dependencies**: 2.2, 2.4
- [ ] 2.6 Checkpoint: run ledger + compact tests, review diff, verify scope
- [ ] 2.7 Write test for gate skills reading the ledger as warm context without
  weakening consensus [S]
  **Spec scenarios**: review-ledger (Gate review reads the ledger)
  **Dependencies**: 2.4
- [ ] 2.8 Wire gate-time review skills to load outstanding ledger findings as
  prior context (additive, non-blocking) [S]
  **Spec scenarios**: review-ledger (Gate review reads the ledger)
  **Dependencies**: 2.7

## Phase 3: Standalone refine loop

- [ ] 3.1 Write tests for the standalone refine entry point: runs over a commit
  range with no OpenSpec change present; terminates on clean or max iters [M]
  **Spec scenarios**: refine-loop (Refine a commit range without OpenSpec
  ceremony), (Refine terminates on clean or max iterations)
  **Dependencies**: None
- [ ] 3.2 Implement the standalone refine entry point over `refine-core`,
  reporting terminal status and findings to the ledger [M]
  **Spec scenarios**: refine-loop (Refine a commit range without OpenSpec
  ceremony)
  **Dependencies**: 3.1, 0.4, 2.4
- [ ] 3.3 Checkpoint: run refine tests, review diff, verify scope

## Phase 4: Findings → issue tracker

- [ ] 4.1 Write tests for issue sync: blocking confirmed finding files one issue,
  no duplicate filing, retire closes issue, no-op when MCP unavailable [M]
  **Spec scenarios**: review-issue-sync (Blocking finding becomes an issue),
  (No duplicate issue for an already-filed finding), (Retired finding closes its
  issue), (Issue sync is opt-in safe)
  **Dependencies**: None
- [ ] 4.2 Implement issue sync over the GitHub MCP tools: file on
  confirmed/blocking, record issue number, close on `retired`, fail-open [M]
  **Spec scenarios**: review-issue-sync (Blocking finding becomes an issue),
  (Retired finding closes its issue)
  **Dependencies**: 4.1, 2.5
- [ ] 4.3 Checkpoint: run issue-sync tests, review diff, verify scope

## Phase 5: Review-ledger swimlane in kanban-viz

- [ ] 5.1 Write component tests for the ledger swimlane: renders cards by
  lifecycle/severity/vendor, live SSE update, empty-state fallback [M]
  **Spec scenarios**: coordinator-kanban-viz (Ledger findings render as cards),
  (Live update on ledger change), (Swimlane degrades gracefully without ledger
  data)
  **Dependencies**: None
- [ ] 5.2 Add the SSE event payload for ledger changes (server side) [S]
  **Spec scenarios**: coordinator-kanban-viz (Live update on ledger change)
  **Dependencies**: 2.4
- [ ] 5.3 Implement the review-ledger swimlane component in `apps/kanban-viz` [M]
  **Spec scenarios**: coordinator-kanban-viz (Ledger findings render as cards),
  (Swimlane degrades gracefully without ledger data)
  **Dependencies**: 5.1, 5.2
- [ ] 5.4 Checkpoint: run kanban-viz tests, review diff, verify scope

## Phase 6: Integration & docs

- [ ] 6.1 End-to-end test: commit → ambient review → ledger → compact → issue
  sync → swimlane reflects state [M]
  **Spec scenarios**: ambient-review + review-ledger + review-issue-sync +
  coordinator-kanban-viz (cross-cutting)
  **Dependencies**: 1.5, 2.5, 4.2, 5.3
- [ ] 6.2 Document the ambient-review-ledger workflow including the kill-switch
  (CLAUDE.md pointer + docs page) [S]
  **Dependencies**: 6.1
- [ ] 6.3 Checkpoint: full test suite, review cumulative diff, verify scope
