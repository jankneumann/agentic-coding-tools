# Tasks — Fix Compact-Hook Session Scope

## 1. Shared session scope

- [x] 1.1 Add `skills/session-bootstrap/scripts/hooks/session_scope.py` with `session_key`, `flag_path`, `all_worktree_roots`, `owning_root`, `SessionScope`, `load_session_scope`.
- [x] 1.2 Key the flag on payload `session_id` first; sanitize the key for use as a filename.
- [x] 1.3 Resolve worktree ownership to the most specific root so nested `.git-worktrees/<id>` checkouts are not owned by main-checkout sessions.

## 2. Hooks

- [x] 2.1 `check_compact.py`: read the payload before the flag check; pass the payload to `_recent_phase_boundary`; apply the ownership check after the applied-handoff gate; report `session=<key>`.
- [x] 2.2 `precompact_handoff.py`: clear the payload-keyed flag; restrict `_latest_phase_record` to owned handoffs; report `session=<key>`.
- [x] 2.3 Remove the duplicated `_all_worktree_roots` implementations.

## 3. Tests

- [x] 3.1 Existing boundary tests pass a session payload.
- [x] 3.2 Regression: another session's applied handoff (unvisited worktree, unmentioned change, nested linked worktree) does not trigger.
- [x] 3.3 Regression: flag named after `session_id`, never `unknown` when a session id is present; one session's flag does not suppress another's.
- [x] 3.4 Round trip: Stop creates the flag, PreCompact with the same payload clears it, next Stop re-blocks.
- [x] 3.5 Transcript is not read when no applied candidate exists.
- [x] 3.6 PreCompact snapshot ignores another session's newer handoff.
- [x] 3.7 `skills/.venv/bin/python -m pytest skills/tests/session-bootstrap/` passes.
