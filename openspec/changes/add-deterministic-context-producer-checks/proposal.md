# Add deterministic context producer checks

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `add-deterministic-context-producer-checks`
> Effort: L
> Priority: 5

## Summary

Add reproducible generation and check modes for documentation inventories, API contracts and generated bindings, decision timelines, and OpenSpec projections. Reuse update-specs, documentation-and-adrs, and the existing documentation-sync work rather than duplicating their domain logic.

## Dependencies

- None

## Acceptance Outcomes

- Each configured deterministic producer can regenerate output and report a precise list of stale artifacts without relying on mtimes.
- Generated artifacts carry source revision and producer metadata while hand-authored documentation outside managed regions remains unchanged.
- The add-update-documentation-skill proposal is explicitly absorbed, superseded, or declared as a prerequisite so no competing refresh lifecycle remains.
- API, decision, documentation, and OpenSpec checks are independently runnable and testable through their canonical owners.

## Rationale

Shared orchestration and CI need a uniform way to distinguish deterministic repository drift from optional external-service degradation.
