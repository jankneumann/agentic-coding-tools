# Rescope review convergence from consensus to disagreement routing

> Parent roadmap: `skill-rightsizing`
> Change ID: `rescope-review-convergence-disagreement-routing`
> Effort: M
> Priority: 2

## Summary

Stop treating multi-vendor agreement as a proxy for correctness in the review convergence loop, and repurpose disagreement as a triage signal that routes contested findings into human review.

## Dependencies

- `ri-06`

## Acceptance Outcomes

- Convergence output distinguishes contested findings from agreed findings and routes contested ones to a human queue.
- No gate treats unanimous vendor agreement as sufficient evidence of correctness on its own.
- Routing precision is reported against the seeded-defect set from ri-06.

## Rationale

Shared training distributions produce shared blind spots, so a five-vendor consensus can be five-way wrong identically. Disagreement genuinely localizes hard cases; agreement is not a verdict. The ri-06 recall figures establish what each vendor actually detects.
