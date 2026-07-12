# merge-infrastructure — Delta Spec

## ADDED Requirements

### Requirement: Merge Plan Persistence and Projection

Merge plan storage SHALL select a tier using the existing merge-backend detection so the
coordinator is never a hard dependency. In the absence of an available coordinator, the
local `merge-plan.json` file SHALL be the authoritative store of plan state. The
human-readable `merge-plan.md` SHALL always be a faithful projection of the authoritative
`merge-plan.json` — rendering it SHALL NOT change plan state, and every node present in the
JSON SHALL appear in the projection.

#### Scenario: File tier is authoritative when no coordinator is available

- **WHEN** plan storage is initialised and no coordinator is available
- **THEN** the local `merge-plan.json` SHALL be treated as the authoritative store
- **AND** reads and writes of plan state SHALL operate on that file

#### Scenario: Rendered projection matches the authoritative JSON

- **WHEN** `merge-plan.md` is rendered from `merge-plan.json`
- **THEN** every node in the JSON SHALL appear in the projection with its current `outcome`
- **AND** rendering SHALL NOT mutate the authoritative plan state

#### Scenario: Plan state is separated into definition and live fields

- **WHEN** a plan is persisted
- **THEN** definition fields (PR set, dependency edges, strategy, gate rules) SHALL be
  distinguishable from live-state fields (`outcome`, in-flight claim, vendor verdict, inserted blockers)
- **AND** a live-state update SHALL NOT require rewriting the definition fields
