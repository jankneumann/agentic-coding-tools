## ADDED Requirements

### Requirement: Coordinated Autopilot Phase Projection

A coordinated Autopilot host SHALL project every durably persisted phase generation to the work queue using the existing idempotent projection contract. The projected identity SHALL be derived only from `(LoopState.change_id, LoopState.current_phase, LoopState.total_iterations)`. The canonical `task_type=issue`, priority-1 row SHALL be excluded from unfiltered work claims and SHALL receive the adapter-owned labels `change:<change_id>` and `projection:autopilot-phase` so the current kanban query path can select it; stale projection rows SHALL lose both labels without modifying ordinary issues. Queue responses SHALL NOT mutate authoritative loop state.

#### Scenario: Live phase transition is mirrored

- **GIVEN** Autopilot is running in the coordinated tier with a projection adapter
- **WHEN** it durably advances to a new phase generation
- **THEN** the matching keyed queue row SHALL be submitted after the loop-state write
- **AND** only a bridge `status=error`, HTTP-409 problem response whose `response.detail` is `reconciliation_required` SHALL advance through reconciliation rather than degrade
- **AND** every direct transition to ESCALATE SHALL increment `total_iterations` exactly once before persistence and projection
- **AND** the canonical `task_type=issue` row SHALL be idempotently labelled `change:<change_id>` and `projection:autopilot-phase`
- **AND** the existing kanban `/issues/list` query and an already connected SSE client SHALL expose that phase within 5 seconds without a reload
- **AND** the row SHALL be derivable from the persisted loop-state tuple

#### Scenario: Host-driven execution uses the same projection

- **GIVEN** the Autopilot skill drives phases through its CLI protocol
- **WHEN** a canonical CLI state mutation is persisted in coordinated mode
- **THEN** `runner.py init` and `runner.py transition` SHALL durably own initialization and ordinary phase advances
- **AND** the host SHALL invoke `runner.py project-state --mode submit` after every successfully persisted runner state mutation
- **AND** resume SHALL invoke `runner.py project-state --mode reconcile` before gate handling or phase work
- **AND** the shared projection adapter SHALL project the resulting durable tuple
- **AND** a supervise-dispatched run SHALL require no supervise-specific phase publisher

#### Scenario: Crash after persistence repairs on resume

- **GIVEN** loop-state advanced but the process ended before queue submission
- **AND** an older queue generation remains active
- **WHEN** coordinated Autopilot resumes
- **THEN** it SHALL reconcile from the loaded loop-state before phase work
- **AND** stale active rows SHALL be cancelled
- **AND** exactly one active canonical row carrying both adapter-owned labels SHALL represent the loaded generation
- **AND** interrupted stale-label cleanup across at most the 100-row coordinator page limit SHALL be retried without modifying ordinary change-labelled issues

#### Scenario: Projection outage is degraded, not authoritative

- **GIVEN** loop-state persistence succeeds
- **AND** the coordinator projection call fails or returns a non-success envelope
- **WHEN** the host reports the transition
- **THEN** the durable loop-state SHALL remain unchanged
- **AND** a failed canonical-row label update or stale-label cleanup SHALL also report projection degradation with a bounded reason
- **AND** label operations SHALL target the configured coordinator even when GitHub issues are enabled
- **AND** it SHALL NOT derive state from a queue response

#### Scenario: Coordinator-free tiers stay isolated

- **GIVEN** execution selected local-parallel or sequential tier
- **WHEN** Autopilot starts, transitions, or resumes
- **THEN** no projection adapter SHALL be registered or constructed
- **AND** the projection module SHALL NOT be imported
- **AND** no projection submit, reconcile, or coordinator-only projection-label helper SHALL be called
- **AND** pre-existing coordinator detection and archetype-resolution imports are outside this projection-isolation guarantee
