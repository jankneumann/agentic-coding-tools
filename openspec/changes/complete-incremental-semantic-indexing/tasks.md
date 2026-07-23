# Tasks: Complete incremental semantic indexing

Tasks follow test-driven order. No implementation task exceeds M. Checkpoints
occur after every two to three implementation tasks.

## Phase 0 — Contract freeze and compatibility proof

- [ ] 0.1 (S) Validate request, v2 record, execution-result, and database
  contracts. Prove every terminal result and policy-fingerprint variant, plus
  reject ready/non-durable, promoted/non-main, reused/non-ready, partial-parent,
  credential-bearing parameter, and other impossible JSON combinations.
  **Spec scenarios**: Duplicate ready request is a no-op, Policy change creates a distinct index, Missing database is explicit
  **Contracts**: contracts/index-request.schema.json, contracts/index-record-v2.schema.json, contracts/index-execution-result.schema.json, contracts/db/schema.sql
  **Design decisions**: D2, D6, D7
  **Dependencies**: None
- [ ] 0.2 (M) Write a mandatory non-skipping target-contract test with a
  deterministic fake for copied-row ownership, per-attempt staging, stale-write
  fencing, retry reset, and atomic publication. Freeze the selected thin
  `storage_pg.py` adapter boundary in `contracts/target-strategy.md`; live
  Postgres/CocoIndex evidence verifies but does not choose the architecture.
  Pin `cocoindex-code==0.2.37` and the light gitignore matcher dependency.
  **Spec scenarios**: One-file revision embeds only changed content, Deleted file is absent, Stale attempt cannot mutate published storage
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D3, D9
  **Dependencies**: 0.1

- [ ] Checkpoint: contracts parse, compatibility strategy is evidenced, no full-rebuild fallback selected

## Phase 1 — Registry identity, manifests, and heartbeat

- [ ] 1.1 (M) Write structural and live Postgres tests for contract
  fingerprints in index uniqueness, attempt/final manifests,
  compatible-parent lookup, lease renewal, and absence of destructive
  table/data DDL. Apply migration 030 over populated migration-029 pending,
  ready, and canonical rows and prove data/pointers survive.
  **Spec scenarios**: Policy change creates a distinct index, Current worker renews its lease, Compatible parent is selected
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D2, D3, D6
  **Dependencies**: 0.1
- [ ] 1.2 (M) Add migration
  `030_incremental_code_search_indexes.sql`, update typed registry models, and
  implement fingerprint-aware ensure, guarded compatible-parent linkage,
  attempt/final manifest persistence, and current-token lease renewal. Publish
  and validate the v2 index-record schema while preserving v1 legacy decoding.
  **Spec scenarios**: Policy change creates a distinct index, Stale worker cannot renew or complete, Manifest is revision-specific
  **Contracts**: contracts/db/schema.sql, contracts/index-request.schema.json, contracts/index-record-v2.schema.json
  **Design decisions**: D2, D3, D6
  **Dependencies**: 1.1

## Phase 2 — Exact source, eligibility, and embedding protocol

- [ ] 2.1 (M) Write pure tests for 40/64-character object resolution, clean
  HEAD equality, pre/post source proof, normalized repository-relative paths,
  nested `.gitignore`, include/exclude, `read_allow`, `deny`, baseline secret
  and generated-tree exclusions, symlink escapes, built-in scanner findings and
  scanner timeout/error, and fail-closed scope errors.
  **Spec scenarios**: Exact source is proven, Dirty source is rejected, Deny wins before read, Escaping symlink is rejected
  **Contracts**: contracts/index-request.schema.json
  **Design decisions**: D1, D4
  **Dependencies**: 0.1
- [ ] 2.2 (M) Implement the light source-proof and eligibility modules without
  importing CocoIndex or embedding dependencies. Produce a canonical policy
  fingerprint and an auditable eligibility reason for every manifest path.
  Pin the path matcher dependency and implement a bounded local-only scanner
  protocol with sanitized evidence.
  **Spec scenarios**: Exact source is proven, Ignored and out-of-scope files are excluded
  **Contracts**: contracts/index-request.schema.json
  **Design decisions**: D1, D2, D4
  **Dependencies**: 2.1
- [ ] 2.3 (S) Write protocol tests for explicit embedding model/dimension,
  deterministic whitelisted indexing parameters, readiness classification,
  sanitized credential references, and provider-independent fingerprints.
  **Spec scenarios**: Gateway is opt-in, Missing configuration makes no network attempt
  **Contracts**: contracts/index-request.schema.json
  **Design decisions**: D2, D5
  **Dependencies**: 0.1
- [ ] 2.4 (S) Implement the light `embedding_protocol.py` types consumed by
  both the CocoIndex adapter and later local/OpenAI-compatible configuration.
  **Spec scenarios**: Policy change creates a distinct index, Gateway is opt-in
  **Contracts**: contracts/index-request.schema.json
  **Design decisions**: D2, D5
  **Dependencies**: 2.3

- [ ] Checkpoint: registry and policy suites green, cumulative diff reviewed, package scope verified

## Phase 3 — Incremental isolated storage

- [ ] 3.1 (M) Write adapter tests for path-aware stable chunk IDs, annotated
  pgvector schema, final and attempt table naming, compatible-parent
  copy-forward, changed-file-only processing, deleted/ineligible omission,
  HNSW/count/schema verification, crash retry, and a late stale write after the
  replacement worker publishes.
  **Spec scenarios**: One-file revision embeds only changed content, Deleted file is absent, Retry reconciles isolated storage, Stale attempt cannot mutate published storage
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D3, D5, D9
  **Dependencies**: 0.2, 1.2, 2.2
- [ ] 3.2 (M) Implement the CocoIndex v1 `App` adapter and incremental storage
  builder. Provide stable contexts for repository root, Postgres pool, embedder,
  embedding parameters, and chunkers; use attempt-scoped storage plus a
  current-lease fenced publish transaction and return measured file/chunk
  statistics.
  **Spec scenarios**: Complete index is verified before readiness, One-file revision embeds only changed content
  **Contracts**: contracts/db/schema.sql, contracts/index-execution-result.schema.json
  **Design decisions**: D3, D5, D9
  **Dependencies**: 2.4, 3.1

## Phase 4 — Durable operation orchestration

- [ ] 4.1 (M) Write dependency-injected tests for ready short-circuit,
  concurrent claim, expired takeover, heartbeat, not-configured, failure,
  source mutation during execution, storage verification, ready completion,
  guarded main promotion, and cleanup of abandoned attempt storage.
  **Spec scenarios**: Duplicate ready request is a no-op, Concurrent request observes the durable operation, Missing embedder is durable, Runtime failure is durable, Main promotes only after readiness
  **Contracts**: contracts/index-request.schema.json, contracts/index-execution-result.schema.json
  **Design decisions**: D1, D6, D7
  **Dependencies**: 1.2, 2.2, 3.2
- [ ] 4.2 (M) Implement the light `indexing_runtime.py` orchestration layer,
  including lease heartbeat/cancellation, source re-verification, terminal
  result mapping, and canonical compare-and-swap after readiness.
  **Spec scenarios**: Stale worker cannot renew or complete, Source mutation prevents readiness, Feature index is not promoted
  **Contracts**: contracts/index-execution-result.schema.json
  **Design decisions**: D1, D6, D7
  **Dependencies**: 4.1

## Phase 5 — CLI and explicit embedder configuration

- [ ] 5.1 (M) Write CLI/config tests for exact revision and namespace
  arguments, scope files, JSON result output, exit codes, isolated
  `--full-rebuild`, pool cleanup, explicit local provider, explicit
  OpenAI-compatible/gateway provider, missing DSN, missing credentials, provider
  failures, dimension mismatch, wholly absent model/dimension as ephemeral
  not-configured, declared-but-unavailable provider as durable not-configured,
  unready full rebuild, and ready full-rebuild no-op.
  **Spec scenarios**: Missing database is explicit, Missing embedding contract is ephemeral, Missing embedder is durable, Gateway is opt-in, Full rebuild is isolated, Ready identity remains immutable
  **Contracts**: contracts/index-request.schema.json, contracts/index-execution-result.schema.json
  **Design decisions**: D5, D7, D8
  **Dependencies**: 2.2, 4.2
- [ ] 5.2 (M) Replace the legacy upsert/`NotImplementedError` path with request
  parsing, provider construction, registry/runtime invocation, structured
  output, and safe cleanup. Preserve ready-record immutability under
  `--full-rebuild` and keep light imports for `--help` and exact-search
  fallback.
  **Spec scenarios**: Reachable resources complete indexing, Gateway is opt-in, Missing configuration makes no network attempt, Ready identity remains immutable
  **Contracts**: contracts/index-request.schema.json, contracts/index-execution-result.schema.json
  **Design decisions**: D5, D8, D9
  **Dependencies**: 5.1

- [ ] Checkpoint: package unit suites green, CLI result contract stable, no query-path behavior changed

## Phase 6 — Live evidence and operator documentation

- [ ] 6.1 (M) Add the real sample repository fixture and replace unconditional
  E2E skips with resource-gated tests for table/HNSW shape, provenance,
  duplicate no-op, one-file delta, deletion, scope/secret exclusion,
  namespace/revision isolation, crash retry, and optional gateway smoke.
  **Spec scenarios**: all code-search scenarios
  **Design decisions**: D1-D9
  **Dependencies**: 5.2
- [ ] 6.2 (S) Update `docs/guides/code-search.md` with operation identity,
  copy-forward behavior, source/scope safety, provider configuration, gateway
  opt-in, result/error semantics, retries, and the boundary with `ri-03`.
  **Spec scenarios**: Missing database is explicit, Gateway is opt-in
  **Design decisions**: D5, D7, D8
  **Dependencies**: 6.1
- [ ] 6.3 (M) Run code-search and coordinator tests, strict OpenSpec and
  work-package validation, Ruff/Pyright, architecture checks, and live
  Postgres/embedder tests when resources are available. The report MUST
  distinguish mandatory target-contract passage, live integration passage, and
  environment-deferred live evidence.
  **Dependencies**: 6.2

- [ ] Checkpoint: all available suites green, cumulative diff maps to tasks, no scope creep
