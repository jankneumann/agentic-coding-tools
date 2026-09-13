# Design: harden-substantive-review-gates

## Context

`ReviewResult.success` currently means parsed and schema-valid, and that same bit determines quorum. The convergence loop receives all results only after `dispatch_and_wait()` completes, then checkpoints them as a batch. Ledger policy intentionally keeps unconfirmed judgment findings out of the automatic-fix blocking set, but currently also lets high-impact ones pass convergence.

## Goals / Non-Goals

Goals:

- Close the exact false-quorum, false-convergence, and interruption-loss windows demonstrated by `ri-09`, `ri-06`, and `ri-12`.
- Keep the dispatcher API backward compatible.
- Preserve automated fixing only for existing blocking classes.

Non-goals:

- Define a general positive-evidence or reviewer-attestation contract.
- Redesign disagreement consensus semantics.
- Replace local checkpoints with a coordinator completion ledger.

## Decisions

### D1: Reject placeholder-only terminal output at ingestion

A response is non-substantive when its only findings or wrapper message match explicit provisional markers such as “placeholder”, “review pending”, or “while review runs”. It remains preserved as raw output but returns `success=False` with `non_substantive_placeholder`. A real substantive finding is not rejected merely because it quotes such language elsewhere.

### D2: Adjudication is separate from automatic fixing

The ledger derives open, unconfirmed, judgment-class findings with high or critical impact. If any exist, convergence returns `adjudication_required`, invokes the escalation callback, and never invokes the fix callback. Low and medium unconfirmed judgments remain advisory.

### D3: Terminal completion drives write-through checkpointing

`dispatch_and_wait()` accepts an optional callback receiving `(result, expected_count)`. It calls the callback exactly once for each terminal result from its collector thread. Async submission success is not terminal; only submission failure or the eventual poll result is emitted.

### D4: Every incremental checkpoint is independently readable

The convergence callback atomically writes raw output, successful findings, and a manifest after every terminal result. `quorum_requested` is the expected panel size and `quorum_received` is the successful result count seen so far. The final batch write remains idempotent.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Safety: zero placeholder quorum votes | Historical Grok placeholder regression | new |
| Recoverability: all terminal callbacks durable | Interrupted-panel checkpoint regression | new |
| Compatibility: zero focused regressions | Dispatcher and convergence pytest suites | existing |

## Alternatives Considered

- Quorum-eligibility metadata was deferred to the overlapping atomic-harness work because it changes several public data shapes.
- A required review-evidence schema was rejected for this recovery because it would invalidate all current vendor outputs.
- Post-return persistence was rejected because it leaves the demonstrated interruption window open.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Marker detection rejects quoted placeholder language | Reject only when the whole response is placeholder-only |
| Callback failure yields partial panel execution | Fail closed and preserve the original checkpoint error |
| New adjudication exit surprises callers | Reuse existing non-converged result and escalation surfaces |
| Concurrent completions lose manifest entries | Invoke callbacks from the single collector thread and rewrite atomically |

## Migration Plan

The callback is optional and last in the method signature. Existing callers and cached manifests remain valid. Rollback removes the callback and adjudication branch; no durable data migration is required.
