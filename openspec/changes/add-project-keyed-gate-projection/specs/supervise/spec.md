## ADDED Requirements

### Requirement: Gate Projection Collector

The repository SHALL provide a deterministic command, `skills/supervise/scripts/gate_projection.py`, that builds a snapshot of the checkout's pending gates from `openspec/roadmaps/*/checkpoint.json`, `openspec/changes/*/loop-state.json` and `TRUST_POSTURE.md`. `collect` SHALL print the snapshot and `push` SHALL send it to the coordinator. The command MUST NOT modify any file in the repository.

#### Scenario: A parked dispatch attempt is collected
- **WHEN** a roadmap checkpoint holds a dispatch attempt with `status: parked` and a gate
- **THEN** the snapshot SHALL contain a gate with `source: checkpoint`, the roadmap id, the item id, the gate, the parked deadline and an `answer_hint`

#### Scenario: A loop-state pending gate is collected
- **WHEN** a change's `loop-state.json` holds a non-null `pending_gate`
- **THEN** the snapshot SHALL contain a gate with `source: loop_state`, the change id, the gate, the prompt and the loop's phase

#### Scenario: Resolved and unparked records are not collected
- **WHEN** a checkpoint holds only launched or completed attempts and a loop-state has a null `pending_gate`
- **THEN** the snapshot SHALL contain no gate for them

#### Scenario: Disposition comes from the trust posture
- **WHEN** `TRUST_POSTURE.md` gives a gate the disposition `notify_with_timeout`
- **THEN** the collected gate SHALL carry that disposition and its default action
- **AND** with no `TRUST_POSTURE.md` the collected gate SHALL carry `block`

#### Scenario: An unreadable source is reported, not fatal
- **WHEN** one gate file is not valid JSON
- **THEN** the snapshot SHALL name it in `source_errors`
- **AND** gates from the other files SHALL still be collected

#### Scenario: Collection is repeatable
- **WHEN** the command runs twice on an unchanged checkout
- **THEN** the two snapshots SHALL contain the same gate identifiers

#### Scenario: An approval link is carried
- **WHEN** the latest gate record for a parked attempt carries an `approval_id`
- **THEN** the collected gate SHALL carry that `approval_id`

#### Scenario: Push without a coordinator fails clearly
- **WHEN** `push` runs and no coordinator URL resolves
- **THEN** the command SHALL exit non-zero with a message and SHALL send nothing
