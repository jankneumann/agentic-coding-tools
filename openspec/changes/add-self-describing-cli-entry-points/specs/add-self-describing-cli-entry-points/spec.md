## ADDED Requirements

### Requirement: Give cross-skill scripts self-describing CLI interfaces

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-11` and is refined by
`/plan-feature` before implementation.

#### Scenario: No SKILL.md contains a <skill-base-dir> placeholder or a…

- **WHEN** the roadmap item is implemented
- **THEN** No SKILL.md contains a <skill-base-dir> placeholder or a sys.path.insert line

#### Scenario: Every shared command supports --json and --help

- **WHEN** the roadmap item is implemented
- **THEN** Every shared command supports --json and --help

#### Scenario: Failure paths exit non-zero with a message naming the corrective action

- **WHEN** the roadmap item is implemented
- **THEN** Failure paths exit non-zero with a message naming the corrective action

#### Scenario: The "run it BARE — do not pipe" warning class is removed because…

- **WHEN** the roadmap item is implemented
- **THEN** The "run it BARE — do not pipe" warning class is removed because exit status is no longer ambiguous
