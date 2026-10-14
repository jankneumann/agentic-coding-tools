# Promote repeated gate resolutions to auto policy rules

> Parent roadmap: `operator-front-door`
> Change ID: `promote-repeated-gate-resolutions-to-auto-policy-rules`
> Effort: M
> Priority: 3

## Summary

Log every resolved card with gate kind, context features, and answer; after a configurable number of identical resolutions under matching features, raise one promotion card, and once the operator approves, resolve later matching gates as tier auto with the rule ID recorded.

## Dependencies

- `ri-01`
- `ri-07`

## Acceptance Outcomes

- After the configured number of identical resolutions of a gate kind under matching features, a promotion card is raised once and not raised again while it is pending.
- After the promotion is approved, the next matching gate resolves as tier auto with the rule ID recorded in loop-state and the dispatch result.
- Approved rules are stored as decision-point playbook entries, and a rejected promotion raises no further card for that pattern until new resolutions accumulate.

## Rationale

Drives mechanical gates out of the human path so the headline metric falls. Reuses the decision-point playbook from evidence-grounded-debugging ri-14 and ri-15 rather than a second policy store, and plugs approved rules into the runner's tiering.
