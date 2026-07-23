# Tasks: Add revision-aware semantic index registry

Tasks follow test-driven order. Sizes use the plan-feature attention budget;
none are L or XL. Checkpoints occur after every two to three implementation
tasks.

## Phase 0 — Contract freeze

- [x] 0.1 (S) Validate the registry contracts against the selected design;
  verify SQL parses in a transaction plus the JSON Schema accepts every
  lifecycle state.
  **Spec scenarios**: code-search (Stable identity is reused, Storage identity is isolated, Ready completion records provenance)
  **Contracts**: contracts/db/schema.sql, contracts/index-record.schema.json
  **Design decisions**: D1, D3, D4
  **Dependencies**: None

## Phase 1 — Additive persistence

- [x] 1.1 (S) Write structural migration tests for the natural-key uniqueness,
  revision constraint, lifecycle constraint, canonical pointer, and absence of
  destructive DDL.
  **Spec scenarios**: code-search (Concurrent creation returns one record, Canonical promotion accepts a ready main index)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D1, D2, D5
  **Dependencies**: 0.1
- [x] 1.2 (M) Write live Postgres tests for idempotent migration, duplicate
  ensure under concurrency, trigger-enforced canonical safety, and compare-and-swap
  promotion.
  **Spec scenarios**: code-search (Concurrent creation returns one record, Non-main index cannot become canonical, Stale promotion is rejected)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D1, D4, D5
  **Dependencies**: 1.1
- [x] 1.3 (M) Create
  `agent-coordinator/database/migrations/029_revision_aware_code_search_indexes.sql`
  from the frozen DB contract.
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D1, D2, D3, D5
  **Dependencies**: 1.1, 1.2

- [x] Checkpoint: run migration tests, review the cumulative diff, verify package scope

## Phase 2 — Identity and registry lifecycle

- [x] 2.1 (S) Write unit tests for exact revision validation, namespace
  validation, natural-key construction, storage-key generation, and JSON record
  decoding.
  **Spec scenarios**: code-search (Symbolic revision is rejected, Storage identity is isolated)
  **Contracts**: contracts/index-record.schema.json
  **Design decisions**: D2, D3
  **Dependencies**: 0.1
- [x] 2.2 (M) Implement the revision-aware identity model with storage-table
  naming in the light import layer of `code_search_pkg`.
  **Contracts**: contracts/index-record.schema.json
  **Design decisions**: D2, D3, D7
  **Dependencies**: 2.1
- [x] 2.3 (M) Write async repository tests for idempotent ensure, lease claim,
  expired-lease takeover, guarded completion, durable failure, and
  not-configured outcomes.
  **Spec scenarios**: code-search (Stable identity is reused, Active lease owns completion, Expired lease permits takeover, Ready completion records provenance)
  **Contracts**: contracts/db/schema.sql, contracts/index-record.schema.json
  **Design decisions**: D4
  **Dependencies**: 1.3, 2.2
- [x] 2.4 (M) Implement the asyncpg registry repository with atomic
  ensure/claim/complete operations and typed lifecycle errors.
  **Contracts**: contracts/db/schema.sql, contracts/index-record.schema.json
  **Design decisions**: D1, D4
  **Dependencies**: 2.3

- [x] Checkpoint: run package unit tests, review the cumulative diff, verify package scope

## Phase 3 — Canonical promotion

- [x] 3.1 (M) Write registry tests for ready-main promotion, cross-repository
  rejection, non-main rejection, incomplete-index rejection, and stale
  compare-and-swap rejection.
  **Spec scenarios**: code-search (Canonical promotion accepts a ready main index, Non-main index cannot become canonical, Stale promotion is rejected)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D5
  **Dependencies**: 2.4
- [x] 3.2 (M) Implement guarded canonical promotion in the registry repository.
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D5
  **Dependencies**: 3.1

## Phase 4 — Garbage collection

- [x] 4.1 (M) Write tests for retention eligibility, active-lease exclusion,
  main exclusion, canonical exclusion, deletion success, and deletion failure.
  **Spec scenarios**: code-search (Expired feature index is collected, Main indexes are never collected, Failed storage deletion remains retryable)
  **Contracts**: contracts/db/schema.sql, contracts/index-record.schema.json
  **Design decisions**: D6
  **Dependencies**: 2.4, 3.2
- [x] 4.2 (M) Implement candidate claiming, injected storage deletion, durable
  tombstoning, and retryable failure handling.
  **Contracts**: contracts/db/schema.sql, contracts/index-record.schema.json
  **Design decisions**: D6
  **Dependencies**: 4.1

- [x] Checkpoint: run lifecycle tests, review the cumulative diff, verify package scope

## Phase 5 — Compatibility and documentation

- [x] 5.1 (S) Write compatibility tests proving existing repo-slug query helpers
  and disabled-by-default code-search service behavior remain unchanged.
  **Spec scenarios**: code-search (Legacy reader remains compatible)
  **Design decisions**: D7
  **Dependencies**: 1.3, 2.4
- [x] 5.2 (S) Update `docs/guides/code-search.md` with namespace identity,
  canonical promotion, lifecycle inspection, garbage-collection safety, and
  the legacy-field deprecation boundary.
  **Spec scenarios**: code-search (Legacy reader remains compatible)
  **Design decisions**: D7
  **Dependencies**: 4.2, 5.1
- [x] 5.3 (M) Run code-search package tests, coordinator registry tests,
  strict OpenSpec validation, work-package validation, and live Postgres tests
  when `POSTGRES_DSN` is available.
  **Dependencies**: 5.2

- [x] Checkpoint: all suites green, cumulative diff maps to tasks, no scope creep
