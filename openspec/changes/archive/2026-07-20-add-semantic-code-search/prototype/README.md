# Implementation Prototype: add-semantic-code-search

Working-shape prototype accompanying [decision-memo.md](../decision-memo.md). These files
demonstrate that the storage-backend swap is a ~300-line seam, written against the **actual**
upstream APIs (verified by source inspection of `cocoindex-io/cocoindex-code` and
`cocoindex-io/cocoindex` @ HEAD, 2026-07-19). They are illustrative — not wired into any build,
not imported by anything, and superseded by whatever `wp-vendor-backend` /
`wp-coordinator-service` produce against the specs and contracts.

| File | Replaces / mirrors | Notes |
|---|---|---|
| `postgres_backend/indexer_pg.py` | upstream `indexer.py` (123 lines, sqlite-vec) | Same flow; `postgres.mount_table_target` + `declare_vector_index(metric="cosine", method="hnsw")`; per-repo tables (D2); `memo=True` incremental seam untouched |
| `postgres_backend/query_pg.py` | upstream `query.py` (147 lines, three code paths) | One pgvector statement replaces KNN/full-scan/heapq-merge branches; BM25 RRF slot marked (D3) |
| `coordinator/code_search.py` | pattern of `agent-coordinator/src/memory.py` | Service consumed by both surfaces; registry consistency (D4), 409/422 error taxonomy, scope filtering (D7) |

Key upstream API facts the prototype encodes (so reviewers don't need to re-derive them):

- `postgres.mount_table_target(db: ContextKey[asyncpg.Pool], table_name, table_schema, ...)` —
  the connection context is an **asyncpg pool**, unlike sqlite's `ManagedConnection`.
- `TableSchema.from_class(CodeChunk, primary_key=["id"])` maps the
  `Annotated[NDArray[np.float32], EMBEDDER]` field to `vector(n)` automatically, resolving `n`
  from the embedder — no hand-written dimension.
- `declare_vector_index` supports `metric={"cosine","l2","ip"}`, `method={"ivfflat","hnsw"}`.
- sqlite-vec's `Vec0TableDef` partition/auxiliary columns have no Postgres equivalent because
  none is needed — filtering happens in the ranking statement.
