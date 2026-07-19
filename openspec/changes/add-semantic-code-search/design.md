# Design: add-semantic-code-search

Technical decisions for adopting cocoindex-code with a Postgres backend and coordinator-surfaced
retrieval. Each decision is numbered (D1…) so tasks and tests can reference the ID.

## Architecture overview

Three layers, one seam each:

1. **Pipeline (vendored)** — `packages/code-search/`: cocoindex-code's chunking, language
   detection, file-walk, and embedder modules imported as libraries; two new modules
   (`indexer_pg.py`, `query_pg.py`) replace the sqlite pair against
   `cocoindex.connectors.postgres`.
2. **Storage (existing)** — the coordinator's ParadeDB: per-repo chunk tables
   (`code_chunks__<repo_slug>`, system-managed by the pipeline), HNSW cosine index, plus one
   coordinator-managed `code_search_registry` migration.
3. **Serving (existing pattern)** — `agent-coordinator/src/code_search.py` service consumed by
   the MCP tool (`search_code`) and HTTP endpoint (`POST /search/code`).

## Decisions

### D1 — Vendor the backend patch; attempt upstream contribution in parallel

cocoindex-code has a pluggable chunker registry but **no storage-backend registry**, so Postgres
support cannot be injected from outside; it is a patch. We vendor only the two replaced modules
plus glue (~300–400 lines) under `packages/code-search/`, importing everything else from the
pinned `cocoindex-code` distribution. An upstream PR proposing a `--backend postgres` option is
filed best-effort; acceptance removes our patch, rejection costs nothing. Full-fork is rejected
(maintenance burden for 2 files).

### D2 — Per-repo table names, not a repo_id column

`code_chunks__<repo_slug>` via the connector's `table_name` parameter. Zero query changes,
per-repo unload is `DROP TABLE`, and no cross-repo index contention. The slug is registered in
`code_search_registry` (D6). Cross-repo federated search is out of scope (codeviz territory);
revisit only if a real use case appears. Slug derivation: lowercase, `[^a-z0-9]+ → _`, prefixed
validation against `^[a-z][a-z0-9_]{0,50}$` to keep identifiers SQL-safe.

### D3 — Vector-only first; hybrid BM25 fusion behind the same service API

Phase 1 ships pgvector cosine KNN (`embedding <=> $1`, HNSW, `vector_cosine_ops`). Phase 2 adds a
`pg_search` BM25 term fused via Reciprocal Rank Fusion inside `code_search.py` — the service
signature (`query → ranked slices`) does not change, so surfaces are untouched. Hybrid is a
ranked-quality improvement, not an API change.

### D4 — Coordinator-side query embedding

The query string is embedded **in the coordinator service**, not by callers: cloud agents cannot
be assumed to have model access, and centralizing guarantees query/index embedder consistency
(model + dimension recorded per repo in `code_search_registry`; mismatch is a hard error, not a
silent wrong-answer). Default embedder: SentenceTransformers local model (no API key) loaded
lazily and kept warm in-process; LiteLLM cloud embedders configurable via env. Index-time
embedding runs wherever the indexer job runs (same settings module, same consistency check).

### D5 — Retrieval is a read; indexing is a write; surfaces expose only the read

`search_code` / `POST /search/code` are classified `read` (direct, uncoordinated — "direct reads,
coordinated writes"). Re-indexing (`index_repo`) is a separate entrypoint triggered post-merge or
on demand — never from the query path, and never implicitly by an agent search. Exposed as a
**tool/endpoint, not an MCP resource**, so it works identically through `http_proxy.py` (the D6
note in `coordination_mcp.py` — resources are not proxied in HTTP mode).

### D6 — `code_search_registry` migration; chunk tables are pipeline-managed

One additive coordinator migration creates `code_search_registry` (repo_slug PK, repo_root,
last_indexed_commit, embedder_model, embedding_dim, chunk_count, updated_at). Chunk tables are
created/evolved by the cocoindex pipeline itself (`managed_by=SYSTEM` targets) — the migration
system does not own tables whose schema the vendored pipeline derives from `CodeChunk`. The
contract file `contracts/db/schema.sql` documents both: the registry as DDL to apply, the chunk
table as the reference shape the pipeline produces.

### D7 — Scope-aware filtering is optional and server-side

`search_code(query, repo, k, scope=?)`: when a caller passes a work-package id (or explicit glob
list), the service intersects results with the package's `read_allow`/`deny` globs before
returning. Enforcement reuses the glob semantics of
`skills/parallel-infrastructure/scripts/scope_checker.py` (shared helper extracted, not
duplicated). Default (no scope) returns unrestricted results — parity with ripgrep today; scoped
dispatch (implement-feature work packages) passes the package id.

### D8 — Hard pin and fixture tripwire for the upstream dependency

`cocoindex[litellm]>=1.0.13,<1.1.0` and `cocoindex-code` pinned exact in
`packages/code-search/pyproject.toml`. A fixture test indexes a tiny sample tree and asserts
chunk/table shape, so an upstream API change breaks CI loudly at upgrade time, not at runtime.
Upgrades are deliberate PRs.

### D9 — Spike gate before Postgres work

Phase 0 runs **stock** cocoindex-code (sqlite-vec, local) on this repo: ~10 realistic retrieval
tasks with hand-labeled expected files, measured hit@5 and token cost vs. a ripgrep baseline,
recorded in `eval/spike-report.md` in this change directory. Proceed criteria: semantic search
finds the expected file in top-5 for ≥7/10 tasks, including ≥2 tasks where ripgrep's top hits
miss it. Failing the gate stops the change with a written finding (the vendored-backend work
never starts). This is the codeviz "adopt-before-build" principle applied at feature scale.

### D10 — Feature flag and rollback

`CODE_SEARCH_ENABLED` (default `off`) gates surface registration; the migration is additive-only;
`DROP TABLE code_chunks__*` + registry truncate fully unwinds. No existing agent behavior changes
while off.

## Data shapes

`CodeChunk` (pipeline row, pgvector-mapped): `id BIGINT PK, file_path TEXT, language TEXT,
content TEXT, start_line INT, end_line INT, embedding vector(N)` — N fixed per repo by the
registered embedder (D4).

Search result (service + both surfaces): `file_path, language, content, start_line, end_line,
score` — mirrors cocoindex-code's `QueryResult` so upstream tooling remains compatible; plus
`repo_slug` and optional `scope_filtered: bool` envelope fields at the surface layer.

## Failure modes

- **Registry/table missing** → structured 409 "repo not indexed" with the `index_repo` hint, not
  an empty result set (empty results must mean "indexed, nothing similar").
- **Embedder mismatch** (query model ≠ registry model) → hard error naming both models (D4).
- **DB unreachable** → surfaces return the same unavailable envelope the other coordinator tools
  use; agents fall back to ripgrep (their current behavior) — degradation is graceful by
  construction.
