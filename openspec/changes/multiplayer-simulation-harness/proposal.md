# Build the multi-player simulation harness

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `multiplayer-simulation-harness`
> Effort: M
> Priority: 2

## Summary

Add a gen-eval scenario pack that simulates two or more principals with separate identities, worktrees, and agents working overlapping changes, starting with a reproduction of the memory-store incident.

## Dependencies

- None

## Acceptance Outcomes

- A scenario with two principals modifying the same requirement runs and records whether a collision was detected at plan time (baseline: not detected).
- The memory-store scenario reports a time-blocked-on-dependency metric for the dependent principal.
- Scenarios run in CI without network access to a shared coordinator.
- Scenario tests resolve change paths with change_dir() and pass the OpenSpec path-stability guard test.

## Rationale

Multi-player behavior is otherwise untestable in a solo-maintained repository; the harness provides the before/after baselines that verify each capability against the proposal's motivating failure modes.
