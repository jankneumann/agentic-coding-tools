# Measure validator recall with a seeded-defect harness

> Parent roadmap: `skill-rightsizing`
> Change ID: `measure-validator-recall-seeded-defects`
> Effort: L
> Priority: 2

## Summary

Inject 40 known defects drawn from the categories established in ri-01, run each review skill against them, and report per-skill recall.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- Each review skill reports a recall figure against the 40-defect set.
- Defect categories are traceable to real observations from the failure record.
- Seeded defects are injected reproducibly from a committed manifest.
- Recall is reported per defect category, not only in aggregate.

## Rationale

/security-review, /parallel-review-plan, /parallel-review-implementation and the convergence loop have no measured detection rate. Ground truth is known by construction, so this tier is free of circularity entirely.
