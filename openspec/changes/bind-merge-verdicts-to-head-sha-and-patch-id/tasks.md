# Tasks: Bind merge verdicts to head SHA and patch-id

> Change ID: `bind-merge-verdicts-to-head-sha-and-patch-id`
> Test command (from `skills/`): `.venv/bin/python -m pytest merge-pull-requests/scripts/tests tests/merge-pull-requests -q`
> Paths below are relative to `skills/merge-pull-requests/` unless they start with `skills/` or `openspec/`.

## 1. Verdict-binding module (wp-binding)

- [x] 1.1 Write real-git tests for patch-id survival in `scripts/tests/test_verdict_binding.py` (M)
  <!-- Scenario ID: merge-pull-requests.verdict-current -->
  <!-- Scenario ID: merge-pull-requests.verdict-rebased -->
  <!-- Scenario ID: merge-pull-requests.verdict-stale -->
  <!-- Scenario ID: merge-pull-requests.verdict-unbound-stale -->
  - **Spec scenarios:** verdict-current, verdict-rebased, verdict-stale, verdict-unbound-stale
  - **Contracts:** binding shape in design D1
  - **Design decisions:** D2, D3
  **Dependencies**: none
  - Build a throwaway repo in `tmp_path` (pattern: `test_head_guard.py:23-37`). Rebase a feature branch onto a moved base with an identical diff → `rebased`; amend a hunk → `stale`; `patch_id_from_diff("")` → `None` → `stale`.
- [x] 1.2 Write unit tests for independence and family in `scripts/tests/test_verdict_binding.py` (S)
  <!-- Scenario ID: merge-pull-requests.self-review-rejected -->
  <!-- Scenario ID: merge-pull-requests.unknown-author-same-vendor-rejected -->
  <!-- Scenario ID: merge-pull-requests.same-family-recorded -->
  - **Spec scenarios:** self-review-rejected, unknown-author-same-vendor-rejected, same-family-recorded
  - **Design decisions:** D1 (family table), D5
  **Dependencies**: none
  - Also cover `derive_author` on `Co-Authored-By:` / `Claude-Session:` trailers, on a human PR with no trailers (all-`null` vendor), and on two sessions (the latest commit wins).
- [x] 1.3 Implement `scripts/verdict_binding.py` (M)
  - `bind`, `verdict_currency`, `stale_reason`, `independence_violation`, `derive_author`, `family_of`, `patch_id_from_diff`, `patch_id`, `validate_binding`, `POLICY_WAIVABLE_REASONS`.
  - Pure apart from the two `git patch-id` subprocess helpers. No `gh` calls; callers pass `gh` output in.
  **Dependencies**: 1.1, 1.2
- [x] Checkpoint: run tests, review diff, verify scope

## 2. Plan schema 1.2 (wp-schema)

- [x] 2.1 Write contract tests for schema 1.2 in `scripts/tests/test_merge_plan_contract.py` (S)
  <!-- Scenario ID: merge-pull-requests.plan-1-1-rejected -->
  - **Spec scenarios:** plan-1-1-rejected; "Analysis round emits a durable plan" (1.2)
  - **Contracts:** `contracts/merge-plan.schema.json`
  - **Design decisions:** D8
  **Dependencies**: none
  - A 1.2 node with `state.review_waiver` validates. A node carrying `iterate_consensus_path` fails `additionalProperties`. A 1.1 plan raises `MergePlanValidationError` whose message contains "rebuild".
- [x] 2.2 Bump the schema to 1.2 in `contracts/merge-plan.schema.json` (S)
  - Add `state.review_waiver`, remove `state.iterate_consensus_path`, update the description.
  **Dependencies**: 2.1
- [x] 2.3 Add the version pre-check to `scripts/merge_plan.py` (S)
  **Dependencies**: 2.1
- [x] 2.4 Emit 1.2 plans from `scripts/build_plan.py` (S)
  - Write `schema_version` `1.2` and drop the `iterate_consensus_path` initialiser; update `test_build_plan.py` expectations.
  **Dependencies**: 2.2
- [x] Checkpoint: run tests, review diff, verify scope

## 3. Head-pinned merge (wp-merge-pin)

- [x] 3.1 Write tests for head-pinned merge arguments in `scripts/tests/test_merge_pr_head_pin.py` (S)
  <!-- Scenario ID: merge-pull-requests.merge-pinned -->
  - **Spec scenarios:** merge-pinned
  - **Design decisions:** D6
  **Dependencies**: none
  - Monkeypatch `run_gh_unchecked`; assert `--match-head-commit <sha>` is in the args for `_try_merge` and for `_try_merge_queue`, and absent when `expected_head_sha` is `None` (other callers are unchanged).
- [x] 3.2 Write tests for the live head SHA in `scripts/tests/test_merge_pr_head_pin.py` (S)
  - **Design decisions:** D6
  **Dependencies**: none
  - `headRefOid` is in the requested `--json` fields and surfaces as `head_sha` from `get_pr_status`.
  - `validate_pr(...)["head_sha"]` carries it too: execution reads live state through `validate_pr` (`execute_plan.py` `get_live_status=validate_pr`), which builds its own dict, so a field added only to `get_pr_status` never reaches the predicate or the merge pin.
- [x] 3.3 Write tests for waiver fields on the merge event in `scripts/tests/test_merge_pr_records_events.py` (S)
  <!-- Scenario ID: merge-pull-requests.operator-waiver-recorded -->
  - **Spec scenarios:** operator-waiver-recorded (event-log half)
  - **Design decisions:** D6
  **Dependencies**: none
  - With no waiver the serialised record is byte-identical to today's.
- [x] 3.4 Implement head pinning in `scripts/merge_pr.py` (M)
  - `get_pr_status` adds `headRefOid`; `validate_pr` returns it as `head_sha`; `merge_pr(…, expected_head_sha=None, review_waiver=None)` threads both through `_try_merge` / `_try_merge_queue` / `_record_merge_event`.
  - When pinned and the merge fails, the response carries a structured `head_mismatch: True` key (see D6 for the matched markers) instead of leaving callers to parse stderr.
  **Dependencies**: 3.1, 3.2, 3.3
- [x] 3.5 Add optional waiver fields to `scripts/merge_events.py` (S)
  - `waiver_source`, `waiver_reason` on `MergeEvent`.
  **Dependencies**: 3.3
- [x] Checkpoint: run tests, review diff, verify scope

## 4. Reviewer identity at dispatch (wp-vendor-review)

- [x] 4.1 Write tests for collection-valued `exclude_vendor` in `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher_exclude_vendor.py` (S)
  - **Design decisions:** D5
  **Dependencies**: none
  - The string form excludes one vendor as before; a set excludes each member; `None` excludes nothing.
- [x] 4.2 Write tests for reviewer identity in the vendor summary in `skills/tests/merge-pull-requests/test_vendor_review_identity.py` (S)
  - **Design decisions:** D1, D5
  **Dependencies**: none
  - Each per-vendor summary keeps `agent_id` and `model_used`. Every author vendor found across the PR's commits is passed to dispatch exclusion alongside `claude_code`.
  - Snapshot check: with a fake `gh` whose head SHA changes between the pre- and post-dispatch reads, the result is marked `head_moved: true`, carries no binding-eligible verdict, and its reason names the head movement; with an unchanged head the pre-dispatch SHA is returned as `reviewed_head_sha`.
  <!-- Scenario ID: merge-pull-requests.head-moved-during-review-blocks -->
- [x] 4.3 Widen `exclude_vendor` in `skills/parallel-infrastructure/scripts/review_dispatcher.py` (S)
  **Dependencies**: 4.1
- [x] 4.4 Thread the author vendor through `scripts/vendor_review.py` (S)
  - `dispatch_vendor_reviews(…, author_vendors=())`; keep `agent_id` in each summary.
  - Read the head SHA before and after dispatch; return `reviewed_head_sha` (pre-dispatch) and `head_moved` (D6).
  **Dependencies**: 4.2, 4.3
- [x] Checkpoint: run tests, review diff, verify scope

## 5. Total predicate and execution wiring (wp-predicate-execute)

- [x] 5.1 Write predicate tests for the total review gate in `skills/tests/merge-pull-requests/test_review_predicate_total.py` (M)
  <!-- Scenario ID: merge-pull-requests.ineligible-without-waiver-blocks -->
  <!-- Scenario ID: merge-pull-requests.vendor-review-fails-closed -->
  <!-- Scenario ID: merge-pull-requests.skip-path-without-binding-or-waiver-blocks -->
  - **Spec scenarios:** ineligible-without-waiver-blocks, vendor-review-fails-closed, skip-path-without-binding-or-waiver-blocks
  - **Design decisions:** D4
  **Dependencies**: 1.3
  - Table-driven: `None`, missing eligibility, `{"skipped": True}`, each ineligible reason with and without each waiver source, `changes_requested` with an operator waiver (still blocks), a stale binding, a self-review, and the verified path.
- [x] 5.2 Rewrite the execution tests for currency, waivers and pinning in `scripts/tests/test_execute_plan.py` (M)
  <!-- Scenario ID: merge-pull-requests.skip-pr-diff-review-after-iterate -->
  <!-- Scenario ID: merge-pull-requests.cheap-path-merges -->
  <!-- Scenario ID: merge-pull-requests.cheap-path-dropped-on-comments -->
  <!-- Scenario ID: merge-pull-requests.policy-waiver-recorded -->
  <!-- Scenario ID: merge-pull-requests.merge-push-race-fails -->
  - **Spec scenarios:** skip-pr-diff-review-after-iterate, cheap-path-merges, cheap-path-dropped-on-comments, policy-waiver-recorded, merge-push-race-fails
  - **Design decisions:** D3, D4, D6
  **Dependencies**: 1.3, 2.2
  - A head-mismatch merge is asserted via the `head_mismatch: True` key on the merge response, not on stderr text.
  - Replace `test_iterate_consensus_matching_head_skips_vendor_review` (:564-592) with `current` and `rebased` variants; flip `test_cheap_path_skips_vendor_review` (:544) to assert the recorded waiver; keep `test_vendor_review_eligible_without_verdict_blocks` (:445). Update the `dependencies` fixture (:38-61) for the new `merge` signature and a `pr_diff` seam.
- [x] 5.3 Write CLI tests for `--waive-review` in `scripts/tests/test_execute_plan.py` (S)
  <!-- Scenario ID: merge-pull-requests.operator-waiver-recorded -->
  <!-- Scenario ID: merge-pull-requests.operator-waiver-empty-rejected -->
  - **Spec scenarios:** operator-waiver-recorded, operator-waiver-empty-rejected
  - **Design decisions:** D7
  **Dependencies**: none
  - `""` and `"   "` exit 2 before any dependency is called; a real reason lands in `state.review_waiver`, the result's `vendor_review` evidence and the `merge` call.
- [x] 5.3a Write evidence tests in `skills/tests/merge-pull-requests/test_execute_plan_review_evidence.py` (S)
  <!-- Scenario ID: merge-pull-requests.policy-waiver-recorded -->
  <!-- Scenario ID: merge-pull-requests.operator-waiver-recorded -->
  - **Spec scenarios:** policy-waiver-recorded, operator-waiver-recorded (evidence half)
  - **Design decisions:** D4, D7
  **Dependencies**: none
  - The merged result's `vendor_review` evidence carries `binding` (classification, head SHA, patch-id) and, when a waiver applied, `review_waiver` with its source (`policy` or `operator`) and reason; with no waiver the key is absent.
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 5.4 Make `vendor_review_block_reason` total in `scripts/execution_safety.py` (M)
  **Dependencies**: 5.1
- [x] 5.5 Wire binding, waivers and pinning into `scripts/execute_plan.py` (L)
  - Add `head_sha` to live state; add `pr_diff` and `pr_author` seams to `ExecutionDependencies`; bind every stored review; route the skip path through the predicate; record policy waivers; delete `_iterate_consensus_current` and the line-519 overwrite; pass `head_sha` and the waiver to `merge`; map a head-mismatch merge failure to `pending`; add `--waive-review` to `main()`; extend `_review_evidence` with `binding` and `review_waiver`.
  - Refuse to merge (node stays `pending`, reason `live head sha unavailable`) when the live head SHA is missing or not 40-hex, on the waived path as well as the verified path (D6).
  - Re-check a stored policy waiver against live eligibility on every run and clear it when the reasons differ; clear an operator waiver whose `waived_head_sha` differs from the live head (D4).
  - Bind a fresh vendor review to its `reviewed_head_sha`; when `head_moved` is true, do not bind it and keep the node `pending` with `head moved during review` (D6).
  - Derive `authors` from every PR commit and check independence against all of them (D5).
  <!-- Scenario ID: merge-pull-requests.missing-live-head-blocks -->
  <!-- Scenario ID: merge-pull-requests.stale-policy-waiver-cleared -->
  <!-- Scenario ID: merge-pull-requests.earlier-commit-author-rejected -->
  - Tests go in `scripts/tests/test_execute_plan.py` (missing head SHA, stale waiver, `head_moved` not bound) and `scripts/tests/test_verdict_binding.py` (multi-commit `authors`), written before the code.
  **Dependencies**: 3.4, 4.4, 5.2, 5.3, 5.3a, 5.4
- [x] Checkpoint: run tests, review diff, verify scope

## 6. Documentation and mirrors (wp-docs)

- [x] 6.1 Write the SKILL lint assertion for the verdict-binding reference in `skills/tests/merge-pull-requests/test_skill_md.py` (S)
  - **Design decisions:** D9
  **Dependencies**: none
  - `references/verdict-binding.md` exists, SKILL.md links it, and SKILL.md has no `iterate consensus` / `head_sha matches` phrasing.
- [x] 6.2 Write `references/verdict-binding.md` (S)
  - The currency table, `POLICY_WAIVABLE_REASONS`, `--waive-review`, the independence rules.
  **Dependencies**: 5.5
- [x] 6.3 Rewrite SKILL.md lines 141-142 in place (S)
  - Line count unchanged (`wc -l` before and after = 1128).
  **Dependencies**: 6.1, 6.2
- [x] 6.4 Add a coordination note to the adjudication design (S)
  - Append to `openspec/changes/add-orchestrator-adjudication-review-gate/design.md` D5: "use `verdict_binding.verdict_currency`; `same_family` matches".
  **Dependencies**: 5.5
- [x] 6.5 Re-sync runtime mirrors (S)
  - `bash skills/install.sh --mode rsync --deps none --python-tools none`, then `bash skills/install.sh --check`.
  - Mirrors touched: `merge-pull-requests` and `parallel-infrastructure` (wp-vendor-review changes `review_dispatcher.py`) under both `.claude/skills/` and `.agents/skills/`.
  **Dependencies**: 6.3
- [x] Checkpoint: run tests, review diff, verify scope

## 7. Verification

- [x] 7.1 Run the isolated merge-pull-requests suites (S)
  - From `skills/`: `.venv/bin/python -m pytest merge-pull-requests/scripts/tests tests/merge-pull-requests parallel-infrastructure/scripts/tests -q`
  **Dependencies**: 6.5
- [x] 7.2 Assert no `iterate_consensus_path` references remain (S)
  - `git grep -n iterate_consensus_path -- skills/merge-pull-requests skills/tests` is empty.
  **Dependencies**: 6.5
- [x] 7.3 Run strict OpenSpec validation (S)
  - `openspec validate bind-merge-verdicts-to-head-sha-and-patch-id --strict`
  **Dependencies**: 7.1, 7.2
