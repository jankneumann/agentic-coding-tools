# Add deterministic context drift gates

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `add-deterministic-context-drift-gates`
> Effort: M
> Priority: 10

## Summary

Add CI and merge-validation checks that regenerate deterministic context through the shared lifecycle and compare it with committed output. Report deterministic failures separately from optional external-service degradation.

## Dependencies

- `ri-04`
- `ri-05`
- `ri-07`

## Acceptance Outcomes

- CI fails with a precise artifact list when committed architecture, documentation, API, decision, or OpenSpec output is stale.
- Drift decisions use source revision and producer inputs rather than file modification time.
- CI reports semantic Postgres or embedder unavailability as explicit external-service degradation without treating stale semantic results as current.
- A clean checkout at the recorded revision passes regeneration checks with no diff.

## Rationale

Context freshness must become an enforceable, precise invariant before automated main convergence relies on generated artifacts.
