# Change: add-semantic-code-search

**Status**: Draft
**Created**: 2026-07-19
**Author**: Claude (plan-feature, coordinated tier)
**Decision record**: [decision-memo.md](./decision-memo.md)

## Why

Coding agents in this repo retrieve code context through lexical search (ripgrep/Glob/Read) and
the structural tree-sitter graph — there is no semantic retrieval anywhere in the stack. Queries
like "find how work-queue claiming handles retries" are unanswerable unless an agent already knows
the identifier names, so agents over-read files and burn context tokens. Meanwhile the ParadeDB
instance the coordinator already runs ships `pgvector` and `pg_search` mandated-but-unused, and
the codeviz roadmap reserves a semantic-retrieval slot (Phase 3 similarity expansion) that nothing
implements.

[`cocoindex-io/cocoindex-code`](https://github.com/cocoindex-io/cocoindex-code) (Apache 2.0)
provides AST-aware chunking (tree-sitter, 28+ languages), local or cloud embeddings, incremental
indexing, and an agent-facing MCP `search` tool. Source analysis (see decision memo) shows ~95%
of its ~5,900 Python lines are storage-agnostic; the sqlite-vec coupling is confined to
`indexer.py` (123 lines) + `query.py` (147 lines), and the base `cocoindex` framework already
ships a Postgres/pgvector connector with full API parity (`mount_table_target`,
`declare_vector_index`, automatic `vector(n)` type mapping).

**Latent intent (from discovery conversation, 2026-07-18/19)**: reduce per-agent context-token
burn and make retrieval quality a fleet-wide, persistent capability rather than a per-session
rebuild — cloud sessions are ephemeral, so the index must live server-side; retrieval must
respect work-package scope boundaries; and the coordinator must expose it uniformly to local
(MCP) and cloud (HTTP) agents like every other capability.

## What Changes

- **New capability `code-search`** owning semantic indexing and retrieval of repository code.
- **Vendored Postgres backend for cocoindex-code**: a small vendored package
  (`packages/code-search/`) that reuses cocoindex-code's chunking/embedder/settings/file-walk
  modules as libraries and replaces its two storage modules with Postgres equivalents built on
  `cocoindex.connectors.postgres` (asyncpg + pgvector, HNSW index, cosine metric). Per-repo
  namespacing via table names (`code_chunks__<repo_slug>`).
- **Coordinator database migration**: `code_search_registry` table tracking indexed repos
  (slug, root path, last-indexed commit, embedder model + dimension); chunk tables are created by
  the cocoindex pipeline itself (system-managed targets).
- **Coordinator service `src/code_search.py`** (pattern: `memory.py`): embeds the query
  server-side, runs the pgvector KNN (phase 2: hybrid with `pg_search` BM25), returns ranked
  source slices with file/line provenance.
- **Dual-surface exposure**: `search_code` MCP tool in `coordination_mcp.py` (local agents) and
  `POST /search/code` in `coordination_api.py` (cloud agents). Read-only; classified `read`;
  works through the `http_proxy.py` fallback. Optional `scope` parameter intersects results with
  a work package's `read_allow` globs.
- **Indexer job**: an `index_repo` entrypoint (CLI + coordinator-triggerable) running the
  incremental cocoindex pipeline; wired as a post-merge hook target, not into agent query paths.
- **Spike gate (phase 0)**: stock cocoindex-code evaluated on this repo against a ripgrep
  baseline (~10 realistic retrieval tasks) before Postgres implementation proceeds; results
  recorded in the change directory. If quality fails the gate, the change stops with a written
  finding.
- **Not in scope**: replacing grep/structural retrieval (complementary, not superseded); codeviz
  graph substrate decisions; agent-memory embeddings in `memory.py`; upstream-PR acceptance
  (attempted, not required).

## Approaches Considered

### Selected Approach

**Approach B — adopt cocoindex-code, vendored Postgres backend, coordinator-exposed**
(selected during the planning conversation, 2026-07-19; user explicitly directed the
Postgres-backend extension and coordinator dual-surface exposure after reviewing the reuse
analysis). Approaches A and C retained as brief records below.

### Approach A — Adopt as-is (sqlite-vec + standalone daemon/MCP)

Install cocoindex-code unmodified; each developer machine / session runs its own index and MCP
server.

- **Pros**: zero integration cost; upstream-supported path; local-first with no API key.
- **Cons**: ephemeral cloud containers rebuild the index every session (defeats the token-savings
  economics); N warm daemons for N agents; no hybrid BM25; bypasses coordinator scope
  enforcement; a fourth storage silo.
- **Effort**: S

### Approach B — Adopt + vendored Postgres backend + coordinator exposure — **Recommended**

Reuse ~95% of cocoindex-code as a library; replace `indexer.py`/`query.py` with Postgres
equivalents on the base framework's connector; expose retrieval via the coordinator's MCP + HTTP
surfaces backed by the shared ParadeDB.

- **Pros**: index persists across ephemeral sessions; one shared index per fleet; hybrid
  BM25+vector unlocked by ParadeDB; scope-aware retrieval; no new datastore; read path actually
  simplifies (~147 lines of three-branch sqlite-vec SQL → one pgvector query); incremental
  indexing survives the swap (memoization is framework-level).
- **Cons**: carries a small vendored patch until upstream accepts a backend option; hard version
  pin required (`cocoindex>=1.0.13,<1.1.0`); indexer job needs embedding-model access
  server-side.
- **Effort**: M

### Approach C — Build natively on the base cocoindex framework

Skip cocoindex-code; write our own pipeline directly against `cocoindex` + `postgres` connector.

- **Pros**: no vendored patch; full control of schema and query shape.
- **Cons**: re-implements the AST chunker registry, language detection, ignore-file semantics,
  embedder rate-pacing, CLI, and MCP server (~5,600 working lines); slower to first value; the
  differentiated parts of cocoindex-code are exactly the parts we'd be rewriting.
- **Effort**: L

## Impact

- **Affected specs**: `code-search` (new), `agent-coordinator` (new endpoints/tool + migration).
- **Affected code**: `packages/code-search/` (new), `agent-coordinator/src/code_search.py` (new),
  `agent-coordinator/src/coordination_mcp.py`, `agent-coordinator/src/coordination_api.py`,
  `agent-coordinator/database/migrations/` (new migration), `agent-coordinator/pyproject.toml`
  (optional extra `code-search`).
- **Rollback plan**: capability is additive and feature-flagged (`CODE_SEARCH_ENABLED=off`
  default until the eval gate passes); migration is additive-only; dropping per-repo chunk tables
  fully unwinds the index. No existing behavior changes when disabled.
