# Extend reflection to harnesses without PreCompact

> Parent roadmap: `closed-loop-learning`
> Change ID: `extend-reflection-to-harnesses-without-precompact`
> Effort: S
> Priority: 3

## Summary

Give harnesses lacking a PreCompact surface the same bounded reflection at session end via their adapter's Stop or SessionEnd hooks, and document per-harness coverage in the adapter matrix.

## Dependencies

- `ri-10`

## Acceptance Outcomes

- A harness without PreCompact runs the same bounded reflection at session end via its adapter, writing to the same stores.
- The adapter matrix documents per-harness reflection coverage and the hook each harness uses.
- Missing hook surfaces degrade to a no-op, never a block.

## Rationale

All harness integration must land behind the adapter seam with graceful degradation; session-end reflection is the documented degradation path so knowledge capture is fleet-wide, not Claude-only.
