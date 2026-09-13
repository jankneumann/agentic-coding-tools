# Change: harden-substantive-review-gates

## Why

Three historical supervisor-roadmap failures exposed ways that a review round can look complete without being trustworthy or recoverable. A schema-valid placeholder can count toward quorum, unconfirmed high-impact judgment can pass through the zero-blocker convergence branch, and completed vendor responses are not checkpointed until the entire panel returns.

These defects must be closed before retrying `ri-12` and `ri-09`; otherwise a retry could falsely converge or lose completed work when the supervising process is interrupted.

## What Changes

- Treat placeholder-only review output as an unsuccessful terminal result with a stable error code, so it cannot count toward quorum.
- Route unconfirmed high/critical judgment findings to adjudication and stop convergence without sending them to the automated fix callback.
- Add an optional per-result callback to concurrent review dispatch and use it to atomically checkpoint every terminal vendor result before the panel returns.
- Preserve returned result ordering and compatibility for orchestrators that do not support the new callback.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Safety | Historical placeholder fixture counted toward quorum | 0 occurrences | Focused dispatcher tests |
| Recoverability | Completed vendor results recoverable after an interrupted panel | 100% of terminal callbacks | Checkpoint interruption test |
| Compatibility | Existing focused review/convergence tests regress | 0 failures | Implementation validation |

## Approaches Considered

### Approach 1: Narrow fail-closed incident guard

Reject placeholder-only output at the existing ingestion boundary, add a distinct adjudication exit in convergence, and introduce an optional terminal-result callback for write-through checkpoints. This preserves current contracts and confines the change to the demonstrated failure modes.

### Approach 2: Separate quorum-eligibility metadata

Add `counts_toward_quorum` and structured evidence fields across review results, manifests, and consensus contracts. This is more expressive but overlaps the active atomic-harness and structured-vendor-channel changes.

### Approach 3: Breaking evidence-attestation schema

Require every clean or actionable review to enumerate inspected artifacts and checks. This provides the strongest positive proof but would break every current vendor prompt and deterministic emitter.

### Recommended

Approach 1 closes the recovery blockers with the smallest compatible surface. The broader eligibility and structured completion contracts remain owned by their existing proposals.

### Selected Approach

The user selected Approach 1 by directing implementation of the proposed recovery order: harden review gates first, then retry `ri-12`, `ri-09`, and revise `ri-06`.

## Impact

- Affected capability: `review-convergence-safety`.
- Runtime: `review_dispatcher.py`, `checkpoint_findings.py`, `review_ledger.py`, and `convergence_loop.py`.
- Tests: focused dispatcher and convergence suites.
- Relationship: `build-structured-vendor-result-channel` remains responsible for the broader typed completion ledger; `rescope-review-convergence-disagreement-routing` remains responsible for general disagreement policy.
