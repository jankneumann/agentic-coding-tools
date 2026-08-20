# Design — Residual Ephemeral Validation Worktree

## Context

The original change was superseded by `introduce-fitness-function-gates` except
for its selected ephemeral validation worktree. `phase-scoped-worktree-lifecycle`
depends on that exact residual surface and will wrap it with phase ownership;
this change owns only the scratch validation checkout itself.

## Decisions

### D1 — Detached scratch worktree at the exact source `HEAD`

Local execution creates a uniquely named detached worktree under
`.git-worktrees/.validation/`. It records both the source commit and the Git tree
that is actually validated. No feature branch is created or checked out in the
scratch directory.

### D2 — Dirty state is explicit and exactly materialized

`--ephemeral` fails when the source index or working tree is dirty because a
plain `HEAD` checkout would be stale. `--include-dirty` is the explicit opt-in:
the implementation captures the staged binary diff, unstaged binary diff, and
untracked file list before the scratch directory exists; applies them in that
order; then writes the materialized scratch index tree id. The source index and
working tree are never changed.

### D3 — Only two artifacts cross the isolation boundary

Immediately before teardown, the implementation records `validated_commit` and
`validated_tree`, then copies only `validation-report.md` and
`validation-findings.json` from the change directory. Deploy artifacts, scanner
output, logs, and all other files remain disposable.

### D4 — Teardown is exception-safe and scratch-scoped

Persistence and teardown run in nested `finally` blocks. Git worktree removal
uses force only for the exact uniquely owned scratch path, because validation
artifacts intentionally make that disposable checkout dirty. A failed Git
removal falls back only to that resolved scratch directory, then prunes worktree
metadata.

### D5 — Harness isolation wins

When `shared.environment_profile.detect()` reports `isolation_provided=true`,
the helper logs a downgrade and yields the current checkout. It creates no nested
worktree and performs no copy-back or teardown, matching the repository's shared
cloud-execution contract.

## Compatibility

The default `validate-feature` invocation remains in place. The new flags are
opt-in and do not alter the merged fitness-function gate logic, DEGRADED status,
or architecture thresholds.
