You are reviewing a remediation commit on PR #703 (OpenSpec change bind-merge-verdicts-to-head-sha-and-patch-id) in this repository. Read-only review: do not modify files.

Scope (keep it tight):
1. Run: git show 3d82f3b8 -- skills/ openspec/changes/bind-merge-verdicts-to-head-sha-and-patch-id/work-packages.yaml
2. Read for context only as needed: skills/merge-pull-requests/scripts/verdict_binding.py (validate_binding, verdict_currency, independence_violation), skills/merge-pull-requests/scripts/execution_safety.py (vendor_review_block_reason), and the execute_node function in skills/merge-pull-requests/scripts/execute_plan.py (from "live_head = live.get" to the end of execute_node).
3. Requirements: openspec/changes/bind-merge-verdicts-to-head-sha-and-patch-id/specs/ (spec deltas).

The commit addresses two review findings:
(a) A stored verdict whose binding is malformed (e.g. only head_sha) must not pass the merge predicate: currency would say "current" and the independence check would treat a missing author/reviewers as no violation. Fix: vendor_review_block_reason calls validate_binding and blocks; execute_plan treats a malformed stored binding as superseded and dispatches a fresh review.
(b) The bound verdict and review waiver must be durably persisted before calling the merge dependency, so a crash after GitHub accepts the merge (or before it) does not lose audit evidence and replay finds a recorded operator waiver. Fix: store.save(plan) under the held claim right before dependencies.merge.
It also declares context_impact surfaces (apis on wp-schema, documentation on wp-docs).

Evaluate: is each fix correct and complete? Can a malformed or partial binding still reach a merge by any path (stored reuse, fresh review, cheap path, operator waiver, replay)? Does the pre-merge save introduce revision-conflict, replay, or reconciliation regressions? Are the new tests meaningful?

Output ONLY valid JSON conforming to review-findings.schema.json (review_type "implementation", target "bind-merge-verdicts-to-head-sha-and-patch-id"). Use an empty findings array if nothing at medium or higher is wrong.
