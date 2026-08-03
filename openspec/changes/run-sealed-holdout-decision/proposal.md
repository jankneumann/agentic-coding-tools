# Run the sealed holdout and apply the pre-registered decision rule

> Parent roadmap: `skill-rightsizing`
> Change ID: `run-sealed-holdout-decision`
> Effort: M
> Priority: 1

## Summary

Unseal the 32-change holdout partition, run both arms across it, and accept or reject the rightsizing work against the rule registered in ri-09.

## Dependencies

- `ri-10`
- `ri-12`
- `ri-13`
- `ri-14`
- `ri-15`

## Acceptance Outcomes

- Both arms run across all 32 holdout changes at N=3 with blinded judging.
- The accept/reject verdict is stated against the rule as registered, without amendment.
- Per-metric deltas are published with variance, and any rejected cut is reverted or reworked rather than retained.

## Rationale

This is the decision the entire programme exists to support, and it is only credible if the holdout was never consulted during authoring.
