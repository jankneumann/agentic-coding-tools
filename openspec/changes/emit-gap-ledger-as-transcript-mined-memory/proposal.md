# Emit gap ledger entries into episodic memory as transcript-mined findings

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `emit-gap-ledger-as-transcript-mined-memory`
> Effort: M
> Priority: 4

## Summary

Write graduated gaps from the gap ledger (backpass's or the ported one) into episodic memory as source:transcript-mined entries carrying affected_skill, domain, and verbatim quotes, and route orchestration-domain gaps to the improve-harness report.

## Dependencies

- `ri-01`
- `ri-07`
- `ri-13`

## Acceptance Outcomes

- Each graduated gap produces exactly one memory entry with source:transcript-mined, domain:, affected_skill, and at least one verbatim quote; a gap that is not graduated produces none.
- Rerunning the emitter does not duplicate entries for already-emitted gaps (idempotency test).
- The improve-harness report generated from the emitted entries lists the orchestration-domain gaps under affected_skill headings.

## Rationale

Adapt item 5 in section 4 and Phase 4. backpass sets orchestration-domain gaps aside as report-only; for a repo that is the orchestrating harness they are exactly the signal /improve-harness wants. This is the thin emitter the recommendation in section 5 names for the engine path.
