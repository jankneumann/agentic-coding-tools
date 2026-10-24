# Verdict Binding

A vendor review verdict is evidence about one specific diff, reviewed by
specific reviewers, for a specific author. `execute_plan.py --execute` binds
every stored review to that context (`scripts/verdict_binding.py`) and merges
only when the predicate in `execution_safety.vendor_review_block_reason`
returns no block reason. The predicate is total: it passes on exactly two
paths, a valid recorded waiver or a bound, current-or-rebased, independent
verdict with zero blocking findings. Every other input blocks the merge with a
named reason.

## The binding block

`bind()` stores a `binding` object next to the review in `merge-plan.json`
(schema 1.2):

| Field | Meaning |
|---|---|
| `head_sha` | The PR head the reviewers saw (40-char hex). |
| `patch_id` | `git patch-id --stable` of the reviewed diff, or `null` when it could not be computed. |
| `reviewers` | One entry per *successful* lane: `vendor`, `family`, `model`, `agent_id`. Failed lanes vouch for nothing and are not recorded. |
| `author` | `{login, vendor, session_id}` derived from the PR's commits. |
| `same_family` | `true` when a reviewer shares the author's model family, `false` when none does, `null` when unknown. |
| `bound_at` | UTC timestamp. |

## Currency

`verdict_currency(binding, live_head_sha, live_patch_id)` classifies a stored
verdict against the live PR at execution time:

| Currency | Condition | Effect |
|---|---|---|
| `current` | Stored `head_sha` equals the live head. | Reused; `vendor_review.py` is not re-run. |
| `rebased` | Head moved, but both patch-ids are known and equal (a rebase that changed no content). | Reused; `vendor_review.py` is not re-run. |
| `stale` | Head moved and the patch-ids differ, or either patch-id is unknown. | Recorded as `superseded_verdict: "stale verdict: reviewed <old>, live <new>"`; a fresh review is dispatched and bound. |
| `stale` (unbound) | No binding, or a binding with no `head_sha`. | Treated as stale; the verdict is never reused. |
| `stale` (uncomputable) | The live patch-id could not be computed and the head moved. | Treated as stale; currency fails closed. |

A missing live head SHA leaves the node pending (`live_state_gate`) rather
than guessing. The merge itself is pinned with `gh pr merge
--match-head-commit <live head>`, so a push that lands between the review
check and the merge is refused (`head mismatch`) and the node stays pending.

## Policy waivers

A review that was never run can only stand in for a review when a policy
decided it should. `POLICY_WAIVABLE_REASONS` is closed:

| Reason | Source |
|---|---|
| `skip_origin` | Scoped automation or dependency-update origin. |
| `small_pr` | Below the configured size thresholds. |
| `has_approval` | The PR already carries a human approval. |
| `low_risk_judged` | The risk classifier judged the PR low-risk. |
| `automation_cheap_path` | `automation` node with green CI and zero comments. |

A policy waiver is valid only when its `eligibility_reason` equals the live
ineligibility reason and its approver is `policy:merge-pull-requests`. Any
other ineligibility (`draft_pr`, `changes_requested`, a missing or malformed
eligibility, an unknown reason) blocks.

## Operator waiver

`execute_plan.py --execute <plan> --pr <n> --waive-review "<reason>"` records
an operator waiver (`source: operator`, approver from `$USER` or `git config
user.email`). It overrides a missing, failed, ineligible or blocking review,
with two limits:

- A blank or whitespace-only reason exits 2 and leaves the plan unchanged.
- It never overrides unresolved change requests (`changes_requested`).

The waiver is stored in the node's evidence and passed to the merge call, so
the audit trail names who waived what and why.

## Independence

`independence_violation(binding)` blocks a verdict that was not independent of
the PR author:

- **Self-review:** a reviewer whose `agent_id` equals the author's session
  blocks.
- **Same vendor, unknown session:** a reviewer from the author's vendor blocks
  when the author's session is unknown, because independence cannot be shown.
- **Same vendor, different session:** accepted.
- **Same family, different vendor:** recorded in `same_family`, not blocking.

Dispatch already excludes the author's vendor alongside the orchestrating
`claude_code` lane; the independence check catches stored verdicts and any
lane that slipped through.

A reviewer's `agent_id` is a dispatcher adapter id (for example
`codex-local`), while the author's `session_id` is the last segment of a
`<Vendor>-Session:` trailer URL. The two rarely share a namespace, so the
self-review rule is defence in depth. The effective guards are dispatch
exclusion of the author's vendor and the same-vendor, unknown-session rule.

## Author identity is advisory

The author's vendor and session come from commit trailers
(`<Vendor>-Session: <url>`, or `Co-Authored-By: Claude` with no session). A
trailer is text anyone can write, so this is provenance, not authentication.
A PR with no agent trailer is treated as human-authored.
