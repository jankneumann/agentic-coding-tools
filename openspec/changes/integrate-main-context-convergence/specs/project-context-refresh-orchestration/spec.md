# project-context-refresh-orchestration Specification Delta

## MODIFIED Requirements

### Requirement: Sync-point-only main writes

No refresh path SHALL write canonical main outputs except from a managed worktree or from an explicitly authorized sync-point operation that has enforced its clean-tree, active-agent, and exclusive-lock guards.

The refresh command SHALL keep the OpenSpec projection read-only, SHALL write the
durable manifest to a location that never mutates the tracked working tree, and
SHALL refuse an unauthorized shared or bare checkout exactly as before. Sync-point
authorization SHALL be an explicit caller opt-in, never inferred from the
environment, and canonical specification merges SHALL remain the responsibility of
the cleanup operation.

<!-- Scenario ID: project-context-refresh-orchestration.no-main-write -->
#### Scenario: Refresh never writes main directly

- **WHEN** the refresh command runs without sync-point authorization
- **THEN** it SHALL refuse to run against a shared or bare checkout
- **AND** it SHALL write only producer-managed outputs plus a durable manifest kept
  outside the tracked working tree
- **AND** canonical specification merges SHALL remain the responsibility of the
  sync-point cleanup operation

<!-- Scenario ID: project-context-refresh-orchestration.authorized-sync-point -->
#### Scenario: An authorized sync point may refresh main in place

- **WHEN** the refresh command is invoked with explicit sync-point authorization from
  the main-synchronization skill
- **THEN** it SHALL be permitted to write producer-managed outputs in the shared
  checkout on the main branch
- **AND** the caller SHALL have verified a clean working tree, no active agent
  worktrees, and exclusive sync-point access before the write
- **AND** the OpenSpec projection SHALL remain read-only in that mode

<!-- Scenario ID: project-context-refresh-orchestration.deferred-semantic-index -->
#### Scenario: Semantic indexing can be deferred to a later revision

- **WHEN** the refresh command is invoked with the semantic index deferred
- **THEN** it SHALL run every deterministic and architecture producer as usual
- **AND** it SHALL record the semantic index as a pending reference carrying a bounded
  exact-search fallback rather than attempting the index inline
- **AND** the recorded deterministic results SHALL be identical to those of a run that
  attempted the index
