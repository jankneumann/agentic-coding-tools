# Design — Route parked escalations through the escalate-resume gate

## Context

`autopilot.run_loop` catches a phase exception, persists `current_phase=ESCALATE`, and the supervised child-result protocol exposes that state as `parked.kind=policy_pause`. `apply_delegated_batch` then persists the parent attempt as parked and releases its lease. Today `ExecutionAdapter.apply` returns at that point. `gate_router.resolve_parked` already owns the safe route from a policy pause to `Gate.ESCALATE_RESUME`, including posture evaluation, audit recording, mirror projection, and authorized resume.

## Decisions

### D1 — Route only after the complete batch is durably applied

`ExecutionAdapter.apply` remains the existing exact-result validation and `apply_delegated_batch` operation, with its signature and return shape unchanged. The host calls `ExecutionAdapter.route_parked_escalations(workspace, batch_id, repo_root, evaluator=None)` only after apply returns successfully, which proves every batch member is terminal with `application_journal.state == effects_applied`. If apply raises after an earlier member was persisted, error cleanup may report bounded candidate dispatch IDs but MUST NOT evaluate, notify, route, or resume them. Recovery first retries the exact apply batch; the application journal prevents a second `dispatch_fn` effect. Only after apply succeeds does the host route policy pauses. The route scans named-batch parked policy pauses for action and prepared `continuation.kind=policy_pause` attempts only for `already_routed` reporting.

### D2 — Serialize the decision subject, not a network wait under the workspace lock

`gate_router` owns a deterministic per-subject lock keyed by gate, roadmap, dispatch, and for `escalate_resume`, lease generation. `evaluate`, `answer`, and `resolve_parked` share private already-subject-locked helpers so `resolve_parked` holds one subject lock across prior-record lookup, file/notify/poll, projection, decision persistence, and optional resume. Public `ExecutionAdapter.resume` then takes the existing short workspace lock only for its state CAS. `route_parked_escalations` never holds the workspace lock across approval-service I/O and never calls a nested workspace-locking helper. Concurrent automatic and manual resolution of one subject therefore produce one decision/notification/resume without blocking unrelated durable operations for the gate timeout.

### D3 — Make `escalate_resume` identity generation-scoped end to end

For `escalate_resume` only, the subject key and gate-decision correlation include the parked attempt's `lease_generation`. `_correlation_extra` and the late-answer correlation copy retain that value. Same-generation retries reuse one decision; a later exhaustion is a new subject. `require_approval_ref` receives the current parked generation and refuses an old proceed reference for a later generation. Console `gate-answer` remains backward compatible: `--dispatch-id` alone resolves the newest blocked `escalate_resume` record for that dispatch and answers its recorded generation; an optional `--lease-generation` selects explicitly. A following route reuses that answer. Other gates and existing CLI calls keep their current subject identity.

The open gate-decision JSON schema documents optional `lease_generation` as the parked generation authorized by an `escalate_resume` record. No closed wire version is introduced.

### D4 — Preserve failure and gate meanings

`pending_gate` is excluded because it names the child's own gate and already has an explicit reconciliation flow. `quarantined` is excluded because uncertain liveness is not approval-resumable. Failed results remain failures. Only an ESCALATE-derived `policy_pause` in a fully applied batch is routed automatically.

### D5 — Make routing observable, bounded, and injectable

`ExecutionAdapter.route_parked_escalations` accepts an optional gate evaluator for deterministic tests and returns at most one entry per named-batch attempt. Every entry has exactly `dispatch_id`, `outcome`, and `decided_lease_generation`; `outcome` is `proceed`, `blocked`, `deferred`, or `already_routed`. `proceed` and `already_routed` additionally contain exactly `resumed_lease_generation`. `blocked` additionally contains exactly one `pending_gate` normalized through the supervisor-record allowlist. `deferred` is reserved for a recorded proceed whose state CAS could not yet complete; it never describes partial apply, which is not routed. `decided_lease_generation` names the parked generation on the gate record and `resumed_lease_generation` names its post-increment continuation.

The approval request/notification context for an automatic policy pause contains exactly `dispatch_id`, `change_id`, `item_id`, `lease_generation`, `verb`, and `reason`. Values come from the validated durable attempt; `verb` is exactly `resume` and `reason` is exactly `supervised phase retry budget exhausted`. Existing identity string bounds and the integer generation constraint apply. No output or outbound context contains a child transcript, raw approval response, child-provided reason, or additional key. `ExecutionAdapter.apply` remains unchanged.

### D6 — Fail closed per routed attempt without corrupting the applied result

After a completely successful apply, routing processes dispatch IDs in stable lexical order. If routing raises, the current attempt stays parked unless its own decision or resume already committed; earlier resolutions remain durable. A retry re-reads state, reports a prepared authorized continuation as `already_routed`, and acts only on still-parked policy pauses. The host retries only `route_parked_escalations`, never `apply`, after this boundary. This rule is distinct from a partial apply failure, which is recovered by idempotently retrying apply before routing begins.

### D7 — Resume establishes a fresh application generation

Authorized resume preserves dispatch ID, attempt number, launch token, worktree, and branch, increments `lease_generation`, and clears the prior generation's `application_journal` with its other per-generation terminal fields. `_bound_application_journal` then takes its fresh-bind path for the new result. The next child-start/acknowledge/enter/apply cycle can therefore commit a fresh journal instead of conflicting with the prior `effects_applied` result.

### D8 — Retire stale mirror entries across generations

Blocked routing synchronously projects a normalized pending gate into the supervisor mirror. When an `escalate_resume` decision is recorded for generation G, projection also removes pending entries whose decision IDs belong to earlier `escalate_resume` records for the same roadmap and dispatch at lower generations. A proceed leaves no stale pending entry. The next supervisor rehydrate selects the newer mirror over a stale or missing handoff, and the normal end-of-cycle digest writes that normalized state into the next supervisor handoff. Execute does not originate a separate coordinator handoff.

### D9 — Notification latency is scoped to one decision subject

Routing inherits `notify_with_timeout`'s synchronous polling window, and named-batch attempts are processed serially in stable order. The per-subject lock may therefore be held for one configured gate window, while the workspace state lock remains available to unrelated durable operations. The total route call can still take the sum of the configured windows and the skill reports that cost.

## Test Strategy

1. RED: a fully applied policy pause under auto posture evaluates `escalate_resume` and resumes generation 2 without lock reentrancy.
2. RED: concurrent automatic/manual resolution of one generation produces one decision, notification, and resume while an unrelated workspace transition remains available during a blocked coordinator wait.
3. RED: notify-with-timeout projects one pending gate/deadline; stale-handoff rehydrate and the next supervisor handoff preserve it.
4. RED: a partial two-member apply under auto posture does not evaluate or resume the earlier pause; exact apply replay completes without a second `dispatch_fn`, then routing resumes it.
5. RED: a routing failure after successful apply leaves `dispatch_fn` at one call and recovers by retrying only route.
6. RED: park -> route -> resume -> child-start/acknowledge/enter -> apply succeeds with a fresh application journal.
7. RED: a second exhaustion gets a new generation decision, rejects the old approval ref, and retires the older pending mirror entry; same-generation retry remains idempotent.
8. RED: backward-compatible console answer resolves the newest blocked generation, optional explicit generation works, and the next route reuses the answer without refiling.
9. Guard exact response/context keys, literal reason, prepared-continuation reporting, late-answer generation retention, and non-escalation exclusions.
10. Run supervise and recovery suites, Ruff, package/DAG/scope checks, strict change and repo-wide OpenSpec validation, and the deterministic context-drift gate.
