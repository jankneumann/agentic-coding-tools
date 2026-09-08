# Route parked escalations through the escalate-resume gate

> Parent roadmap: `roadmap-supervisor-orchestration`
> Roadmap item: `ri-06`
> Change ID: `route-parked-escalations-through-the-escalate-resume-gate`

## Why

A supervised Autopilot child already enters `ESCALATE` when a phase sub-agent exhausts its retry budget. The child is collected as a durable `policy_pause` attempt, but `ExecutionAdapter.apply` stops after marking it parked. The existing `gate_router.resolve_parked` mapping from `policy_pause` to `escalate_resume` therefore runs only when a later session happens to discover the parked attempt. The structured phase-failed handoff exists, yet notification and the supervisor pending-gate deadline do not happen at the failure boundary.

## What Changes

After a delegated batch result is validated and durably applied, the supervise host invokes a separate `ExecutionAdapter.route_parked_escalations` operation, including from the apply error-cleanup path when an earlier member of a partially applied batch may already be durable. The operation routes each newly parked `policy_pause` attempt through `gate_router.resolve_parked`. The gate router remains the single approval-service seam: it evaluates `escalate_resume`, reuses prior decisions idempotently for the same dispatch generation, sends `notify_with_timeout` notifications, and projects blocked decisions with deadlines into the supervisor mirror. A proceed decision resumes the same durable dispatch into its next lease generation; a blocked decision leaves it parked. Ordinary child `pending_gate` results and quarantined attempts keep their current paths.

`route_parked_escalations` returns its own allowlisted, bounded resolution list so the host can report whether each exhausted dispatch resumed, remains pending, or was already routed without reading a transcript. `ExecutionAdapter.apply` retains its exact existing return shape. Keeping routing as a retryable post-apply operation means a coordinator error cannot replay the already-acknowledged `dispatch_fn` effect.

## Selected Approach

Route from a separately retryable cleanup step after `apply_delegated_batch` has persisted any terminal attempt, never before exact-result validation. At that point the correlated result and exact loop-state evidence have been checked, the callback has been acknowledged, the attempt is durably `parked`, its lease is released, and `resolve_parked` can safely use the existing authorized resume CAS. The route owns one workspace serialization boundary and delegates resume to a non-locking internal helper to avoid nested `flock` acquisition. This keeps approval policy out of `phase_agent.py` and `autopilot-roadmap`, avoids a second gate implementation, and makes retries consult a generation-scoped prior record.

## Impact

- `skills/supervise/scripts/execution.py`: retryable post-persist policy-pause routing and bounded resolution summary.
- `skills/supervise/scripts/gate_router.py`: generation-scoped `escalate_resume` decision identity and sanitized escalation context.
- `skills/tests/supervise/`: TDD coverage for auto, notify-with-timeout, idempotent repeat, and exclusions.
- `skills/supervise/SKILL.md`: collect/apply protocol documents immediate escalation routing.
- `openspec/specs/supervise/spec.md`: durable behavior after archive.

## Out of Scope

- Changing Autopilot's three-attempt retry budget or its ESCALATE state machine.
- Adding a new gate or notification channel.
- Automatically resolving ordinary child `pending_gate` results.
- Approval-resuming quarantined attempts or weakening exact-result validation.
- Sweeping policy pauses from earlier batches; those keep the existing manual reconciliation path.

## Dependencies

- ri-04: the supervisor gate router and approval audit/mirror projection are complete.
- ri-05: the supervisor handoff record carries pending gates and deadlines.
- always-on ri-06: Autopilot gates, including `escalate_resume`, are encoded in code.

## Acceptance Outcomes

- An exhausted phase dispatch is durably parked and immediately produces one `escalate_resume` evaluation, never only a phase-failed handoff note.
- Under `notify_with_timeout`, the evaluation files/notifies within the configured gate window and returns a bounded pending resolution.
- A blocked evaluation remains in the supervisor mirror/handoff as a pending gate with its computed deadline.
- A routing failure never causes `apply` or `dispatch_fn` to be replayed, and a later retry resumes from durable routing state.
- A later exhaustion of the same dispatch is a new generation-scoped escalation decision rather than silent reuse of an old proceed.
