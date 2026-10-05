# Dispatch implementation through the queue with owner acceptance

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `queue-dispatch-owner-acceptance`
> Effort: L
> Priority: 2

## Summary

Separate owner from implementer on roadmap items and changes, default the implementer to the agent queue (optionally restricted to a named principal's agents), have queue agents implement from the agreed contract and open PRs into the owner's domain, and mirror claims as draft PRs so in-flight work is visible from the remote.

## Dependencies

- `ri-08`
- `ri-09`
- `ri-12`

## Acceptance Outcomes

- A roadmap item with default implementer policy is dispatched to the queue without requiring its owner to start a session.
- A queue-implemented PR requests review from the item owner and cannot be merged without the owner's acceptance.
- Claimed, in-flight implementation is visible from the git remote alone via a draft PR naming the item and claim time.
- An owner rejection is recorded with its reason and linked to the contract, so spec gaps surfaced by rejection become amendments.
- In solo mode the sole principal is both owner and acceptor and no additional acceptance gate appears.

## Rationale

Owning decisions rather than labor (P2) with the queue as the execution path (P10) is the core fix for the motivating incident, where a dependency waited on its domain owner's own implementation.
