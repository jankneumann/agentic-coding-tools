## ADDED Requirements

### Requirement: Scenario-parity capability-gap source

The shared capability-gap tag schema SHALL accept `scenario-parity` as an additional `source` value, extending the `source` enum stated in "Capability Gap Detection", emitted by the agent-scenarios nightly runner for deterministic scenario failures, and `/improve-harness` SHALL consume and attribute it like the other sources without requiring source-specific code.

#### Scenario: source value is documented and pinned
- **WHEN** the memory tag convention tests run
- **THEN** `scenario-parity` SHALL be part of the source vocabulary constant
- **AND** `docs/guides/memory-conventions.md` SHALL document `scenario-parity` with its emitter, its trigger, and the auxiliary `vendor:` and `scenario:` tags

#### Scenario: improve-harness attributes scenario-parity findings
- **WHEN** `/improve-harness` failure analysis receives memory entries tagged `capability_gap`, `capability_gap:<value>`, `affected_skill:<skill>`, `severity:high` and `source:scenario-parity`
- **THEN** the ranked finding for `<value>` SHALL include `scenario-parity` in its source set
- **AND** repeated entries for the same `<value>` from different nightly runs SHALL increase that finding's frequency

#### Scenario: frequency counts failing run-and-vendor pairs
- **WHEN** two vendors fail the same gate in one nightly run and one vendor fails it again in a later run
- **THEN** the ranked finding for that `<value>` SHALL have frequency 3
- **AND** every entry's `details.run_id` SHALL name the nightly run that produced it

#### Scenario: scenario-parity entries are retrievable by the improve-harness memory query
- **WHEN** a scenario-parity entry is stored through the coordinator memory API
- **THEN** it SHALL carry the bare `capability_gap` tag so the improve-harness memory query, which filters on that tag, returns it

#### Scenario: the improve-harness memory query matches the coordinator API
- **WHEN** `/improve-harness` queries `POST /memory/query` against a coordinator that requires `agent_id` and an API key and answers with a `memories` list envelope
- **THEN** the request SHALL include `agent_id` and, when `COORDINATION_API_KEY` is set, an `Authorization: Bearer` header
- **AND** the entries in the `memories` list SHALL be returned to failure analysis
- **AND** entries older than the requested time window SHALL be dropped by `created_at` on the client side
