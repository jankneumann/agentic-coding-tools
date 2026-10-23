# Design: Bind merge verdicts to head SHA and patch-id

> Change ID: `bind-merge-verdicts-to-head-sha-and-patch-id`
> Selected approach: **A — shared verdict-binding module plus a total predicate**

## Context

The merge path lands a PR on a vendor-review "verdict" that records neither
what it reviewed nor who wrote the code, and that passes when absent. This
design closes four gaps with one rule. Line references are to `main` at
plan time (`e11534f`).

| Gap | Where |
|---|---|
| No head SHA in live status or in the stored verdict | `merge_pr.get_pr_status` 78-88; `vendor_review.py` |
| Dead currency check | `execute_plan._iterate_consensus_current` 221-228; `build_plan.py:177` |
| Absence and ineligibility pass | `execution_safety.vendor_review_block_reason` 52-76; skip path `execute_plan.py:486-519` |
| No independence check | `vendor_review.py:610,641` (hard-coded `claude_code`); `agent_id` dropped ~686 |
| Unpinned merge | `merge_pr._try_merge` ~378, `_try_merge_queue` ~461 |

## Decisions

### D1 — One binding shape, named to match adjudication

`verdict_binding.bind(review, *, head_sha, patch_id, author, now)` returns the
review dict extended with a `binding` object:

```json
{
  "head_sha": "<40-hex>",
  "patch_id": "<40-hex> | null",
  "reviewers": [{"vendor": "codex", "family": "openai", "model": "…", "agent_id": "…"}],
  "author": {"login": "…", "vendor": "claude_code | null", "session_id": "… | null"},
  "same_family": false,
  "bound_at": "<RFC3339>"
}
```

`head_sha`, `reviewer.{vendor,family,model}` and `same_family` use the names in
`add-orchestrator-adjudication-review-gate` D5/D6, so that change calls
`verdict_currency` instead of adding a second staleness rule.

**Family** is not modelled anywhere in the repo today. `verdict_binding` owns a
small table: the model-string prefix decides first (`claude-` → `anthropic`,
`gpt-`/`o1`/`o3`/`o4` → `openai`, `gemini-` → `google`, `grok-` → `xai`), then a
vendor fallback (`claude_code` → `anthropic`, `codex` → `openai`,
`gemini`/`antigravity` → `google`, `grok` → `xai`), else `null`. `same_family` is
`true` only when both sides resolve to the same non-null family; `null` when
either is unknown. It is recorded, never enforced (adjudication D6).

`vendor_review.py` keeps `agent_id` and `model_used` in each per-vendor summary
(today it drops `agent_id`). That is the only change to the dispatch result.

### D2 — Patch-id from `gh pr diff`, never a checkout

`patch_id_from_diff(diff_text)` pipes text to `git patch-id --stable` and
returns the first field, or `None` on empty input or non-zero exit. Execution
reads the diff with `gh pr diff <n>`; the existing invariant "execution SHALL
NOT check out, commit, or push to the PR branch" holds.

`patch_id(repo, base, head)` computes the same value from a local repo
(`git diff $(git merge-base base head) head | git patch-id --stable`) and exists
for real-git tests and for ri-03, which already has a local checkout.

*Trade-off.* `--stable` hashes hunks with their context lines. A rebase over a
base change that touches lines adjacent to the PR's hunks changes the context
and therefore the patch-id, yielding `stale` although the PR's own lines are
identical. That errs toward re-review, which is the safe direction; it costs
one dispatch. Accepted.

### D3 — `verdict_currency` is total and pure

```
verdict_currency(binding, live_head_sha, live_patch_id) -> "current" | "rebased" | "stale"
```

- `binding` missing, or no `head_sha` → `stale`.
- `head_sha == live_head_sha` → `current`.
- both patch-ids non-null and equal → `rebased`.
- otherwise → `stale`.

`stale_reason(binding, live_head_sha)` formats
`stale verdict: reviewed <sha7>, live <sha7>`. Execution computes the live
patch-id lazily: only when a stored binding exists and its `head_sha` differs.

A stored verdict is used only when the predicate passes on it against live
state. Otherwise execution dispatches a fresh review and evaluates the
predicate on that; the stale reason of the discarded verdict is recorded in the
node's result for observability.

### D4 — The predicate is total; waivers live in `state`

`vendor_review_block_reason(review, *, waiver=None, live_head_sha=None, live_patch_id=None)`
returns `None` only on one of two paths:

1. **Waived:** `waiver` is a dict with non-blank `reason`, `source ∈ {policy, operator}`,
   non-blank `approver`, `recorded_at`, and the key `eligibility_reason` — for
   `source: policy` it must be in `POLICY_WAIVABLE_REASONS`. Both sources require
   `approver`: a policy waiver's approver is the fixed string
   `policy:merge-pull-requests`; an operator waiver's approver is defined in D7.
   `eligibility_reason` is the live ineligibility reason at the time of the waiver
   (a string, or `null` for an operator waiver recorded while the PR was eligible).
   An operator waiver does **not** override `changes_requested`: that is a
   human reviewer's state, not ours to waive. Everything else it does override.
2. **Verified:** eligibility is eligible; consensus dispatched with at least one
   successful vendor; `blocking_count == 0`; a binding is present;
   `verdict_currency` is `current` or `rebased`; `independence_violation` is `None`.

Every other input returns a reason string, including `review is None`, a
missing eligibility, `{"skipped": True}` with no waiver, and an ineligible reason
outside the policy set (`draft_pr`, `changes_requested`, unknown strings).

```python
POLICY_WAIVABLE_REASONS = frozenset({
    "skip_origin", "small_pr", "has_approval", "low_risk_judged", "automation_cheap_path",
})
```

**Why `state` and not `definition` (correction found during planning).** The
proposal sketch had `build_plan` writing policy waivers into
`definition.review_waiver`. That cannot work: eligibility is computed **live** in
`check_review_eligibility` from current reviews, PR size and the low-risk
judgement, none of which `build_plan` sees. `execute_plan` therefore records a
policy waiver into `state.review_waiver` at the moment it observes a
policy-waivable reason, before the merge, and the predicate reads it from
there. `remediation_skill == "none"` is produced only for the automation class
(`classify_kind._remediation_skill` 80-118), so it is folded into
`automation_cheap_path` rather than kept as a second skip key.

### D5 — Independence: exclude at dispatch, reject in the predicate

- **Author derivation** (`derive_author(pr_view)`): `gh pr view <n> --json author,commits`.
  `login` from `author.login`. `vendor`/`session_id` from the **head** commits'
  trailers: `Co-Authored-By: Claude …` → `claude_code`; `Claude-Session: <url>`
  → session id is the URL's last path segment; generic `<Vendor>-Session:` maps
  by a lowercase vendor table. Multiple distinct sessions → the latest commit's.
  Underivable fields are `null`.
- **Dispatch exclusion:** `vendor_review.py` passes
  `exclude_vendor={"claude_code", author.vendor} - {None}`.
  `ReviewOrchestrator.dispatch_and_wait` re-runs `discover_reviewers`
  internally (`review_dispatcher.py` 2817, 2917), so both widen
  `exclude_vendor` from `str | None` to `str | Collection[str] | None`; the
  string form keeps working for every other caller. When exclusion leaves no
  reviewer (single-vendor environment, author is that vendor), dispatch
  returns its existing "No vendor CLIs available" result, which blocks; the
  operator waiver is the way through.
- **Predicate backstop** (`independence_violation(binding)`): a reason when any
  successful reviewer has `(vendor, agent_id) == (author.vendor, author.session_id)`;
  or `reviewer.vendor == author.vendor` while `author.session_id is None`.
  Otherwise `None`.

The backstop exists because dispatch exclusion only covers vendor review; a
stored verdict from another path (ri-03, adjudication) can still be checked.

### D6 — The merge is pinned to the head the predicate saw

- `get_pr_status` requests `headRefOid` and returns it as `head_sha`.
- `merge_pr(…, expected_head_sha=None, review_waiver=None)` appends
  `--match-head-commit <sha>` to both `_try_merge` and `_try_merge_queue` when
  set. The `ExecutionDependencies.merge` signature becomes
  `(pr_number, strategy, head_sha, review_waiver)`.
- A non-zero exit whose stderr names a head mismatch keeps the node `pending`
  with `blocking_reason: "head moved after review check"`.
- `_record_merge_event` gains two optional `MergeEvent` fields,
  `waiver_source` and `waiver_reason`. `to_dict` drops `None`, so existing
  readers see byte-identical records when no waiver is set.

### D7 — Operator waiver CLI

`execute_plan.py --execute <plan> --pr <n> --waive-review "<reason>"`.
`main()` rejects a blank or whitespace-only reason with `parser.error` (exit 2)
before `execute_node` runs, matching ri-02's `--accept-missing-validation`.
`approver` is `$USER` / `git config user.email` / `"operator"`, first non-empty.
The waiver is written to `state.review_waiver` inside the same claim as the
merge, so a crash after recording but before merging replays with the waiver
already present.

### D8 — Schema 1.2 removes the dead field and rejects 1.1

- `schema_version` const `"1.2"`; `state.review_waiver` (object|null,
  `additionalProperties: false`) added; `state.iterate_consensus_path` removed.
  `vendor_verdict` stays `additionalProperties: true`; the binding is
  validated by `verdict_binding.validate_binding`, not by the plan schema,
  because the adjudication change will extend it.
- `merge_plan.validate_plan` checks the version before schema validation and
  raises `MergePlanValidationError("plan schema <v> is no longer
  supported; rebuild with the analysis round")` for any other version. Plans
  are short-lived analysis artifacts regenerated each round, so a migration
  path buys nothing.
- `build_plan.py` moves to `1.2` and stops initialising `iterate_consensus_path`.

### D9 — SKILL.md stays line-neutral

`skills/merge-pull-requests/SKILL.md:141-142` (the two lines describing the
iterate-consensus skip) are rewritten in place as two lines that point to a
new `references/verdict-binding.md`. That file carries the currency table, the
waiver set, the operator flag and the independence rules. `test_skill_md.py`
gains an assertion that the reference file exists and is linked.

## Alternatives rejected at Gate 1

- **B — build on adjudication first.** Blocks on an unlanded plan; covers only
  single-vendor high-impact findings; leaves the ineligible-pass branch open.
- **C — strict head-SHA only.** Every stacked rebase discards the verdict, which
  makes ri-03 unaffordable, and absence-as-pass and self-review stay open.

## Risks

| Risk | Mitigation |
|---|---|
| Blocking every ineligible PR that used to pass silently | The policy set preserves today's merge behaviour for the five classes, but now visibly; only `draft_pr`, unknown reasons and missing eligibility newly block. |
| `gh pr diff` unavailable or truncated for huge PRs | `patch_id` → `None` → `stale` → re-review. Never a pass. |
| Context-line patch-id drift (D2) | Conservative; one extra dispatch. |
| Edits to `execution_safety.py` collide with adjudication's `wp-merge-gate` | File lock on `execution_safety.py`; this change lands first; adjudication calls `verdict_currency`. |
| Author trailers absent on human-authored PRs | `vendor: null` → the vendor-equality rule cannot fire; human PRs are independent of every vendor reviewer by construction. |

## Planning-process notes

- The plan-feature Step 2 architecture refresh was skipped to avoid
  regenerating tracked `docs/architecture-analysis/*` files in this commit;
  context came from direct code reads (line references above).

## Plan-iteration refinements

Two points the decisions above left implicit, settled before implementation:

- **Seam signatures.** `ExecutionDependencies` gains `pr_diff(pr_number) -> str`
  and `pr_author(pr_number) -> dict` (the `derive_author` result).
  `review_vendor` takes the author as a fourth argument,
  `(pr_number, origin, comments, author)`, so `_default_vendor_review` can pass
  `author_vendor` to `dispatch_vendor_reviews`. A `pr_author` seam that
  raises keeps the node pending ("PR author could not be determined"): an
  all-`null` author is what a human PR with no trailers looks like, so a
  lookup failure must not be mistaken for one. A `pr_diff` seam that raises
  yields a `null` patch-id, which can only reach `current`, never `rebased`.
- **Operator waiver still runs eligibility and review.** `--waive-review` does
  not skip `review_vendor`. Eligibility must still run so `changes_requested`
  keeps blocking (D4), and any review that does dispatch is stored as evidence.
  The waiver then satisfies the predicate in place of a verified verdict.
