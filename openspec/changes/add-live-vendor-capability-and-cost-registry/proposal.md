# Add live vendor capability and cost registry

> Parent roadmap: `repo-improvement`
> Change ID: `add-live-vendor-capability-and-cost-registry`
> Effort: M
> Priority: 1

## Summary

Add a coordinator vendor_registry service holding static capabilities from agents.yaml plus dynamic availability, rate-limit windows with known reset times, and a versioned real cost table replacing the policy.py stub tiers; expose GET /vendors and GET /vendors/{id}/availability, teach coordination_bridge.py the same, and delete the hardcoded vendor list in orchestrator.py.

## Dependencies

- None

## Acceptance Outcomes

- evaluate_policy receives live availability and real cost deltas from the registry.
- Taking a vendor offline or hitting its limit is visible in the registry within one probe interval and changes routing output.
- No hardcoded vendor list remains in orchestrator.py; available vendors come from the registry filtered by capability.

## Rationale

Routing is reactive because vendor selection has only static config and stub cost estimators; a live registry gives the router and policy engine real availability and cost inputs (fixes weakness W1).
