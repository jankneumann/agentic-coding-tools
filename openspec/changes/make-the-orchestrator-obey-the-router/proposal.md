# Make the orchestrator obey the router

> Parent roadmap: `dispatch-governance` (dg-06; re-homed from repo-improvement ri-06)
> Change ID: `make-the-orchestrator-obey-the-router`
> Effort: M
> Priority: 1

## Summary

Resolve a typed routing assignment before every roadmap dispatch, persist its identity before invoking the host dispatcher, and make every submitted/claimed/completed vendor result prove the assignment it executed. On a vendor-limit result, obtain a fresh alternate assignment and resume the same item phase exactly once per durable attempt. Persist loop-safety state so a restarted roadmap cannot spin forever without a durable transition.

## Dependencies

- `dispatch-governance/dg-02` — structured VendorResultEnvelope and atomic ledger lifecycle
- `dispatch-governance/dg-04` — routing assignment and route-decision audit contract
- `dispatch-governance/dg-05` — canonical isolation vocabulary and precedence

## Acceptance Outcomes

- No host dispatch runs unless its context carries a validated, durable routing decision and canonical resolved isolation.
- An induced rate-limit on the preferred lane causes a fresh alternate assignment and ledger-correlated completion for the alternate lane; stale or mismatched results fail closed.
- Per-item/phase switch retries and global no-progress safeguards survive restart, checkpoint before escalation, and do not duplicate an already submitted attempt.

## Rationale

The policy engine can select lanes, but the roadmap state machine currently calls the host dispatch seam without a route contract and merely records a vendor-limit decision. This change binds the already-completed router, isolation contract, and structured completion ledger at that seam. It does not reimplement pricing, model selection, or OS-level sandbox enforcement.

## Non-goals

- Replacing dg-04 router policy or calling model SDKs from autopilot-roadmap.
- Replacing dg-02's ledger lifecycle or expanding VendorResultEnvelope with unrelated fields.
- Reimplementing catalog-aware pricing or the existing loud missing-loop-state failure.
- Enforcing the isolation posture; dg-07 owns OS-level sandbox enforcement.
