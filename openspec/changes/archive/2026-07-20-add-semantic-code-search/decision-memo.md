# Decision Memo: Adopt cocoindex-code with a Postgres (ParadeDB) Storage Backend

**Change**: `add-semantic-code-search`
**Status**: Draft (pending Gate 2 approval)
**Created**: 2026-07-19
**Author**: Claude (plan-feature, coordinated tier)
**Decision class**: adopt-before-build substrate decision (per `openspec/roadmaps/codeviz/proposal.md`, Guiding Principles)

## Decision

Adopt [`cocoindex-io/cocoindex-code`](https://github.com/cocoindex-io/cocoindex-code) as the
semantic code-search engine for coding harnesses, with two scoped modifications:

1. **Swap its storage backend from sqlite-vec to Postgres/pgvector** (the ParadeDB instance the
   coordinator already runs), using the `postgres` connector that ships in the base
   [`cocoindex`](https://github.com/cocoindex-io/cocoindex) framework.
2. **Expose retrieval through the coordinator's dual surface** (`coordination_mcp.py` MCP tool for
   local agents, `coordination_api.py` HTTP endpoint for cloud agents), following the same
   service-module pattern as `memory.py`.

Do **not** replicate the tool from scratch, and do **not** adopt its standalone per-project
daemon/MCP topology as the primary integration for cloud sessions.

## Context: the gap this fills

An investigation of this repo (2026-07-19) found the stack has **lexical** retrieval
(ripgrep/Glob/Read), **structural** retrieval (the tree-sitter graph in
`docs/architecture-analysis/architecture.graph.json`), and **zero semantic** retrieval:

- No embeddings, vector stores, or similarity search anywhere in `agent-coordinator/` or `skills/`.
- Coordinator "memory" (`agent-coordinator/src/memory.py`, migration `004_memory_tables.sql`) is
  tag-overlap + time-decay over agent episodes — not code, not vectors.
- The ParadeDB image (`paradedb/paradedb:v0.22.2`) ships `pgvector` and `pg_search`, and
  `openspec/specs/agent-coordinator/spec.md` mandates both extensions be available — yet no
  migration or query uses either. The capability is provisioned but unwired.
- The codeviz roadmap (Phase 3, "Subgraph retrieval and context assembly") already anticipates
  embedding-based similarity expansion but nothing implements it.

cocoindex-code's four capabilities — AST-aware chunking (tree-sitter, 28+ languages), embeddings
(local SentenceTransformers or LiteLLM cloud providers), incremental indexing (only changed files
re-index, via the base framework's Rust engine), and an MCP `search` tool for agents — occupy
exactly this empty slot. There is nothing to rip out and nothing that conflicts.

## Reuse analysis (measured against source, cocoindex-code @ HEAD 2026-07-19)

The package is ~5,900 lines of pure Python (the Rust engine lives in the `cocoindex` pip
dependency). Storage coupling, measured by direct inspection:

| Module | Lines | Storage coupling | Disposition |
|---|---|---|---|
| `cli.py` | 1,133 | 3 trivial refs | **Reuse** |
| `daemon.py` | 858 | 1 ref | **Reuse** (local sessions) |
| `client.py` | 716 | none | **Reuse** |
| `settings.py` | 634 | path helper | **Reuse** (DSN instead of path) |
| `grep.py` | 411 | none | **Reuse** |
| `server.py` (MCP) | 380 | **none** | **Reuse** |
| `project.py` | 319 | ~4 call sites | **Reuse with glue edits** |
| `protocol.py` | 256 | none | **Reuse** |
| `file_walk.py`, `chunking.py`, embedder stack | ~560 | none | **Reuse** |
| `indexer.py` | 123 | core (write path) | **Replace** (~120 lines) |
| `query.py` | 147 | core (read path) | **Replace** (~60 lines — simpler) |

**~95% reuse.** The storage seam is confined to two small modules plus a context key
(`shared.py:SQLITE_DB`) and glue. Note the README's "LMDB" description is stale — the code uses
`sqlite-vec` (SQLite `vec0` virtual tables).

### Postgres connector parity (base framework, verified against source)

`cocoindex/python/cocoindex/connectors/postgres/_target.py` (1,517 lines) provides everything the
two replaced modules need:

- `mount_table_target(db: ContextKey[asyncpg.Pool], table_name, table_schema, ...)` — same generic
  pattern as the sqlite connector cocoindex-code uses today.
- `TableSchema.from_class(...)` with automatic `vector(n)`/`halfvec(n)` pgvector type mapping from
  numpy-annotated dataclass fields (dimension resolved from the embedder annotation).
- `declare_vector_index(column=..., metric="cosine"|"l2"|"ip", method="ivfflat"|"hnsw", ...)`.
- The incremental engine's memoization (`@coco.fn(memo=True)`) lives in the framework, not the
  connector — **incremental re-indexing survives the backend swap untouched**.

The read path *simplifies* under Postgres: sqlite-vec's `vec0` KNN cannot combine nearest-neighbor
with arbitrary filters, forcing cocoindex-code into a three-way branch (per-partition KNN /
full-scan for path filters / Python heapq merge across languages). pgvector expresses all of it as
one `WHERE ... ORDER BY embedding <=> $1 LIMIT k` query — and that query is also where ParadeDB's
`pg_search` BM25 term slots in for hybrid lexical+semantic retrieval (exact-identifier matches
matter for code; hybrid reliably beats pure-vector).

## Why Postgres instead of the stock sqlite-vec backend

1. **Ephemeral cloud sessions.** Cloud harness containers are reclaimed after each session; a
   per-project on-disk index would rebuild every session, destroying the token-savings economics.
   A shared ParadeDB index persists server-side across container churn and is reachable by cloud
   agents over the network they already use for coordination.
2. **One shared index per fleet, not N per-agent daemons.** All parallel agents in a run query the
   same index through the coordinator, instead of each spawning a warm-model process.
3. **Hybrid BM25 + vector in one engine.** ParadeDB bundles `pg_search` and `pgvector`; the stock
   backend would need a bolt-on lexical index.
4. **Scope-aware retrieval.** Results can be intersected with `work-packages.yaml`
   `scope.read_allow` whitelists (`skills/parallel-infrastructure/scripts/scope_checker.py`) —
   an agent cannot retrieve code it is not allowed to read. A standalone index has no notion of
   these boundaries.
5. **No new storage silo.** Vectors live in the operational database the coordinator already
   deploys, backs up, and migrates — consistent with the codeviz storage-tier policy (embedding
   stores are operational-tier, never committed).

## Alternatives rejected

- **Adopt as-is (sqlite-vec, per-project daemon + standalone MCP).** Zero integration cost, but
  fails the ephemeral-cloud constraint, duplicates warm daemons per agent, cannot do hybrid BM25,
  and bypasses coordinator scope enforcement. Retained as the *spike vehicle* (see Risks) because
  it validates retrieval quality with an afternoon of setup.
- **Build natively on the base `cocoindex` framework (skip cocoindex-code).** The framework's
  Postgres target makes the pipeline easy, but we would re-implement the AST chunker registry,
  language detection, file-walk/ignore semantics, embedder management with rate pacing, CLI UX,
  and MCP server — the ~5,600 lines that work today. Poor trade.
- **Build on latent pgvector with no cocoindex at all.** Maximal datastore consolidation, but we
  would also own chunking, incremental change tracking, and 28-language parsing. This is exactly
  the "greenfielding extraction" the codeviz proposal warns against.

## Integration shape

```
                    ┌────────────────────────────────────────────┐
                    │      agent-coordinator (FastAPI + MCP)     │
  local agents ──── │  coordination_mcp.py   @mcp.tool           │
   (MCP/stdio)      │    search_code(query, repo, k, scope)      │
                    │  coordination_api.py   POST /search/code   │
  cloud agents ──── │  src/code_search.py    (service, like      │
   (HTTP)           │    memory.py: embed → SQL → ranked slices) │
                    └───────────────┬────────────────────────────┘
                                    │ asyncpg
                    ┌───────────────▼────────────────────────────┐
                    │  ParadeDB (Postgres + pgvector + pg_search)│
                    │  code_chunks__<repo_slug> tables + HNSW    │
                    └───────────────▲────────────────────────────┘
                                    │ cocoindex incremental pipeline
                    ┌───────────────┴────────────────────────────┐
                    │  vendored cocoindex-code + pg backend      │
                    │  (indexer_pg.py / query_pg.py replace the  │
                    │   sqlite pair; all other modules reused)   │
                    └────────────────────────────────────────────┘
```

Read path is a coordinator **read** (direct, uncoordinated — consistent with "direct reads,
coordinated writes"). Re-indexing is a **write** owned by an indexer job (post-commit hook or
scheduled), never by query-path callers. Retrieval is exposed as a **tool/endpoint, not an MCP
resource**, so it survives the `http_proxy.py` fallback identically for local and cloud agents
(see `coordination_mcp.py` D6 note).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Retrieval quality unproven on this repo | **Spike gate (task phase 0)**: run stock cocoindex-code locally on this repo; measure hit-rate vs. ripgrep baseline on ~10 real agent retrieval tasks before any Postgres work proceeds. |
| Tight upstream pin `cocoindex>=1.0.13,<1.1.0`; young API | Vendor the two replaced modules; pin hard in `pyproject.toml`; treat upgrades as deliberate events with the fixture tests as the tripwire. |
| No storage-backend registry upstream (unlike chunkers) | Open an upstream PR proposing a backend option; carry the vendored patch (~2 files) until accepted or declined. Apache 2.0 permits either outcome. |
| Multi-repo collisions in shared DB | Per-repo table names (`code_chunks__<repo_slug>`) via the existing `table_name` parameter — zero query changes, trivial unload per repo (DROP TABLE). |
| Embedding model access in cloud sessions | Coordinator-side query embedding (server embeds the query string); index-time embedding runs where the indexer job runs. Local sessions may still use the warm daemon. |

## Relationship to codeviz

This change occupies the **semantic-retrieval slot** codeviz Phase 3 reserves for
similarity-based expansion, and respects its substrate separation: deterministic code facts stay
with tree-sitter/SCIP-class extractors; agent memory stays with `memory.py`; embeddings are an
operational retrieval aid with no provenance claims. The base framework also ships a `falkordb`
connector — if codeviz's substrate evaluation ratifies FalkorDB, the same pipeline engine adopted
here can feed the graph store. This memo satisfies the "adopt-before-build" evaluation for the
code-search retrieval substrate only; it does not pre-empt the codeviz Phase 0 graph-substrate
benchmark.

## Implementation prototype

A working-shape prototype accompanies this memo under
[`prototype/`](./prototype/README.md):

- `prototype/postgres_backend/indexer_pg.py` — the write path against
  `cocoindex.connectors.postgres` (mount, vector index declaration, per-repo tables).
- `prototype/postgres_backend/query_pg.py` — the read path as a single pgvector query with
  language/path filters and the pg_search hybrid extension point.
- `prototype/coordinator/code_search.py` — the coordinator service module and the MCP/HTTP
  surface wiring, mirroring `memory.py` conventions.

The prototype is illustrative (not wired into the build); the authoritative behavior is specified
in `specs/` and the contracts in `contracts/`.
