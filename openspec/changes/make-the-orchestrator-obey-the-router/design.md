# Design: Make the orchestrator obey the router

## Decision D1 — Routing is injected at the host seam

The roadmap state machine accepts a routing resolver protocol and invokes it before
every host dispatch. The resolver is responsible for bridge/coordinator access; the
state machine never imports a vendor SDK or executes a model directly. Legacy callers
may omit the resolver during migration, but a configured resolver fails closed when it
is unavailable, raises, or returns malformed data.

## Decision D2 — Dispatch context is immutable and versioned

Every routed attempt carries schema version 1, the router's durable `decision_id`, the
roadmap item and phase, an attempt number, a dispatch/ledger work ID, and the complete
selected assignment. Canonical isolation is copied to the host envelope as one of
`none`, `worktree`, or `sandbox`. The state machine validates and deep-copies this
context so host code cannot mutate the router's decision in place.

## Decision D3 — Completion must prove the active routed attempt

A routed host result is terminal only when its proof echoes the active decision ID,
dispatch work ID, and observed agent ID, and the coordinator ledger reports that work
as completed. Capacity failures exclude the observed lane and request a fresh router
decision; retrying the same decision or accepting a mismatched proof fails closed.

## Decision D4 — Loop safety is durable state

The checkpoint records a global iteration count, a durable-progress fingerprint,
consecutive no-progress count, and the most recent escalation. A durable item, phase,
or ledger transition changes the fingerprint and resets the no-progress count. Hitting
either configured cap checkpoints the escalation before execution parks, so restart
cannot erase the guard or duplicate the escalation.

## Decision D5 — Additive migration preserves current callers

The routing resolver and safety state are additive. Existing checkpoints deserialize
with empty safety state, and callers without a resolver retain the current host-assisted
path until the skill host wires the bridge. Once a resolver is supplied, no implicit
static route or unverified success is accepted.
