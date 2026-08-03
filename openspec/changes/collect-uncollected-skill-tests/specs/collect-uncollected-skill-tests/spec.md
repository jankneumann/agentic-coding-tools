## ADDED Requirements

### Requirement: Collect the 25 test directories CI never runs

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-20` and is refined by
`/plan-feature` before implementation.

#### Scenario: Every directory under skills/tests/ containing test files is listed…

- **WHEN** the roadmap item is implemented
- **THEN** Every directory under skills/tests/ containing test files is listed in testpaths

#### Scenario: The default sweep collects all of them without import errors

- **WHEN** the roadmap item is implemented
- **THEN** The default sweep collects all of them without import errors

#### Scenario: Modules sharing a name across skills are namespaced or imported…

- **WHEN** the roadmap item is implemented
- **THEN** Modules sharing a name across skills are namespaced or imported unambiguously

#### Scenario: The number of tests collected by the default sweep is recorded…

- **WHEN** the roadmap item is implemented
- **THEN** The number of tests collected by the default sweep is recorded before and after
