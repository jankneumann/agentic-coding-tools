# Build approval gate service (interviewer abstraction)

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `build-approval-gate-service-interviewer-abstraction`
> Effort: M
> Priority: 1

## Summary

A shared library (skills/shared/approval_gate.py) modeled on attractor's Interviewer interface that consults the trust posture and executes auto, notify_with_timeout (via request_approval plus reply-to-approve notifications and check_approval polling with default action on expiry), or block dispositions.

## Dependencies

- `ri-04`

## Acceptance Outcomes

- All four disposition paths (auto, notify_with_timeout resolved, notify_with_timeout defaulted, block) are covered by tests.
- Coordinator-unreachable degrades to block, covered by a test.
- Every gate decision, including auto and defaulted ones, lands in the audit log with the posture that authorized it.

## Rationale

Wires the existing approval queue and notification service into a single reusable gate primitive so gates stop being prose; core of the "wire before building" principle.
