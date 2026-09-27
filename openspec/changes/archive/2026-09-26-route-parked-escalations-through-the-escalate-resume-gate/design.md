# Design — Route parked escalations through the escalate-resume gate

## Context

The original ri-06 design was stopped before implementation because a stale pre-wait checkpoint snapshot could overwrite a concurrent transition, and its exact-whole-batch result rule stranded resumed members. The checkpoint is the execution authority; the supervisor mirror and handoff are derived views. This design closes both authority boundaries before immediate routing is introduced.

## Decisions

### D1 — Route only after the runtime proves complete batch application

`ExecutionAdapter.route_parked_escalations(workspace, batch_id, repo_root, evaluator=None)` SHALL load the named batch and verify every member is terminal with `application_journal.state == effects_applied` before it evaluates, files, projects, or resumes anything. It scans only parked `policy_pause` attempts in stable dispatch-ID order and reports already-prepared policy-pause continuations as `already_routed`.

A partial apply error may expose bounded candidate IDs for diagnostics, but SHALL not call routing. Recovery replays apply through the journal first; after the complete-apply boundary a routing failure retries routing only. Ordinary `pending_gate`, failed, and quarantined attempts remain excluded.

### D2 — One shared checkpoint transaction is the authority boundary

Roadmap runtime SHALL expose one process-safe per-workspace transaction mechanism. It uses the same lock namespace for execution, router, and direct orchestrator checkpoint writers, loads the current checkpoint *inside* the lock, invokes a bounded mutation callback, and writes one atomic checkpoint payload. `gate_decisions` becomes a serialized checkpoint field in that same payload; there is no post-save sidecar read/overwrite step.

Every current checkpoint read-modify-write path migrates to this mechanism or a non-reentrant helper invoked under it. The old execution-private lock is moved behind this shared interface so router and execution cannot serialize different snapshots. The transaction lock never covers approval service calls, notification polling, host callback execution, or other network I/O.

### D3 — Subject lock plus fresh-CAS commits the decision and proceed transition

`escalate_resume` has a process-safe per-subject lock keyed by roadmap, dispatch ID, and parked lease generation. Automatic routing, manual resolution, and answering use the same subject lock. The holder may evaluate/check a prior approval outside the workspace transaction. Before recording a new outcome it enters the shared checkpoint transaction, reloads current state, re-applies the prior-record rule, and verifies the exact attempt is still parked with the expected `policy_pause` and generation.

For a blocked decision, the fresh transaction appends one decision record. For proceed, the same transaction appends the record and converts that exact attempt from parked G to prepared G+1, clearing its generation-G terminal fields and journal. It returns the durable continuation request. A candidate that no longer matches is stale: it does not append, project, or resume. A concurrent resolver reuses the winning current record rather than filing another approval.

The router validates a pending-gate projection before authority commit so refusal creates no record. It projects derived mirror state only after the authoritative transaction; the short transaction serializes mirror read/merge/write for different subjects. Projection failure never rolls back authority and is reconciled idempotently from the ledger on rehydrate/gate-log.

### D4 — Escalate identity is generation-aware and legacy-safe

New `escalate_resume` records carry optional positive integer `lease_generation`. Subject lookup, late answers, approval references, mirror retirement, and optional `gate-answer --lease-generation` all use it. A dispatch-only answer selects the newest blocked generation. `require_approval_ref` rejects a proceed whose recorded generation differs from the currently parked generation.

A legacy generationless `escalate_resume` record matches the current parked generation once, is reused rather than refiled, and is retired with older same-dispatch mirror entries once a newer generation is recorded. Other gate identities remain unchanged.

### D5 — Policy-pause context is always sanitized at the shared seam

Every `policy_pause` call to `resolve_parked`, automatic or manual, builds exactly:
`dispatch_id, change_id, item_id, lease_generation, verb: resume, reason: supervised phase retry budget exhausted`.
Values come from the current validated attempt. Child-provided reason, transcript, raw approval response, and additional keys never enter outbound context, route output, checkpoint record, or pending mirror entry. Blocked output contains only normalized pending-gate data.

### D6 — Current journal state defines required apply membership

For a named batch, `apply_delegated_batch` derives its required result IDs from attempts whose current journal state is not `effects_applied`. Submitted IDs must exactly equal that nonempty set before callbacks or state mutation. Omitted attempts are valid only when already `effects_applied`; submitted results retain all current identity, generation, isolation, evidence, digest, and at-most-once journal checks.

Thus an untouched initial batch still requires every member. After A parks, B completes, and A is authorized to G+1, only A's current result is admitted. A historical B result is rejected rather than revalidated, and a missing resumed member fails before any callback. A terminal-persisted-but-not-effects-applied attempt remains required for crash recovery.

## Test Strategy

1. Block routing after its evaluation snapshot, concurrently commit unrelated child transition and apply mutations, then prove both survive with exactly one decision record.
2. Change the target attempt while routing waits and prove the stale candidate cannot resume, append, or project.
3. Race automatic/manual resolution and prove one evaluation, notification, decision, and generation bump; prove two different blocked subjects retain both mirror entries.
4. Inject a checkpoint-save boundary and prove visible state has either old or new checkpoint-plus-gate-decision payload, never a separate sidecar state.
5. Verify complete-batch guard, post-apply route retry, exact sanitized context, exclusions, legacy reuse, generation answer selection, and stale-ref rejection.
6. Prove two-member park → route → G+1 resume → fresh A-only apply after B cleanup; cover multiple resumed members, missing subset, historical peer, stale generation, and terminal-persisted recovery.
