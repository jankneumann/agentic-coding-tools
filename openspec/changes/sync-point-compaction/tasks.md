# Tasks

## 1. Hook

- [x] 1.1 Measure only transcript rows after the last `compact_boundary`
- [x] 1.2 Gate phase-boundary and push/merge/PR sync points on `CLAUDE_COMPACT_SYNC_PCT` (default 15%); hard limit `CLAUDE_COMPACT_THRESHOLD_PCT` default 20%
- [x] 1.3 Reason asks for state capture; it no longer tells the agent to run `/compact`

## 2. Settings

- [x] 2.1 `autoCompactWindow: 200000` in `.claude/settings.json`

## 3. Tests

- [x] 3.1 Live-window measurement, sync point near/far from the limit, push and merge sync actions, no-sync-action turn (`skills/tests/session-bootstrap/test_check_compact.py`)
