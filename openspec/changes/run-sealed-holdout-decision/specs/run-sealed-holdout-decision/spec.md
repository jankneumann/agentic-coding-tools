## ADDED Requirements

### Requirement: Run the sealed holdout and apply the pre-registered decision rule

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-17` and is refined by
`/plan-feature` before implementation.

#### Scenario: Both arms run across all 32 holdout changes at N=3 with blinded judging

- **WHEN** the roadmap item is implemented
- **THEN** Both arms run across all 32 holdout changes at N=3 with blinded judging

#### Scenario: The accept/reject verdict is stated against the rule as registered,…

- **WHEN** the roadmap item is implemented
- **THEN** The accept/reject verdict is stated against the rule as registered, without amendment

#### Scenario: Per-metric deltas are published with variance, and any rejected cut…

- **WHEN** the roadmap item is implemented
- **THEN** Per-metric deltas are published with variance, and any rejected cut is reverted or reworked rather than retained
