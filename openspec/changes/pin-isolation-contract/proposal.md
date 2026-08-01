# Pin the isolation contract between router and dispatch

> Parent roadmap: `dispatch-governance`
> Change ID: `pin-isolation-contract`
> Effort: S
> Priority: 1

## Summary

Specify the isolation vocabulary (none, worktree, sandbox) in one place and reference it from both producer and consumer; define the resolution precedence (router when reachable, then agents.yaml via get_agent_isolation(), then none); and extend resolution to a (agent_type, dispatch_mode) pair so review and alternative can carry different postures under one agent entry.

## Dependencies

- `dg-04`

## Acceptance Outcomes

- The isolation vocabulary and precedence ladder are specified once and referenced by both producer and consumer
- An (agent_type, dispatch_mode) pair resolves to an effective isolation mode, with per-mode overrides expressible in agents.yaml
- A coordinator-unreachable path yields a defined decision rather than an error

## Rationale

The router emits isolation and the dispatch layer consumes it, but nothing defines the vocabulary, the precedence, or the fallback. Small in effort and disproportionate in leverage - it is the seam two larger items on either side must agree on, and the cheapest moment to get it right is before either is written. agents.yaml already implies per-mode postures (review uses read-only flags, alternative uses write flags) and currently cannot express them.
