## ADDED Requirements

### Requirement: Assert in CI that skill-generated artifacts pass their own validators

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-19` and is refined by
`/plan-feature` before implementation.

#### Scenario: Every artifact-generating skill has a test that runs its artifact…

- **WHEN** the roadmap item is implemented
- **THEN** Every artifact-generating skill has a test that runs its artifact through the real validator, not a structural approximation

#### Scenario: Bypassing the scaffolder's spec-delta writer makes that test fail

- **WHEN** the roadmap item is implemented
- **THEN** Bypassing the scaffolder's spec-delta writer makes that test fail

#### Scenario: The checks run in CI on every push and block merge on failure

- **WHEN** the roadmap item is implemented
- **THEN** The checks run in CI on every push and block merge on failure

#### Scenario: Each generator documents which validator is authoritative for its output

- **WHEN** the roadmap item is implemented
- **THEN** Each generator documents which validator is authoritative for its output
