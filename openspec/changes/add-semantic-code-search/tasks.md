# Tasks: add-semantic-code-search

Sizing per plan-feature Task Sizing Reference (no XL; L flagged). Test tasks precede the
implementation they verify (TDD). Spec scenario references use `<capability>.<n>` ordinals in
file order.

## Phase 0 — Spike gate (blocks all later phases; design D9)

- [ ] 0.1 (M) Build the retrieval eval set: 10 realistic agent retrieval tasks against this repo
  with hand-labeled expected files, plus the ripgrep baseline commands
  **Spec scenarios**: code-search.6 (quality gate)
  **Design decisions**: D9
  **Dependencies**: none
- [ ] 0.2 (S) Run stock cocoindex-code (sqlite-vec, local) on this repo; record hit@5 and token
  cost per task in `eval/spike-report.md` with an explicit pass/fail verdict
  **Spec scenarios**: code-search.6
  **Design decisions**: D9
  **Dependencies**: 0.1
- [ ] Checkpoint: review spike report; if verdict is FAIL, stop the change and write the finding

## Phase 1 — Contracts (wp-contracts)

- [ ] 1.1 (S) Validate `contracts/openapi/v1.yaml` (spectral or openapi-spec-validator) and
  `contracts/db/schema.sql` (apply registry DDL to a scratch ParadeDB)
  **Contracts**: contracts/openapi/v1.yaml, contracts/db/schema.sql
  **Dependencies**: 0.2
- [ ] 1.2 (S) Generate Pydantic request/response models into `contracts/generated/models.py`
  from the OpenAPI schemas
  **Contracts**: contracts/openapi/v1.yaml
  **Dependencies**: 1.1

## Phase 2 — Vendored Postgres backend (wp-vendor-backend)

- [ ] 2.1 (M) Write fixture tests for `indexer_pg`: index the sample tree
  (`tests/fixtures/sample_repo/`) into a scratch ParadeDB; assert chunk-table shape, HNSW index
  presence, provenance columns, and idempotent re-run
  **Spec scenarios**: code-search.1 (namespaced table), code-search.2 (provenance),
  code-search.3 (incremental no-op)
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D2, D6, D8
  **Dependencies**: 1.1
- [ ] 2.2 (M) Implement `packages/code-search/src/code_search_pkg/indexer_pg.py` — port of
  cocoindex-code `indexer.py` to `cocoindex.connectors.postgres` (asyncpg pool context key,
  `mount_table_target`, `declare_vector_index(metric="cosine", method="hnsw")`, per-repo table
  naming, slug validation); reuse upstream chunker registry/file-walk/settings unchanged
  **Design decisions**: D1, D2, D3, D8
  **Dependencies**: 2.1
- [ ] 2.3 (S) Write tests for single-file incremental reprocessing (modify one fixture file,
  assert only its chunks change)
  **Spec scenarios**: code-search.4 (single-file change)
  **Dependencies**: 2.2
- [ ] Checkpoint: run tests, review diff, verify scope (packages/code-search only)
- [ ] 2.4 (S) Write tests for `query_pg`: single-statement ranking with language/path filters;
  score in [0,1]; offset/limit
  **Spec scenarios**: code-search.5 (single statement), code-search.5a (conceptual query —
  eval fixture)
  **Contracts**: contracts/db/schema.sql (query contract)
  **Dependencies**: 2.2
- [ ] 2.5 (S) Implement `packages/code-search/src/code_search_pkg/query_pg.py` — single pgvector
  KNN statement replacing upstream `query.py`'s three-branch logic
  **Design decisions**: D3
  **Dependencies**: 2.4
- [ ] 2.6 (S) Package glue: `pyproject.toml` with hard pins (`cocoindex>=1.0.13,<1.1.0`,
  exact `cocoindex-code`), upstream-API fixture tripwire test, `index_repo` CLI entrypoint
  **Design decisions**: D1, D8
  **Dependencies**: 2.2, 2.5
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 3 — Coordinator service and surfaces (wp-coordinator-service)

- [ ] 3.1 (M) Write tests for `code_search.py` service — registry lookup, embedder-mismatch hard
  error, repo-not-indexed 409 envelope, scope glob filtering, DB-outage unavailable envelope
  **Spec scenarios**: code-search.4a (mismatch), code-search.4b (not indexed vs empty),
  code-search.5b (scope filtering), agent-coordinator.4 (graceful outage)
  **Contracts**: contracts/openapi/v1.yaml, contracts/generated/models.py
  **Design decisions**: D4, D5, D7
  **Dependencies**: 1.2
- [ ] 3.2 (M) Implement `agent-coordinator/src/code_search.py` — server-side query embedding
  (lazy warm SentenceTransformers default, LiteLLM via env), registry consistency check, KNN
  query, scope filtering via shared glob helper extracted from `scope_checker.py`
  **Design decisions**: D4, D5, D7
  **Dependencies**: 3.1, 2.5
- [ ] Checkpoint: run tests, review diff, verify scope (agent-coordinator only)
- [ ] 3.3 (S) Write surface tests — MCP tool and HTTP endpoint return identical payloads;
  http_proxy passthrough; `CODE_SEARCH_ENABLED=off` hides tool and 404s the route
  **Spec scenarios**: agent-coordinator.1 (identical results), agent-coordinator.2 (proxy),
  agent-coordinator.5 (flag)
  **Design decisions**: D5, D10
  **Dependencies**: 3.2
- [ ] 3.4 (S) Register `search_code` in `coordination_mcp.py` and `POST /search/code` in
  `coordination_api.py` behind the flag; read-only classification; no resource registration
  **Spec scenarios**: agent-coordinator.3 (never mutates)
  **Dependencies**: 3.3
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Indexing infrastructure (wp-indexing-infra)

- [ ] 4.1 (S) Write migration test — registry table shape, slug CHECK constraint, additive-only
  **Spec scenarios**: code-search.4 (registry)
  **Contracts**: contracts/db/schema.sql
  **Dependencies**: 1.1
- [ ] 4.2 (S) Add coordinator migration `NNN_code_search_registry.sql` (next free number) with
  `CREATE EXTENSION IF NOT EXISTS vector`
  **Design decisions**: D6
  **Dependencies**: 4.1
- [ ] 4.3 (S) Wire `index_repo` as a post-merge hook target and document the reindex trigger in
  `docs/guides/` (indexing never reachable from query surfaces)
  **Design decisions**: D5
  **Dependencies**: 2.6, 4.2
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 5 — Integration (wp-integration)

- [ ] 5.1 (M) End-to-end: index this repo into a live ParadeDB, run the Phase 0 eval set through
  `POST /search/code`, compare hit@5 to the spike report; append results to
  `eval/spike-report.md`
  **Spec scenarios**: code-search.5a, code-search.6
  **Dependencies**: all prior phases
- [ ] 5.2 (S) Docs: capability page, coordinator CLAUDE.md tool table entry, EMBEDDINGS/env
  configuration notes
  **Dependencies**: 5.1
- [ ] 5.3 (S) File the upstream PR proposing a `--backend postgres` option (best-effort; link in
  the session log)
  **Design decisions**: D1
  **Dependencies**: 5.1
- [ ] Checkpoint: full suite green, diff maps to tasks, scope verified

## Deferred (recorded, not scheduled)

- Hybrid BM25 + RRF fusion via pg_search (design D3 phase 2) — service-internal change only.
- Coordinator-triggered scheduled reindex (WatchdogService) — revisit after post-merge hook
  proves insufficient.
- Cross-repo federated search — codeviz territory.
