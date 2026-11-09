# Auto-apply matching playbook policies at escalation time

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `auto-apply-matching-playbook-policies-at-escalation-time`
> Effort: M
> Priority: 7

## Summary

Have agents consult the playbook before escalating, auto-resolve when a policy's trigger matches with a citation to the policy ID, and audit each auto-resolution. Escalations with no matching policy still go to a human, with every option and its tradeoffs stated.

## Dependencies

- `ri-14`

## Acceptance Outcomes

- A later escalation matching an existing policy's trigger is auto-resolved with a citation to the policy ID, and the auto-resolution is audited.
- An unmatched escalation presents at least two options with tradeoffs, not a single recommendation.

## Rationale

Applying recorded policy automatically removes repeat interventions for already-decided judgment calls, while auditing and option presentation keep humans in control of novel decisions.
