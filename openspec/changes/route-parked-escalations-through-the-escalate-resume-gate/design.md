# Design — Route parked escalations through the escalate-resume gate

## Context

`autopilot.run_loop` catches a phase exception, persists `current_phase=ESCALATE`, and the supervised child-result protocol exposes that state as `parked.kind=policy_pause`. `apply_delegated_batch` then persists the parent attempt as parked and releases its lease. Today `ExecutionAdapter.apply` returns at that point. `gate_router.resolve_parked` already owns the only safe route from a policy pause to `Gate.ESCALATE_RESUME`, including posture evaluation, audit recording, mirror projection, and authorized resume.

## Decisions

### D1 — Route only after terminal application persistence

`ExecutionAdapter.apply` remains the existing exact-result validation and `apply_delegated_batch` transaction, with its return shape unchanged. The host calls `ExecutionAdapter.route_parked_escalations(workspace, batch_id, repo_root, evaluator=None)` after apply returns and from apply's error-cleanup path, because `apply_delegated_batch` may have durably parked an earlier member before a later member fails. The route reloads durable state and considers only attempts from the named batch. It routes attempts whose current status is `parked` and whose `parked.kind` is `policy_pause`; a prepared continuation already authorized by a policy-pause decision may be reported as `already_routed` but is never routed again. Gate evaluation never precedes exact-result validation or durable parking. If both apply and route fail, the host preserves and reports both errors; recovery retries only route, never apply.

### D2 — Serialize once without nested `flock`

`route_parked_escalations` owns one workspace `_serialized_transition` boundary covering candidate re-read, gate evaluation persistence, and optional resume. It processes dispatch IDs in stable lexical order, re-reads each candidate immediately before resolving it, and never saves its scan-time checkpoint. Because `gate_router.resolve_parked` calls back into resume on proceed, public `ExecutionAdapter.resume` and routed resume share a private `_resume_locked` helper: public resume acquires the workspace lock before the helper, while the route passes a narrow adapter facade that calls the helper under the already-held lock. The route MUST NOT acquire a second file descriptor lock through public `resume`. This prevents duplicate file/notify races and avoids non-reentrant `flock` deadlock.

### D3 — Reuse `gate_router.resolve_parked` with generation-scoped identity

No approval logic is copied into execution or Autopilot. The adapter calls `resolve_parked(attempt, workspace, repo_root, adapter=<locked-resume-facade>, evaluator=...)`. That function maps the pause to `escalate_resume`, applies the prior-record rule, projects blocked decisions, and resumes only with a recorded `gate-decision:<id>` authorization. For `escalate_resume` only, the subject key and recorded correlation include the parked attempt's `lease_generation`; retries of one parked generation reuse one decision, while a later exhaustion after resume is a new decision subject. Other gate subject keys remain backward compatible.

### D4 — Preserve failure and gate meanings

`pending_gate` is excluded because it names the child's own gate and already has an explicit reconciliation flow. `quarantined` is excluded because uncertain liveness is not approval-resumable. Failed results remain failures. Only an ESCALATE-derived `policy_pause` represents the parked escalation this change owns.

### D5 — Make routing observable, bounded, and injectable

`ExecutionAdapter.route_parked_escalations` accepts an optional gate evaluator for deterministic tests and returns at most one entry per attempt belonging to the named batch. Every entry has exactly `dispatch_id` and `outcome`; `outcome` is `proceed`, `blocked`, or `already_routed`. A `proceed` entry may add only `lease_generation`. A `blocked` entry adds only a `pending_gate` normalized through the existing supervisor-record allowlist. No entry contains child transcripts, raw approval responses, or the child-provided parked reason. For policy pauses, the router receives a fixed bounded reason such as `supervised phase retry budget exhausted`, not untrusted child prose. Existing dispatch-ID and pending-gate field bounds apply. `ExecutionAdapter.apply` and all existing apply result keys remain unchanged.

### D6 — Fail closed per attempt without corrupting the applied result

If gate routing raises after an attempt is durably parked, that attempt stays parked unless its own resolution already committed. Resolutions are applied in stable dispatch-ID order. On a later-attempt error the operation raises; already-resolved attempts remain durable, and retry re-reads state, reports an authorized prepared continuation as `already_routed`, and resumes only still-parked policy pauses. The host retries `route_parked_escalations` directly, never `apply`, so the already-applied batch is not replayed through `dispatch_fn`. The serialized, generation-scoped prior-record rule prevents duplicate approvals, notifications, and audit records.

### D7 — Resume establishes a fresh application generation

Authorized resume preserves dispatch ID, attempt number, launch token, worktree, and branch, increments `lease_generation`, and clears the prior generation's `application_journal` with its other per-generation terminal fields. The next child-start/acknowledge/enter/apply cycle therefore binds a fresh result journal instead of conflicting with the prior `effects_applied` result.

### D8 — Mirror is the execute-time durability path

Blocked routing relies on `gate_router`'s synchronous supervisor-mirror projection. Execute does not originate a separate coordinator handoff. The next supervisor rehydrate selects the newer mirror over a stale or missing handoff, retains the normalized `escalate_resume` pending gate and `requested_at + timeout_seconds` deadline, and the normal end-of-cycle digest writes that record into the next supervisor handoff. The tests cover mirror projection, stale-handoff rehydrate, and rendered handoff payload.

### D9 — Notification latency is explicit

Routing inherits `notify_with_timeout`'s synchronous per-attempt poll window. Attempts are processed serially in stable order, so the worst-case batch duration is the sum of those configured windows. The skill reports that behavior and the retry protocol; it does not introduce an independent timeout or notification channel.

## Test Strategy

1. RED: a policy-pause result applied under an auto posture routes without deadlock, evaluates `escalate_resume`, and resumes generation 2.
2. RED: two concurrent routing calls produce one generation-scoped gate record/notification and one resume.
3. RED: notify-with-timeout calls the coordinator once, leaves the attempt parked, and projects a pending gate with the configured deadline; stale-handoff rehydrate and the next handoff preserve it.
4. RED: a forced routing error after successful apply leaves `dispatch_fn` at one call and recovers by retrying only route; a partial two-member apply still routes the earlier durable pause.
5. RED: park -> route -> resume -> child-start/acknowledge/enter -> apply succeeds with a fresh application journal.
6. RED: a second policy pause after an earlier proceed gets a new generation-scoped decision; retrying the same generation reuses its prior record.
7. Guard: exact response keys/bounds, fixed notification reason, stable partial-batch retry, ordinary `pending_gate`, failed, and quarantined paths.
8. Guard the SKILL host sequence and prose-free gate-name invariant, then run supervise, autopilot-roadmap, phase-recovery, Ruff, scope, and strict OpenSpec validation.
