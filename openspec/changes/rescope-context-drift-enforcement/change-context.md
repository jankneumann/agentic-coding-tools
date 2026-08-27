# Change Context: rescope-context-drift-enforcement

Capability: `project-context-refresh-orchestration`. Rows are one-per-scenario, following the
convention `fix-architecture-freshness-evidence` established — scenarios are the testable
unit, requirements are the grouping.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|---|---|---|---|---|---|---|---|
| pcro.1 | specs/project-context-refresh-orchestration/spec.md | Stale artifacts are named individually | --- | --- | --- | test_gate.py (existing pin) | --- |
| pcro.2 | specs/project-context-refresh-orchestration/spec.md | Gate reproduces locally | --- | D1 | --- | test_gate.py (existing pin) | --- |
| pcro.3 | specs/project-context-refresh-orchestration/spec.md | Gate reproduces across environments in both directions | contracts/context-drift-gate.schema.json | D1 | --- | test_gate.py::test_remote_ref_wins_over_stale_local (1.2), ::test_one_tree_one_verdict_across_checkout_shapes (1.3) | --- |
| pcro.4 | specs/project-context-refresh-orchestration/spec.md | Resolved base is recorded | contracts/context-drift-gate.schema.json | D1 | --- | test_gate.py::test_resolved_base_revision_in_report (1.1) | --- |
| pcro.5 | specs/project-context-refresh-orchestration/spec.md | Gate leaves the checkout unchanged | --- | --- | --- | test_gate.py (existing pin) | --- |
| pcro.6 | specs/project-context-refresh-orchestration/spec.md | Groups are disjoint | --- | D3 | --- | test_classify_degradation.py (existing pin) | --- |
| pcro.7 | specs/project-context-refresh-orchestration/spec.md | Inherited drift names the integration branch as owner | contracts/context-drift-gate.schema.json | D2, D3 | --- | test_gate.py::test_base_present_drift_is_inherited (2.1) | --- |
| pcro.8 | specs/project-context-refresh-orchestration/spec.md | Introduced drift is attributed to the branch | contracts/context-drift-gate.schema.json | D2, D3 | --- | test_gate.py::test_branch_caused_drift_is_introduced (2.2) | --- |
| pcro.9 | specs/project-context-refresh-orchestration/spec.md | Ambiguous attribution errs toward inherited | contracts/context-drift-gate.schema.json | D2 | --- | test_gate.py::test_indeterminate_attribution_is_inherited (2.3) | --- |
| pcro.10 | specs/project-context-refresh-orchestration/spec.md | Existing outcome decision is unaffected | --- | D3 | --- | test_classify_degradation.py::TestPurity, ::test_informational_producers_pinned (2.8) | --- |
| pcro.11 | specs/project-context-refresh-orchestration/spec.md | Failure outranks drift | --- | --- | --- | test_gate.py (existing pin) | --- |
| pcro.12 | specs/project-context-refresh-orchestration/spec.md | Inherited drift alone does not fail a pull request | --- | D4 | --- | test_gate.py::test_inherited_only_passes_pull_request (3.1) | --- |
| pcro.13 | specs/project-context-refresh-orchestration/spec.md | Introduced drift fails a pull request | --- | D4 | --- | test_gate.py::test_introduced_fails_pull_request (3.2) | --- |
| pcro.14 | specs/project-context-refresh-orchestration/spec.md | Inherited drift blocks on the integration branch | --- | D4 | --- | test_gate.py::test_inherited_blocks_on_integration_branch (3.3) | --- |
| pcro.15 | specs/project-context-refresh-orchestration/spec.md | Absent optional owner alone passes | --- | --- | --- | test_gate.py (existing pin) | --- |
| pcro.16 | specs/project-context-refresh-orchestration/spec.md | Existing entry points keep their codes | --- | D4 | --- | test_gate.py (existing pin), Makefile equivalence at test_gate.py:824 (3.8) | --- |
| pcro.17 | specs/project-context-refresh-orchestration/spec.md | Unchanged packages are not reported | --- | D6 | --- | test_context_impact.py (existing pin) | --- |
| pcro.18 | specs/project-context-refresh-orchestration/spec.md | Co-present work-package files are not blamed for unrelated paths | --- | D6 | --- | test_context_impact.py::test_copresent_file_not_blamed (4.1) | --- |
| pcro.19 | specs/project-context-refresh-orchestration/spec.md | Legacy packages without declarations pass | --- | D6 | --- | test_context_impact.py (existing pin) | --- |
| pcro.20 | specs/project-context-refresh-orchestration/spec.md | Validator usage error is an apparatus failure | --- | D6 | --- | test_context_impact.py (existing pin) | --- |
| pcro.21 | specs/project-context-refresh-orchestration/spec.md | Gate runs on every declared event | --- | D4 | --- | ci.yml job-level `if:` absence check (3.7) | --- |
| pcro.22 | specs/project-context-refresh-orchestration/spec.md | Unknown event fails loudly | --- | D4 | --- | test_gate.py::test_unhandled_event_fails (3.6) | --- |
| pcro.23 | specs/project-context-refresh-orchestration/spec.md | Dependency-update pull request is remediated | --- | D5 | --- | test_remediation_policy.py::test_dependabot_pr_is_remediated (5.3, 5.4) | --- |
| pcro.24 | specs/project-context-refresh-orchestration/spec.md | Human pull request is not written to | --- | D5 | --- | test_remediation_policy.py::test_human_pr_not_written (5.1) | --- |
| pcro.25 | specs/project-context-refresh-orchestration/spec.md | Write permission is scoped to the remediation job | --- | D5 | --- | test_remediation_policy.py::test_write_permission_is_job_scoped (5.2) | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|---|---|---|---|
| D1 | Base resolution prefers the remote ref and records what it chose | `gate.py` resolver; `base_resolved_from` + resolved revision in report | `describe_tree` already used `origin/<base>`, and a fresh `actions/checkout` has no local base branch — preferring local would make CI the outlier |
| D2 | Attribution uses path-level ancestry, not content | `git diff --name-only <source_revision>..<merge_base> -- <input_roots>` | Content comparison is unavailable at another revision; revision-aware hashing would change the payload format and invalidate every recorded `input_fingerprint` |
| D3 | Attribution is a separate axis, not a fifth group | Computed alongside `classify_degradation`, attached to findings in the report | `test_classify_degradation.py:235` pins the informational set and `TestPurity` asserts no IO; attribution shells out to git |
| D4 | Event behaviour lives inside one always-running job | `EVENT_NAME` `case` in the gate step with a failing `*)` arm | Repository precedent (`requirement-traceability-sweep`, `ci.yml:626`); a skipped required check reports success to branch protection |
| D5 | The servo is confined to dependabot and a job-scoped write grant | Remediation job in `ci.yml` with job-level `permissions: contents: write` | First write grant in the repo; dependabot is provably never the cause of context drift |
| D6 | Context-impact attributes by declared scope | `context_impact.py` matches changed paths against each package's declared scope | Co-presence in a diff is not authorship — reproduced from PR #423's false `wp-integration` blame |
| D7 | Metrics are an additive event type | `context_gate` record on `MergeEvent` | `event_type` is an open `str` and `to_dict()` drops `None`; existing readers ignore unknown types |
| D8 | Both promotion notes are rewritten together | Single edit across `session-completion.md` | `specs/fitness-functions/spec.md:115-116` makes the adjacency normative; deleting one leaves a dangling back-reference |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|---|---|---|---|---|---|

## Coverage Summary

- **Requirements traced**: 0/25
- **Tests mapped**: 25 requirements have at least one test
- **Evidence collected**: 0/25 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: tasks 7.2 and 7.3 (branch-protection promotion) require repository-admin action and cannot be performed by a pull request
