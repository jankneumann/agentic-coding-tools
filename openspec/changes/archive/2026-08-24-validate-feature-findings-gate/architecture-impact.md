# Architecture Impact: validate-feature-findings-gate

## Scope

This residual prerequisite adds an opt-in disposable validation boundary. It
does not change deployed API, database, findings-gate, DEGRADED-status, or
architecture-threshold semantics.

## Boundaries

- The source checkout supplies a validated Git commit/tree and receives only
  three changed, allowlisted durable artifacts through atomic replacement.
- Scratch creation, copy-back, and teardown validate resolved containment;
  artifact symlinks and unregistered worktrees fail closed.
- The bash/zsh adapter parses helper output as JSON data, never as generated
  shell, and finalizes before durable session-log/handoff bookkeeping.
- Cloud harnesses reuse their existing isolation while retaining dirty-state
  refusal and exact temporary-index tree calculation.

## Diagnostics

Structural linters reported three advisory size nits: the pre-existing
`validate-feature/SKILL.md`, the required single-surface lifecycle helper, and
its comprehensive behavioral test module exceed 500 lines. No dependency
cycle, cross-layer violation, deployed interface change, or blocking
architecture finding was introduced. Independent implementation review was
clean.

## Result

Architecture mode remains advisory and the change is compatible with the
phase-scoped worktree lifecycle prerequisite contract.
