# Route parked escalations through the escalate-resume gate

> Parent roadmap: `roadmap-supervisor-orchestration`
> Roadmap item: `ri-06`
> Change ID: `route-parked-escalations-through-the-escalate-resume-gate`

## Why

A supervised Autopilot child already enters `ESCALATE` when a phase sub-agent exhausts its retry budget. The child is collected as a durable `policy_pause` attempt, but `ExecutionAdapter.apply` stops after marking it parked. The existing `gate_router.resolve_parked` mapping from `policy_pause` to `escalate_resume` therefore runs only when a later session happens to discover the parked attempt. The structured phase-failed handoff exists, yet notification and the supervisor pending-gate deadline do not happen at the failure boundary.

## What Changes

After a delegated batch result is validated and durably applied, `ExecutionAdapter.apply` immediately routes each newly parked `policy_pause` attempt through `gate_router.resolve_parked`. The gate router remains the single approval-service seam: it evaluates `escalate_resume`, reuses prior decisions idempotently, sends `notify_with_timeout` notifications, and projects blocked decisions with deadlines into the supervisor mirror. A proceed decision resumes the same durable dispatch generation through the existing `ExecutionAdapter.resume`; a blocked decision leaves it parked. Ordinary child `pending_gate` results and quarantined attempts keep their current paths.

The apply result gains a bounded `escalation_resolutions` list so the host can report whether each exhausted dispatch resumed or remains pending without reading a transcript.

## Selected Approach

Route after `apply_delegated_batch`, never before it. At that point the correlated result and exact loop-state evidence have been checked, the callback has been acknowledged, the attempt is durably `parked`, its lease is released, and `resolve_parked` can safely reuse the existing authorized resume CAS. This keeps approval policy out of `phase_agent.py` and `autopilot-roadmap`, avoids a second gate implementation, and makes a repeated apply/resume follow the router's prior-record rule.

## Impact

- `skills/supervise/scripts/execution.py`: post-persist policy-pause routing and bounded resolution summary.
- `skills/tests/supervise/`: TDD coverage for auto, notify-with-timeout, idempotent repeat, and exclusions.
- `skills/supervise/SKILL.md`: collect/apply protocol documents immediate escalation routing.
- `openspec/specs/supervise/spec.md`: durable behavior after archive.

## Out of Scope

- Changing Autopilot's three-attempt retry budget or its ESCALATE state machine.
- Adding a new gate or notification channel.
- Automatically resolving ordinary child `pending_gate` results.
- Approval-resuming quarantined attempts or weakening exact-result validation.

## Dependencies

- ri-04: the supervisor gate router and approval audit/mirror projection are complete.
- ri-05: the supervisor handoff record carries pending gates and deadlines.
- always-on ri-06: Autopilot gates, including `escalate_resume`, are encoded in code.

## Acceptance Outcomes

- An exhausted phase dispatch is durably parked and immediately produces one `escalate_resume` evaluation, never only a phase-failed handoff note.
- Under `notify_with_timeout`, the evaluation files/notifies within the configured gate window and returns a bounded pending resolution.
- A blocked evaluation remains in the supervisor mirror/handoff as a pending gate with its computed deadline.
