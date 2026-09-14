## MODIFIED Requirements

### Requirement: Work Queue

The system SHALL provide task assignment, tracking, dependency management, and atomic projection submission through a work queue. An ordinary submission without `projection_key` SHALL create a new row. A submission with the complete `(change_id, phase, transition_sequence)` key SHALL use submit-if-absent semantics enforced by PostgreSQL uniqueness and per-change transaction serialization. `transition_sequence` SHALL be the strict bounded integer copied from `LoopState.total_iterations`; phase-local `iteration` SHALL NOT identify a projection. A replay SHALL return the canonical row and SHALL NOT create a second row.

- Tasks SHALL support priority levels
- Task claiming SHALL be atomic (no double-claiming)
- Tasks SHALL support dependencies on other tasks
- Blocked tasks (with unmet dependencies) SHALL NOT be claimable

#### Scenario: Agent claims task from queue
- **WHEN** agent calls `get_work(task_types?)`
- **THEN** system atomically claims the highest-priority pending task
- **AND** returns `{success: true, task_id, task_type, task_description, input_data}`

#### Scenario: No tasks available
- **WHEN** agent calls `get_work()` with no pending tasks matching criteria
- **THEN** system returns `{success: false, reason: "no_tasks_available"}`

#### Scenario: Agent completes task
- **WHEN** agent calls `complete_work(task_id, success, result?, error_message?)`
- **THEN** system returns `{success: true, status: "completed"}`
- **AND** dependent tasks become unblocked if applicable

#### Scenario: Agent submits new task
- **WHEN** agent calls `submit_work(task_type, task_description, input_data?, priority?, depends_on?)`
- **THEN** system returns `{success: true, task_id: uuid}`

#### Scenario: Task with unmet dependencies
- **WHEN** agent attempts to claim a task with pending dependencies
- **THEN** the task SHALL NOT be returned by `get_work()`

#### Scenario: Agent submits ordinary new task

- **WHEN** an agent calls `submit_work` without `projection_key`
- **THEN** the system SHALL create a new work-queue row
- **AND** return `{success: true, task_id, created: true, deduplicated: false}`

#### Scenario: Concurrent projection replay creates one task

- **GIVEN** multiple clients submit the same complete projection key concurrently
- **WHEN** PostgreSQL resolves the submissions
- **THEN** exactly one row SHALL exist for that key
- **AND** every success SHALL return the same canonical task ID
- **AND** exactly one success SHALL report `created=true`

#### Scenario: Different tuple race serializes by change

- **GIVEN** keyed submit and reconciliation concurrently target different sequences of one change
- **WHEN** both database transactions execute
- **THEN** both SHALL acquire the same change-scoped transaction lock
- **AND** the reconciled current sequence SHALL be the only active projection row
- **AND** a delayed submit below the committed high-water sequence SHALL fail as `stale_projection`

#### Scenario: Only reconciliation advances projection sequence

- **GIVEN** a projection head already exists for a change
- **WHEN** keyed submit requests a sequence above that head
- **THEN** it SHALL fail as `reconciliation_required`
- **AND** reconciliation SHALL be the only operation that may advance the high-water sequence

#### Scenario: Equal-sequence different-phase submit is rejected

- **GIVEN** a projection head exists for one `(phase, transition_sequence)` generation
- **WHEN** keyed submit requests a different phase at the same sequence
- **THEN** it SHALL fail as `projection_generation_mismatch`
- **AND** it SHALL NOT create a second active generation

#### Scenario: Reserved or malformed identity is rejected

- **WHEN** submit or reconcile receives a partial key, boolean or out-of-range sequence, unknown phase, invalid change ID, or reserved identity field inside `input_data`
- **THEN** the boundary SHALL return 422 without a queue mutation

## ADDED Requirements

### Requirement: Loop-State Projection Reconciliation

The coordinator SHALL atomically reconcile from one caller-provided `projection_key`, cancel stale active rows for the change, preserve terminal rows, and ensure the current generation is represented. It MUST NOT return queue fields as authoritative state inputs.

#### Scenario: Resume converges stale projection rows

- **GIVEN** stale `pending`, `claimed`, or `running` rows for earlier sequences
- **WHEN** reconciliation runs for the authoritative current key
- **THEN** stale active rows SHALL become `cancelled`
- **AND** exactly one canonical row SHALL represent the current key
- **AND** unrelated and terminal rows SHALL remain unchanged

#### Scenario: Terminal current generation is already satisfied

- **GIVEN** the current key already identifies a `completed`, `failed`, or `cancelled` row
- **WHEN** reconciliation replays
- **THEN** it SHALL return that canonical row with `created=false`
- **AND** it SHALL NOT create a replacement generation

#### Scenario: Phase revisit uses a new generation

- **GIVEN** `LoopState.iteration` differs from `total_iterations` or a phase is revisited
- **WHEN** the projection key is derived
- **THEN** `transition_sequence` SHALL equal `total_iterations`
- **AND** the revisit SHALL not collide with the earlier phase generation

### Requirement: Projection Transport Parity

Direct MCP, HTTP-proxy MCP, HTTP, and `coordination-cli` SHALL map keyed submit and reconcile to the same service contract. HTTP successes SHALL match `ProjectionMutationSuccess`; authentication, policy, and validation failures SHALL be 4xx RFC 7807 Problems. MCP and CLI failures SHALL use a discriminated `{success:false, reason}` envelope without success-only fields.

#### Scenario: Direct and proxy MCP mappings agree

- **WHEN** direct MCP and HTTP-proxy MCP submit or reconcile the same valid key
- **THEN** both SHALL expose canonical task ID, status, created, deduplicated, and cancelled IDs with structurally equal values

#### Scenario: CLI exposes projection operations

- **WHEN** an operator invokes `coordination-cli work submit` with all projection-key flags or `coordination-cli work reconcile`
- **THEN** the CLI SHALL validate and delegate the explicit key without embedding a second identity source

#### Scenario: Policy denial is not a success payload

- **WHEN** HTTP authentication or policy denies a projection mutation
- **THEN** the response SHALL be a 401 or 403 Problem
- **AND** it SHALL NOT contain a null `task_id` in a success schema

#### Scenario: Reconciliation uses queue-submission authorization

- **WHEN** any transport requests projection reconciliation
- **THEN** authorization SHALL evaluate the existing `submit_work` policy operation
- **AND** policy context SHALL identify `mode=reconcile`

### Requirement: Projection Migration Preflight

Migration 035 SHALL prevent unsafe index creation by checking legacy reserved keys while blocking concurrent keyed writes. Failure SHALL roll back and provide deterministic remediation evidence.

#### Scenario: Malformed legacy row aborts safely

- **GIVEN** seeded partial, fractional, boolean, string, huge, or duplicate legacy projection identities
- **WHEN** migration 035 runs
- **THEN** it SHALL abort with documented SQLSTATE and offending task IDs
- **AND** no partial index or function change SHALL remain
- **AND** after rows are remediated, the unchanged migration SHALL succeed on retry
