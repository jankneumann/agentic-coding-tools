## ADDED Requirements

### Requirement: Work Projection Helper Envelope

The coordination bridge SHALL expose submit and reconcile helpers for loop-state-derived queue projections. Helpers SHALL accept one explicit bounded `projection_key`, reject reserved identity fields in `input_data`, preserve the uniform no-raise transport envelope, include the canonical task ID plus creation/deduplication outcome, and SHALL accept authoritative phase fields only from their caller. A reconciliation response MUST NOT be used to update loop-state.

#### Scenario: Bridge reports a deduplicated replay

- **GIVEN** a projection tuple already exists
- **WHEN** `try_submit_work` submits the same complete tuple
- **THEN** the helper SHALL return the canonical task ID
- **AND** it SHALL report `created=false` and `deduplicated=true`

#### Scenario: Reconcile transport failure preserves caller truth

- **GIVEN** loop-state has already been persisted
- **AND** the coordinator transport is unavailable
- **WHEN** the reconcile helper runs
- **THEN** it SHALL return a structured failed result without raising
- **AND** it SHALL NOT modify or replace the caller's loop-state
