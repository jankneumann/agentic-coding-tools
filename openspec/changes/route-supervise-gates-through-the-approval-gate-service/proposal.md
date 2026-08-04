# Route supervise gates through the approval gate service

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `route-supervise-gates-through-the-approval-gate-service`
> Effort: M
> Priority: 1

## Summary

Evaluate every gate the stack raises during supervised execution through `skills/shared/approval_gate.py` against the repo's `TRUST_POSTURE.md`, auto-approving where delegated, notifying with timeout where reversible, and blocking where posture requires. Requires the always-on roadmap's ri-06 (encode autopilot gates in code) to have landed so gate call sites exist to route; no new gate prose is introduced.

## Dependencies

- `ri-03`

## Acceptance Outcomes

- A single conversation takes a natural-language request to a merged PR with the human touched only at gates whose posture is not auto.
- Every gate raised during a supervised run appears in the approval gate service's evaluation log with the posture that was applied.
- No gate decision in a supervised run bypasses approval_gate.py, verified by test or audit over a full run.

## Rationale

Escalating only real decisions is a guiding principle; routing all human touchpoints through the existing trust posture and gate service is what lets a conversation reach a merged PR with minimal human interruption.
