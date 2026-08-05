# Migrate discovery generators to emit candidate-work stubs

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `migrate-discovery-generators-to-emit-candidate-work-stubs`
> Effort: M
> Priority: 2

## Summary

Update all three discovery generators — bug-scrub finding promotion, improve-harness proposal stubs, and explore-feature shortlist entries — to emit schema-valid candidate-work stubs, and wire the approved-stub path so an approved stub enters `/plan-roadmap` as a roadmap item without hand-editing.

## Dependencies

- `ri-11`

## Acceptance Outcomes

- All three generators emit stubs that validate against the canonical schema, covered by tests per generator.
- An approved stub becomes a roadmap item via /plan-roadmap without hand-editing intermediate artifacts.
- /prioritize-proposals successfully ranks a mixed batch of stubs from all three generators.

## Rationale

Loops close only when every producer emits what the consumer reads; this completes the discovery back-edge the proposal exists to standardize.
