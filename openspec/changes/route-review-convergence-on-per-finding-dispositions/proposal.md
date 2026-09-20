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

- max_rounds remains a hard ceiling that no judged answer can extend, asserted by a test where the round Noul stays high across every round of a max_rounds-length run.
- A replay over a fixture-constructed ledger trend sequence (recorded per-round blocking counts and dispositions) shows fewer fix dispatches than the old stall rule for the same terminal blocking count, with both counts recorded in the replay output; comparing against genuine multi-round production trends is deferred until autopilot persists real trend history from normal runs.
- defer_to_followup and reject_out_of_scope both route through the existing park_item(ledger, item, reason=...) call -- the same function needs_human already uses for disagreement -- distinguished only by the reason string passed in, so no new ledger mutation surface is introduced; covered by a test asserting all three dispositions produce a "parked" item via that one function.
- needs_human parks the item via park_item(..., reason="disagreement") rather than dispatching a fix, covered by a test.
- With the helper returning None, every blocking item defaults to fix_now and the stall rule trend[-1] >= trend[-stall_window] still governs exactly as before, proven by the existing convergence tests in skills/autopilot/scripts/tests/test_convergence_loop.py and skills/tests/autopilot/test_convergence_loop.py passing unchanged.

## Rationale

Pilot step 4 and the change that removes the most wasted fix dispatches: the current stall rule fires on a round that fixed three findings and surfaced two, and fails to fire when a fixer keeps re-addressing a finding reviewers keep rejecting. Classifying intent before the expensive action is the point.

**Grounding correction (2026-09-18):** the scaffolded text above named `reject_out_of_scope_fix` as the existing path for the `reject_out_of_scope` disposition. That function is a POST-fix scope check -- `reject_out_of_scope_fix(files_modified, allowed)` raises `ScopeViolation` when an already-applied diff strayed outside the cited paths; it takes no ledger item and cannot mark a finding out-of-scope before a fix is ever attempted. `park_item(ledger, item, reason=...)` is the one existing function generic enough to shelve a finding pre-fix, already used for `needs_human`/disagreement; `defer_to_followup` and `reject_out_of_scope` reuse it with a distinct `reason` string. Also, no round-by-round ledger trend history is persisted anywhere today -- `converge()`'s `trend` list is a local variable, never serialized -- so the replay outcome is scoped to a fixture-constructed sequence, deferring real production-trend comparison the same way ri-04/ri-06/ri-07 deferred their own real-data measurements.
