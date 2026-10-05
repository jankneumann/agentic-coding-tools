# Add per-principal attention budgets and digests

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `attention-budgets-digests`
> Effort: M
> Priority: 3

## Summary

Give each principal an urgency threshold and digest cadence, extending event_bus.classify_urgency so events below the threshold are batched into a per-principal digest and only events above it notify through the existing notification channel seam.

## Dependencies

- `ri-09`

## Acceptance Outcomes

- A principal receives notifications only for events above their configured threshold; the remainder appear in their next digest.
- Digest cadence is configurable per principal and a digest lists every below-threshold event since the previous digest.
- With no per-principal configuration, notification behavior is unchanged from today.

## Rationale

Attention is the scarce resource (P8); once escalations are routed to owners, budgets keep the escalation inbox from becoming the next bottleneck.
