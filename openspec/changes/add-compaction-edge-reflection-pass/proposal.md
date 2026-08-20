# Add compaction-edge reflection pass

> Parent roadmap: `closed-loop-learning`
> Change ID: `add-compaction-edge-reflection-pass`
> Effort: M
> Priority: 3

## Summary

Add a PreCompact hook in the Claude Code adapter that runs one bounded reflection pass before context compaction, a single dispatched look back over the turn's actions with a restricted toolset (record to episodic memory, record a signal-type-mapped lesson, update the current handoff), using an economy-tier model, writing durable records or nothing and discarding the reflection transcript itself.

## Dependencies

- `ri-03`

## Acceptance Outcomes

- When compaction fires in a Claude Code session, a reflection pass runs first and any records it writes land in episodic memory or the handoff store before the verbatim context is summarized away.
- At most one reflection is dispatched per compaction, under a hard step cap, on an economy-tier model, with only the restricted toolset available.
- The reflection transcript is discarded and only the written records persist.
- The pass degrades to a no-op (never a block) when the coordinator is unreachable.

## Rationale

Phase-boundary handoffs guard phase edges but compaction destroys evidence at context edges, which is currently unguarded; capturing knowledge right before the verbatim context is summarized away closes that gap.
