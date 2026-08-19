# Build the coordinator signal-type registry

> Parent roadmap: `closed-loop-learning`
> Change ID: `build-the-coordinator-signal-type-registry`
> Effort: M
> Priority: 1

## Summary

Add a versioned, coordinator-served signal-type registry in Postgres that extends the memory-conventions failure_type taxonomy, where each signal type carries a detection prompt describing how that failure manifests. Includes the local file fallback per the coordination-bridge degradation ladder and updates the memory-conventions guide (the single canonical schema statement, not per-skill copies).

## Dependencies

- `ri-01`

## Acceptance Outcomes

- The coordinator serves a versioned signal-type registry where each entry pairs a failure_type-style tag with a detection prompt, backed by Postgres with the documented file-fallback ladder.
- Adding or refining a signal type is a registry data change requiring no skill-code change.
- The memory-conventions guide is updated in exactly one canonical place to document the signal-type extension, and the deleted memory_working/memory_procedural tables are not reintroduced.
- Registry reads degrade to the file fallback (no-op, never block) when the coordinator is unreachable.

## Rationale

The registry is the shared substrate for semantic recall - lessons map to signal types and the classifier maps diagnoses to them. Coordinator Postgres storage is what makes recall fleet-wide, the strategic payoff over Abacus's per-process JSON files.
