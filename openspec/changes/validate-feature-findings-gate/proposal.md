# Proposal: Residual Ephemeral Validation Worktree

**Change ID**: validate-feature-findings-gate
**Status**: Approved (residual scope)
**Created**: 2026-06-26
**Scope revised**: 2026-08-19

## Supersession boundary

`introduce-fitness-function-gates` superseded the original findings model,
pre-push gate, and finding-triage phases while they remained untouched at 0/31
tasks. Those phases MUST NOT be implemented here: the merged fitness-function
work owns the current findings, DEGRADED-status, architecture-gate, and report
semantics.

The original Phase 3 was not absorbed. It remains a prerequisite of
`phase-scoped-worktree-lifecycle`, whose authoritative prerequisite contract
requires these exact surfaces:

- `skills/validate-feature/scripts/validation_worktree.py`
- `skills/tests/validate-feature/test_validation_worktree.py`

This proposal is therefore narrowed to that residual deliverable only.

## Why

Validation may create deploy artifacts, scanner output, logs, and partial
reports. Running those operations directly in the feature checkout can leave
residue or accidentally validate stale `HEAD` while local changes exist. A
disposable worktree gives each run an exact, inspectable input and a deterministic
cleanup boundary.

## What Changes

- Add `--ephemeral` validation mode backed by a detached scratch worktree at the
  current `HEAD`.
- Fail fast on a dirty source checkout unless `--include-dirty` is explicitly
  requested; that opt-in materializes staged, unstaged, and untracked state and
  records the resulting Git tree.
- Persist only newly produced or changed `validation-report.md`,
  `validation-findings.json`, and `architecture-impact.md` back to the change
  checkout, recording the exact validated commit and tree before teardown.
- Reject unsafe identifiers, escaping or symlinked paths, and use atomic
  replacement for every copy-back artifact.
- Provide a concrete prepare/finalize CLI boundary so the documented validation
  phases run in scratch while session-log/handoff bookkeeping remains durable.
- Always remove the scratch checkout, including when validation fails.
- Fall back to in-place execution when shared environment detection reports that
  the cloud harness already provides isolation.
- Document the flags in the canonical `validate-feature` skill and regenerate
  runtime mirrors from `skills/`.

## Non-goals

- Reintroducing the superseded findings schema, pre-push hook, auto-fix, or
  interactive triage design.
- Changing current DEGRADED, architecture-gate, coverage, or validation-report
  semantics.
- Creating commits or branches from validation.

## Rollback

The mode is opt-in. Removing the flag wiring and reverting the single residual
implementation commit returns validation to the existing in-place behavior.
