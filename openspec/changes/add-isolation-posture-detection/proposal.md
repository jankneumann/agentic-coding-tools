# Widen execution-environment detection to an isolation posture

> Parent roadmap: `dispatch-governance`
> Change ID: `add-isolation-posture-detection`
> Effort: S
> Priority: 1

## Summary

Replace the single isolation_provided boolean in skills/shared/environment_profile.py with separate filesystem and network isolation dimensions, add the missing cloud-harness detection signals, and expose a compatibility property so existing boolean callers are unaffected. Update worktree.py and merge_worktrees.py to read the filesystem dimension.

## Dependencies

- None

## Acceptance Outcomes

- Filesystem and network isolation are reported as independent dimensions
- The cloud harness that currently reports source=default is detected correctly
- worktree.py and merge_worktrees.py read the filesystem dimension with no behavior change

## Rationale

A container provides strong filesystem isolation and entirely open egress; a boolean cannot express that, and dg-07 must be able to say "skip the filesystem sandbox here, still apply the network allowlist". The heuristic layer also has a demonstrated gap - planning this epic inside a cloud harness returned isolation_provided=False source=default, so worktree.py setup attempted a real worktree and failed against the already-checked-out branch.
