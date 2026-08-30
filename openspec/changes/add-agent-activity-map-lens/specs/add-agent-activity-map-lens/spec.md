## ADDED Requirements

### Requirement: Agent-activity infinity map lens

The system SHALL deliver the outcomes below. This requirement is a preliminary
sketch generated from roadmap item `agent-activity-map-lens` and is refined by
`/plan-feature` before implementation.

#### Scenario: The lens MUST register in the lens framework, be URL-encodable, and…

- **WHEN** the roadmap item is implemented
- **THEN** The lens MUST register in the lens framework, be URL-encodable, and restore its full view state from URL alone

#### Scenario: Every rendered edge MUST trace to a provenance entry in the consumed…

- **WHEN** the roadmap item is implemented
- **THEN** Every rendered edge MUST trace to a provenance entry in the consumed IR; selecting an edge MUST reveal its evidence pointer; the lens MUST NOT render inferred edges absent from the document

#### Scenario: Agent activity indicators MUST reflect coordinator state within 10…

- **WHEN** the roadmap item is implemented
- **THEN** Agent activity indicators MUST reflect coordinator state within 10 seconds during live viewing

#### Scenario: Semantic zoom MUST expose at least three levels (roadmap…

- **WHEN** the roadmap item is implemented
- **THEN** Semantic zoom MUST expose at least three levels (roadmap territories, change/ package DAG, path-level activity) with zone-anchored positions stable across reloads for unchanged topology

#### Scenario: A touched edge flagged out_of_scope MUST be visually distinguished…

- **WHEN** the roadmap item is implemented
- **THEN** A touched edge flagged out_of_scope MUST be visually distinguished within one refresh interval, and a touch on a path scoped to a completed work package MUST raise a visible regression accent

#### Scenario: A delta view MUST render added/removed/changed nodes and edges…

- **WHEN** the roadmap item is implemented
- **THEN** A delta view MUST render added/removed/changed nodes and edges between two frozen snapshots selected by snapshot_id

#### Scenario: A frozen export MUST produce a self-contained HTML document of the…

- **WHEN** the roadmap item is implemented
- **THEN** A frozen export MUST produce a self-contained HTML document of the current view requiring no coordinator connectivity
