# Gate semantic context default enablement

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `gate-semantic-context-default-enablement`
> Effort: M
> Priority: 13

## Summary

Add retrieval-quality and coding-context utility evaluations that compare semantic augmentation with exact-search and direct-source baselines. Keep semantic injection opt-in until measurable thresholds pass and preserve automatic fail-closed fallback afterward.

## Dependencies

- `ri-12`

## Acceptance Outcomes

- Evaluation scenarios measure retrieval relevance, scope compliance, context utility, and coding-task outcomes against an exact-search baseline.
- Evaluation reports record the indexed revision, embedding model, configuration, and pass or fail thresholds.
- Semantic context remains disabled by default unless both retrieval-quality and coding-context utility gates pass.
- A later regression or unavailable exact-revision index disables semantic injection and restores explicit exact-search fallback.

## Rationale

The proposal explicitly forbids production-default semantic context before both the existing retrieval gate and the new worker-context evaluation demonstrate benefit.
