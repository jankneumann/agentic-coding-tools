# Tasks: add-phase-session-logs

## 1. Refactor session-log infrastructure skill

- [x] 1.1 Refactor `extract_session_log.py`: remove Tier 1 (JSONL transcript parsing — `try_extract_claude_transcript`, `_parse_jsonl_messages`, `_format_transcript_as_session_log`) and Tier 2 (handoff compilation — `try_extract_from_handoffs`, `_format_handoffs_as_session_log`) and the 3-tier `main()` CLI. Add `append_phase_entry(change_id, phase_name, content, session_log_path)` and `append_merge_entry(date, content, merge_log_path)` functions that handle: file creation with header, phase section appending with `---` separator, directory creation via `mkdir -p`, and iteration number auto-increment (count existing `## Phase: <prefix>` headers in the file + 1). Keep `generate_self_summary_prompt()` as a callable utility (agents may use it to structure their phase entries, but it is not required).
  **Dependencies**: None
  **Files**: `skills/session-log/scripts/extract_session_log.py`

- [x] 1.2 Update `session-log/SKILL.md` to document the new append-based pattern, phase entry template (with concrete section names: Decisions, Alternatives Considered, Trade-offs, Open Questions, Context), merge-log format, sanitize-then-verify flow with verification checklist, and in-place sanitization usage. Remove references to 3-tier extraction.
  **Dependencies**: 1.1
  **Files**: `skills/session-log/SKILL.md`

- [x] 1.3 Update tests in `test_extract_session_log.py`: add tests for `append_phase_entry()` (file creation, append-to-existing, header initialization, `---` separator, directory creation), `append_merge_entry()` (dated file creation, append-to-existing, session timestamp), and iteration number auto-increment (counting existing entries, first iteration = 1). Remove tests for retired Tier 1/2 functions.
  **Dependencies**: 1.1
  **Files**: `skills/session-log/scripts/test_extract_session_log.py`

## 2. Integrate session-log into planning skills

- [x] 2.1 Add session-log append step to `plan-feature/SKILL.md` — insert before Step 9 (Present for Approval). Include session-log.md in the Step 8 `git add` commit. Agent writes `Plan` phase entry with architecture decisions, scope choices, tier selection rationale. Include the phase entry template and sanitize-then-verify instructions with verification checklist.
  **Dependencies**: 1.1
  **Files**: `skills/plan-feature/SKILL.md`

- [x] 2.2 Add session-log append step to `iterate-on-plan/SKILL.md` — before the existing iteration commit step (Step 9). Agent writes `Plan Iteration <N>` phase entry (auto-increment N by counting existing "Plan Iteration" entries in session-log.md + 1) with what changed and why. Include session-log.md in the existing `git add openspec/changes/$CHANGE_ID/` commit.
  **Dependencies**: 1.1
  **Files**: `skills/iterate-on-plan/SKILL.md`

## 3. Integrate session-log into implementation skills

- [x] 3.1 Add session-log append step to `implement-feature/SKILL.md` — insert before Step 9 (Push and Create PR). Include session-log.md in the PR commit. Agent writes `Implementation` phase entry with approach, deviations from plan, and issues encountered.
  **Dependencies**: 1.1
  **Files**: `skills/implement-feature/SKILL.md`

- [x] 3.2 Add session-log append step to `iterate-on-implementation/SKILL.md` — before the existing iteration commit step. Agent writes `Implementation Iteration <N>` phase entry (auto-increment N) with review findings addressed and changes made. Include session-log.md in the existing `git add .` commit.
  **Dependencies**: 1.1
  **Files**: `skills/iterate-on-implementation/SKILL.md`

## 4. Integrate session-log into validation and cleanup skills

- [x] 4.1 Add session-log append step to `validate-feature/SKILL.md` — new final step after Step 13 (PR Comment). Agent writes `Validation` phase entry with results summary, waivers, and deferred issues. Commit session-log.md and push.
  **Dependencies**: 1.1
  **Files**: `skills/validate-feature/SKILL.md`

- [x] 4.2 Replace existing Step 5b in `cleanup-feature/SKILL.md` with the new append pattern. Agent writes `Cleanup` phase entry with merge strategy, open task migration decisions. Remove calls to `extract_session_log.py` extraction tiers. Keep sanitization step. Add scenario for cleanup without prior session-log (create file and summarize change from context).
  **Dependencies**: 1.1
  **Files**: `skills/cleanup-feature/SKILL.md`

## 5. Add merge-log to merge-pull-requests

- [x] 5.1 Add merge-log step to `merge-pull-requests/SKILL.md` — new final step after Step 12 (Summary). Agent writes to `docs/merge-logs/YYYY-MM-DD.md` with session timestamp (HH:MM), agent type, PR triage table (PR number, origin, action, rationale), vendor review findings, user decisions, and observations. Create `docs/merge-logs/` directory (with `.gitkeep`) if it doesn't exist. Run sanitization and verify. Commit and push.
  **Dependencies**: 1.1
  **Files**: `skills/merge-pull-requests/SKILL.md`, `docs/merge-logs/.gitkeep`

## 6. Testing and validation

- [x] 6.1 Add sanitizer regression tests for merge-log payloads: test `sanitize_session_log.py` with representative merge-log content containing PR comments, vendor-review text, user-provided content, and mixed secret patterns. Also add an explicit in-place operation test (same path for input and output). Keep existing tests for `generate_self_summary_prompt()`.
  **Dependencies**: 1.1
  **Files**: `skills/session-log/scripts/test_sanitize_session_log.py`

- [x] 6.2 Run `skills/.venv/bin/python -m pytest skills/session-log/scripts/` to verify all session-log tests pass (both extract and sanitize).
  **Dependencies**: 1.3, 6.1
  **Files**: N/A

- [x] 6.3 Run `openspec validate add-phase-session-logs --strict` and fix any issues.
  **Dependencies**: 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 5.1
  **Files**: N/A
