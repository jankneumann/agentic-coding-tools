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
| `head_sha` | The PR head the reviewers saw (40-char hex): `vendor_review.py` reads it immediately before dispatch and reports it as `reviewed_head_sha`. |
| `patch_id` | `git patch-id --stable` of the reviewed diff, or `null` when it could not be computed. |
| `reviewers` | One entry per *successful* lane: `vendor`, `family`, `model`, `agent_id`. Failed lanes vouch for nothing and are not recorded. |
| `author` | `{login, vendor, session_id}` of the latest commit carrying an agent trailer. |
| `authors` | Every commit's agent identity as `{vendor, session_id}`, de-duplicated in commit order. Optional in older bindings; when absent, `author` alone is checked. |
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

A live head SHA that is missing, empty, or not 40 lowercase hex characters
leaves the node pending (`live_state_gate`, reason `live head sha unavailable`)
rather than guessing; this applies on every path, including the cheap path and
a waived merge.

`vendor_review.py` also reads the PR head immediately before and after vendor
dispatch. If the two reads differ (or either fails), it returns
`head_moved: true` and no consensus; execution stores the review without a
binding and leaves the node pending with reason `head moved during review`. The merge itself is pinned with `gh pr merge
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
ineligibility reason and its approver is `policy:merge-pull-requests`. A stored
policy waiver is never carried forward: execution recomputes it from the live
eligibility on every run, so one whose reason no longer applies is cleared
before the predicate runs. Every waiver records the live head it was granted
for in `waived_head_sha`. Any
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
the audit trail names who waived what and why. A replay of the same claim
reuses a stored operator waiver only while its `waived_head_sha` equals the
live head; after a push the waiver is cleared and must be given again.

## Shape check

Before currency or independence is evaluated, the merge predicate runs
`validate_binding()` and blocks a malformed binding: a missing or non-sha
`head_sha`, a missing `patch_id` key, an author without `login`, `vendor` and
`session_id` keys, or a `reviewers` list that is empty or has an entry without
a `vendor` and an `agent_id` key. Every reviewer must also match a successful
lane in the verdict's `vendors`. A truncated or hand-edited stored binding is
treated as superseded and a fresh review is dispatched; it is never reused.
The bound verdict and any waiver are saved to the plan, under the held claim,
before the merge call, so a crash cannot lose the evidence the merge used.

## Independence

`independence_violation(binding)` blocks a verdict that was not independent of
the PR author. Every identity in `authors` (plus `author`) is checked, so a
reviewer that authored an earlier commit blocks even when a later commit came
from another session:

- **Self-review:** a reviewer whose `agent_id` equals the author's session
  blocks.
- **Same vendor, unknown session:** a reviewer from the author's vendor blocks
  when the author's session is unknown, because independence cannot be shown.
- **Same vendor, unknown reviewer agent id:** blocks for the same reason.
- **Same vendor, different session:** accepted.
- **Same family, different vendor:** recorded in `same_family`, not blocking.

Dispatch already excludes every author vendor (`author_vendors`) alongside
the orchestrating `claude_code` lane; the independence check catches stored verdicts and any
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
