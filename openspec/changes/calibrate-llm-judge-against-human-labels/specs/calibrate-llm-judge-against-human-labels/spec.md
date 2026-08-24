## ADDED Requirements

### Requirement: Calibrate the LLM judge against human labels

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-08` and is refined by
`/plan-feature` before implementation.

#### Scenario: Cohen's kappa is reported per judged dimension against the 40-item…

- **WHEN** the roadmap item is implemented
- **THEN** Cohen's kappa is reported per judged dimension against the 40-item labelled set

#### Scenario: Dimensions scoring below kappa 0.7 are excluded from the scorecard

- **WHEN** the roadmap item is implemented
- **THEN** Dimensions scoring below kappa 0.7 are excluded from the scorecard

#### Scenario: The judge runs blind to arm identity and with randomized…

- **WHEN** the roadmap item is implemented
- **THEN** The judge runs blind to arm identity and with randomized presentation order

#### Scenario: The judge does not receive the skill under test in its context

- **WHEN** the roadmap item is implemented
- **THEN** The judge does not receive the skill under test in its context
