# review-convergence-safety Specification

## Purpose
TBD - created by archiving change harden-substantive-review-gates. Update Purpose after archive.
## Requirements
### Requirement: Placeholder-only review output is ineligible

The review dispatcher MUST reject a schema-valid response whose complete substantive content is a provisional placeholder, and the rejected result MUST NOT count toward quorum.

#### Scenario: Historical placeholder response

- **WHEN** a vendor returns the historical “Placeholder while review runs” response in an otherwise schema-valid envelope
- **THEN** the terminal result is unsuccessful with reason `non_substantive_placeholder`
- **AND** its raw output remains available for diagnosis

#### Scenario: Placeholder does not invalidate a substantive review

- **WHEN** a response contains at least one concrete non-placeholder finding
- **THEN** placeholder wording outside that finding does not by itself make the response unsuccessful

### Requirement: High-impact judgment requires adjudication

The convergence loop MUST stop without convergence when an open judgment-class finding is unconfirmed and has high or critical impact, and MUST route that finding to escalation instead of automated fixing.

#### Scenario: Unconfirmed high judgment

- **WHEN** consensus yields an unconfirmed high-impact judgment finding
- **THEN** convergence returns `adjudication_required`
- **AND** the escalation callback receives the finding
- **AND** the automated fix callback is not invoked

#### Scenario: Medium judgment remains advisory

- **WHEN** consensus yields only unconfirmed medium-impact judgment findings
- **THEN** the existing advisory convergence behavior is preserved

### Requirement: Terminal vendor results are checkpointed incrementally

The dispatcher MUST expose each terminal vendor result exactly once, and the convergence loop MUST durably checkpoint that result before waiting for the whole panel to return.

#### Scenario: Supervisor interruption after one completion

- **WHEN** one of two vendors completes and the supervising process is interrupted before the second result
- **THEN** the completed vendor's findings and raw output are present in a readable round manifest
- **AND** the manifest reports two requested results and one received result

#### Scenario: Async submission is not terminal

- **WHEN** an asynchronous vendor submission returns a task identifier
- **THEN** no terminal-result callback occurs until polling returns a result or the submission fails

#### Scenario: Callback preserves return order

- **WHEN** vendors complete out of dispatch order
- **THEN** each completion is checkpointed promptly
- **AND** the final returned list remains in dispatch order

