# Route review convergence on per-finding dispositions

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `route-review-convergence-on-per-finding-dispositions`
> Effort: L
> Priority: 2

## Summary

In convergence_loop.converge, ask a round-level Noul("another fix round is likely to reduce blocking findings") and, per blocking finding, Choice(disposition, {fix_now, defer_to_followup, reject_out_of_scope, needs_human}) over the ledger trend, the last fix diff and each item's mark_addressed / reject_out_of_scope_fix history. Route fix_now to fix_callback, defer and reject through the existing ledger calls, and park needs_human.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- max_rounds remains a hard ceiling that no judged answer can extend, asserted by a test where the round Noul stays high.
- A replay over recorded ledger trends shows fewer fix dispatches than the stall rule for the same terminal blocking count, with both counts recorded.
- defer_to_followup and reject_out_of_scope go through the existing park_item and reject_out_of_scope_fix paths, with no new ledger mutation surface.
- needs_human parks the item as a disagreement rather than dispatching a fix, covered by a test.
- With the helper returning None the stall rule trend[-1] >= trend[-stall_window] still governs, proven by existing convergence tests passing unchanged.

## Rationale

Pilot step 4 and the change that removes the most wasted fix dispatches: the current stall rule fires on a round that fixed three findings and surfaced two, and fails to fire when a fixer keeps re-addressing a finding reviewers keep rejecting. Classifying intent before the expensive action is the point.
