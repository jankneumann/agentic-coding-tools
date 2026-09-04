## MODIFIED Requirements

### Requirement: Proposal Decomposition into Roadmap Changes

The system SHALL provide a `plan-roadmap` workflow that decomposes a long-form markdown proposal into a prioritized set of OpenSpec change candidates, and SHALL scaffold each approved candidate as a change that already validates.

#### Scenario: Decompose markdown proposal into roadmap candidates
WHEN a user provides a long markdown proposal to `plan-roadmap`
THEN the workflow SHALL extract candidate capabilities, constraints, and phases
AND it SHALL emit a roadmap artifact conforming to `contracts/roadmap.schema.json`
AND each candidate SHALL include effort estimate and rationale.

#### Scenario: Reject decomposition when proposal input is insufficient
WHEN the input markdown omits required implementation intent (no actionable capabilities or constraints)
THEN `plan-roadmap` SHALL fail with a structured validation error
AND it SHALL provide guidance for minimum required proposal sections.

#### Scenario: Seed OpenSpec change scaffolds from approved candidates
WHEN the user approves selected roadmap candidates
THEN `plan-roadmap` SHALL create draft OpenSpec change directories for each approved candidate
AND each created change SHALL include a proposal scaffold with a `parent_roadmap` field linking back to the roadmap change-id and item-id.

#### Scenario: Scaffolded changes are valid OpenSpec changes
WHEN `plan-roadmap` scaffolds an approved candidate
THEN the created change SHALL include at least one spec delta file under `specs/<capability>/spec.md`
AND that change SHALL pass `openspec validate --strict`
AND the delta SHALL survive being committed, rather than relying on a directory that git does not track.

#### Scenario: Spec deltas are derived from acceptance outcomes
WHEN a scaffolded candidate declares acceptance outcomes
THEN each outcome SHALL become one requirement with at least one scenario
AND each requirement's first body line SHALL contain SHALL or MUST
AND an outcome that already states a modal verb SHALL NOT be wrapped in a second one.

#### Scenario: A candidate without acceptance outcomes still scaffolds validly
WHEN a scaffolded candidate declares no acceptance outcomes
THEN `plan-roadmap` SHALL still emit a delta that passes `openspec validate --strict`
AND that delta SHALL state that its requirements are to be replaced during refinement.

#### Scenario: Scaffolded artifacts declare themselves preliminary
WHEN `plan-roadmap` writes a spec delta or design sketch
THEN the artifact SHALL carry a marker identifying it as a scaffold awaiting refinement
AND the marker SHALL name the roadmap and item it was generated from.

#### Scenario: Design sketches are written only when they carry content
WHEN a scaffolded candidate declares a rationale or dependencies
THEN `plan-roadmap` SHALL write a `design.md` sketch for it
AND WHEN the candidate declares neither
THEN no `design.md` SHALL be written.

#### Scenario: Merge undersized roadmap items during decomposition
WHEN decomposition produces candidate items that are smaller than a single implementable OpenSpec change
THEN `plan-roadmap` SHALL merge them with adjacent items
AND it SHALL record the merge rationale in the merged item's description.

#### Scenario: Split oversized roadmap items during decomposition
WHEN a candidate item exceeds single-change scope (spans multiple independent capabilities or systems)
THEN `plan-roadmap` SHALL split it into separate items
AND it SHALL add dependency edges between the resulting items where ordering matters.

#### Scenario: Replan scope is the affected subgraph only
WHEN `decomposer.py replan-scope <workspace>` runs against a roadmap where `ri-03` failed with a replan signal and `ri-04`, `ri-06` depend on it while `ri-05` is completed
THEN the output SHALL list exactly `ri-04` and `ri-06` (and their transitive dependents that are not in a preserved status)
AND it SHALL NOT list `ri-05` or any completed item.

#### Scenario: Replan preserves completed items and learnings
WHEN `/plan-roadmap --replan <roadmap-id>` completes
THEN every item that was `completed`, `superseded`, or `in_progress` SHALL be byte-identical to its pre-replan entry
AND every file under `learnings/` SHALL be unchanged
AND `replan-request.json` SHALL no longer exist
AND `decomposer.py validate` SHALL exit 0.

#### Scenario: Replan without a request file is refused
WHEN `/plan-roadmap --replan <roadmap-id>` is invoked and `<workspace>/replan-request.json` does not exist
THEN the workflow SHALL exit with a structured error naming the missing file
AND the roadmap SHALL be unchanged.

## ADDED Requirements

### Requirement: Roadmap items are refined before they are implemented

An item advanced to by the roadmap runtime SHALL enter the planning phase, so that its preliminary scaffold is refined using what was learned implementing its dependencies before any implementation begins.

Roadmap items are planned one at a time rather than all at once precisely so that later items benefit from earlier ones. Advancing straight into implementation spends that opportunity and implements against a scaffold nobody revisited.

#### Scenario: Advancing to the next item enters planning
WHEN the roadmap runtime advances to the next ready item
THEN the checkpoint phase SHALL be set to planning
AND the persisted checkpoint SHALL record that phase.

#### Scenario: The refinement pass is not reported as already complete
WHEN the roadmap runtime has just advanced to an item
THEN the planning phase SHALL NOT be reported as skippable for that item
AND a refinement pass SHALL therefore run before implementation.

#### Scenario: Refinement acts on the scaffold rather than an empty directory
WHEN a refinement pass begins for a newly advanced item
THEN the item's change directory SHALL already contain the preliminary proposal and spec delta written at roadmap-creation time.
