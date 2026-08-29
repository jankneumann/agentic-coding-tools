## ADDED Requirements

### Requirement: Seal the archive benchmark corpus into development and holdout partitions

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-02` and is refined by
`/plan-feature` before implementation.

#### Scenario: A committed manifest assigns all 92 archived changes to exactly one…

- **WHEN** the roadmap item is implemented
- **THEN** A committed manifest assigns all 92 archived changes to exactly one partition

#### Scenario: The manifest records a checksum that detects post-hoc reassignment

- **WHEN** the roadmap item is implemented
- **THEN** The manifest records a checksum that detects post-hoc reassignment

#### Scenario: Tooling refuses to run holdout tasks unless explicitly invoked with…

- **WHEN** the roadmap item is implemented
- **THEN** Tooling refuses to run holdout tasks unless explicitly invoked with a decision-run flag

#### Scenario: The holdout partition is drawn predominantly from changes archived…

- **WHEN** the roadmap item is implemented
- **THEN** The holdout partition is drawn predominantly from changes archived after 2026-05-01
