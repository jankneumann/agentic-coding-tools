## ADDED Requirements

### Requirement: Exhausted Phase Dispatches Route Immediately Through Escalate Resume

After a supervised Autopilot child exhausts its phase sub-agent retry budget and returns a schema-valid `parked.kind: policy_pause` result, the supervise host SHALL first complete exact-result application for the entire named batch and then invoke its separately retryable parked-escalation operation. The operation SHALL route each persisted policy pause through `gate_router.resolve_parked` under a generation-scoped decision-subject lock. The router SHALL evaluate `escalate_resume` exactly once per dispatch and parked lease generation, SHALL require any resume approval reference to authorize that same generation, and SHALL either resume the dispatch into its next generation or leave it parked and project the decision. A phase-failed handoff alone SHALL NOT complete escalation routing.

#### Scenario: Exhausted phase routes after complete durable application

- **WHEN** an exact named batch containing `parked.kind: policy_pause` has completed durable application for every member
- **THEN** the policy-pause attempt is parked with its lease released before gate evaluation
- **AND** the host separately routes it through `gate_router.resolve_parked`
- **AND** `ExecutionAdapter.apply` retains its exact existing signature and return shape

#### Scenario: Partial apply preserves replayable generations

- **WHEN** an earlier batch member is durably parked but a later member makes apply raise
- **THEN** error cleanup may report bounded candidate dispatch IDs but does not evaluate, notify, route, or resume them
- **AND** recovery retries the exact apply batch without a second `dispatch_fn` effect
- **AND** automatic escalation routing begins only after every batch member reaches terminal `effects_applied`

#### Scenario: Notify-with-timeout surfaces the pending escalation

- **WHEN** `escalate_resume` has disposition `notify_with_timeout` with timeout T and the coordinator does not approve within T
- **THEN** the approval service files and sends one notification within the configured window
- **AND** the dispatch remains parked
- **AND** the supervisor mirror contains the normalized pending gate with the approval identifier and deadline derived from recorded request time plus T
- **AND** a subsequent rehydrate prefers that newer mirror and the next normal supervisor handoff retains it

#### Scenario: Auto posture resumes a fresh application generation

- **WHEN** `escalate_resume` has disposition `auto`
- **THEN** a proceed decision recorded for parked generation G authorizes only generation G
- **AND** the same dispatch resumes at generation G+1 with attempt, launch token, worktree, and branch unchanged
- **AND** the generation-G application journal is cleared so G+1 can start, acknowledge, enter, and apply a fresh journal

#### Scenario: Same-generation routing is concurrency safe

- **WHEN** automatic and manual routing race for the same parked dispatch generation
- **THEN** a shared decision-subject lock admits one evaluation, notification, audit record, and optional resume
- **AND** approval-service waiting does not hold the workspace state lock

#### Scenario: Later exhaustion requires a new decision

- **WHEN** a dispatch resumed from generation G later parks again at a higher generation
- **THEN** the generation-G proceed reference cannot authorize the later parked generation
- **AND** the later generation receives a new evaluation while retries of that generation reuse one record
- **AND** projecting the later decision retires pending mirror entries from older generations of the same dispatch

#### Scenario: Blocked escalation remains answerable

- **WHEN** an operator answers blocked `escalate_resume` using the existing gate-answer surface with its dispatch ID
- **THEN** the router selects the newest blocked generation for that dispatch unless an optional generation was supplied explicitly
- **AND** it records the answer for that generation and the next route reuses it without refiling or renotifying

#### Scenario: Routing failure never replays apply effects

- **WHEN** the complete batch was applied and routing then raises
- **THEN** the attempt remains parked unless its own resolution already committed and `dispatch_fn` remains called once
- **AND** recovery retries only `route_parked_escalations`, not `apply`

#### Scenario: Routing response and notification are bounded

- **WHEN** automatic escalation routing returns or files an approval request
- **THEN** each result contains only the contract's outcome and generation-correlation keys plus normalized pending-gate data when blocked
- **AND** request context contains exactly validated durable identities, parked lease generation, `verb: resume`, and `reason: supervised phase retry budget exhausted`
- **AND** neither surface contains transcript content, a raw approval payload, an extra key, or the child-provided reason

#### Scenario: Routing retry recognizes committed proceed

- **WHEN** proceed and resume commit but the host crashes before receiving the route result
- **THEN** retry reports the prepared policy-pause continuation as `already_routed` with decided and resumed generations
- **AND** it does not evaluate, notify, audit, or resume again

#### Scenario: Non-escalation states keep their routes

- **WHEN** a result is an ordinary `pending_gate`, a failed result, or an attempt is quarantined
- **THEN** automatic `escalate_resume` routing does not run
- **AND** existing child-gate, failure, and quarantine semantics remain unchanged
