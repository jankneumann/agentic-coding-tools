# Design — Route parked escalations through the escalate-resume gate

## Context

`autopilot.run_loop` catches a phase exception, persists `current_phase=ESCALATE`, and the supervised child-result protocol exposes that state as `parked.kind=policy_pause`. `apply_delegated_batch` then persists the parent attempt as parked and releases its lease. Today `ExecutionAdapter.apply` returns at that point. `gate_router.resolve_parked` already owns the only safe route from a policy pause to `Gate.ESCALATE_RESUME`, including posture evaluation, audit recording, mirror projection, and authorized resume.

## Decisions

### D1 — Route only after terminal application persistence

`ExecutionAdapter.apply` remains the existing exact-result validation and `apply_delegated_batch` transaction. Immediately after it succeeds, the host calls `ExecutionAdapter.route_parked_escalations(workspace, batch_id, repo_root, evaluator=None)`. That method reloads the checkpoint and routes only attempts from the applied batch whose durable status is `parked` and whose `parked.kind` is `policy_pause`. Gate evaluation never precedes result correlation or durable parking.

### D2 — Reuse `gate_router.resolve_parked`

No approval logic is copied into execution or Autopilot. The adapter calls `resolve_parked(attempt, workspace, repo_root, adapter=self, evaluator=...)`. That existing function maps the pause to `escalate_resume`, applies the prior-record rule, projects blocked decisions, and calls `resume` only with a recorded `gate-decision:<id>` authorization.

### D3 — Preserve failure and gate meanings

`pending_gate` is excluded because it names the child's own gate and already has an explicit reconciliation flow. `quarantined` is excluded because uncertain liveness is not approval-resumable. Failed results remain failures. Only an ESCALATE-derived `policy_pause` represents the parked escalation this change owns.

### D4 — Make routing observable and injectable

`ExecutionAdapter.route_parked_escalations` accepts an optional gate evaluator for deterministic tests and returns entries containing `dispatch_id`, `outcome`, and a bounded pending-gate entry when blocked. It never exposes approval-service responses or child transcripts. `ExecutionAdapter.apply` and all existing return keys remain unchanged.

### D5 — Fail closed without corrupting the applied result

If gate routing raises after the attempt is durably parked, the attempt stays parked and the routing call surfaces the error. The host retries `route_parked_escalations` directly, never `apply`, so the already-applied batch is not replayed through `dispatch_fn`. The router's subject-key prior-record rule prevents duplicate approvals and audit records.

## Test Strategy

1. RED: a policy-pause result applied under an auto posture must evaluate `escalate_resume` and resume generation 2.
2. RED: notify-with-timeout must call the coordinator once, leave the attempt parked, and project a pending gate with the configured deadline.
3. RED: repeated routing reuses the recorded decision without duplicate notification/audit.
4. Guard: ordinary `pending_gate`, failed, and quarantined paths are unchanged.
5. Run supervise, autopilot-roadmap, and phase-recovery suites plus strict OpenSpec validation.
