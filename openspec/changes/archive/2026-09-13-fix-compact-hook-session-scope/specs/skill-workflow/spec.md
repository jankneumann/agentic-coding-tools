## MODIFIED Requirements

### Requirement: Compact-Hook Phase-Boundary Gate on Applied Handoff

The `check_compact.py` Stop hook's phase-boundary detector (`_recent_phase_boundary()`) SHALL only treat a recently-modified handoff JSON as a phase-completion signal when that handoff has been recorded as the change's most-recently-applied phase outcome AND belongs to the session named in the hook payload.

The applied-handoff state is canonically captured by the orchestrator (e.g. autopilot's `apply-outcome` step) in `openspec/changes/<id>/loop-state.json` as the `last_handoff_id` field. The hook SHALL cross-reference handoff filenames against `last_handoff_id` before classifying them as boundaries.

A handoff belongs to the session when the most specific worktree root containing it is a worktree the session has worked in, per the `cwd` recorded on the session's transcript rows or the payload `cwd`, AND the handoff's change id appears in the session's transcript.

#### Scenario: Applied handoff inside the recent window triggers compaction

- **WHEN** a handoff JSON under `openspec/changes/<id>/handoffs/` has an mtime newer than `PHASE_BOUNDARY_WINDOW_SEC` (300s)
- **AND** the same change directory contains a `loop-state.json` whose `last_handoff_id` filename component matches the handoff filename
- **AND** the handoff belongs to the session in the hook payload
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

#### Scenario: Another session's applied handoff does not trigger compaction

- **WHEN** an applied handoff falls inside the recent window
- **AND** it lives in a worktree the session never worked in, OR its change id does not appear in the session's transcript
- **THEN** `_recent_phase_boundary()` SHALL skip that handoff
- **AND** a session that worked only in the main checkout SHALL NOT own handoffs in linked worktrees nested beneath it

#### Scenario: Session ownership is evaluated only for applied candidates

- **WHEN** no handoff passes the recency and applied-handoff gates
- **THEN** the hook SHALL NOT read the session transcript for the ownership check

## ADDED Requirements

### Requirement: Compact-Pending Flag Keyed on Session Identity

The compact hooks SHALL key the compact-pending flag file on an identity that the Stop and PreCompact hooks each derive from their own hook payload, so that one session's pending `/compact` request neither suppresses nor re-arms another session's triggers.

The identity SHALL be resolved in the order: hook-payload `session_id`, `SESSION_ID` environment variable, `AGENT_ID` environment variable, a hash of the payload `transcript_path`, and finally `unknown`. It SHALL be sanitized to be filesystem-safe.

#### Scenario: Flag named after the payload session id

- **WHEN** the Stop hook requests `/compact` and its payload carries `session_id` `S`
- **AND** `AGENT_ID` is unset
- **THEN** the hook SHALL create `~/.claude/compact-pending-S.flag`
- **AND** SHALL NOT create `compact-pending-unknown.flag`
- **AND** the block reason SHALL identify the session as `session=S`

#### Scenario: One session's flag does not suppress another session

- **WHEN** `compact-pending-A.flag` exists
- **AND** the Stop hook runs for session `B` above the threshold
- **THEN** the hook SHALL request `/compact` for session `B`

#### Scenario: PreCompact clears the flag its session's Stop hook created

- **WHEN** the Stop hook created the flag for session `S`
- **AND** the PreCompact hook runs with a payload carrying `session_id` `S`
- **THEN** the PreCompact hook SHALL remove that flag
- **AND** the next Stop above the threshold SHALL request `/compact` again

### Requirement: Pre-Compact Snapshot Uses Only the Session's Handoffs

The `precompact_handoff.py` hook SHALL build its pre-compact snapshot from the newest handoff that belongs to the session in its payload, using the same ownership rule as the phase-boundary detector.

#### Scenario: Another session's newer handoff is ignored

- **WHEN** the session owns handoff `H1`
- **AND** a newer handoff `H2` exists for a change the session never mentioned
- **THEN** the snapshot SHALL be built from `H1`
