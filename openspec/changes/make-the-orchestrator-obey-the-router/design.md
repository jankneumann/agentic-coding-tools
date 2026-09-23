# Design: Make the orchestrator obey the router

## Decision D1 — Routing is injected at the host seam

The roadmap state machine accepts a routing resolver protocol and invokes it before
every synchronous `execute_roadmap` host dispatch. The resolver is responsible for bridge/coordinator access; the
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

A routed host result is terminal only when its proof echoes the durable active decision
ID, dispatch work ID, observed agent ID, and expected ledger status. Completed work
advances the phase. Capacity failures first persist the policy decision: WAIT preserves
the lane and pause window, while SWITCH excludes the observed lane and requests a fresh
router decision. Failed work closes the attempt and fails the item. Vendor-limit
status, policy action, and any WAIT pause window are committed in one checkpoint save;
a configured cost ceiling without authoritative routed cost evidence fails closed.
The host-owned
resolver/reconciler boundary supplies coordinator ledger evidence; the state machine
validates that evidence against its checkpoint and never treats host mutation of the
dispatch copy as authority. Retrying the same decision or accepting a stale,
mismatched, unavailable, or unknown result fails closed.

## Decision D4 — Loop safety is durable state

The checkpoint records a global iteration count, a durable-progress fingerprint,
consecutive no-progress count, and the most recent escalation. A durable item, phase,
or ledger transition changes the fingerprint and resets the no-progress count. Hitting
either configured cap checkpoints the escalation before execution parks, so restart
cannot erase the guard or duplicate the escalation. Resumption requires an explicit
host acknowledgement; prepared work is reconciled before any new submission, and a
counter-based escalation parks again unless the host intentionally raises the relevant
positive cap.

## Decision D5 — Additive migration preserves current callers

The opt-in delegated batch lifecycle is outside this change: it prepares requests and
applies collected results through a distinct durable contract rather than invoking the
synchronous phase `dispatch_fn` seam. Routing that lifecycle requires a separate change.

The routing resolver and safety state are additive. Existing checkpoints deserialize
with empty safety state, and callers without a resolver retain the current host-assisted
path until the skill host wires the bridge. The new global iteration and no-progress
guards intentionally bound both legacy and routed execution; legacy policies configured
above the no-progress cap may park at the safety boundary first. Once a resolver is supplied, no implicit
static route or unverified success is accepted.
