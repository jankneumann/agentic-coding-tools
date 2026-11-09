# Add eliminative adversarial review mode

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `add-eliminative-adversarial-review-mode`
> Effort: L
> Priority: 3

## Summary

Add an eliminate mode to parallel-review-implementation and to iterate-on-implementation when it is debugging, whose reviewer must find contradicting facts, flag uncited claims, check that the control is not broken like the variable, re-check fact provenance, and run removal tests on multi-cause components. Dispatch routes the reviewer to a different vendor/model than the author with a ledger-derived context slice, and findings use new types in review-findings.schema.json.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- In eliminate mode the dispatcher refuses a reviewer whose vendor/model matches the author's unless an operator override is supplied, and the override is recorded in the audit trail.
- A seeded ledger with an uncited claim and a contradicting fact yields findings of type uncited_claim and contradicting_fact that validate against review-findings.schema.json.
- The reviewer prompt contains the ledger and excludes the author's reasoning transcript.

## Rationale

A same-model reviewer that corroborates rather than eliminates validated the wrong cert-reload theory in the motivating essay. The constraint that eliminative review runs on a different vendor/model must be enforced at dispatch, not left to convention.
