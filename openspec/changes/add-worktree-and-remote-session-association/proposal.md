# Add worktree-list and recorded-remote session association to transcript adapters

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `add-worktree-and-remote-session-association`
> Effort: M
> Priority: 4

## Summary

Extend the adapter base with tiered session-to-repo association: worktree cwd, sibling worktree from the git worktree list, recorded remote URL, and a dead-path tier that matches on repo name for sessions whose container path no longer exists. Label the tier on each association and make the best-effort tier opt-in.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- A fixture session recorded under a deleted worktree path is associated with this repo via the dead-path tier and the association record names the tier.
- A fixture session from a sibling worktree is associated via the worktree-list tier without the best-effort flag.
- With the best-effort tier disabled, sessions matching only by repo name are excluded (asserted by test).

## Rationale

Adapt item 7 in section 4. Adapters today glob everything under the cwd-encoded store, so sessions from managed worktrees and cloud containers whose paths die with them are either missed or misattributed. The dead-path tier is what claude_code_web sessions require.
