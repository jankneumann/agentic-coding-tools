# Compute earned maturity tiers from dispatch outcomes

> Parent roadmap: `closed-loop-learning`
> Change ID: `compute-earned-maturity-tiers-from-dispatch-outcomes`
> Effort: M
> Priority: 2

## Summary

Add a coordinator service that derives a maturity tier per (vendor x archetype) from the dispatch ledger over a rolling window, using the Abacus priors, leave probing after 3 clean runs, reach full trust after 12 clean runs with under 30% worker failure rate, with failures paying the tier back down. Expose the tier and its underlying outcome aggregates via a coordinator endpoint in the shape the ri-13 routing scorecard specifies.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- The coordinator serves a maturity tier per (vendor x archetype) computed from the dispatch ledger, with unit tests covering promotion thresholds and tier demotion on failures.
- Outcome aggregates are queryable in the shape the ri-13 routing scorecard specifies, and the adaptive-model-router change can consume them without schema translation.
- Tier computation parameters (clean-run thresholds, failure-rate ceiling, window) are configuration, not code constants.

## Rationale

Replaces "confidence is configured" with "confidence is earned" from recorded outcomes, and the aggregates it maintains are the same numbers the ri-13 scorecard and the add-adaptive-model-router signal ledger need, so this feeds routing rather than competing with it.
