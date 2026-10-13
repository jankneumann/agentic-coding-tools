# Enforce fork policies in CI, worktrees, and sync points

> Parent roadmap: `durable-execution`
> Change ID: `enforce-fork-policies-in-ci-worktrees-and-sync-points`
> Effort: M
> Priority: 3

## Summary

Add a fork-policy check run in CI and by /expedite, make worktree setup materialize fresh artifacts empty and skip copying latest artifacts, and update /merge-pull-requests, /update-specs, and /cleanup-feature to reference the registry instead of restating per-artifact rules.

## Dependencies

- `ri-03`

## Acceptance Outcomes

- The check flags a latest-policy artifact modified on a feature branch outside its declared single writer and a fresh-policy artifact copied into a new change from another change, and passes on a clean branch.
- Worktree setup for a work package creates fresh artifacts empty and does not copy latest artifacts into the package branch; a test covers each of the three policies.
- The check short-circuits correctly in cloud-harness environments where worktree operations are skipped.
- The three sync-point SKILL.md files reference the registry and contain no locally restated per-artifact fork rules.

## Rationale

A declared policy only prevents stale reads and cross-change leakage if it is checked and honored at the points where forks are created and merged.
