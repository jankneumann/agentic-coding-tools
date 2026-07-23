## ADDED Requirements

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
