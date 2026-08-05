# Route supervise gates through the approval gate service

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `route-supervise-gates-through-the-approval-gate-service`
> Effort: M
> Priority: 1

## Summary

Evaluate every gate the stack raises during supervised execution through `skills/shared/approval_gate.py` against the repo's `TRUST_POSTURE.md`, auto-approving where delegated, notifying with timeout where reversible, and blocking where posture requires. Requires the always-on roadmap's ri-06 (encode autopilot gates in code) to have landed so gate call sites exist to route; no new gate prose is introduced.

## Dependencies

- `ri-03`

**BLOCKED** — status is `blocked`, not `approved`, so `/autopilot-roadmap` will not
select this item (`orchestrator.py` `_get_ready_items` admits only `approved` /
`in_progress`). The blocker is cross-roadmap and therefore cannot be expressed in
`depends_on`, which the DAG validator restricts to in-roadmap item ids:

- `roadmap-always-on-agent-automation:ri-06` → change
  `encode-autopilot-gates-and-goal-gate-in-code`, which moves the prose gates into
  `autopilot.py` and creates the gate call sites this item routes through
  `skills/shared/approval_gate.py`. Routing gates that do not yet exist as call
  sites would mean inventing them here — exactly the duplication the ordering avoids.

**To unblock:** once `encode-autopilot-gates-and-goal-gate-in-code` is completed,
set this item's status to `approved` and clear `blocked_by` in
`openspec/roadmaps/roadmap-supervisor-orchestration/roadmap.yaml`.

## Acceptance Outcomes

- A single conversation takes a natural-language request to a merged PR with the human touched only at gates whose posture is not auto.
- Every gate raised during a supervised run appears in the approval gate service's evaluation log with the posture that was applied.
- No gate decision in a supervised run bypasses approval_gate.py, verified by test or audit over a full run.

## Rationale

Escalating only real decisions is a guiding principle; routing all human touchpoints through the existing trust posture and gate service is what lets a conversation reach a merged PR with minimal human interruption.
