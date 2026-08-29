# supervise — delta

## ADDED Requirements

### Requirement: Supervisor Rehydration Record

The `/supervise` skill SHALL rehydrate a fresh session from a supervisor record with four sections — `active_changes`, `pending_gates`, `standing_decisions`, `back_edge` — conforming to `contracts/schemas/supervisor-record.schema.json`. The record SHALL be produced by the deterministic host-assisted command `cycle_state.py supervisor-record [--prior PATH] [--repo-root PATH]`, which SHALL derive `active_changes` from `openspec/changes/*/loop-state.json` and `openspec/roadmaps/*/roadmap.yaml` on every run and SHALL carry `pending_gates`, `standing_decisions`, and `back_edge` forward from the prior record. At the end of INTAKE and CYCLE the skill SHALL write the record to the coordinator handoff (`supervisor_record`) and SHALL write the three non-derivable sections to the tracked mirror `openspec/supervise/supervisor-record.json`. On rehydrate the skill SHALL read the most recent handoff via `try_handoff_read`; when the coordinator is unreachable, or the mirror's `written_at` is newer than the handoff's, it SHALL rehydrate from the mirror plus a fresh derivation and report `Degraded: handoff`.

#### Scenario: Fresh session lists state from the handoff alone
- **GIVEN** a handoff whose `supervisor_record` lists two active changes, one pending gate, and one standing decision
- **WHEN** a fresh `/supervise cycle` session rehydrates with no conversation context
- **THEN** its rehydrate output SHALL list both changes with their phases, the pending gate with its deadline, and the standing decision
- **AND** its "Needs a decision" section SHALL include the pending gate

#### Scenario: Builder is deterministic
- **WHEN** `cycle_state.py supervisor-record --prior P` runs twice over an unchanged tree
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
