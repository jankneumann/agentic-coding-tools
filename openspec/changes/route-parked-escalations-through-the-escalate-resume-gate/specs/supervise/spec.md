## ADDED Requirements

### Requirement: Exhausted Phase Dispatches Route Immediately Through Escalate Resume

After a supervised Autopilot child exhausts its phase sub-agent retry budget and returns a schema-valid parked result with `kind: policy_pause`, the supervise execution adapter SHALL first validate and durably apply that result, then the host SHALL invoke its separately retryable parked-escalation operation, including from apply error cleanup when an earlier batch member may already be durable. The operation SHALL route the persisted attempt through `gate_router.resolve_parked` under one non-reentrant workspace serialization boundary. The router SHALL evaluate `escalate_resume` through the approval gate service exactly once per dispatch-and-lease-generation decision subject, and SHALL either resume the same dispatch into its next lease generation with a recorded approval reference or leave the attempt parked and project the decision into the supervisor pending-gate record. A phase-failed handoff alone SHALL NOT be treated as a completed escalation route.

#### Scenario: Exhausted phase routes after durable parking

- **WHEN** a supervised child has entered `ESCALATE` after exhausting phase dispatch attempts and its exact result is collected as `parked.kind: policy_pause`
- **THEN** the adapter durably records the attempt as parked and releases its lease before gate evaluation
- **AND** it routes the persisted attempt through `gate_router.resolve_parked`, which evaluates `escalate_resume`
- **AND** `ExecutionAdapter.apply` retains its exact existing return shape
- **AND** the separate routing result reports one allowlisted correlated resolution without child transcript, raw approval response, or child-provided reason content

#### Scenario: Notify-with-timeout surfaces the pending escalation

- **WHEN** `escalate_resume` has disposition `notify_with_timeout` with timeout T and the coordinator does not approve within T
- **THEN** the approval service files and sends one notification within the configured window
- **AND** the dispatch remains parked
- **AND** the supervisor mirror contains an `escalate_resume` pending gate with the approval identifier and deadline derived from the recorded request time plus T
- **AND** a subsequent supervisor rehydrate prefers that newer mirror over a stale or missing handoff and the next normal supervisor handoff retains the same normalized pending gate

#### Scenario: Auto posture resumes the same dispatch

- **WHEN** `escalate_resume` has disposition `auto`
- **THEN** the gate router records a proceed decision and resumes the same dispatch ID through the existing approval-reference-checked CAS
- **AND** the lease generation increments while attempt number, launch token, worktree, and branch remain unchanged
- **AND** the prior generation's application journal is cleared so the resumed generation can be started, acknowledged, entered, and applied with a fresh journal

#### Scenario: Repeated reconciliation does not duplicate escalation notification

- **WHEN** the same parked policy pause and lease generation are reconciled again after a gate record was filed
- **THEN** the router applies its prior-record rule and does not file a second approval or append a duplicate decision
- **AND** a blocked decision leaves the same pending gate and deadline available for supervisor rehydration

#### Scenario: Concurrent retries serialize one decision

- **WHEN** two routing calls race for the same parked policy pause and lease generation
- **THEN** one workspace serialization boundary admits one gate evaluation, notification, audit record, and optional resume
- **AND** routed resume does not reacquire the same non-reentrant file lock

#### Scenario: A later exhaustion requires a new generation decision

- **WHEN** a dispatch previously resumed from a proceeded `escalate_resume` decision later exhausts its retry budget again in a higher lease generation
- **THEN** the old proceed record is not reused for the higher generation
- **AND** the higher generation receives a new posture evaluation while retries of that same generation reuse its one prior record

#### Scenario: Routing failure never replays apply effects

- **WHEN** apply has durably parked a policy pause and routing then raises
- **THEN** the attempt remains durably parked and the already acknowledged `dispatch_fn` call count remains one
- **AND** recovery retries only `route_parked_escalations`, not `apply`
- **AND** if a later member of a multi-member apply fails after the first pause was persisted, error cleanup still routes that earlier durable pause

#### Scenario: Routing retry reports already completed work safely

- **WHEN** a proceed decision and resume commit but the host crashes before receiving the routing result
- **THEN** a retry does not notify, audit, or resume the prepared continuation again
- **AND** it may report `already_routed` using only the allowlisted bounded response fields

#### Scenario: Non-escalation parked states keep their existing routes

- **WHEN** a result is an ordinary `pending_gate`, a failed result, or an attempt is quarantined for unknown liveness
- **THEN** this automatic `escalate_resume` path does not run
- **AND** the existing child-gate, failure, or quarantine semantics remain unchanged
