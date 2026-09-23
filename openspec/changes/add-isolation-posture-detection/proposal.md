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

## Approaches Considered

### Nested boolean posture with a compatibility facade (recommended)

Add `IsolationPosture(filesystem: bool, network: bool)` as
`EnvironmentProfile.posture`. Keep `isolation_provided` as a derived property and
accept the legacy constructor keyword. This factual contract stays separate from router
requests and coordinator trust-posture modes.

### Flat fields or trust-posture enums

Rejected: flat fields obscure the widened boundary, while asserted containment enums do
not answer whether this session already has a unique workspace.

## Detection Decisions

- Explicit/coordinator inputs map filesystem only unless they report structured posture.
- `CLAUDE_CODE_REMOTE=true` and the conservative pair `CODEX_CI=1` plus
  `CODEX_PERMISSION_PROFILE=:workspace` are exact filesystem heuristics.
- `CODEX_SANDBOX_NETWORK_DISABLED=1` independently reports network isolation.
- Existing container markers report filesystem only; the default is false/false.
- Repairing the coordinator endpoint is outside dg-03.
