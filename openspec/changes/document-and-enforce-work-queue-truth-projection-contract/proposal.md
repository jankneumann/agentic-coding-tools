# Document and enforce work-queue truth/projection contract

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `document-and-enforce-work-queue-truth-projection-contract`
> Effort: M
> Priority: 2

## Summary

State the authority split in `docs/guides/` and `skills/coordination-bridge/SKILL.md` — `loop-state.json` is authoritative execution state, the coordinator work queue is a derived distribution/claim mechanism — and add grep-enforced tests preventing any skill from reading authoritative phase state from the queue.

## Dependencies

- None

## Acceptance Outcomes

- The contract is stated in a docs/guides/ page and in skills/coordination-bridge/SKILL.md.
- A grep-enforced test fails if any skill reads authoritative phase state from the queue, and passes on the current tree.
- The contract text specifies idempotent keying, outbox ordering, and resume reconciliation semantics for later enforcement.

## Rationale

Git-is-truth is a guiding principle; a supervisor is only trustworthy if the projection can never masquerade as the source of record, matching the authority split coordinator-task-status-renderer already established.
