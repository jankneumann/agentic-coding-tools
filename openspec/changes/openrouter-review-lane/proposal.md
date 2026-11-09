# OpenRouter review lane for cloud workers

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `openrouter-review-lane`
> Effort: M
> Priority: 2

## Summary

Make API-based multi-vendor review available in cloud containers by registering OpenRouter-backed reviewer lanes (non-Anthropic model families) that dispatch over HTTP through the existing OpenAI-compatible adapter, need no vendor CLI, and count toward converge() quorum. Lanes are declared in the dispatch request's execution_profile and review_requirements from ri-21, verified by a dry invocation rather than credential probing, bounded by the existing spend ceiling, and their use retires the temporary cloud single-vendor review policy.

## Dependencies

- `ri-21`

## Acceptance Outcomes

- In a cloud container with an OpenRouter credential provisioned as an environment secret, converge() reaches min_quorum=2 for PLAN_REVIEW using claude_code plus at least one OpenRouter lane from a different model family, verified end to end on a fixture change.
- Lane availability is established by a dry invocation of the lane for the requested mode and reported in execution_profile; no worker reads environment variables or credentials to discover it, and --check-vendors no longer reports a lane that cannot dispatch.
- Every OpenRouter review records model, generation id and cost against the existing monthly spend ceiling; exceeding the ceiling parks with capability_unavailable instead of silently dropping to single-vendor review.
- OpenRouter findings conform to review-findings.schema.json and are synthesized by ConsensusSynthesizer like CLI lanes, with vendor attribution preserved in the ledger.
- The "Review quorum in cloud containers (temporary)" section of TRUST_POSTURE.md is removed once the lane passes in cloud, restoring quorum 2 everywhere, and review_requirements expresses any remaining per-environment exception as data with a sunset.

## Rationale

Restores the two-vendor review quorum for cloud workers at metered API cost instead of waiting on the GX10 review lane, and replaces a prompt-level policy exception with a configured, observable lane.
