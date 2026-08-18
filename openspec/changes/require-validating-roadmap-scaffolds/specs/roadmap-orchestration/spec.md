## MODIFIED Requirements

### Requirement: Proposal Decomposition into Roadmap Changes

The system SHALL provide a `plan-roadmap` workflow that decomposes long markdown
proposals into prioritized OpenSpec change candidates with explicit dependencies
and acceptance outcomes.

#### Scenario: Seed OpenSpec change scaffolds from approved candidates
WHEN the user approves selected roadmap candidates
THEN `plan-roadmap` SHALL create draft OpenSpec change directories for each approved candidate
AND each created change SHALL include a proposal scaffold with a `parent_roadmap` field linking back to the roadmap change-id and item-id
AND each created change SHALL pass `openspec validate --strict` as created.

#### Scenario: Seeded scaffolds carry the item's acceptance outcomes as spec deltas
WHEN `plan-roadmap` seeds a change scaffold for an approved candidate
THEN the scaffold SHALL include a spec delta under `specs/` declaring at least one requirement
AND each of the item's acceptance outcomes SHALL appear as a `#### Scenario:` block within that delta
AND the delta SHALL be marked as a preliminary sketch that `plan-feature` refines before implementation.
