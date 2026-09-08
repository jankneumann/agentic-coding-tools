## ADDED Requirements

### Requirement: Exhausted Phase Dispatches Route Immediately Through Escalate Resume

After a supervised Autopilot child exhausts its phase sub-agent retry budget and returns a schema-valid parked result with `kind: policy_pause`, the supervise execution adapter SHALL first validate and durably apply that result, then immediately route the persisted parked attempt through `gate_router.resolve_parked`. The router SHALL evaluate `escalate_resume` through the approval gate service exactly once per decision subject, and SHALL either resume the same dispatch generation with a recorded approval reference or leave the attempt parked and project the decision into the supervisor pending-gate record. A phase-failed handoff alone SHALL NOT be treated as a completed escalation route.

#### Scenario: Exhausted phase routes after durable parking

- **WHEN** a supervised child has entered `ESCALATE` after exhausting phase dispatch attempts and its exact result is collected as `parked.kind: policy_pause`
- **THEN** the adapter durably records the attempt as parked and releases its lease before gate evaluation
- **AND** it routes the persisted attempt through `gate_router.resolve_parked`, which evaluates `escalate_resume`
- **AND** the bounded apply result reports the correlated escalation resolution without child transcript content

#### Scenario: Notify-with-timeout surfaces the pending escalation

- **WHEN** `escalate_resume` has disposition `notify_with_timeout` with timeout T and the coordinator does not approve within T
- **THEN** the approval service files and sends one notification within the configured window
- **AND** the dispatch remains parked
- **AND** the supervisor mirror and rehydrated handoff contain an `escalate_resume` pending gate with the approval identifier and deadline derived from the recorded request time plus T

#### Scenario: Auto posture resumes the same dispatch

- **WHEN** `escalate_resume` has disposition `auto`
- **THEN** the gate router records a proceed decision and resumes the same dispatch ID through the existing approval-reference-checked CAS
- **AND** the lease generation increments while attempt number, launch token, worktree, and branch remain unchanged

#### Scenario: Repeated reconciliation does not duplicate escalation notification

- **WHEN** the same parked policy pause is reconciled again after a gate record was filed
- **THEN** the router applies its prior-record rule and does not file a second approval or append a duplicate decision
- **AND** a blocked decision leaves the same pending gate and deadline available for supervisor rehydration

#### Scenario: Non-escalation parked states keep their existing routes

- **WHEN** a result is an ordinary `pending_gate`, a failed result, or an attempt is quarantined for unknown liveness
- **THEN** this automatic `escalate_resume` path does not run
- **AND** the existing child-gate, failure, or quarantine semantics remain unchanged
