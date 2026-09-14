## ADDED Requirements

### Requirement: Coordinated Autopilot Phase Projection

A coordinated Autopilot host SHALL project every durably persisted phase generation to the work queue using the existing idempotent projection contract. The projected identity SHALL be derived only from `(LoopState.change_id, LoopState.current_phase, LoopState.total_iterations)`. Every `task_type=issue` row SHALL be excluded from all work claims. The canonical priority-1 projection row SHALL receive the adapter-owned labels `change:<change_id>` and `projection:autopilot-phase` so the current kanban query path can select it; stale projection rows SHALL lose both labels without modifying ordinary issues. Queue responses SHALL NOT mutate authoritative loop state.

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
- **AND** interrupted cleanup across at most 100 concurrently double-labelled projection rows SHALL be retried without modifying ordinary change-labelled issues

#### Scenario: Projection publication is elevated and change-scoped

- **GIVEN** a trust-level-2 principal may submit ordinary work
- **WHEN** it submits a request carrying `projection_key` or calls projection reconciliation
- **THEN** authorization SHALL evaluate the distinct `publish_work_projection` operation against the exact requested change ID
- **AND** the request SHALL fail with HTTP 403 before any projection service or database mutation
- **AND** trust-resolution failure during submit or reconcile SHALL fail closed before the mutating RPC
- **AND** a trust-level-3 coordinator publisher SHALL retain the operation through native policy and synchronized capability profiles

#### Scenario: Pre-registry rows block every labelled generation repair

- **GIVEN** a pre-migration active row carries the reserved projection label and identifies a change by payload or exact change label but lacks registry ownership
- **WHEN** a labelled submit or reconcile requests either the same generation or a newer generation for that change
- **THEN** it SHALL return `projection_key_collision` before head advancement, insertion, cancellation, reactivation, or relabelling
- **AND** the legacy row, requested row, and projection head SHALL remain unchanged
- **AND** repair SHALL succeed only after an administrator verifies provenance and explicitly registers the legacy row UUID

#### Scenario: Reserved projection identity and owned rows reject ordinary issue mutation

- **GIVEN** migration 039 is active
- **WHEN** an ordinary issue create, update, or label-PATCH supplies `projection:autopilot-phase`
- **OR** an ordinary issue update, label-PATCH, or close targets a registry-owned projection row
- **THEN** the issue API SHALL return HTTP 403 before changing the target row
- **AND** a database insert or label update SHALL reject the reserved marker unless the row UUID is already registry-owned
- **AND** a projection RPC SHALL insert without labels, register ownership, and apply the canonical label pair within one transaction
- **AND** ordinary mutation of an unowned pre-registry reserved-labelled row SHALL return a structured `reserved_projection_label` refusal without reaching the label trigger
- **AND** no forged board or SSE projection and no future reconciliation wedge SHALL be created
- **AND** a close request containing multiple issue IDs SHALL lock and validate the complete issue batch before mutation, so any protected projection member leaves every ordinary member unchanged

#### Scenario: Labelled and legacy unlabelled projection modes cannot collide

- **GIVEN** a change has any registry-owned labelled projection row
- **WHEN** a keyed submit or reconcile omits `projection_labels`
- **THEN** it SHALL return `projection_mode_mismatch` before head or row mutation
- **AND** the canonical owned row SHALL retain its status and exact label pair
- **AND** a labelled submit or reconcile SHALL return `projection_key_collision` before mutation when the change already contains any complete unowned projection tuple
- **AND** direct MCP and HTTP-proxy projection calls SHALL accept and forward the exact label pair
- **AND** an associated unowned reserved-labelled upgrade row SHALL return `projection_key_collision` in either mode
- **AND** legacy unlabelled tuple cancellation SHALL remain available for changes with neither owned nor reserved-labelled projection state

#### Scenario: Projection outage is degraded, not authoritative

- **GIVEN** loop-state persistence succeeds
- **AND** the coordinator projection call fails or returns a non-success envelope
- **WHEN** the host reports the transition
- **THEN** the durable loop-state SHALL remain unchanged
- **AND** a failed canonical-row label update or stale-label cleanup SHALL also report projection degradation with a bounded reason
- **AND** label-removal events SHALL derive change identity from OLD labels when NEW labels are empty
- **AND** label operations SHALL target the configured coordinator even when GitHub issues are enabled
- **AND** it SHALL NOT derive state from a queue response

#### Scenario: Coordinator-free tiers stay isolated

- **GIVEN** execution selected local-parallel or sequential tier
- **WHEN** Autopilot starts, transitions, or resumes
- **THEN** no projection adapter SHALL be registered or constructed
- **AND** the projection module SHALL NOT be imported
- **AND** no projection submit, reconcile, or coordinator-only projection-label helper SHALL be called
- **AND** pre-existing coordinator detection and archetype-resolution imports are outside this projection-isolation guarantee
