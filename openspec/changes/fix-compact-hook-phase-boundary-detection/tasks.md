# Tasks — Fix Compact-Hook Phase-Boundary Detection

## 1. Implement the cross-reference gate

- [ ] 1.1 In `skills/session-bootstrap/scripts/hooks/check_compact.py`, modify `_recent_phase_boundary()` to read `openspec/changes/<id>/loop-state.json` for each candidate handoff and skip when the filename does not match `last_handoff_id`.
- [ ] 1.2 Treat missing or malformed `loop-state.json` as "no boundary signal" (fail closed).
- [ ] 1.3 Treat missing/null/empty `last_handoff_id` as "no applied handoff" — no boundary signal.
- [ ] 1.4 Use `endswith(basename)` comparison since `last_handoff_id` is stored as a repo-relative path while `p` may resolve differently across worktree roots.
- [ ] 1.5 Verify the change does not regress the threshold-based trigger by reading the surrounding `main()` flow — the gate only affects `_recent_phase_boundary()`.

## 2. Add unit tests

- [ ] 2.1 Create `skills/tests/session-bootstrap/test_check_compact_phase_boundary.py`.
- [ ] 2.2 Add `test_applied_handoff_triggers_boundary` — fresh handoff matches `last_handoff_id` → returns phase name.
- [ ] 2.3 Add `test_unapplied_handoff_does_not_trigger` — fresh sub-agent handoff, but `last_handoff_id` points elsewhere → returns `None`.
- [ ] 2.4 Add `test_stale_mtime_touch_ignored` — old archived handoff has fresh mtime, but `last_handoff_id` points at a different (also-fresh) applied handoff → returns the applied one's phase, not the stale one.
- [ ] 2.5 Add `test_missing_loop_state_fails_closed` — fresh handoff, no `loop-state.json` → returns `None`.
- [ ] 2.6 Add `test_malformed_loop_state_fails_closed` — fresh handoff, `loop-state.json` contains non-JSON text → returns `None`.
- [ ] 2.7 Add `test_outside_window` — handoff matches `last_handoff_id` but mtime is older than 300s → returns `None`.
- [ ] 2.8 Add `test_null_last_handoff_id` — `loop-state.json` exists with `last_handoff_id: null` → returns `None`.
- [ ] 2.9 Add `test_sibling_worktree_handoff_isolated` — fake two worktree roots; sibling has fresh handoff that doesn't match its own loop-state → does not propagate to the current session's boundary.

## 3. Run tests and verify no regressions

- [ ] 3.1 Run `skills/.venv/bin/python -m pytest skills/tests/session-bootstrap/ -v`. All new tests pass.
- [ ] 3.2 Run any existing session-bootstrap tests to ensure no regressions: `skills/.venv/bin/python -m pytest skills/tests/session-bootstrap/ -v --collect-only` first to inventory, then `-v` to execute.
- [ ] 3.3 Manually exercise the hook end-to-end with a synthetic stdin payload:
  ```bash
  echo '{"session_id":"test","transcript_path":"/dev/null","hook_event_name":"Stop"}' | \
    python3 skills/session-bootstrap/scripts/hooks/check_compact.py
  ```
  Confirm exit code 0 and no `decision: block` JSON when no qualifying handoff exists.

## 4. Sync runtime mirrors

- [ ] 4.1 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` from the repo root to propagate the fix to `.claude/skills/session-bootstrap/` and `.agents/skills/session-bootstrap/`.
- [ ] 4.2 Verify the runtime copies got the new logic: `diff skills/session-bootstrap/scripts/hooks/check_compact.py .claude/skills/session-bootstrap/scripts/hooks/check_compact.py` — should be byte-identical.

## 5. Validate

- [ ] 5.1 Run `openspec validate fix-compact-hook-phase-boundary-detection --strict`. Must pass.
- [ ] 5.2 Confirm the change has a single ADDED requirement under `skill-workflow` capability.

## 6. Commit and push

- [ ] 6.1 Commit on `openspec/fix-compact-hook-phase-boundary-detection` with subject `fix(session-bootstrap): gate compact-hook boundary detection on applied handoff` and reference this change-id in the body.
- [ ] 6.2 Push to origin.
- [ ] 6.3 (Out of scope for this change — done after merge to main:) update `docs/lessons-learned.md` if the gate semantics surface as a recurring debugging touchstone.

## 7. Manual verification

- [ ] 7.1 Confirm by inspection of `loop-state.json` from a recent autopilot run that `last_handoff_id` is updated at the moments the hook should fire — proving the gate aligns with reality. Reference data: `openspec/changes/extract-gen-eval-package/loop-state.json` (existing autopilot loop, contains `last_handoff_id: "openspec/changes/extract-gen-eval-package/handoffs/plan_review-3.json"`).
