# Seed scenario suite and nightly cross-vendor parity runs

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `seed-scenario-suite-and-nightly-cross-vendor-parity-runs`
> Effort: M
> Priority: 3

## Summary

Author at least 10 seed scenarios covering plan, implement, validate, and merge skills, schedule the parity matrix nightly on the GX10, feed failures into the /improve-harness capability-gap pipeline, and store per-vendor per-skill results for trend queries.

## Dependencies

- `ri-15`

## Acceptance Outcomes

- At least 10 seed scenarios covering plan/implement/validate/merge skills run nightly across at least 2 vendors.
- A deliberately-broken skill change fails the suite and produces a capability-gap finding.
- Scenario results are queryable per vendor per skill over time.

## Rationale

The harness only pays off with coverage and cadence; parity results gate whether the dispatcher routes real work through changed skills.
