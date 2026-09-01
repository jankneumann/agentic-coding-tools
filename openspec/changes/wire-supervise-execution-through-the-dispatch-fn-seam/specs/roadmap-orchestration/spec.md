## ADDED Requirements

### Requirement: Delegated Autopilot Item Lifecycle

The roadmap orchestrator SHALL provide an opt-in two-stage delegated lifecycle: prepare persists a batch without invoking `dispatch_fn`; apply invokes the existing synchronous callback exactly once per collected generation result with phase `autopilot`. The child Autopilot run remains the sole writer of that change phase state.

#### Scenario: Delegate one item lifecycle
- **WHEN** a dependency-ready item with an exact `change_id` is executed in delegated-lifecycle mode
- **THEN** prepare returns a durable batch ID and request without invoking `dispatch_fn`, and apply later invokes `dispatch_fn(item_id, "autopilot", context)` exactly once for that generation through the bound result lookup
- **AND** the roadmap checkpoint is completed only after a successful structured dispatch result

#### Scenario: Reject an item without an exact change identifier
- **WHEN** delegated-lifecycle mode selects an item whose `change_id` is absent or invalid
- **THEN** no background dispatch is admitted
- **AND** the item and checkpoint remain resumable with a deterministic failure reason

### Requirement: Scope-Safe Ready Batches

The roadmap orchestrator MUST admit multiple items to the same ready batch only when their aggregated declared write scopes and lock keys prove that they are independent.

#### Scenario: Fan out disjoint ready items
- **WHEN** two dependency-ready items have valid work packages with disjoint `write_allow` scopes and lock keys
- **THEN** both items are emitted in the same prepared host batch without invoking `dispatch_fn`
- **AND** a synchronization-barrier test observes both host task handles live before either result is awaited

#### Scenario: Serialize overlapping or indeterminate items
- **WHEN** ready items overlap by write scope or lock key, or either item has missing, invalid, empty, or boundless write-scope evidence
- **THEN** the items are not admitted to the same batch and each affected request carries `proof: serial_indeterminate` with a schema-valid possibly empty `write_allow`
- **AND** deterministic priority and item-id ordering selects the first item while the remainder stay ready

#### Scenario: Treat ambiguous glob intersection conservatively
- **WHEN** two items declare globs whose intersection cannot be disproven, including `a/*/c` versus `a/b/*`
- **THEN** the classifier returns `ambiguous` rather than `disjoint`
- **AND** all package scopes, including integration and runtime-mirror write scopes, participate in the decision

### Requirement: Outcome-Only Resume Contract

The roadmap orchestrator SHALL persist only structured dispatch outcomes and handoff identifiers needed to resume; it MUST NOT persist a child transcript in roadmap state or dispatch context.

#### Scenario: Apply a successful child outcome
- **WHEN** a child returns a schema-valid success result correlated to the current dispatch identifier and change identifier
- **THEN** the item is completed and its learning entry is written once only after result path, branch, and loop-state evidence exactly match the prepared attempt and the resolved path remains contained by its verified worktree
- **AND** contradictory status/outcome pairs are schema-invalid and the checkpoint records bounded outcome metadata without transcript content

#### Scenario: Reject stale or mismatched child outcome
- **WHEN** a result carries a different dispatch identifier, change identifier, or already-applied attempt
- **THEN** the result is rejected without advancing the item
- **AND** a resumed run can safely redispatch or reconcile the current attempt

#### Scenario: Preserve a parked child
- **WHEN** a child Autopilot run returns a schema-valid parked result for a pending gate or paused policy state
- **THEN** the attempt is recorded as parked and the roadmap item is not marked failed or completed
- **AND** dependents are not failure-blocked while the pending gate metadata remains available to ri-04

### Requirement: Durable Delegated Attempt Ledger

The roadmap checkpoint SHALL record every delegated dispatch attempt before its request is returned to the host and SHALL preserve unresolved attempts across session restart.

#### Scenario: Persist a prepared batch before launch
- **WHEN** the scheduler prepares a safe batch of delegated item requests
- **THEN** each request's identity, exact isolation/scope/context envelope, stable launch token, marker path, attempt, phase, and prepared status are saved in `checkpoint.json` before the requests are emitted
- **AND** a crash after preparation loses agent launch work rather than losing the identity of potentially running work

#### Scenario: Resume with an unresolved attempt
- **WHEN** a fresh supervisor loads a checkpoint containing a prepared attempt without a correlated result
- **THEN** it reconciles a persisted host launch acknowledgement, an atomic child-start marker, and worktree Autopilot state before deciding whether work launched
- **AND** pre-go stale claims may be reclaimed by generation compare-and-swap; after go, takeover requires positive task-death evidence, and unknown liveness becomes non-resumable quarantine

#### Scenario: Reconcile lease crash windows
- **WHEN** a crash occurs before marker creation, after marker but before Autopilot entry, before host acknowledgement, or while a child is active
- **THEN** the generation-specific ack/go barrier prevents Autopilot entry before durable handle acknowledgement, while markers, heartbeats, handle status, exact worktree loop-state, and terminal handoff/result evidence classify the generation
- **AND** a pre-go expired claim may be reclaimed safely, but a post-go generation may be reclaimed only after positive task-death evidence; mere absence or expiry enters quarantine
- **AND** duplicate owners, active-lease token reuse, and stale owners that fail compare-and-swap are refused

#### Scenario: Resume an authorized parked attempt
- **WHEN** ri-04 supplies a durable approval reference for a `pending_gate` or `policy_pause` parked dispatch
- **THEN** the resume command compare-and-swaps parked to prepared, increments the lease generation, and emits one continuation with the same dispatch ID, attempt, token, worktree, and loop-state
- **AND** the normal child-start protocol transitions it to launched while duplicate or unauthorized resumes are rejected

#### Scenario: Quarantine unknown post-go liveness
- **WHEN** a post-go generation has no terminal result and its durable task handle cannot positively establish live or dead status
- **THEN** the attempt becomes `quarantined` with its uncertain lease unreleased and no takeover or duplicate Autopilot entry occurs
- **AND** approval-gate resume is forbidden until reconciliation positively proves the prior task dead or terminal
