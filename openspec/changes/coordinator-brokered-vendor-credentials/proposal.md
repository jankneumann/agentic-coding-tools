# Coordinator-brokered vendor credentials for cloud review lanes

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `coordinator-brokered-vendor-credentials`
> Effort: M
> Priority: 3

## Summary

Let cloud workers obtain metered vendor credentials (first OpenRouter) from the coordinator instead of a per-environment variable. The coordinator reads the credential from OpenBao and serves it on an authenticated, principal-scoped, audited route; ApiKeyResolver gains a coordinator mode alongside the environment and OpenBao modes. A later step may have the coordinator mint short-lived, spend-capped OpenRouter sub-keys per session from a provisioning key held in OpenBao, and revoke them when the session ends.

## Dependencies

- `ri-22`

## Acceptance Outcomes

- In a cloud container with no OpenRouter variable set, the review lane obtains its key from the coordinator, and the lane's dry invocation passes; the key is never written to disk, logs, or the dispatch result.
- The coordinator route authenticates the caller, authorizes the vendor against the principal's configured scope, reads OpenBao afresh on each call, and records an audit entry without the secret value.
- When the coordinator or OpenBao is unreachable or refuses, the lane reports capability_unavailable rather than falling back to an environment key silently; an explicit environment key remains a supported, reported fallback.
- The ri-22 design decision about the lane's coordinator identity is revised in a reviewed trust-posture change before the route ships.

## Rationale

Removes long-lived vendor secrets from cloud environments, centralises rotation and audit in OpenBao, and lets the per-session spend cap be enforced by the key itself. Revisits ri-22 design decision that the lane never calls the coordinator under its own identity, so it needs its own trust-posture review.
