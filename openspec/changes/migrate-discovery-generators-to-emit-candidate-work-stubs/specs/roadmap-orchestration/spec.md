## ADDED Requirements

### Requirement: Approved candidate-work intake

`/plan-roadmap` MUST provide a validated intake seam that maps one approved
candidate-work stub and operator-approved acceptance outcomes to one roadmap item
without hand-editing intermediate artifacts.

#### Scenario: Approved stub creates a new-roadmap item

- **WHEN** an approved canonical stub targets a new roadmap and supplies measurable acceptance outcomes
- **THEN** plan-roadmap SHALL create a schema-valid roadmap item
- **AND** the item SHALL preserve title, rationale, effort, priority, and exact suggested change ID
- **AND** the item's description SHALL retain candidate provenance

#### Scenario: Approved stub targets an existing roadmap

- **WHEN** an approved canonical stub targets an existing roadmap workspace
- **THEN** plan-roadmap SHALL route the mapped item through a refine-roadmap add request
- **AND** the existing roadmap SHALL NOT be written before preview and apply authorization

#### Scenario: Approved stub omits acceptance outcomes

- **WHEN** candidate intake is requested without non-empty acceptance outcomes
- **THEN** plan-roadmap MUST refuse the request
- **AND** no roadmap or change scaffold SHALL be written

#### Scenario: Candidate dependency cannot be resolved

- **WHEN** a stub dependency cannot be mapped to an item in the target roadmap
- **THEN** plan-roadmap MUST fail with the unresolved dependency name
- **AND** it MUST NOT silently drop or rewrite the dependency

#### Scenario: Approved input is a batch or collides with existing work

- **WHEN** intake receives an array, an active or archived change ID, or an ambiguous dependency
- **THEN** plan-roadmap MUST refuse before roadmap or scaffold writes
- **AND** the error SHALL identify the collision

#### Scenario: Existing-roadmap request is previewable

- **WHEN** one approved stub and nonblank outcomes target an existing roadmap
- **THEN** the request SHALL contain exactly one add operation and the next free item ID
- **AND** refine-roadmap preview SHALL accept it without direct mutation
