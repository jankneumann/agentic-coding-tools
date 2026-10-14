# Add cloud overflow placement for dispatches

> Parent roadmap: `operator-front-door`
> Change ID: `add-cloud-overflow-placement-for-dispatches`
> Effort: M
> Priority: 4

## Summary

When the GX10 launcher is saturated or unreachable past a threshold, place a dispatch on a cloud Claude Code session using the same dispatch contract, decision cards, and inbox, recorded as a degradation and visible in the governor.

## Dependencies

- `ri-09`

## Acceptance Outcomes

- When the launcher reports saturation or is unreachable past the threshold, a dispatch is placed on a cloud session and its result returns through the same inbox and dispatch-result schema.
- A placement test proves no dispatch is placed on cloud while the GX10 has free capacity.
- Every cloud placement is recorded in the dispatch result's degradations[] and appears as cloud consumption in the governor.

## Rationale

Keeps work flowing when the GX10 is full or down without making cloud the default; honours the visible-degradation constraint. Phase 4, after the queue-backed launcher whose saturation signal it reads.
