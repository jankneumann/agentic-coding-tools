# code-search Specification (delta)

## ADDED Requirements

### Requirement: Semantic Code Index in Coordinator Postgres

The system SHALL maintain a semantic index of repository source code in the coordinator's
PostgreSQL database (ParadeDB), storing AST-aware chunks with pgvector embeddings in per-repo
tables named `code_chunks__<repo_slug>`, with an HNSW cosine index on the embedding column. Chunk
production SHALL reuse the vendored cocoindex-code chunking pipeline (tree-sitter AST chunkers
with recursive-splitter fallback), and each stored chunk SHALL carry `file_path`, `language`,
`content`, `start_line`, and `end_line` provenance.

#### Scenario: Indexing a repository creates a namespaced chunk table

- **WHEN** `index_repo` runs against a repository registered with slug `agentic_coding_tools`
- **THEN** a table `code_chunks__agentic_coding_tools` SHALL exist containing one row per chunk
  with non-null file path, language, line range, and an embedding of the registered dimension
- **AND** an HNSW index using cosine distance SHALL exist on the embedding column

#### Scenario: Chunks carry line-accurate provenance

- **WHEN** any chunk row is read back and its `file_path`, `start_line`, `end_line` are resolved
  against the working tree at the indexed commit
- **THEN** the resolved slice SHALL contain the chunk's `content`

### Requirement: Incremental Re-indexing

Re-indexing a repository SHALL reprocess only files whose content changed since the previous run,
using the cocoindex framework's memoized incremental engine. A re-run with no source changes
SHALL be a no-op on the chunk table.

#### Scenario: Unchanged repository is a no-op

- **WHEN** `index_repo` runs twice consecutively with no file modifications between runs
- **THEN** the second run SHALL NOT modify any chunk rows

#### Scenario: Single-file change reprocesses only that file

- **WHEN** exactly one indexed source file is modified and `index_repo` re-runs
- **THEN** only chunks belonging to that file SHALL be inserted, updated, or removed

### Requirement: Repo Registry with Embedder Consistency

The system SHALL record every indexed repository in a `code_search_registry` table carrying
`repo_slug`, `repo_root`, `last_indexed_commit`, `embedder_model`, `embedding_dim`, and
`updated_at`. Query-time embedding SHALL use the registered model for the target repo; a mismatch
between the service's configured embedder and the registry entry SHALL be a hard error naming
both models, never a silently degraded search.

#### Scenario: Embedder mismatch fails loudly

- **WHEN** a search targets a repo whose registry row records `embedder_model = A` while the
  service is configured with model `B`
- **THEN** the search SHALL fail with an error identifying both `A` and `B`
- **AND** no similarity results SHALL be returned

#### Scenario: Unindexed repo is distinguishable from empty results

- **WHEN** a search targets a repo slug absent from `code_search_registry`
- **THEN** the response SHALL be a structured "repo not indexed" error that names `index_repo`
  as the remediation, not an empty result list

### Requirement: Semantic Retrieval Query

Given a natural-language query, a repo slug, and a result limit, the system SHALL return the
top-k chunks ranked by cosine similarity, each with file path, language, content, line range, and
a similarity score in [0, 1]. Optional `languages` and `paths` filters SHALL be applied in the
same database query as the nearest-neighbor ranking (single-statement filtering, no client-side
merge).

#### Scenario: Filtered search executes as one statement

- **WHEN** a search specifies both a `languages` list and a `paths` glob filter
- **THEN** results SHALL satisfy both filters and be ranked by similarity
- **AND** the service SHALL issue exactly one SQL statement for ranking and filtering combined

#### Scenario: Conceptual query finds renamed implementations

- **WHEN** the eval fixture query "how are file locks released after a crash" runs against this
  repo's index
- **THEN** at least one returned chunk SHALL originate from the lock-management implementation
  even though the query shares no identifier tokens with it

### Requirement: Scope-Aware Result Filtering

When a search request carries a scope (a work-package id or explicit glob lists), the service
SHALL drop result chunks whose `file_path` falls outside the scope's `read_allow` globs or inside
its `deny` globs before returning, using the same glob semantics as the parallel-infrastructure
scope checker. Absence of a scope SHALL return unrestricted results.

#### Scenario: Out-of-scope chunks are dropped server-side

- **WHEN** a search passes a scope whose `read_allow` is `["agent-coordinator/**"]` and a chunk
  from `skills/worktree/scripts/worktree.py` would otherwise rank in the top-k
- **THEN** that chunk SHALL NOT appear in the response
- **AND** the response SHALL indicate that scope filtering was applied

### Requirement: Retrieval Quality Gate

Adoption SHALL be gated on a recorded spike evaluation: at least 10 realistic retrieval tasks
with hand-labeled expected files, run against stock cocoindex-code on this repository, reporting
hit@5 and token cost against a ripgrep baseline. The gate passes only if hit@5 ≥ 7/10 including
at least 2 tasks the ripgrep baseline misses; a failing gate SHALL stop the change with a written
finding before any Postgres backend work proceeds.

#### Scenario: Gate report exists before backend implementation

- **WHEN** any task from the vendored-backend work packages starts
- **THEN** `eval/spike-report.md` SHALL exist in the change directory with per-task hit results
  and an explicit pass verdict
