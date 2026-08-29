## ADDED Requirements

### Requirement: Extend handoff document with supervisor record

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `ri-05` and is refined by
`/plan-feature` before implementation.

#### Scenario: Killing the supervisor session mid-roadmap and starting a fresh one…

- **WHEN** the roadmap item is implemented
- **THEN** Killing the supervisor session mid-roadmap and starting a fresh one loses no state; the new session lists active changes, pending gates, and next actions from the handoff alone

#### Scenario: The supervisor record round-trips through serialization with all…

- **WHEN** the roadmap item is implemented
- **THEN** The supervisor record round-trips through serialization with all four sections (active changes, pending gates, standing decisions, back-edge digest state) intact, covered by unit tests

#### Scenario: The SessionStart hook loads the supervisor record without changes…

- **WHEN** the roadmap item is implemented
- **THEN** The SessionStart hook loads the supervisor record without changes beyond the schema extension
