# Bind merge verdicts to head SHA and patch-id

> Parent roadmap: `verification-enforcement-discipline` (item `ri-01`)
> Change ID: `bind-merge-verdicts-to-head-sha-and-patch-id`
> Effort: L
> Priority: 1

## Why

`/merge-pull-requests` decides whether a PR may merge from a vendor-review
"verdict". As implemented, that verdict is not bound to the code it reviewed,
and absence of a verdict is usually a pass.

1. **Nothing records what was reviewed.**
   - `vendor_review.py` never writes the PR's `head_sha`. The only SHA it
     captures is the *local checkout's* HEAD for the head guard
     (`_helpers.capture_head`, 109-118).
   - `merge_pr.get_pr_status` (78-88) does not request `headRefOid`, so the
     live status has no head SHA either.
   - `gh pr merge` is invoked without `--match-head-commit` (`merge_pr.py:382`),
     so a push between review and merge merges unreviewed code.
2. **The "verdict is current" check is dead code.**
   - `execute_plan._iterate_consensus_current` (221-228) compares
     `vendor_verdict.head_sha` to the live head. Nothing writes
     `iterate_consensus_path` (`build_plan.py:177` sets `None`), and live status
     carries no `head_sha`.
   - SKILL.md:141-142 and the spec scenario
     `merge-pull-requests.skip-pr-diff-review-after-iterate` both document this
     skip as if it works.
3. **Missing or ineligible verdicts pass.**
   - `execution_safety.vendor_review_block_reason` (52-76) returns `None`
     (pass) for every ineligible reason except `changes_requested`. That covers
     `small_pr`, `has_approval`, `low_risk_judged`, `skip_origin` and `draft_pr`.
   - The skip path (`execute_plan.py:486-496`) never calls the predicate.
     Line 519 then overwrites `vendor_verdict` with the skip dict.
4. **Independence is not checked.**
   - The only self-review rule is the hard-coded `exclude_vendor="claude_code"`
     (`vendor_review.py:610,641`).
   - `ReviewResult.agent_id` exists but is dropped (`vendor_review.py:686`).
   - The PR author login is discovered (`discover_prs.py:110`) and then dropped
     by `build_plan`.

pstack's lesson, adopted by this roadmap, is that a verdict counts only if an
agent that did not write the code produced it, for exactly the code being
landed. A rebase that changes nothing should not discard the verdict, and
anything else should.

## What Changes

- **A verdict binding.** Every review the merge path stores in
  `node.state.vendor_verdict` carries:
  - `head_sha`: the PR `headRefOid` at review time.
  - `patch_id`: `git patch-id --stable` over the PR diff, read with
    `gh pr diff <n>` so execution never checks out the PR branch.
  - `reviewer`: `{vendor, family, model, agent_id}`. The field names match the
    `adjudicator` block of `add-orchestrator-adjudication-review-gate`.
  - `author`: `{login, vendor, session_id}`, derived from the PR author and the
    head commits' `Co-Authored-By:` / `*-Session:` trailers. Fields that cannot
    be derived are `null`.
  - `bound_at`: when the binding was made.
- **A currency rule.** A single pure function, `verdict_currency(binding, live)`,
  returns one of:
  - `current`: same `head_sha`.
  - `rebased`: different `head_sha`, same `patch_id`, so the verdict survives.
  - `stale`: the patch-id differs or cannot be computed. This blocks with the
    reason `stale verdict: reviewed <sha7>, live <sha7>`.

  This replaces the dead `_iterate_consensus_current`.
- **A fail-closed predicate.** `vendor_review_block_reason` becomes total:
  - A missing verdict blocks.
  - An ineligible verdict blocks, unless the node carries a **review waiver**.
  - A stale verdict blocks.
  - A verdict whose reviewer is not independent of the author blocks.
  - The skip path routes through the same predicate.
- **Waivers are recorded, never implicit.**
  - merge-plan schema `1.1 → 1.2` adds `state.review_waiver{reason,
    source: policy|operator, approver, recorded_at, eligibility_reason}`.
    It lives in `state`, not `definition`, because eligibility is computed
    live at execute time (`check_review_eligibility` reads current reviews,
    size and judgement); `build_plan` has no eligibility data to write from.
  - `execute_plan` records a `source: policy` waiver only when the live
    ineligible reason is in the closed set `POLICY_WAIVABLE_REASONS =
    {skip_origin, small_pr, has_approval, low_risk_judged,
    automation_cheap_path}`. Any other reason — `draft_pr`,
    `changes_requested`, a missing or unknown eligibility, the old bare
    `skipped` marker — blocks.
  - An operator override (`execute_plan.py --execute <plan> --pr <n>
    --waive-review "<reason>"`) writes `source: operator`. A blank reason
    exits 2, as in ri-02. It appears in `_review_evidence` and the merge
    event log.
- **An independence rule.**
  - Dispatch excludes `{"claude_code", <author vendor>}` instead of the
    hard-coded `claude_code` alone.
  - As a backstop, a verdict is rejected when the reviewer's `(vendor, agent_id)` equals the
    author's `(vendor, session_id)`.
  - It is also rejected when the vendors match and the author session is
    unknown, because independence cannot be shown.
  - When the family matches but the session differs, the verdict is accepted
    and recorded as `same_family: true`, consistent with that
    change's D6.
- **The merge is pinned.** `merge_pr merge` passes `--match-head-commit
  <live head_sha>` on both the direct merge and the merge-queue path, so a push after the check makes the merge fail instead of
  landing unreviewed code.
- **The dead field is removed.** `iterate_consensus_path` leaves the schema and
  the code. The iterate-consensus skip is re-expressed as "a stored verdict
  whose currency is `current` or `rebased` skips re-review".
- **SKILL.md stays line-neutral.** Lines 141-142 are rewritten in place to point
  at a new `references/verdict-binding.md`, which carries the rules, the waiver
  classes and the override.

## Approaches Considered

### Selected Approach

**Approach A: shared verdict-binding module plus a total predicate in
`execution_safety`**, selected at Gate 1 without modification.

A new pure module, `skills/merge-pull-requests/scripts/verdict_binding.py`,
provides:

- `bind`
- `verdict_currency`
- `independence_violation`
- `patch_id(repo, base, head)`

How the pieces connect:

- `execute_plan` binds every stored review.
- `execution_safety.vendor_review_block_reason` calls the module and becomes
  total.
- `execute_plan` records policy waivers from a closed set at execute time.

The binding's field names match the adjudication verdict schema (`head_sha`,
`reviewer{vendor, family, model}`, `same_family`). As a result,
`add-orchestrator-adjudication-review-gate` can check its verdicts with the
same `verdict_currency` instead of adding a second staleness rule.

- **Why:**
  - It closes all four gaps in one rule.
  - Its pure functions are unit-testable against real throwaway git repos.
  - It does not wait on unlanded work.
- **Accepted costs:**
  - L-sized overall.
  - It must coordinate edits to `execution_safety.py`, which the adjudication
    change's work-packages also declare (see Coordination).

### Rejected alternatives

- **B: land on top of `add-orchestrator-adjudication-review-gate`.** Rejected
  for three reasons:
  - It blocks on a change that is still only a plan.
  - Adjudication covers only single-vendor high-impact findings, not every PR's
    verdict.
  - It leaves the ineligible-passes branch open.
- **C: strict head-SHA binding only.** Rejected for two reasons:
  - Every rebase in a stacked merge discards the verdict, which makes ri-03
    unaffordable.
  - It leaves absence-as-pass and self-review open.

## Coordination with in-flight changes

- **`add-orchestrator-adjudication-review-gate`** (planning only). Both changes
  edit `execution_safety.vendor_review_block_reason`.
  - Its tasks 5.1-5.5 add adjudication conditions; this change makes the
    function total and binds verdicts.
  - Proposed order: this change lands first. Adjudication task 5.x then calls
    `verdict_currency` for its `head_sha` staleness rule (its D5) and gains
    `patch_id` survival for free.
  - Its D6, "record same-family, don't forbid", is preserved. This change
    forbids only *identity* equality and unknown-author same-vendor.
  - A note is added to that change's design.md during implementation, not in
    this plan commit.
- **`judge-multi-vendor-review-eligibility-for-pull-requests`** (implemented,
  awaiting merge). It adds `low_risk_judged` as an ineligible reason. Under
  this change that reason becomes a `policy` waiver class instead of a silent
  pass.
- **ri-03 `land-verified-stack-prefixes-via-gate-merge`** depends on this
  change for `rebased` currency.

## Non-Goals

- Routing `/cleanup-feature` and autopilot `Gate.MERGE` merges through the
  vendor gate. Today `cleanup-feature` calls `merge_pr.py merge` directly and
  bypasses `execute_plan`. That is ri-03.
- Vendor-family policy beyond identity equality, which belongs to the
  adjudication change's D6.
- Changing which PRs are review-eligible; only how ineligibility is recorded
  changes.
- Gating a missing validation report in `merge_pr.py`.

## Impact

- **Code (skills/merge-pull-requests/scripts/):**
  - `verdict_binding.py` (new)
  - `execution_safety.py`
  - `execute_plan.py`
  - `build_plan.py`: schema version, drops `iterate_consensus_path`
  - `merge_pr.py`: `headRefOid` in status, `--match-head-commit`
  - `vendor_review.py`: keeps `agent_id`, emits `reviewer`
  - `merge_plan.py`: schema 1.2 and the 1.1 load path
  - `merge_events.py`: optional waiver fields on the merge record
- **Code (shared):** `skills/parallel-infrastructure/scripts/review_dispatcher.py`
  widens `exclude_vendor` to accept a collection; the string form is unchanged
  for other callers.
- **Schema:** `contracts/merge-plan.schema.json` `1.1 → 1.2`.
  - The 1.1 load path is rejected with a "rebuild the plan" message, matching
    the existing `const` version check, rather than migrated.
- **Docs:**
  - `SKILL.md` stays line-neutral.
  - `references/verdict-binding.md` is new.
- **Specs:** MODIFY in `merge-pull-requests`:
  - "Plan-Driven Single-PR Execution"
  - "Cheap Path for Scoped Automation"
  - "Durable Merge Plan Artifact"
- **Tests:**
  - New real-git tests for patch-id survival and staleness.
  - `test_iterate_consensus_matching_head_skips_vendor_review` is rewritten
    for currency.
  - Ineligible-pass tests flip to require waivers.

## Acceptance Outcomes

- **Patch-id survival.** In a real-git test, a branch rebased onto a moved base
  with an identical diff yields `rebased` and merges without re-review. A
  branch whose diff changed yields `stale verdict` and blocks.
- **Total predicate.** `vendor_review_block_reason` returns a block reason for
  a missing, ineligible or skipped review unless `state.review_waiver` holds a
  policy-set or operator waiver. Operator waivers appear in `_review_evidence` and the merge
  event log.
- **Independence.** A verdict whose reviewer `(vendor, agent_id)` equals the
  author `(vendor, session_id)` is rejected. So is a same-vendor verdict whose
  author session is unknown.
- **Pinned merge.** `merge_pr merge` passes `--match-head-commit`.
- **Dead field gone.** No code or schema references `iterate_consensus_path`.
- **SKILL.md line-neutral.** `skills/merge-pull-requests/SKILL.md`'s line count
  is unchanged.
