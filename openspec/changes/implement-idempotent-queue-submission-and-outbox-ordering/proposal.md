# Implement idempotent queue submission and outbox ordering

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `implement-idempotent-queue-submission-and-outbox-ordering`
> Effort: L
> Priority: 2

## Summary

Key queue submissions idempotently by `(change_id, phase, iteration)` in `input_data` with submit-if-absent semantics, persist loop-state before enqueueing (outbox-style), and on resume re-derive or cancel queue entries from loop-state, never the reverse. Claim atomicity is exercised only in the coordinated tier; local-parallel and sequential tiers stay coordinator-free.

## Dependencies

- `ri-07`

## Acceptance Outcomes

- Re-submitting the same (change_id, phase, iteration) is a no-op, covered by an integration test.
- A simulated crash between loop-state write and enqueue reconciles cleanly on resume, with queue entries re-derived or cancelled from loop-state.
- Local-parallel and sequential tiers run with no coordinator dependency, verified by existing tier tests still passing without a coordinator.

## Rationale

Enforces the truth/projection contract in code so crashes between state-write and enqueue reconcile cleanly, preserving the three-tier availability design.
