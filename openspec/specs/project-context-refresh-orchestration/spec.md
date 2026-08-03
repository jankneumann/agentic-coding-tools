# project-context-refresh-orchestration Specification

## Purpose
TBD - created by archiving change implement-project-context-refresh-orchestration. Update Purpose after archive.
## Requirements
### Requirement: Unified context refresh command

The system SHALL provide one refresh-project-context command that, for an explicit
repository and full source Git revision, runs every configured context producer and
emits a manifest that validates against the ri-06 refresh-manifest schema. The
command SHALL orchestrate only configured producers and SHALL NOT define its own
result, manifest, or operation model.

<!-- Scenario ID: project-context-refresh-orchestration.runs-all-configured -->
#### Scenario: One command runs all configured producers

- **WHEN** the refresh command runs for a repository at a full source Git revision
- **THEN** it SHALL invoke each configured deterministic producer, the architecture
  producer, and the semantic-index producer through their canonical owners
- **AND** it SHALL record every producer result on one canonical operation for that
  repository and revision
- **AND** it SHALL emit a manifest that validates against the ri-06
  `context-refresh-manifest` schema
- **AND** the manifest `refresh_status` SHALL equal the finalized operation outcome

<!-- Scenario ID: project-context-refresh-orchestration.capability-follow-up -->
#### Scenario: Unconfigured producers are not fabricated

- **WHEN** the proposal names a producer that has no canonical owner configured
- **THEN** the refresh command SHALL omit it rather than invent an implementation
- **AND** the omission SHALL be recorded as a documented follow-up, not a failure

### Requirement: Idempotent revision-addressed refresh

A second refresh for the same repository revision SHALL reuse the single canonical
operation and SHALL produce no repository diff. The command SHALL reuse or verify the
existing semantic-index operation rather than start a duplicate pipeline.

<!-- Scenario ID: project-context-refresh-orchestration.no-diff-on-rerun -->
#### Scenario: Repeat refresh produces no repository diff

- **WHEN** the refresh command runs twice for the same revision, inputs, and producer
  versions
- **THEN** the second run SHALL reuse the same canonical operation identity
- **AND** deterministic producer outputs SHALL remain byte-identical
- **AND** the working tree SHALL show no change attributable to the rerun
- **AND** the semantic-index reference SHALL be reused or re-verified, not duplicated

### Requirement: Semantic-index degradation isolation

Failure or unavailability of the semantic index SHALL NOT corrupt or discard any
successful deterministic producer output. Deterministic and architecture producer
results SHALL be recorded before the semantic index is attempted, and a non-succeeded
semantic index SHALL be represented as a degraded reference with a bounded fallback.

<!-- Scenario ID: project-context-refresh-orchestration.semantic-degradation -->
#### Scenario: Semantic failure preserves deterministic output

- **WHEN** the semantic index is unavailable or errors during a refresh
- **THEN** all previously recorded deterministic and architecture results SHALL
  remain intact on the operation
- **AND** the semantic index SHALL be recorded as a non-succeeded reference carrying a
  bounded fallback, not as a failed deterministic producer
- **AND** the operation SHALL finalize as degraded rather than failed
- **AND** the emitted manifest SHALL still contain the successful deterministic output

### Requirement: Preserved producer ownership

Each producer SHALL remain independently runnable, and every refresh result SHALL
be attributable to the canonical owner of its producer. Producer identity SHALL be
carried by the stable producer ID, which SHALL map to exactly one canonical owner
through the producer registry; the refresh output SHALL surface that owner so the
aggregate never collapses per-producer identity or ownership.

<!-- Scenario ID: project-context-refresh-orchestration.independent-producer -->
#### Scenario: A single producer runs independently

- **WHEN** the refresh command is invoked for one named producer
- **THEN** it SHALL run only that producer and report exactly one result
- **AND** the result SHALL carry that producer's stable ID
- **AND** the refresh output SHALL resolve that stable ID to its canonical owner
  via the producer registry

### Requirement: Sync-point-only main writes

No refresh path SHALL write canonical main outputs outside an authorized sync-point
operation. The refresh command SHALL operate within a managed worktree, SHALL keep
the OpenSpec projection read-only, and SHALL write the durable manifest to a location
that never mutates the tracked working tree.

<!-- Scenario ID: project-context-refresh-orchestration.no-main-write -->
#### Scenario: Refresh never writes main directly

- **WHEN** the refresh command runs
- **THEN** it SHALL refuse to run against a shared or bare checkout
- **AND** it SHALL write only producer-managed outputs plus a durable manifest kept
  outside the tracked working tree
- **AND** canonical specification merges SHALL remain the responsibility of the
  sync-point cleanup operation

