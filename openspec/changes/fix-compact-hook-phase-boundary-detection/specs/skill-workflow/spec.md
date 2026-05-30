## ADDED Requirements

### Requirement: Compact-Hook Phase-Boundary Gate on Applied Handoff

The `check_compact.py` Stop hook's phase-boundary detector (`_recent_phase_boundary()`) SHALL only treat a recently-modified handoff JSON as a phase-completion signal when that handoff has been recorded as the change's most-recently-applied phase outcome.

The applied-handoff state is canonically captured by the orchestrator (e.g. autopilot's `apply-outcome` step) in `openspec/changes/<id>/loop-state.json` as the `last_handoff_id` field. The hook SHALL cross-reference handoff filenames against `last_handoff_id` before classifying them as boundaries.

#### Scenario: Applied handoff inside the recent window triggers compaction

- **WHEN** a handoff JSON under `openspec/changes/<id>/handoffs/` has an mtime newer than `PHASE_BOUNDARY_WINDOW_SEC` (300s)
- **AND** the same change directory contains a `loop-state.json` whose `last_handoff_id` filename component matches the handoff filename
- **THEN** `_recent_phase_boundary()` SHALL return the handoff's phase name
- **AND** the hook SHALL emit a `{"decision": "block", "reason": "..."}` JSON object requesting `/compact`

#### Scenario: Unapplied handoff inside the recent window does not trigger compaction

- **WHEN** a handoff JSON has an mtime newer than the boundary window
- **AND** the change's `loop-state.json` exists but `last_handoff_id` does NOT match the handoff filename
- **THEN** `_recent_phase_boundary()` SHALL skip that handoff
- **AND** the hook SHALL NOT request `/compact` based on that handoff
- **AND** any other applied handoffs in the window MAY still trigger compaction

#### Scenario: Missing or malformed loop-state defers compaction

- **WHEN** a handoff JSON has an mtime newer than the boundary window
- **AND** the change directory has no `loop-state.json`, OR the file exists but fails JSON decode
- **THEN** `_recent_phase_boundary()` SHALL skip that handoff
- **AND** the hook SHALL fail closed — no phase-boundary `/compact` request based on that handoff
- **AND** the threshold-based trigger SHALL continue to operate independently

#### Scenario: `last_handoff_id` absent or null in loop-state

- **WHEN** `loop-state.json` exists but the `last_handoff_id` field is missing, `null`, or an empty string
- **THEN** `_recent_phase_boundary()` SHALL treat the change as having no applied handoff
- **AND** SHALL NOT classify any handoff in the window as a boundary

#### Scenario: Sibling worktrees write unrelated handoffs

- **WHEN** the hook globs handoff files across all worktrees known to the current repository
- **AND** a handoff from a sibling worktree falls inside the recent window but does not match its own change's `last_handoff_id`
- **THEN** that handoff SHALL NOT propagate as a boundary signal into the current session
