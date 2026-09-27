# Route parked escalations through the escalate-resume gate

> Parent roadmap: `roadmap-supervisor-orchestration`
> Roadmap item: `ri-06`
> Change ID: `route-parked-escalations-through-the-escalate-resume-gate`

## Why

A phase retry-budget exhaustion is durably collected as `parked.kind: policy_pause`, but it is not routed until a later session discovers it. The prior ri-06 plan correctly moved routing after complete batch application, but plan review found two blockers: its gate persistence could overwrite a concurrent checkpoint transition after approval-service waiting, and a resumed member of a multi-member batch could never apply its fresh result once peers had completed.

This recovery retains the immediate escalation outcome while defining one authoritative checkpoint transaction boundary and a safe current-generation result set.

## What Changes

After every complete delegated-batch application, a retryable routing operation processes parked `policy_pause` attempts through the existing `gate_router.resolve_parked` seam. It routes only after a runtime-enforced complete-`effects_applied` batch check; partial application recovery never evaluates or notifies a gate.

The roadmap runtime gains a shared, process-safe checkpoint transaction used by every checkpoint read-modify-write path. It serializes only short fresh reads, authoritative decision/attempt updates, and derived mirror reconciliation—never approval-service I/O. Gate routing holds a generation-scoped subject lock through one external evaluation, then rechecks the current subject inside the shared transaction. A valid proceed records its decision and advances the exact parked attempt to its next lease generation atomically; a stale candidate has no durable or mirror effect. Gate decisions become part of that one checkpoint serialization rather than a post-save sidecar rewrite.

Delegated apply changes its result-membership contract: results must exactly cover all attempts whose *current* application journal is not `effects_applied`. Already-applied peers are deliberately omitted and never revalidated or replayed. That preserves initial-batch exactness and at-most-once callbacks while admitting a fresh result for a resumed member after peer cleanup.

## Selected Approach

Use a shared checkpoint transaction plus a per-`escalate_resume` generation subject lock, and define the fresh-application batch subset by durable journal state.

This approach prevents stale whole-checkpoint writes without holding the workspace state lock during network waits, makes decision-plus-resume an atomic authority update, and fixes multi-member resume without inventing a new batch identity or weakening evidence validation.

### Approaches Considered

1. **Fresh append after approval wait** — reload the checkpoint only before appending `gate_decisions`.
   - Pros: Small code change.
   - Cons: Still leaves a decision-to-resume race and the separate sidecar write; cannot make mirror projection safe.
   - Effort: M.

2. **Hold the existing workspace lock while evaluating approval** — serialize all activity through the current execution lock.
   - Pros: Prevents stale writes.
   - Cons: Blocks unrelated transition work for a notify timeout and violates the intended availability property.
   - Effort: S.

3. **Shared short transaction with generation subject lock** — selected.
   - Pros: Preserves unrelated progress during external I/O; commits fresh decision/resume state atomically; gives a deterministic recovery path.
   - Cons: Requires migrating every checkpoint writer to one lock/serialization seam and explicit stale-candidate handling.
   - Effort: L.

## Impact

- `skills/roadmap-runtime/scripts/checkpoint.py` and models: shared checkpoint transaction and one atomic gate-decision serialization.
- `skills/supervise/scripts/gate_router.py`, `execution.py`, `cycle_state.py`: generation-scoped routing, atomic authorized resume, legacy lookup, derived mirror reconciliation, and shared sanitized context.
- `skills/autopilot-roadmap/scripts/orchestrator.py`: current-journal delegated-result membership.
- `openspec/schemas/gate-decision.schema.json`: optional positive `lease_generation` correlation.
- `skills/tests/roadmap-runtime`, `skills/tests/supervise`, and `skills/tests/autopilot-roadmap`: deterministic concurrency and resumed-batch regressions.
- `openspec/specs/supervise/spec.md` and `openspec/specs/roadmap-orchestration/spec.md`: behavior deltas.

## Out of Scope

- Changing Autopilot's retry budget, ESCALATE state machine, or notification channel.
- Automatically routing ordinary child `pending_gate` results or quarantined attempts.
- Adding a new batch identifier, weakening exact evidence validation, or replaying an already-applied peer callback.
- Changing the separate, already-completed always-on roadmap item with the same local number.

## Acceptance Outcomes

- A complete batch's `policy_pause` immediately produces one generation-scoped `escalate_resume` decision; a partial batch never does.
- A blocked approval wait cannot erase unrelated checkpoint transitions, and concurrent resolutions cannot duplicate a decision, notification, or resume.
- A valid proceed decision and the parked-to-prepared generation transition are authoritative together; mirror loss is recoverable from the checkpoint ledger.
- A resumed member in a multi-member original batch can apply its current-generation result after completed peers are cleaned up, while missing current results and historical peer results fail before any callback.
- Legacy generationless escalation records are reused for their current parked generation without duplicate filing; later generations reject stale approval references.
