# Route approvals and escalations to resolved owners

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `owner-routed-escalation`
> Effort: L
> Priority: 1

## Summary

Make the approval gate resolve its owner set from the ownership map with a fallback chain, enforce that decided_by belongs to that set, let trust posture declare gate owners per capability, add a principal-conflict escalation type, and let an escalating queue agent park its item and claim the next ready entry, with a per-principal escalation inbox.

## Dependencies

- `ri-02`
- `ri-08`

## Acceptance Outcomes

- An approval request records its resolved owner set, and a decision by a principal outside it is rejected.
- An unresolvable owner fails closed to the repository-default owner and the fallback is reported.
- An escalating queue agent parks the item in a resumable state and claims another ready entry; the parked item becomes ready again within one reconciliation cycle of the owner's answer.
- A principal can list every open escalation addressed to them, with its item, options, recommendation, default action, and deadline.
- In solo mode approvals route to the sole principal with no additional prompts or gates compared to today.

## Rationale

Escalation is the primary human interface in the queue-driven model (P10); routing each decision to its owner (P1, P3, P8) and failing closed on unknown owners is what keeps agents from deciding on a human's behalf without idling workers.
