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

## Approaches Considered

### Recommended: canonical pure module with checkout-root fallback import

Put the vocabulary, validation, provenance result, and mapping-level per-mode
helper in `agent-coordinator/src/isolation_contract.py`. The coordinator imports
it normally; the existing local routing fallback imports that exact source file
through its checkout-root import shim. This keeps one runtime definition while
preserving the fallback's no-network property.

The resolver uses a router value only when it is present and valid. A silent or
unreachable router falls through to the exact configured agent/mode value, then
to `none`; an invalid *present* value raises a named contract error.

### Rejected: coordinator-only implementation

Keeping the module importable only from the coordinator leaves the local routing
fallback with a divergent vocabulary and precedence implementation during outages.

### Rejected: defer per-mode values to dg-06

The router already selects a dispatch mode. Deferring mode-specific isolation
would make reachable and unreachable selections differ for the same agent.

### Selected Approach


## Rationale

The router emits isolation and the dispatch layer consumes it, but nothing defines the vocabulary, the precedence, or the fallback. Small in effort and disproportionate in leverage - it is the seam two larger items on either side must agree on, and the cheapest moment to get it right is before either is written. agents.yaml already implies per-mode postures (review uses read-only flags, alternative uses write flags) and currently cannot express them.
