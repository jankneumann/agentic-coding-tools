# project-context-refresh-records Specification

## Purpose
TBD - created by archiving change add-durable-context-refresh-records. Update Purpose after archive.
## Requirements
### Requirement: Deterministic Refresh Operation Identity

The project-context runtime SHALL derive one stable refresh operation identity
from a canonical repository identifier and an exact full Git source revision.
The runtime SHALL retain the complete identity tuple in the persisted record
and SHALL verify it whenever the record is loaded.

#### Scenario: New repository revision creates one operation

- **WHEN** a caller requests a refresh record for repository `R` at source revision `S`
- **AND** no matching record exists
- **THEN** the runtime SHALL create a pending operation with a deterministic operation ID
- **AND** the persisted record SHALL contain `R` and `S` exactly

#### Scenario: Duplicate request reuses the operation

- **WHEN** one or more callers request a refresh record for the same repository `R` and source revision `S`
- **THEN** every caller SHALL receive the same operation ID
- **AND** at most one operation record SHALL be created

#### Scenario: Identity changes create distinct operations

- **WHEN** either the canonical repository identifier or exact source revision differs
- **THEN** the runtime SHALL derive a distinct operation ID
- **AND** neither operation SHALL read or mutate the other's record

### Requirement: Cross-Process Durable Operation Store

The default filesystem store SHALL persist operation records below the
repository's resolved Git common directory so linked worktrees and later
processes in the same clone share state. Every mutation MUST use a
per-operation cross-process lock, validate the current record, apply one legal
transition, and replace the record atomically.

The store SHALL support `pending -> running`,
`running -> {succeeded, degraded, failed}`, and
`{failed, degraded} -> running`. `succeeded` SHALL be terminal. A retry from a
retryable terminal state SHALL increment the attempt number; an idempotent
duplicate begin while already running SHALL not.

#### Scenario: Later process resumes the record

- **WHEN** process A creates or updates an operation and exits
- **AND** process B opens the same repository clone
- **THEN** process B SHALL load the last complete validated record
- **AND** no process-local singleton state SHALL be required

#### Scenario: Concurrent creation is serialized

- **WHEN** two processes concurrently create the same repository-and-revision operation
- **THEN** the per-operation lock SHALL serialize create-or-load
- **AND** both processes SHALL observe one operation ID and one valid record

#### Scenario: Interrupted write preserves complete state

- **WHEN** a process stops after writing a temporary record but before or during replacement
- **THEN** a reader SHALL observe either the previous complete record or the new complete record
- **AND** the reader SHALL never accept a partial JSON document

#### Scenario: Retry follows the state machine

- **WHEN** a failed or degraded operation begins another attempt
- **THEN** its state SHALL become running and its attempt number SHALL increment once
- **AND** an invalid transition from succeeded SHALL be rejected without modifying the record

### Requirement: Truthful Producer Results

Every configured producer result SHALL identify the producer and version and
use exactly one status: `fresh`, `degraded`, `failed`, or `not-configured`.
Every result SHALL contain validations, changed repository artifacts, and a
remediation array. Non-fresh results MUST contain at least one actionable
remediation entry. Degraded and not-configured results MUST identify the
fallback actually used.

Producer IDs SHALL be unique within one operation. Repository artifacts SHALL
use safe repository-relative paths and content digests rather than absolute
paths or embedded content.

#### Scenario: Fresh producer records validated artifacts

- **WHEN** a producer completes successfully for the requested source revision
- **THEN** its result SHALL use status `fresh`
- **AND** its changed artifacts and validation outcomes SHALL conform to the shared schema

#### Scenario: Degraded producer records fallback

- **WHEN** a producer completes through a degraded fallback
- **THEN** its result SHALL use status `degraded`
- **AND** it SHALL record the fallback reason and at least one remediation action

#### Scenario: Unavailable producer is explicit

- **WHEN** a producer is not configured or fails
- **THEN** its result SHALL use `not-configured` or `failed` respectively
- **AND** it SHALL NOT be omitted or represented as fresh
- **AND** it SHALL include actionable remediation

#### Scenario: Duplicate producer identity is rejected

- **WHEN** a record or manifest contains two results with the same producer ID
- **THEN** model validation SHALL reject the document
- **AND** no replacement record or manifest SHALL be written

### Requirement: Deterministic Refresh Manifest

The runtime SHALL project a validated operation into a machine-readable
manifest suitable for staging in a managed worktree. The manifest SHALL record
the source revision, stable operation identity, producer versions and results,
changed repository artifacts, validation results, semantic-index status, and
degraded fallbacks.

The manifest MUST exclude mutable attempt metadata, update timestamps, lock
state, absolute paths, and raw exception output. Serialization SHALL use a
canonical ordering and one trailing newline so the same logical projection
produces identical bytes.

#### Scenario: Same projection produces identical bytes

- **WHEN** the runtime renders the same validated operation projection twice
- **THEN** both manifest byte sequences SHALL be identical
- **AND** ordered collections SHALL use their documented stable sort keys

#### Scenario: Manifest reports changed artifacts and validations

- **WHEN** one or more deterministic producers changed repository artifacts
- **THEN** the manifest SHALL list each changed path, change kind, and content digest where applicable
- **AND** it SHALL include the validation outcome that supports the producer's freshness claim

#### Scenario: Semantic index remains external state

- **WHEN** semantic indexing is pending, unavailable, stale, failed, or successful
- **THEN** the manifest SHALL record only its durable operation and registry references, status, requested revision, indexed revision, and fallback
- **AND** the manifest SHALL NOT list the semantic index as a repository artifact
- **AND** any semantic status other than succeeded SHALL require an explicit fallback

#### Scenario: Same-revision rerun is a no-op

- **WHEN** a caller recreates a record and manifest for the same repository and source revision without logical result changes
- **THEN** the runtime SHALL reuse the existing operation identity
- **AND** replacing the manifest SHALL report no byte change

### Requirement: Versioned Fail-Closed Record Contracts

Operation records and manifests SHALL conform to Draft 2020-12 JSON Schemas
with `schema_version: 1` and closed top-level objects. Readers MUST validate a
complete document before model construction and MUST refuse unknown versions
or malformed freshness-bearing fields.

Schema resolution SHALL use local installed assets and SHALL NOT require a
network fetch. Persisted diagnostics MUST be bounded and sanitized, and all
persisted artifact or manifest paths MUST be repository-relative POSIX paths
without traversal segments.

#### Scenario: Unknown schema version is refused

- **WHEN** a reader receives an otherwise well-formed operation or manifest with an unsupported schema version
- **THEN** it SHALL return a typed compatibility error
- **AND** it SHALL NOT rewrite, downgrade, or infer freshness from the document

#### Scenario: Unsafe persisted path is refused

- **WHEN** an artifact or manifest path is absolute, contains `..`, contains a backslash, or contains a NUL character
- **THEN** schema or model validation SHALL reject it before any target write
- **AND** the rejected value SHALL NOT be normalized into a different path

#### Scenario: Malformed durable record fails closed

- **WHEN** an operation record is truncated, schema-invalid, contains a mismatched identity tuple, or contains an impossible state transition result
- **THEN** the runtime SHALL surface a typed corruption or validation error
- **AND** it SHALL NOT create a replacement record that could make the operation appear fresh

