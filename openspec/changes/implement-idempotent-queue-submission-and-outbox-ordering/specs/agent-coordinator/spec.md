## MODIFIED Requirements

### Requirement: Work Queue

The system SHALL provide task assignment, tracking, dependency management, and atomic projection submission through a work queue. A submission whose `input_data` contains the complete tuple `(change_id, phase, iteration)` SHALL use submit-if-absent semantics enforced by PostgreSQL uniqueness. A replay SHALL return the canonical task ID and SHALL NOT create a second row. Submissions without a complete projection key SHALL preserve existing independent-insert behavior.

#### Scenario: Concurrent projection replay creates one task

- **GIVEN** multiple clients submit the same complete `(change_id, phase, iteration)` tuple concurrently
- **WHEN** PostgreSQL resolves the submissions
- **THEN** exactly one work-queue row SHALL exist for that tuple
- **AND** every successful response SHALL return the same canonical task ID
- **AND** exactly one response SHALL report `created=true`

#### Scenario: Unkeyed tasks remain independent

- **GIVEN** two otherwise identical submissions without a complete projection key
- **WHEN** both are submitted
- **THEN** two distinct work-queue rows SHALL be created
- **AND** both responses SHALL report `created=true`

## ADDED Requirements

### Requirement: Loop-State Projection Reconciliation

The coordinator SHALL expose an atomic reconciliation operation derived from a caller-provided loop-state tuple. It SHALL cancel stale active projection rows for the same change, preserve terminal rows, and ensure the current tuple exists via the same submit-if-absent invariant. It MUST NOT return queue fields as authoritative state inputs.

#### Scenario: Resume converges stale projection rows

- **GIVEN** stale active rows for earlier phase or iteration values of one change
- **AND** loop-state identifies a different current tuple
- **WHEN** reconciliation is invoked from that loop-state
- **THEN** stale `pending`, `claimed`, and `running` rows SHALL be marked `cancelled`
- **AND** exactly one row SHALL exist for the current tuple
- **AND** completed or failed rows SHALL remain unchanged

#### Scenario: Reconciliation replay is idempotent

- **GIVEN** the queue already matches the current loop-state tuple
- **WHEN** reconciliation runs again
- **THEN** it SHALL return the same current task ID
- **AND** it SHALL create no row and cancel no additional row
