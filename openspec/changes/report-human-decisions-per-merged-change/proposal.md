# Report human decisions per merged change

> Parent roadmap: `operator-front-door`
> Change ID: `report-human-decisions-per-merged-change`
> Effort: S
> Priority: 3

## Summary

A report of human decisions per merged change by project and roadmap over a time window, counting only human answers from the inbox and excluding auto-resolved gates and deadline expiries.

## Dependencies

- `ri-07`

## Acceptance Outcomes

- The report returns human decisions per merged change for each project and roadmap over a caller-specified time window.
- Tier-auto resolutions and expired-to-default cards are excluded from the human count, verified by a fixture test.
- The report runs from coordinator records alone without checking out any repository.

## Rationale

The epic's headline metric must be measured release over release, so it ships as soon as the inbox records decisions, giving a baseline before the ladder and promotion start reducing it.
