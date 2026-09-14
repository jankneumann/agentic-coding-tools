## MODIFIED Requirements

### Requirement: Terminal vendor results are checkpointed incrementally

The dispatcher MUST expose each terminal vendor result exactly once, and the convergence loop MUST durably checkpoint that result before waiting for the whole panel to return. The checkpointed vendor file MUST be the raw validated payload before any fact-check removal, and the round manifest MUST carry each vendor's coverage rate and fact-check outcome so a reader can reconstruct what each vendor saw and what was removed.

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

#### Scenario: Checkpoint precedes fact-check removal

- **WHEN** the fact-check pass removes a finding from a vendor's set
- **THEN** the vendor's checkpointed findings file still contains that finding
- **AND** the manifest entry for that vendor records `fact_check_removed` and `coverage_rate`
