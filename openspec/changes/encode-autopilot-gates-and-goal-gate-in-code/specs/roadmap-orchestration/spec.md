# roadmap-orchestration — delta

## MODIFIED Requirements

### Requirement: Adaptive Roadmap Execution

The system SHALL provide an `autopilot-roadmap` workflow that executes roadmap items iteratively and updates pending items using implementation evidence. When an item fails, `CheckpointManager.fail_item(checkpoint, roadmap, item_id, reason, *, replan=False)` SHALL transition the failed item's dependents to `blocked` by default and to `replan_required` only when the failing item's outcome payload carries an explicit `replan: true` signal; the workflow SHALL NOT infer hard-versus-workaroundable from the failure text. For every item in `replan_required`, the orchestrator SHALL evaluate `Gate.REPLAN_REQUIRED` through an injected `GateEvaluator` (default `approval_gate.build_default_gate()`); on `proceed` it SHALL write a `ReplanRequest` conforming to `contracts/events/replan-request.schema.json` to `<workspace>/replan-request.json` and finish the run with status `replan_requested`; on `blocked` the items SHALL stay `replan_required`, the decision SHALL be recorded in the checkpoint, and the run SHALL continue with other ready items. The orchestrator SHALL make no LLM or network call to perform the replan itself; the host executes `/plan-roadmap --replan <roadmap-id>`.

#### Scenario: Learning feedback updates remaining roadmap items
WHEN a roadmap item completes implementation and review
THEN `autopilot-roadmap` SHALL persist a learning entry to `learnings/<item-id>.md` conforming to `contracts/learning-log.schema.json`
AND it SHALL update the root `learning-log.md` index with a one-line summary
AND before the next item begins it SHALL ingest prior learning entries (direct dependencies + most recent 3)
AND it SHALL update pending item recommendations accordingly.

#### Scenario: Resume from persisted checkpoint after interruption
WHEN roadmap execution stops before completion
THEN `autopilot-roadmap` SHALL resume from the last successful checkpoint conforming to `contracts/checkpoint.schema.json`
AND it SHALL skip phases already marked complete unless forced by user input.

#### Scenario: Abort item execution when prerequisite roadmap dependency is incomplete
WHEN a roadmap item is selected for execution
AND one or more of its dependency items are not complete
THEN `autopilot-roadmap` SHALL block execution of that item
AND it SHALL emit a dependency-blocked status with missing dependency IDs.

#### Scenario: Handle individual roadmap item implementation failure
WHEN a roadmap item fails implementation (tests fail, review rejects, or design dead-end)
THEN `autopilot-roadmap` SHALL mark the item as `failed` in `roadmap.yaml` with a structured failure reason
AND it SHALL persist a learning entry recording the failure details, root cause, and recommendations
AND it SHALL transition dependent items in `approved` or `candidate` status to `blocked`
AND it SHALL proceed to the next eligible item rather than halting the entire roadmap.

#### Scenario: Explicit replan signal produces replan_required
WHEN a roadmap item fails and its outcome payload contains `replan: true`
THEN `fail_item(..., replan=True)` SHALL transition dependents in `approved` or `candidate` status to `replan_required` instead of `blocked`
AND each such dependent SHALL record the failed item id in `blocked_by`
AND the failed item itself SHALL still be marked `failed`.

#### Scenario: Replan gate proceeds and emits a request
WHEN at least one item is in `replan_required` after a failure is recorded
AND `Gate.REPLAN_REQUIRED` evaluates to `proceed`
THEN the orchestrator SHALL write `<workspace>/replan-request.json` listing the `replan_required` item ids, the failed item id, and the gate decision
AND the run summary status SHALL be `replan_requested`
AND no item in `replan_required` SHALL be dispatched.

#### Scenario: Replan gate blocked leaves items parked
WHEN `Gate.REPLAN_REQUIRED` evaluates to `blocked` (posture `block`, timeout default block, or coordinator unreachable)
THEN no `replan-request.json` SHALL be written
AND the affected items SHALL remain `replan_required`
AND the decision SHALL be persisted in the checkpoint's `gate_decisions`
AND the orchestrator SHALL continue with other ready items.

#### Scenario: Orchestrator never performs the replan itself
WHEN a replan request is emitted
THEN `skills/autopilot-roadmap/scripts/` SHALL contain no import of an LLM SDK and no network call to perform re-decomposition
AND the host-assisted invariant test SHALL continue to pass.

### Requirement: Proposal Decomposition into Roadmap Changes

The system SHALL provide a `plan-roadmap` workflow that decomposes long markdown proposals into prioritized OpenSpec change candidates with explicit dependencies and acceptance outcomes. The workflow SHALL additionally provide a replan mode, `/plan-roadmap --replan <roadmap-id>`, driven by `<workspace>/replan-request.json`. In replan mode the deterministic helper `decomposer.py replan-scope <workspace>` SHALL emit the affected subgraph: every `replan_required` item plus its transitive non-completed dependents, and nothing else. The host SHALL re-decompose only that subgraph against the source proposal and the failed item's learning entry; items in `completed`, `superseded`, or `in_progress` status, and all existing `learnings/` entries, SHALL be preserved verbatim. On success the workflow SHALL set the re-decomposed items to `approved`, delete `replan-request.json`, and pass `decomposer.py validate`.

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
THEN the output SHALL list exactly `ri-04` and `ri-06` (and their non-completed transitive dependents)
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
