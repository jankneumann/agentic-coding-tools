## MODIFIED Requirements

### Requirement: Compact-Hook Phase-Boundary Gate on Applied Handoff

The `check_compact.py` Stop hook's phase-boundary detector (`_recent_phase_boundary()`) SHALL only treat a recently-modified handoff JSON as a phase-completion signal when that handoff has been recorded as the change's most-recently-applied phase outcome AND belongs to the session named in the hook payload.

The applied-handoff state is canonically captured by the orchestrator (e.g. autopilot's `apply-outcome` step) in `openspec/changes/<id>/loop-state.json` as the `last_handoff_id` field. The hook SHALL cross-reference handoff filenames against `last_handoff_id` before classifying them as boundaries.

A handoff belongs to the session when the most specific worktree root containing it is a worktree the session has worked in, per the `cwd` recorded on the session's transcript rows or the payload `cwd`, AND the handoff's change id appears in the session's transcript.

#### Scenario: Applied handoff inside the recent window is a sync point

- **WHEN** a handoff JSON under `openspec/changes/<id>/handoffs/` has an mtime newer than `PHASE_BOUNDARY_WINDOW_SEC` (300s)
- **AND** the same change directory contains a `loop-state.json` whose `last_handoff_id` filename component matches the handoff filename
- **AND** the handoff belongs to the session in the hook payload
- **THEN** `_recent_phase_boundary()` SHALL return the handoff's phase name
- **AND** the boundary SHALL count as a natural sync point for the Sync-Point Compaction requirement
- **AND** the hook SHALL emit a `{"decision": "block", "reason": "..."}` JSON object requesting state capture only when the measured context is at or above the sync threshold

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

### Requirement: Sync-Point Compaction Measured on the Live Window

The `check_compact.py` Stop hook SHALL measure only the live context window: transcript rows after the last `compact_boundary` row, since the transcript file keeps every pre-compaction message. It SHALL request state capture at two points, both relative to `CLAUDE_CONTEXT_LIMIT` (default 1,000,000 tokens):

- **sync point**: the measured context is at or above `CLAUDE_COMPACT_SYNC_PCT` (default 15%) AND the turn reached a natural sync point, meaning an applied phase handoff owned by this session, or a turn that ran `git push`, merged a pull request, or opened one;
- **hard limit**: the measured context is at or above `CLAUDE_COMPACT_THRESHOLD_PCT` (default 20%), at any point.

The hook cannot start a compaction. Claude Code compacts at the `autoCompactWindow` set in the project `.claude/settings.json` (200,000 tokens), or on a typed `/compact`. The hook's reason SHALL therefore ask for state capture (commit and push what a fresh context needs) and SHALL NOT claim the agent can run `/compact` itself.

#### Scenario: Pre-compaction history is not counted

- **WHEN** the transcript holds a large pre-compaction history followed by a `compact_boundary` row and a small summary
- **THEN** the hook SHALL measure only the rows after the boundary
- **AND** SHALL NOT request state capture for a live window below the thresholds

#### Scenario: A sync point near the limit requests state capture

- **WHEN** the live window is at or above the sync threshold and below the hard limit
- **AND** the turn ran `git push`, merged a pull request, or applied an owned phase handoff
- **THEN** the hook SHALL emit a block decision naming the sync point and asking for state capture

#### Scenario: A sync point far from the limit does not interrupt

- **WHEN** the live window is below the sync threshold
- **THEN** the hook SHALL NOT emit a decision, even at an applied phase boundary

#### Scenario: No sync point waits for the hard limit

- **WHEN** the live window is at or above the sync threshold and below the hard limit
- **AND** the turn performed no sync action
- **THEN** the hook SHALL NOT emit a decision
