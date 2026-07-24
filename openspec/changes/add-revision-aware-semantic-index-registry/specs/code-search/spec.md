## ADDED Requirements

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
