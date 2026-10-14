# Implement the evidence-backed escalation ladder

> Parent roadmap: `operator-front-door`
> Change ID: `implement-the-evidence-backed-escalation-ladder`
> Effort: M
> Priority: 3

## Summary

Escalation requests and repeated phase failures climb a fixed ladder (more thinking, premium tier, frontier tier, cross-vendor, human), each rung auto-approved by gate-tier policy or raised as a decision card, with evidence carried forward from the evidence-grounded-debugging ri-01 ledger.

## Dependencies

- `ri-01`
- `ri-03`
- `ri-07`
- `ri-08`

## Acceptance Outcomes

- An escalation_request moves exactly one rung up the ladder and records the rung, reason, and ledger refs in the dispatch result.
- A rung that policy auto-approves runs without a human decision, and a rung policy does not cover raises a decision card in the inbox.
- The human-rung decision card links the evidence ledger entries accumulated across all previous rungs.
- The ladder never skips the cross-vendor rung before the human rung unless the governor reports no cross-vendor headroom, and that skip is recorded.

## Rationale

Lets workers get more capability without a human for routine climbs and gives the human at the top a card summarising the whole climb. Consumes the evidence ledger (out of scope here) and the governor's cross-vendor headroom rather than building either.
