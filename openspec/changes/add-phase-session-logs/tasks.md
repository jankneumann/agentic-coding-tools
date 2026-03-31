# Tasks: add-phase-session-logs

## 1. Refactor session-log infrastructure skill

- [ ] 1.1 Refactor `extract_session_log.py`: remove Tier 1 (JSONL transcript) and Tier 2 (handoff compilation) extraction. Add `append_phase_entry()` and `append_merge_entry()` functions that handle file creation, header initialization, phase section appending, and separator insertion.
  **Dependencies**: None
  **Files**: `skills/session-log/scripts/extract_session_log.py`

- [ ] 1.2 Update `session-log/SKILL.md` to document the new append-based pattern, phase entry template, merge-log format, and sanitize-then-verify flow. Remove references to 3-tier extraction.
  **Dependencies**: 1.1
  **Files**: `skills/session-log/SKILL.md`

- [ ] 1.3 Update tests in `test_extract_session_log.py` to cover `append_phase_entry()`, `append_merge_entry()`, file creation, append-to-existing, and header initialization. Remove tests for retired Tier 1/2 functions.
  **Dependencies**: 1.1
  **Files**: `skills/session-log/scripts/test_extract_session_log.py`

## 2. Integrate session-log into planning skills

- [ ] 2.1 Add session-log append step to `plan-feature/SKILL.md` — insert before Step 9 (Present for Approval). Include session-log.md in the Step 8 commit. Agent writes Plan phase entry with architecture decisions, scope choices, and tier selection rationale.
  **Dependencies**: 1.1, 1.2
  **Files**: `skills/plan-feature/SKILL.md`

- [ ] 2.2 Add session-log append step to `iterate-on-plan/SKILL.md` — new final step after Step 11 (Present Summary). Agent writes Plan Iteration phase entry with what changed and why. Commit and push.
  **Dependencies**: 1.1, 1.2
  **Files**: `skills/iterate-on-plan/SKILL.md`

## 3. Integrate session-log into implementation skills

- [ ] 3.1 Add session-log append step to `implement-feature/SKILL.md` — insert before Step 9 (Push and Create PR). Include session-log.md in the PR commit. Agent writes Implementation phase entry with approach, deviations from plan, and issues encountered.
  **Dependencies**: 1.1, 1.2
  **Files**: `skills/implement-feature/SKILL.md`

- [ ] 3.2 Add session-log append step to `iterate-on-implementation/SKILL.md` — new final step after Step 12 (Present Summary). Agent writes Implementation Iteration phase entry with review findings addressed and changes made. Commit and push.
  **Dependencies**: 1.1, 1.2
  **Files**: `skills/iterate-on-implementation/SKILL.md`

## 4. Integrate session-log into validation and cleanup skills

- [ ] 4.1 Add session-log append step to `validate-feature/SKILL.md` — new final step after Step 13 (PR Comment). Agent writes Validation phase entry with results summary, waivers, and deferred issues. Commit and push.
  **Dependencies**: 1.1, 1.2
  **Files**: `skills/validate-feature/SKILL.md`

- [ ] 4.2 Replace existing Step 5b in `cleanup-feature/SKILL.md` with the new append pattern. Agent writes Cleanup phase entry with merge strategy, open task migration decisions. Remove calls to `extract_session_log.py` extraction tiers. Keep sanitization step.
  **Dependencies**: 1.1, 1.2
  **Files**: `skills/cleanup-feature/SKILL.md`

## 5. Add merge-log to merge-pull-requests

- [ ] 5.1 Add merge-log step to `merge-pull-requests/SKILL.md` — new final step after Step 12 (Summary). Agent writes to `docs/merge-logs/YYYY-MM-DD.md` with PR triage table, vendor review findings, user decisions, and observations. Run sanitization. Commit and push.
  **Dependencies**: 1.1, 1.2
  **Files**: `skills/merge-pull-requests/SKILL.md`

- [ ] 5.2 Create `docs/merge-logs/.gitkeep` to ensure the directory exists in the repo.
  **Dependencies**: None
  **Files**: `docs/merge-logs/.gitkeep`

## 6. Delta spec and validation

- [ ] 6.1 Create delta spec for `skill-workflow` capturing new session-log requirements: phase-boundary append, sanitize-then-verify, merge-log format, and integration points.
  **Dependencies**: 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 5.1
  **Files**: `openspec/changes/add-phase-session-logs/specs/skill-workflow/spec.md`

- [ ] 6.2 Run `openspec validate add-phase-session-logs --strict` and fix any issues.
  **Dependencies**: 6.1
  **Files**: N/A
