# Route parked escalations through the escalate_resume gate

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `route-parked-escalations-through-the-escalate-resume-gate`
> Effort: S
> Priority: 2

## Summary

Replace escalations that today die in handoff prose (for example a phase dispatch failed after two attempts) with routing through the `escalate_resume` gate, so they notify per trust posture instead of waiting to be discovered by a later session. Consumes the always-on roadmap's ri-05/ri-06 gate machinery; this item adds only the routing.

## Dependencies

- `ri-04`
- `ri-05`

## Acceptance Outcomes

- A twice-failed phase dispatch produces an escalate_resume gate evaluation, never only a handoff note.
- Under a notify_with_timeout posture, the twice-failed dispatch produces a notification within the configured timeout window.
- The failure is still recorded in the supervisor handoff record as a pending gate with its deadline.

## Rationale

Parked escalations discovered by accident are the failure mode the supervisor exists to eliminate; wiring them into the gate service closes that gap with existing machinery.
