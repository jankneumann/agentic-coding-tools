## ADDED Requirements

### Requirement: Approved candidate-work intake

`/plan-roadmap` MUST provide a validated intake seam that maps one approved
candidate-work stub and operator-approved acceptance outcomes to one roadmap item
without hand-editing intermediate artifacts.

#### Scenario: Approved stub creates a new-roadmap item

- **WHEN** an approved canonical stub targets a new roadmap and supplies measurable acceptance outcomes, a roadmap ID, and a capability
- **THEN** plan-roadmap SHALL create a schema-valid roadmap item
- **AND** it SHALL create a complete schema-version-1 roadmap envelope using `provenance.source_artifact` as `source_proposal`
- **AND** the item SHALL preserve title, rationale, effort, priority, and exact suggested change ID
- **AND** the scaffolded spec delta SHALL use the approved capability
- **AND** the item's description SHALL retain candidate provenance

#### Scenario: Approved stub targets an existing roadmap

- **WHEN** an approved canonical stub targets an existing roadmap workspace
- **THEN** plan-roadmap SHALL route the mapped item through a refine-roadmap add request
- **AND** the request SHALL omit execution priority so refine-roadmap assigns the next free priority
- **AND** the candidate priority SHALL remain present in the request rationale
- **AND** the existing roadmap SHALL NOT be written before preview and apply authorization

#### Scenario: Approved stub omits acceptance outcomes

- **WHEN** candidate intake is requested without non-empty acceptance outcomes
- **THEN** plan-roadmap MUST refuse the request
- **AND** no roadmap or change scaffold SHALL be written

#### Scenario: Candidate dependencies retain explicit resolution

- **WHEN** the shared resolver groups exact dependency matches across candidate, roadmap, active-change, and archive sources
- **THEN** plan-roadmap SHALL collapse duplicate completed/archive lifecycle records and record an all-completed group as satisfied rationale
- **AND** exactly one live target-roadmap item SHALL map to its local item ID and exactly one live item in another roadmap SHALL map to the canonical external reference
- **AND** the preview SHALL show that conversion without silently dropping the source change ID

#### Scenario: Candidate dependency cannot be resolved

- **WHEN** a stub dependency is unknown, has multiple live matches, points to active work without a unique roadmap item, or has only failed/skipped/superseded records
- **THEN** plan-roadmap MUST fail with the unresolved dependency name
- **AND** it MUST NOT silently drop or rewrite the dependency

#### Scenario: Approved input is a batch or collides with existing work

- **WHEN** intake receives an array, a change ID already present in any roadmap item or active/archive change, or an ambiguous dependency
- **THEN** plan-roadmap MUST refuse before roadmap or scaffold writes
- **AND** the error SHALL identify the collision

#### Scenario: Existing-roadmap request is previewable

- **WHEN** one approved stub and nonblank outcomes target an existing roadmap
- **THEN** plan-roadmap SHALL freshly load the workspace and place exactly one add operation with the next free item ID into the request immediately before preview
- **AND** refine-roadmap preview SHALL validate that helper-assigned ID without direct mutation
- **AND** apply SHALL refuse a stale preview base if the next item ID or priority changed
