# Plan Review Round 3 Substantive Adjudication

The maximum review round received two schema-valid independent reviewers (Claude Code and Codex). The mechanical synthesizer reports quorum 2/2, 10 unique unconfirmed findings, 0 confirmed findings, 0 disagreements, and `blocking_count: 0`. That lossy grouping is not sufficient for substantive convergence: one reviewer supplied two independently code-traced defects that would corrupt or strand durable execution state.

## Blocking escalations

1. **Escalate/block — stale whole-checkpoint write after approval waiting.** The current gate path loads the shared checkpoint before synchronous coordinator polling and later saves that entire stale snapshot. Releasing the workspace lock during the wait lets another durable transition commit and then be silently overwritten; holding it recreates the long workspace-wide stall. The plan defines a subject lock but no fresh post-wait merge/CAS for `gate_decisions`, so it does not resolve the shared-file transaction boundary.
2. **Escalate/block — resumed member cannot be applied in a multi-member original batch.** Resume preserves a dispatch ID whose prefix binds it to the original batch, while delegated apply requires the exact whole-batch membership and revalidates every sibling's current worktree/commit/evidence. Clearing one member's application journal is insufficient; after sibling cleanup or advancement, the resumed member can be permanently unappliable. The plan tests only the single-member case and does not define a new-batch or generation-aware membership contract.

## Remaining non-blocking warnings

- Define backward-compatible reuse/retirement for legacy `escalate_resume` records without `lease_generation`.
- Apply the exact sanitized context to every policy-pause `resolve_parked` caller, including manual reconciliation.
- Enforce complete-batch `effects_applied` inside the route method, not only in host instructions.

No final-round plan changes were made because round 3 is the configured maximum and any change would require independent re-review. Outcome: `max_iter` / not converged. Implementation MUST NOT start. A human or resumed planning cycle must resolve both blockers and authorize another review round.
