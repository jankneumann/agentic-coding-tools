# Promote behavioral validation gates to blocking

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `promote-behavioral-validation-gates-to-blocking`
> Effort: M
> Priority: 3

## Summary

Make the holdout gate in /merge-pull-requests blocking under scheduled windows, wire an llm_backend so gen-eval SemanticBlock judges run instead of silently skipping, and let the posture file declare which validation phases are merge-blocking per repo.

## Dependencies

- `ri-04`
- `ri-12`

## Acceptance Outcomes

- A holdout scenario failure blocks an unattended merge and files an approval request.
- Semantic evaluations report pass or fail (not skip) in a default GX10 run.
- Merge-blocking validation phases are configurable per repo via the posture file.

## Rationale

Validation is advisory where it matters today; unattended merges must be gated by the behavioral machinery that already exists.
