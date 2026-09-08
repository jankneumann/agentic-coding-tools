## ADDED Requirements

### Requirement: Coordinated Autopilot Phase Projection

A coordinated Autopilot host SHALL project every durably persisted phase generation to the work queue using the existing idempotent projection contract. The projected identity SHALL be derived only from `(LoopState.change_id, LoopState.current_phase, LoopState.total_iterations)`. The canonical row SHALL receive the existing `change:<change_id>` issue label so the current kanban query path can select it. Queue responses SHALL NOT mutate authoritative loop state.

#### Scenario: Live phase transition is mirrored

- **GIVEN** Autopilot is running in the coordinated tier with a projection adapter
- **WHEN** it durably advances to a new phase generation
- **THEN** the matching keyed queue row SHALL be submitted after the loop-state write
- **AND** the canonical row SHALL be idempotently labelled `change:<change_id>`
- **AND** the existing kanban `/issues/list` query SHALL expose that phase within one configured poll interval
- **AND** the row SHALL be derivable from the persisted loop-state tuple

#### Scenario: Host-driven execution uses the same projection

- **GIVEN** the Autopilot skill drives phases through its CLI protocol
- **WHEN** a canonical CLI state mutation is persisted in coordinated mode
- **THEN** the host SHALL invoke `runner.py project-state --mode submit`
- **AND** resume SHALL invoke `runner.py project-state --mode reconcile` before gate handling or phase work
- **AND** the shared projection adapter SHALL project the resulting durable tuple
- **AND** a supervise-dispatched run SHALL require no supervise-specific phase publisher

#### Scenario: Crash after persistence repairs on resume

- **GIVEN** loop-state advanced but the process ended before queue submission
- **AND** an older queue generation remains active
- **WHEN** coordinated Autopilot resumes
- **THEN** it SHALL reconcile from the loaded loop-state before phase work
- **AND** stale active rows SHALL be cancelled
- **AND** exactly one canonical, change-labelled row SHALL represent the loaded generation

#### Scenario: Projection outage is degraded, not authoritative

- **GIVEN** loop-state persistence succeeds
- **AND** the coordinator projection call fails or returns a non-success envelope
- **WHEN** the host reports the transition
- **THEN** the durable loop-state SHALL remain unchanged
- **AND** a failed canonical-row label update SHALL also report projection degradation with a bounded reason
- **AND** it SHALL NOT derive state from a queue response

#### Scenario: Coordinator-free tiers stay isolated

- **GIVEN** execution selected local-parallel or sequential tier
- **WHEN** Autopilot starts, transitions, or resumes
- **THEN** no projection adapter SHALL be registered
- **AND** no coordination-bridge import, availability probe, or queue request SHALL occur
