# supervise Specification

## Purpose
TBD - created by archiving change extend-handoff-document-with-supervisor-record. Update Purpose after archive.
## Requirements
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
- **AND** `gate` SHALL be one of the eight `trust_posture.Gate` values

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

The supervise skill SHALL expose an execution path that drives an operator-approved roadmap through the separate delegated prepare/apply entry points and their existing synchronous `dispatch_fn` normalization seam without requiring per-item approval.

#### Scenario: Execute an inherited-approved roadmap
- **WHEN** the operator invokes `/autopilot-roadmap` or approves a roadmap batch from `/supervise`
- **THEN** the supervisor supplies the delegated dispatch callback and exact roadmap item `change_id` values
- **AND** execution continues through ready items without new discovery, direction, or per-item plan questions

#### Scenario: Refuse unapproved roadmap execution
- **WHEN** no durable roadmap-altitude approval can be established
- **THEN** the supervisor does not dispatch an implementation agent
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

### Requirement: Router-Neutral Supervisor Dispatch

The supervise skill SHALL pass through router-owned dispatch context and SHALL NOT select or override the vendor, model, location, or cost-policy decision itself.

#### Scenario: Preserve routed context
- **WHEN** the roadmap orchestrator supplies router decision fields in dispatch context
- **THEN** the supervisor forwards those fields unchanged to the background dispatch boundary
- **AND** the recorded result remains correlated to the original dispatch identifier

#### Scenario: Router context is unavailable
- **WHEN** no router decision is present
- **THEN** the supervisor uses the existing archetype/provider resolution path
- **AND** it does not invent a vendor preference or widen the item scope

#### Scenario: Reject unsafe additive context
- **WHEN** dispatch context contains a secret-like or token key, raw response or transcript content, nesting deeper than four levels, or canonical JSON larger than 16 KiB
- **THEN** preparation fails before persistence or dispatch with a bounded deterministic reason
- **AND** valid bounded router-owned fields pass through unchanged
