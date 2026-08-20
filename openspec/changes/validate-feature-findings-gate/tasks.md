# Tasks — Residual Ephemeral Validation Worktree

> Original phases 1, 2, and 4 were superseded by
> `introduce-fitness-function-gates` at 0/31 tasks and are intentionally absent.

- [x] 1.1 Write failing lifecycle tests for clean isolation, dirty refusal,
  `--include-dirty`, artifact persistence, exception cleanup, and cloud fallback.
  **Design decisions**: D1-D5
- [x] 1.2 Implement
  `skills/validate-feature/scripts/validation_worktree.py` as an exception-safe
  context manager and CLI wrapper. **Dependencies**: 1.1
  **Design decisions**: D1, D4
- [x] 1.3 Materialize staged, unstaged, and untracked source state only under
  `--include-dirty`, without changing the source checkout. **Dependencies**: 1.2
  **Design decisions**: D2
- [x] 1.4 Record the exact validated commit/tree and persist only the validation
  report and findings artifact before teardown. **Dependencies**: 1.2
  **Design decisions**: D3
- [x] 1.5 Implement the environment-profile fallback to in-place validation.
  **Dependencies**: 1.2
  **Design decisions**: D5
- [x] 1.6 Wire and document `--ephemeral` / `--include-dirty` in canonical
  `skills/validate-feature/SKILL.md` and the worktree guide.
- [x] 1.7 Run strict OpenSpec and environment-safe validation.
  **Dependencies**: 1.1-1.6
- [x] 1.8 Regenerate runtime skill mirrors from canonical `skills/` and verify
  mirror drift checks. **Dependencies**: 1.6
