## ADDED Requirements

### Requirement: Convert the failure record into executable regression scenarios

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-01` and is refined by
`/plan-feature` before implementation.

#### Scenario: Every Observation and Follow-up in docs/merge-logs/ is either…

- **WHEN** the roadmap item is implemented
- **THEN** Every Observation and Follow-up in docs/merge-logs/ is either converted to a scenario or explicitly marked not-reproducible with a reason

#### Scenario: The scenario suite runs from a single command and reports pass/fail…

- **WHEN** the roadmap item is implemented
- **THEN** The scenario suite runs from a single command and reports pass/fail per scenario

#### Scenario: Each scenario carries a defect-category tag drawn from a documented…

- **WHEN** the roadmap item is implemented
- **THEN** Each scenario carries a defect-category tag drawn from a documented closed vocabulary

#### Scenario: At least one converted scenario fails against the current codebase,…

- **WHEN** the roadmap item is implemented
- **THEN** At least one converted scenario fails against the current codebase, proving the suite has teeth rather than encoding only already-fixed behaviour
