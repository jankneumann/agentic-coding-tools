# code-search Specification

## Purpose
TBD - created by archiving change add-semantic-code-search. Update Purpose after archive.
## Requirements
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

The service SHALL drop result chunks whose `file_path` falls outside the scope's `read_allow`
globs or inside its `deny` globs before returning, when a search request carries a scope (a
work-package id or explicit glob lists), using the same glob semantics as the
parallel-infrastructure scope checker. Absence of a scope SHALL return unrestricted results.

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

### Requirement: Revision-Aware Semantic Index Identity

The system SHALL assign one durable semantic-index identity to each unique
combination of repository, namespace kind, namespace key, exact Git source
revision, embedder model, and embedding dimension. The source revision MUST be
a lowercase full Git object ID and MUST NOT be a symbolic or abbreviated ref.

#### Scenario: Stable identity is reused

- **WHEN** two requests ensure an index for the same repository, namespace,
  exact revision, embedder model, and embedding dimension
- **THEN** both requests SHALL return the same durable index identity
- **AND** the registry SHALL contain exactly one authoritative row for that
  natural key

#### Scenario: Symbolic revision is rejected

- **WHEN** a caller requests an index using `main`, `HEAD`, a branch name, or an
  abbreviated object ID as `source_revision`
- **THEN** the registry SHALL reject the request before creating a row
- **AND** the error SHALL direct the caller to resolve the ref to a full object
  ID

### Requirement: Isolated Semantic Index Namespaces

The system SHALL represent `main`, `feature`, and `work_package` as distinct
namespace kinds. Every index identity MUST have a unique SQL-safe storage key
that does not depend on interpolating a human-readable ref or work-package name.

#### Scenario: Storage identity is isolated

- **WHEN** main, feature, and work-package indexes are registered for the same
  repository and source revision
- **THEN** every index SHALL have a distinct durable identity and storage key
- **AND** none of the non-main storage keys SHALL equal or overwrite the main
  storage key

### Requirement: Concurrent Semantic Index Lifecycle

The registry SHALL record lifecycle status, attempt count, lease ownership,
lease expiry, completion metadata, and last error. Duplicate creation MUST be
idempotent, and a terminal update MUST be accepted only from the current
unexpired lease holder.

#### Scenario: Concurrent creation returns one record

- **WHEN** concurrent workers create the same natural index key
- **THEN** all workers SHALL observe one durable index identity
- **AND** the database SHALL persist one row for that key

#### Scenario: Active lease owns completion

- **WHEN** a worker holds the current lease for an `indexing` record and reports
  successful completion
- **THEN** the registry SHALL transition that record to `ready`
- **AND** a worker with an older or different lease token SHALL NOT overwrite
  the ready result

#### Scenario: Expired lease permits takeover

- **WHEN** an index remains `indexing` after its lease expires
- **THEN** another worker SHALL be able to claim a new lease
- **AND** the registry SHALL increment the attempt count while preserving the
  same index identity

#### Scenario: Ready completion records provenance

- **WHEN** the current lease holder completes an index successfully
- **THEN** the ready record SHALL include the exact source revision, embedder
  model, embedding dimension, non-negative chunk count, and completion time
- **AND** `last_error` SHALL be empty

### Requirement: Guarded Canonical Semantic Index

The system SHALL maintain at most one canonical semantic-index pointer per
repository. The canonical
candidate MUST belong to the same repository, MUST use the `main` namespace,
and MUST be `ready`. Promotion SHALL support compare-and-swap against the
currently observed canonical identity.

#### Scenario: Canonical promotion accepts a ready main index

- **WHEN** a ready main index for repository `R` is promoted with the expected
  current canonical identity
- **THEN** repository `R` SHALL point to that index atomically

#### Scenario: Non-main index cannot become canonical

- **WHEN** a caller attempts to promote a feature or work-package index
- **THEN** the registry and database constraint SHALL reject the promotion
- **AND** the existing canonical pointer SHALL remain unchanged

#### Scenario: Stale promotion is rejected

- **WHEN** the current canonical pointer changed after a caller read it
- **AND** that caller promotes with the stale expected identity
- **THEN** the compare-and-swap SHALL fail without changing the pointer

### Requirement: Safe Semantic Index Garbage Collection

The system SHALL expose an explicit garbage-collection operation for expired
feature and work-package indexes. It MUST NOT select a `main` index, a canonical
index, or an index with an active lease. Registry deletion SHALL be recorded
only after its isolated storage is removed successfully.

#### Scenario: Expired feature index is collected

- **WHEN** a terminal feature index is past its retention deadline and is not
  canonical or actively leased
- **THEN** garbage collection SHALL claim it, remove its isolated storage, and
  mark the registry record `deleted`

#### Scenario: Main indexes are never collected

- **WHEN** garbage collection scans expired records
- **THEN** no `main` namespace record SHALL be selected
- **AND** no record referenced by a canonical pointer SHALL be selected

#### Scenario: Failed storage deletion remains retryable

- **WHEN** removal of a claimed index's storage fails
- **THEN** the record SHALL NOT be marked `deleted`
- **AND** the failure SHALL be recorded durably so a later garbage-collection
  attempt can retry it

### Requirement: Compatibility During Registry Rollout

The existing repo-slug registry fields and query path SHALL remain available
until dependent changes migrate indexing and querying to revision-aware
identities. Legacy freshness fields MUST be documented as non-authoritative
once `code_search_indexes` exists.

#### Scenario: Legacy reader remains compatible

- **WHEN** the revision-aware registry migration is applied before downstream
  indexing and query changes
- **THEN** existing disabled-by-default code-search imports and registry lookups
  SHALL continue to function
- **AND** no existing repo-slug chunk table SHALL be renamed or deleted

### Requirement: Exact Source Proof for Semantic Indexing

The indexer SHALL accept only a clean, materialized Git worktree whose HEAD is
the requested full source object ID. It SHALL verify repository containment and
the source proof before registry creation and again before readiness.

#### Scenario: Exact source is proven

- **WHEN** a clean worktree HEAD equals the requested full Git object ID
- **THEN** indexing SHALL label all registry, manifest, and result records with
  that exact object ID

#### Scenario: Dirty source is rejected

- **WHEN** the worktree is dirty, HEAD differs, the revision is symbolic or
  abbreviated, or an eligible path escapes the repository
- **THEN** the request SHALL fail before a falsely labeled index becomes ready

#### Scenario: Source mutation prevents readiness

- **WHEN** the materialized source changes after indexing begins
- **THEN** the worker SHALL NOT mark the index ready
- **AND** the failure SHALL identify source-proof loss without exposing file
  contents

### Requirement: Fingerprinted Indexing Contract

Semantic index identity SHALL include deterministic policy, pipeline, and
embedder fingerprints in addition to repository, namespace, exact revision,
model, and dimension. Credentials MUST NOT be included in fingerprints.

#### Scenario: Policy change creates a distinct index

- **WHEN** two requests differ in read scope, deny rules, secret policy,
  chunking behavior, dependency compatibility, provider parameters, or another
  computation-affecting input
- **THEN** they SHALL NOT reuse the same ready semantic index

#### Scenario: Duplicate ready request is a no-op

- **WHEN** an identical request targets an already ready index
- **THEN** it SHALL return the same durable operation identity
- **AND** it SHALL perform no source read, embedding call, or storage mutation

### Requirement: Incremental Immutable Revision Storage

Every revision SHALL be built in its own storage-key table. A new revision MAY
reuse rows only from a ready compatible Git ancestor. The resulting table MUST
contain the complete eligible view of the new revision before readiness.

#### Scenario: Compatible parent is selected

- **WHEN** a ready ancestor has the same repository, namespace, embedding
  contract, policy fingerprint, and pipeline fingerprint
- **THEN** the operation SHALL record that ancestor as its incremental parent

#### Scenario: One-file revision embeds only changed content

- **WHEN** revision B changes one eligible file relative to compatible ready
  revision A
- **THEN** B's isolated target SHALL contain all eligible files from B
- **AND** unchanged rows SHALL be copied or reused without invoking the
  embedder
- **AND** only added or changed eligible content SHALL be embedded

#### Scenario: Deleted file is absent

- **WHEN** an eligible file from revision A is deleted or becomes ineligible in
  revision B
- **THEN** no chunk for that path SHALL exist in B's isolated target

#### Scenario: Retry reconciles isolated storage

- **WHEN** a worker crashes after writing part of an unready target
- **THEN** a later current lease holder SHALL build a fresh attempt staging
  table and manifest for the same durable index identity
- **AND** the target SHALL remain unavailable to ready-only readers until
  verification succeeds

#### Scenario: Stale attempt cannot mutate published storage

- **WHEN** worker A loses its lease, worker B takes over and publishes a
  verified attempt, and worker A later attempts another write or publish
- **THEN** worker A's write SHALL remain confined to its abandoned staging
  storage
- **AND** its publish SHALL be rejected by the current lease/fencing check
- **AND** the ready table and published manifest SHALL remain unchanged

### Requirement: Fail-Closed Index-Time Eligibility

The indexer SHALL intersect configured includes, excludes, nested gitignore
rules, and `read_allow`, then subtract explicit deny, non-overridable
secret/credential patterns, generated/dependency trees, and escaping paths.
Deny rules SHALL take precedence over allow/include rules.

#### Scenario: Deny wins before read

- **WHEN** a path is both included or allowed and matched by a deny or hard
  security rule
- **THEN** the indexer SHALL exclude it before reading its content
- **AND** the path content SHALL never reach the embedder or target

#### Scenario: Ignored and out-of-scope files are excluded

- **WHEN** a path is gitignored, generated, outside `read_allow`, or inside a
  dependency tree
- **THEN** its eligibility decision and non-sensitive reason SHALL be recorded
- **AND** it SHALL produce no chunks

#### Scenario: Escaping symlink is rejected

- **WHEN** a candidate symlink resolves outside the proven repository root
- **THEN** it SHALL be rejected before target content is read

#### Scenario: Secret scanner fails closed

- **WHEN** the bounded local scanner reports a secret, times out, or errors
- **THEN** the index operation SHALL fail before any affected content reaches
  a remote embedder
- **AND** persisted evidence SHALL contain only a sanitized reason

### Requirement: Lease-Guarded Index Execution

A long-running index operation SHALL periodically renew its current lease.
Only the current lease token may renew, complete, or record a terminal state.

#### Scenario: Current worker renews its lease

- **WHEN** a current worker remains active near lease expiry
- **THEN** it SHALL atomically extend that lease without changing index
  identity or attempt count

#### Scenario: Stale worker cannot renew or complete

- **WHEN** another worker takes over an expired lease
- **THEN** the former token SHALL fail renewal and terminal updates
- **AND** the stale worker SHALL stop local processing

#### Scenario: Concurrent request observes the durable operation

- **WHEN** a duplicate request arrives while a current lease is active
- **THEN** it SHALL return the shared operation identity and an in-progress
  conflict/result
- **AND** it SHALL NOT start a second embedding run

### Requirement: Explicit Optional Infrastructure Outcomes

The operation SHALL distinguish unavailable optional configuration from runtime
failure and SHALL state whether a result was persisted durably.

#### Scenario: Missing database is explicit

- **WHEN** no Postgres DSN is configured
- **THEN** the CLI SHALL return an ephemeral `not_configured` result with no
  operation identity
- **AND** it SHALL NOT claim that a durable database record exists

#### Scenario: Missing embedder is durable

- **WHEN** Postgres is reachable and an intended model/dimension contract is
  declared but its package, credential, or endpoint is unavailable
- **THEN** the current lease holder SHALL durably mark the operation
  `not_configured`
- **AND** no model download or remote request SHALL be attempted

#### Scenario: Missing embedding contract is ephemeral

- **WHEN** model or dimension is wholly absent at CLI preflight
- **THEN** the CLI SHALL return an ephemeral `not_configured` result with no
  operation identity
- **AND** it SHALL NOT create an `IndexRequest` or claim durable storage

#### Scenario: Runtime failure is durable

- **WHEN** a provider, pipeline, or storage verification fails after claim
- **THEN** the current lease holder SHALL durably mark the operation `failed`
  when the registry remains reachable
- **AND** the result SHALL contain a sanitized actionable error code

### Requirement: Explicit Embedding Provider Compatibility

Indexing SHALL support explicit local and OpenAI-compatible provider
configuration. A coordinator-managed gateway SHALL be consumed through the
OpenAI-compatible boundary and SHALL remain opt-in.

#### Scenario: Gateway is opt-in

- **WHEN** a base URL, scoped key, model, and dimension are explicitly supplied
  for the gateway
- **THEN** the indexer SHALL use that endpoint and fingerprint the served
  embedding contract
- **AND** it SHALL NOT import coordinator control-plane code

#### Scenario: Missing configuration makes no network attempt

- **WHEN** neither a local nor remote provider is explicitly usable
- **THEN** provider construction SHALL return `not_configured` without a
  download, readiness request, or embedding call

### Requirement: Verified Readiness and Canonical Promotion

An index SHALL become ready only after source re-verification and isolated
storage schema, vector-index, manifest-coverage, and row-count checks.
Canonical promotion SHALL occur only for a ready main index through guarded
compare-and-swap.

#### Scenario: Complete index is verified before readiness

- **WHEN** the pipeline reports success
- **THEN** the operation SHALL independently verify the isolated target and
  complete manifest before marking ready

#### Scenario: Main promotes only after readiness

- **WHEN** a verified main index becomes ready and the expected canonical
  pointer still matches
- **THEN** it SHALL be promoted atomically

#### Scenario: Feature index is not promoted

- **WHEN** a feature or work-package index becomes ready
- **THEN** it SHALL remain noncanonical

#### Scenario: Full rebuild is isolated

- **WHEN** a caller explicitly requests a full rebuild
- **THEN** compatible-parent reuse SHALL be disabled for that unready attempt
- **AND** only the leased operation's isolated target and manifest MAY be
  cleared or reconciled
- **AND** canonical, parent, and sibling storage SHALL remain unchanged

#### Scenario: Ready identity remains immutable

- **WHEN** a full-rebuild request resolves to an already ready identity
- **THEN** the operation SHALL return that ready identity without mutation
- **AND** replacing its output SHALL require a changed pipeline fingerprint

