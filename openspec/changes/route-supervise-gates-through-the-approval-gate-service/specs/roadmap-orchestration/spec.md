## MODIFIED Requirements

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
- **AND** dependents are not failure-blocked while the pending gate metadata (gate, deadline, any filed `approval_id`) remains available to the supervise gate router, which is the only consumer permitted to resume it

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
- **WHEN** the supervise gate router supplies an `approval_ref` of the form `gate-decision:<decision_id>` for a `pending_gate` or `policy_pause` parked dispatch
- **THEN** the resume command verifies the reference resolves to a `gate_decisions` record in the same checkpoint with outcome `proceed`, a gate equal to the parked gate (or `escalate_resume` for `policy_pause`), and a matching `dispatch_id`, then compare-and-swaps parked to prepared, increments the lease generation, and emits one continuation with the same dispatch ID, attempt, token, worktree, and loop-state
- **AND** a reference that does not resolve, resolves to a `blocked` decision, or names a different gate or dispatch is rejected without mutating the attempt
- **AND** the normal child-start protocol transitions it to launched while duplicate or unauthorized resumes are rejected
- **AND** `ExecutionAdapter.prepare` likewise requires a `roadmap_approval_ref` resolving to a `proceed` `roadmap_approval` decision for the checkpoint's roadmap before any attempt is written

#### Scenario: Quarantine unknown post-go liveness
- **WHEN** a post-go generation has no terminal result and its durable task handle cannot positively establish live or dead status
- **THEN** the attempt becomes `quarantined` with its uncertain lease unreleased and no takeover or duplicate Autopilot entry occurs
- **AND** approval-gate resume is forbidden until reconciliation positively proves the prior task dead or terminal
