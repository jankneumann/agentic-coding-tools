## ADDED Requirements

### Requirement: Agent-activity map-state IR (schema + coordinator projection)

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `map-state-ir` and is refined by
`/plan-feature` before implementation.

#### Scenario: GET /map/state on the coordinator MUST return a document that…

- **WHEN** the roadmap item is implemented
- **THEN** GET /map/state on the coordinator MUST return a document that validates against openspec/schemas/map-state.schema.json, covering all active changes

#### Scenario: Every emitted node and edge MUST carry at least one provenance entry…

- **WHEN** the roadmap item is implemented
- **THEN** Every emitted node and edge MUST carry at least one provenance entry naming its source store and a human-followable evidence pointer; the endpoint MUST NOT emit edges lacking provenance

#### Scenario: Agent nodes MUST reconcile registry agent_id, agent_sessions.id, and…

- **WHEN** the roadmap item is implemented
- **THEN** Agent nodes MUST reconcile registry agent_id, agent_sessions.id, and the <package>--<vendor> naming convention into a single node with an identities block; a fixture test MUST cover an agent visible under all three forms

#### Scenario: Derived agent activity MUST be one of…

- **WHEN** the roadmap item is implemented
- **THEN** Derived agent activity MUST be one of working/waiting/idle/stale/disconnected, computed from heartbeat freshness, active claims, and needs_human status reports; the derivation rule MUST be documented in docs/codeviz/map-state.md and recorded as a derived provenance entry

#### Scenario: Intent-versus-reality MUST be expressible; scoped_to edges from…

- **WHEN** the roadmap item is implemented
- **THEN** Intent-versus-reality MUST be expressible; scoped_to edges from work-packages.yaml scope globs and touched edges from scope_checker output, with out_of_scope flagged on touches outside the owning package's write_allow

#### Scenario: A snapshot writer MUST persist frozen map-state documents as event…

- **WHEN** the roadmap item is implemented
- **THEN** A snapshot writer MUST persist frozen map-state documents as event artifacts under docs/codeviz/map-state/<YYYY-MM-DD>/<run-id>.json carrying the mandatory artifact header

#### Scenario: A validation helper under skills/shared MUST validate documents…

- **WHEN** the roadmap item is implemented
- **THEN** A validation helper under skills/shared MUST validate documents against the schema and MUST be covered by fixture tests for both valid and invalid (provenance-less) documents
