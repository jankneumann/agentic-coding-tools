# Add branch-local context checkpoints

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `add-branch-local-context-checkpoints`
> Effort: L
> Priority: 9

## Summary

Run the shared refresh lifecycle in an isolated checkpoint mode after large or integration work packages. Produce change-local specs, contracts, decisions, documentation validation, architecture slices or diffs, and an optional revision-isolated semantic index.

## Dependencies

- `ri-07`
- `ri-08`

## Acceptance Outcomes

- Large and integration work packages automatically produce a checkpoint report through implement-feature.
- The report lists affected capabilities, APIs, architecture nodes, decisions, documentation, and semantic index revision.
- Branch-local generated artifacts remain isolated from canonical main artifacts.
- Optional semantic indexing uses the exact branch or checkpoint revision and cannot mutate the canonical main index.
- Checkpoint execution enforces the work package's read_allow and deny scopes.

## Rationale

Large branch changes need current review context before main convergence without allowing feature worktrees to mutate canonical project artifacts or indexes.
