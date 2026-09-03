## MODIFIED Requirements

### Requirement: Supervisor Rehydration Record

The `/supervise` skill SHALL rehydrate a fresh session from a supervisor record with four sections — `active_changes`, `pending_gates`, `standing_decisions`, `back_edge` — conforming to `contracts/schemas/supervisor-record.schema.json`. The full record SHALL validate against the canonical `openspec/schemas/supervisor-record.schema.json`, and the mirror SHALL validate against `openspec/schemas/supervisor-record-mirror.schema.json`. The record SHALL be produced by the deterministic host-assisted command `cycle_state.py supervisor-record [--prior PATH] [--repo-root PATH] [--now RFC3339]`, which SHALL derive `active_changes` from `openspec/changes/*/loop-state.json` and `openspec/roadmaps/*/roadmap.yaml` on every run and SHALL carry `pending_gates`, `standing_decisions`, and `back_edge` forward from the prior record. At the end of INTAKE and non-dry-run CYCLE the skill SHALL write the record to the coordinator handoff (`supervisor_record`) and SHALL write the three non-derivable sections to the tracked mirror `openspec/supervise/supervisor-record.json`. On rehydrate the skill SHALL read the most recent handoff via `try_handoff_read(supervisor_only=true)`; when the coordinator is unreachable, or the mirror's `written_at` is newer than the handoff's, it SHALL rehydrate from the mirror plus a fresh derivation and report `Degraded: handoff`.

#### Scenario: Fresh session restores durable state and re-derives active changes
- **GIVEN** repository loop state lists two active changes
- **AND** the newest handoff `supervisor_record` carries one pending gate and one standing decision
- **WHEN** a fresh `/supervise cycle` session rehydrates with no conversation context
- **THEN** its rehydrate output SHALL list both freshly derived changes with their phases, the pending gate with its deadline, and the standing decision
- **AND** its "Needs a decision" section SHALL include the pending gate

#### Scenario: Builder is deterministic
- **WHEN** `cycle_state.py supervisor-record --prior P --now T` runs twice over an unchanged tree with the same T
- **THEN** the two outputs SHALL be byte-identical
- **AND** `active_changes` SHALL be sorted by `change_id`

#### Scenario: Derivable section is recomputed, not carried
- **GIVEN** a prior record whose `active_changes` lists change X at `PLAN`
- **AND** `openspec/changes/X/loop-state.json` now reads `current_phase: IMPLEMENT`
- **WHEN** the builder runs
- **THEN** the output SHALL list X at `IMPLEMENT`
- **AND** a change present in the prior record but no longer under `openspec/changes/` SHALL be absent

#### Scenario: Non-derivable sections are carried forward
- **GIVEN** a prior record with a standing decision and a pending gate
- **WHEN** the builder runs with no new inputs
- **THEN** both SHALL appear unchanged in the output
- **AND** a standing decision whose `expires_at` is in the past SHALL be dropped

#### Scenario: Mirror holds only the non-derivable sections
- **WHEN** the skill writes `openspec/supervise/supervisor-record.json`
- **THEN** the file SHALL contain `schema_version`, `written_at`, `pending_gates`, `standing_decisions`, `back_edge`
- **AND** it SHALL NOT contain `active_changes`
- **AND** the write SHALL pass `cycle_state.py audit-writes`

#### Scenario: Coordinator unreachable falls back to the mirror
- **GIVEN** `try_handoff_read` reports the coordinator unreachable
- **AND** a mirror file exists
- **WHEN** the session rehydrates
- **THEN** the record SHALL be built from the mirror plus a fresh derivation
- **AND** the digest SHALL list `Degraded: handoff`

#### Scenario: Newer mirror wins over a stale handoff
- **GIVEN** a handoff `supervisor_record` written at T1 and a mirror written at T2 > T1
- **WHEN** the session rehydrates
- **THEN** the non-derivable sections SHALL come from the mirror

#### Scenario: Pending gate carries the deadline downstream writers need
- **WHEN** a `pending_gates[]` entry is validated against the record schema
- **THEN** `gate`, `change_id`, `requested_at`, and `deadline` SHALL be required
- **AND** `gate` SHALL be one of the nine `trust_posture.Gate` values, including `roadmap_approval`
- **AND** an entry written by the supervise gate router SHALL carry `decision_id`, `disposition`, and `source: "supervise"`

#### Scenario: Newer ordinary handoff does not mask supervisor state
- **GIVEN** a supervisor handoff followed by a newer ordinary handoff
- **WHEN** `/supervise` rehydrates with `supervisor_only=true`
- **THEN** it SHALL restore the supervisor handoff

#### Scenario: Mirror write preserves unchanged-cycle idempotency
- **GIVEN** a completed cycle has written the mirror and ledger
- **WHEN** the next cycle runs with no other repository or durable-record change
- **THEN** `write_mirror` SHALL be a no-op that preserves `written_at`
- **AND** the cycle fingerprint SHALL be unchanged

#### Scenario: Dry-run writes no supervisor state
- **WHEN** `/supervise cycle --dry-run` completes
- **THEN** neither the mirror nor a supervisor handoff SHALL be written
- **AND** in a non-dry-run cycle the mirror write SHALL occur before the final write audit

#### Scenario: Active-change derivation handles invalid and terminal state
- **GIVEN** change directories in DONE, ESCALATE, malformed, and missing-loop-state conditions
- **WHEN** active changes are derived
- **THEN** DONE, malformed, and missing-state changes SHALL be absent
- **AND** ESCALATE SHALL remain active
- **AND** malformed or ambiguous roadmap/registry inputs SHALL be reported as degraded

### Requirement: Approved Roadmap Execution

The supervise skill SHALL expose an execution path that drives an operator-approved roadmap through the separate delegated prepare/apply entry points and their existing synchronous `dispatch_fn` normalization seam without requiring per-item approval. Roadmap-altitude approval SHALL be a `roadmap_approval` gate decision with outcome `proceed` recorded in the roadmap workspace's `checkpoint.json` `gate_decisions` ledger, and `ExecutionAdapter.prepare` SHALL require a `roadmap_approval_ref` of the form `gate-decision:<decision_id>` that resolves to that record.

#### Scenario: Execute an inherited-approved roadmap
- **WHEN** the operator invokes `/autopilot-roadmap` or approves a roadmap batch from `/supervise`
- **THEN** a `roadmap_approval` gate decision with outcome `proceed` is recorded through the gate router before any dispatch (auto under an `auto` posture, coordinator-approved under `notify_with_timeout`, or console-approved via `cycle_state.py gate-answer`)
- **AND** the supervisor supplies the delegated dispatch callback, the resulting `roadmap_approval_ref`, and exact roadmap item `change_id` values
- **AND** execution continues through ready items without new discovery, direction, or per-item plan questions

#### Scenario: Refuse unapproved roadmap execution
- **WHEN** no `roadmap_approval_ref` is supplied, or the supplied reference does not resolve to a `proceed` decision for that roadmap
- **THEN** `ExecutionAdapter.prepare` raises before writing any attempt and the supervisor does not dispatch an implementation agent
- **AND** it reports the missing approval without mutating roadmap execution state

### Requirement: Background Worktree Isolation

The supervise skill MUST start each delegated Autopilot item as a background sub-agent in a distinct managed worktree and MUST retain only its structured outcome and handoff identifier.

#### Scenario: Run two disjoint changes in parallel
- **WHEN** the delegated batch contains two disjoint changes
- **THEN** the host starts both `/autopilot <change-id>` agents in the background with distinct worktree paths and branches
- **AND** the supervisor context after collection contains both outcomes but no child transcript

#### Scenario: Child dispatch cannot prove isolation
- **WHEN** worktree setup or path/branch verification fails for a selected item
- **THEN** that item returns a failed dispatch outcome before `/autopilot` begins
- **AND** other independently isolated batch members may complete without sharing the failed worktree

#### Scenario: Child parks at a pending gate
- **WHEN** a background Autopilot child reaches a pending gate or policy pause
- **THEN** the host returns a parked result containing the bounded gate or pause snapshot
- **AND** success and parked results include worktree path, branch, and loop-state evidence that exactly match the prepared attempt
- **AND** the supervisor retains the next action without retaining the child transcript or marking the item failed
- **AND** the supervisor resolves the parked gate only through `gate_router.resolve_parked`, which records a gate decision and either resumes the attempt with `approval_ref = gate-decision:<decision_id>` or surfaces the gate in `pending_gates` with its disposition, approval id, and deadline

## ADDED Requirements

### Requirement: Supervise Gate Routing

The supervise skill SHALL evaluate every gate it raises — `roadmap_approval` at the end of `cycle`, the `execute` precondition, and the resolution of parked `pending_gate` and `policy_pause` attempts — exclusively through `skills/supervise/scripts/gate_router.py`, which SHALL call `shared.approval_gate.ApprovalGate.evaluate` against the repository's `TRUST_POSTURE.md` and SHALL append a `gate-decision.schema.json` record carrying `decision_id`, `source: "supervise"`, `roadmap_id`, and any correlating `change_id` / `dispatch_id` to the roadmap workspace's `checkpoint.json` `gate_decisions` ledger before acting on the decision. Records SHALL be built with `shared.approval_gate.build_gate_decision_record` and console answers with `shared.approval_gate.console_decision`; the router SHALL NOT import `autopilot.py`. Before evaluating, the router SHALL apply a prior-record rule to the ledger keyed by the decision's subject (`gate`, `roadmap_id`, and `dispatch_id` for parked attempts or `roadmap_fingerprint` for `roadmap_approval`): a `proceed` record is reused without evaluating; an open `posture_block` record is re-surfaced unchanged unless the posture's disposition for that gate changed; a blocked record carrying an `approval_id` is checked through `ApprovalGate.check_filed` before any new approval is filed; a `rejected` or `console_rejected` record is terminal until the subject changes or a console answer is recorded. No other module under `skills/supervise/scripts/` SHALL import or call the approval gate. `cycle_state.py` SHALL expose `gate-check`, `gate-answer`, and `gate-log` subcommands and SHALL import the `Gate` and `Disposition` enums from `shared.trust_posture` rather than duplicating them. `gate-answer` SHALL require a prior parked record for every gate except `roadmap_approval`, whose console answer MAY originate a record. The router SHALL project every blocked decision into the tracked mirror's `pending_gates` (keyed by `decision_id`) and every `proceed` decision out of it — upserting the `roadmap_approval` standing decision — through `cycle_state.write_mirror`, and a reused decision SHALL leave the mirror untouched. `gate-check` SHALL NOT run under `cycle --dry-run`, and `execute` SHALL begin with `gate-check`, whose exit-3 record supplies the `roadmap_approval_ref`. `skills/supervise/SKILL.md` SHALL contain no gate whose only enforcement is prose.

#### Scenario: Auto posture takes a conversation to execution without a human touch
- **GIVEN** a `TRUST_POSTURE.md` with `roadmap_approval: auto`
- **WHEN** `cycle_state.py gate-check --roadmap R` runs after the digest
- **THEN** it records a `roadmap_approval` decision with resolution `auto` and exits 3
- **AND** the skill proceeds into `/plan-roadmap` approval and `execute` without asking the operator

#### Scenario: Block posture parks the roadmap approval for a console answer
- **GIVEN** no `TRUST_POSTURE.md` (or `roadmap_approval: block`)
- **WHEN** `gate-check --roadmap R` runs
- **THEN** it records a `posture_block` decision, prints a `pending_gates` entry with `gate: roadmap_approval`, a deadline, and `source: supervise`, and exits 0
- **AND** `gate-answer --roadmap R --gate roadmap_approval --decision approved` records a `console_approved` decision, mirrors it into `standing_decisions`, and prints the `roadmap_approval_ref`

#### Scenario: Notify posture waits for the posture timeout and honours a late answer without re-filing
- **GIVEN** `roadmap_approval: notify_with_timeout` with `timeout_seconds: T` and `default_action: block`, and a reachable coordinator that leaves the approval unanswered
- **WHEN** `gate-check --roadmap R` runs
- **THEN** it files exactly one approval request, waits no longer than T, records a `timeout_default_block` decision carrying the `approval_id`, prints a `pending_gates` entry whose `deadline` is `requested_at + T`, and exits 4
- **AND** when the operator approves that request in the coordinator after the timeout and the next `gate-check --roadmap R` runs, the router calls `ApprovalGate.check_filed` with the recorded `approval_id`, records an `approved` decision with outcome `proceed`, files no second request, and exits 3
- **AND** when the coordinator still reports the request `pending`, the second run re-surfaces the same entry and deadline and files nothing

#### Scenario: Approved roadmap is not re-asked until its DAG changes
- **GIVEN** a `proceed` `roadmap_approval` record for roadmap R whose `roadmap_fingerprint` matches R's current sorted `(item_id, change_id, depends_on)` tuples
- **WHEN** `gate-check --roadmap R` runs again after an item of R completes
- **THEN** it reuses the existing record, appends nothing to the ledger, prints the reused record, and exits 3
- **AND** when `refine-roadmap` adds or splits an item so the fingerprint changes, the next `gate-check` evaluates `roadmap_approval` anew

#### Scenario: Direct invocation records an originating console decision
- **WHEN** `/autopilot-roadmap` is invoked directly and runs `gate-answer --roadmap R --gate roadmap_approval --decision approved --note "direct invocation"` with no prior parked record
- **THEN** a `console_approved` `roadmap_approval` decision with outcome `proceed` is recorded, its posture snapshot taken from the live posture, and `roadmap_approval_ref` is printed
- **AND** `gate-answer --gate pr_creation` for a dispatch with no parked record is refused without recording anything

#### Scenario: Parked child unparks after a posture flip
- **GIVEN** a `pending_gate` attempt parked on `pr_creation` under `block`
- **WHEN** the operator edits `TRUST_POSTURE.md` to `pr_creation: auto` and the supervisor runs `resolve_parked`
- **THEN** the router records an `auto` decision and calls `ExecutionAdapter.resume` with `approval_ref = gate-decision:<decision_id>`
- **AND** no console answer is required

#### Scenario: Policy pause resolves through escalate_resume
- **WHEN** a `policy_pause` attempt (child in `ESCALATE`) is resolved
- **THEN** the router evaluates `Gate.ESCALATE_RESUME`, not a new gate
- **AND** a `BLOCKED` decision leaves the attempt parked and surfaces `escalate_resume` in `pending_gates`

#### Scenario: Evaluation log covers every supervised gate
- **WHEN** a full simulated run (cycle → execute → parked child → resume) completes and `cycle_state.py gate-log --roadmap R` runs
- **THEN** the output lists one record per `ApprovalGate.evaluate`, `check_filed` decision, or console answer made by the supervisor — and none for a reused or re-surfaced record — plus the `loop-state.json` `gate_decisions` of every change named by R's items, each with the posture disposition that was applied and its origin
- **AND** every `approval_ref` used during the run resolves to one of those records

#### Scenario: Router is the only seam
- **WHEN** the test scans `skills/supervise/scripts/*.py` by AST
- **THEN** `ApprovalGate`, `build_default_gate`, `check_filed`, and `.evaluate(` appear only in `gate_router.py`
- **AND** no module under `skills/supervise/scripts/` imports `autopilot`

#### Scenario: Unknown parked gate is a schema error, not a decision
- **WHEN** a parked snapshot names a gate outside `trust_posture.Gate`
- **THEN** `resolve_parked` raises without recording a decision or resuming
- **AND** the attempt stays parked

#### Scenario: Router projects gate state into the mirror a fresh session rehydrates
- **GIVEN** no `TRUST_POSTURE.md` and a handoff `supervisor_record` written at T1
- **WHEN** `gate-check --roadmap R` parks `roadmap_approval` at T2 > T1 and a fresh session runs `cycle_state.py rehydrate`
- **THEN** the rehydrated record's `pending_gates` contains the entry with that `decision_id`, `disposition: block`, `source: supervise`, and a deadline, sourced from the mirror
- **AND** after `gate-answer --roadmap R --gate roadmap_approval --decision approved` the next rehydrate shows no such entry and a standing decision `roadmap_approval:proceed` scoped to R
- **AND** a subsequent `gate-check --roadmap R` that reuses the decision leaves the mirror's `written_at` unchanged
