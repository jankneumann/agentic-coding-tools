# Write durable state-artifacts guide

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `write-durable-state-artifacts-guide`
> Effort: S
> Priority: 2

## Summary

Author `docs/guides/state-artifacts.md` documenting every durable artifact — per-change `loop-state.json`, roadmap `checkpoint.json`, `learnings/<item>.md`, phase records, handoff documents — stating what each holds, who writes it, and the rehydration order a fresh session follows, then link each skill doc to it instead of restating semantics. The supervise skill's rehydration step (Phase 1) should be aligned to this order once both land.

## Dependencies

- `ri-07`

## Acceptance Outcomes

- docs/guides/state-artifacts.md exists and covers all five artifact classes with holder, writer, and rehydration order.
- Each skill doc that previously restated artifact semantics links to the guide instead, verified by grep.
- The supervise skill's rehydration step follows the guide's documented order once ri-02 has landed.

## Rationale

Makes the "throw sessions at the role" property real rather than folklore spread across five skill docs, underpinning supervisor rehydration.
