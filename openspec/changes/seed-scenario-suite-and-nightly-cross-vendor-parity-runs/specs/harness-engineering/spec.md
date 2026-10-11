## ADDED Requirements

### Requirement: Scenario-parity capability-gap source

The shared capability-gap tag schema SHALL accept `scenario-parity` as an additional `source` value, emitted by the agent-scenarios nightly runner for deterministic scenario failures, and `/improve-harness` SHALL consume and attribute it like the other sources without requiring source-specific code.

#### Scenario: source value is documented and pinned
- **WHEN** the memory tag convention tests run
- **THEN** `scenario-parity` SHALL be part of the source vocabulary constant
- **AND** `docs/guides/memory-conventions.md` SHALL document `scenario-parity` with its emitter, its trigger, and the auxiliary `vendor:` and `scenario:` tags

#### Scenario: improve-harness attributes scenario-parity findings
- **WHEN** `/improve-harness` failure analysis receives memory entries tagged `capability_gap`, `capability_gap:<value>`, `affected_skill:<skill>`, `severity:high` and `source:scenario-parity`
- **THEN** the ranked finding for `<value>` SHALL include `scenario-parity` in its source set
- **AND** repeated entries for the same `<value>` from different nightly runs SHALL increase that finding's frequency

#### Scenario: scenario-parity entries are retrievable by the improve-harness memory query
- **WHEN** a scenario-parity entry is stored through the coordinator memory API
- **THEN** it SHALL carry the bare `capability_gap` tag so the improve-harness memory query, which filters on that tag, returns it
