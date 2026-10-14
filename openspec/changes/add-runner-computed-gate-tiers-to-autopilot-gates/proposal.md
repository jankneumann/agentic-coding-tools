# Add runner-computed gate tiers to autopilot gates

> Parent roadmap: `operator-front-door`
> Change ID: `add-runner-computed-gate-tiers-to-autopilot-gates`
> Effort: M
> Priority: 1

## Summary

Every gate raised by autopilot and autopilot-roadmap gets a tier (auto, batched, interrupt) computed by the runner from gate kind, trust posture, and attached evidence, recorded in loop-state and the dispatch result. Ships the operator's auto-merge rule for this repository: auto only when CI is green on head, reviews converged, and no security finding; other repositories default to block.

## Dependencies

- None

## Acceptance Outcomes

- Every gate raised by autopilot and autopilot-roadmap carries a runner-computed tier, and the tier appears in loop-state and the dispatch result in tests covering each gate kind.
- Under the operator posture, auto-merge of an agent PR in this repository resolves as tier auto when CI is green on head, reviews have converged, and there is no security finding.
- A table-driven test shows that failing any one of the three auto-merge conditions raises tier interrupt, and that a repository other than this one resolves the merge gate as block.
- Tier computation is deterministic for a given gate kind, posture, and evidence set, and the supervisor has no code path that sets or overrides a tier.

## Rationale

Phase 1 contract that every later item keys on (delivery routes by tier, the ladder and promotion resolve rungs by tier). Extends the approval-gate service and encoded gates from always-on-agent-automation ri-05/ri-06 rather than forking them, and keeps the autopilot phase machine unchanged per Out of Scope.
