## ADDED Requirements

### Requirement: Immediate Policy-Pause Escalation Has One Authoritative Commit

After complete durable application of a named delegated batch, the supervise runtime SHALL route each parked `policy_pause` through `escalate_resume`. It SHALL use a process-safe generation subject lock for external evaluation and a short shared checkpoint transaction for fresh authority updates. The transaction SHALL serialize the gate-decision ledger with checkpoint state and, for proceed, SHALL atomically record the decision and advance only the matching parked attempt to its next generation. It SHALL NOT hold the checkpoint transaction across approval-service I/O, notification polling, or host callbacks. Supervisor mirror and handoff state SHALL be derived from the committed ledger, never authority for resume.

#### Scenario: Complete batch routes exactly once

- **WHEN** every named-batch attempt is terminal with application journal state `effects_applied` and one is parked as `policy_pause`
- **THEN** the runtime SHALL evaluate or reuse exactly one `escalate_resume` decision for that dispatch and parked generation
- **AND** a proceed SHALL create its generation G+1 continuation in the same authoritative transaction
- **AND** a blocked decision SHALL leave the attempt parked and project one normalized pending gate after that transaction

#### Scenario: Partial batch cannot route

- **WHEN** any member of the named batch is not terminal with application journal state `effects_applied`
- **THEN** route operation SHALL refuse before evaluation, notification, projection, or resume
- **AND** application recovery SHALL remain replayable without a second host callback

#### Scenario: Approval wait preserves concurrent authority

- **WHEN** routing waits for an approval decision while a different execution transition commits in the same workspace
- **THEN** the unrelated transition SHALL remain durable after routing commits
- **AND** the workspace transaction SHALL not be held during the wait
- **AND** the committed checkpoint SHALL never expose the new state without its decision ledger update

#### Scenario: Stale and concurrent routing are safe

- **WHEN** the routed attempt changes state or generation while a candidate decision waits
- **THEN** the stale candidate SHALL not append a record, alter the mirror, or resume the attempt
- **AND** when automatic and manual resolution race for the same generation, only one authoritative decision and optional resume SHALL occur
- **AND** concurrent blocked decisions for different subjects SHALL preserve both normalized mirror entries

### Requirement: Escalate Resume Correlation Is Generation-Safe and Sanitized

New `escalate_resume` records SHALL carry the parked positive integer `lease_generation`; prior generationless records SHALL remain reusable for the matching currently parked dispatch. Every policy-pause resolver, including manual reconciliation, SHALL use only the allowlisted context `dispatch_id`, `change_id`, `item_id`, `lease_generation`, `verb: resume`, and fixed retry-budget reason. Approval references SHALL authorize the same parked generation only.

#### Scenario: Legacy and later generations remain distinct

- **WHEN** a current parked dispatch has a generationless legacy escalation record
- **THEN** the router SHALL reuse it without filing a duplicate approval
- **AND** when that dispatch later parks at a higher generation, it SHALL create a new decision and retire older same-dispatch pending mirror entries
- **AND** a prior-generation proceed reference SHALL be rejected

#### Scenario: Manual and automatic context are identical

- **WHEN** either automatic post-apply routing or manual reconciliation resolves a policy pause
- **THEN** its request context SHALL contain exactly the six allowlisted fields and fixed reason
- **AND** no child-provided reason, transcript, raw approval response, or additional key SHALL be persisted or returned

#### Scenario: Answer selects a generation safely

- **WHEN** an operator answers `escalate_resume` with only a dispatch ID
- **THEN** the router SHALL select the newest blocked generation
- **AND** an optional explicit generation SHALL select only that blocked generation
