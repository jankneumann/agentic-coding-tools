# Change Context: rescope-merge-pull-requests-to-plan-execute

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| merge-pull-requests.1 | Plan-Then-Execute Default Path | Default path is analyze/discuss/persist/execute | contracts/merge-plan.schema.json | D1 | skills/merge-pull-requests/SKILL.md | SKILL.md default conductor section | --- |
| merge-pull-requests.2 | Node Kind Classification | Heuristic plus operator override | contracts/merge-plan.schema.json | D2 | skills/merge-pull-requests/scripts/classify_kind.py | test_classify_kind.py | --- |
| merge-pull-requests.3 | Operator Plan Discussion | No side effects before plan approval | --- | D1 | skills/merge-pull-requests/SKILL.md | SKILL.md discuss step | --- |
| merge-pull-requests.4 | Orchestrated Iterate Remediation | iterate-on-plan vs iterate-on-implementation | --- | D1, D3, D9 | skills/merge-pull-requests/scripts/execute_plan.py, iterate_preconditions.py | test_iterate_preconditions.py, test_execute_plan.py | --- |
| merge-pull-requests.5 | Cheap Path for Scoped Automation | Green automation skips iterate and vendor review | --- | D4 | skills/merge-pull-requests/scripts/execute_plan.py | test_cheap_path_skips_vendor_review | --- |
| merge-pull-requests.6 | CI Failure Class in Analysis | transient / pr_specific / stale_base | contracts/merge-plan.schema.json | D8 | skills/merge-pull-requests/scripts/classify_kind.py | test_stale_base_class_from_ci_merge_base_stale | --- |
| merge-pull-requests.7 | Per-Node Agent Compact | compact_requested plus last_merged_pr | contracts/merge-plan.schema.json | D5 | skills/merge-pull-requests/scripts/execute_plan.py, next_node.py | test_next_node.py, test_cheap_path | --- |
| merge-pull-requests.8 | Sync-Point Released Around Remediation | Do not hold main lock across iterate | --- | D6 | skills/merge-pull-requests/SKILL.md | SKILL.md conductor | --- |
| merge-infrastructure.1 | Schema 1.1 kind fields | Round-trip kind / change_id / remediation_skill | contracts/merge-plan.schema.json | D7 | skills/merge-pull-requests/contracts/merge-plan.schema.json | test_merge_plan_contract.py | --- |
| skill-workflow.1 | Merge invokes iterate | Feature-branch writes only | --- | D1, D6 | skills/merge-pull-requests/SKILL.md | SKILL.md conductor | --- |
| skill-workflow.2 | Iterate vendor review from merge | Always pass --vendor-review | --- | D3 | skills/merge-pull-requests/scripts/execute_plan.py | test_plan_kind_delegation | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Conductor vs kernel | SKILL.md + execute_plan.py | Reuse iterate; keep merge safety |
| D2 | Prefix heuristic | classify_kind.py | Operator override is authoritative |
| D3 | Iterate review of record | execute_plan skip on consensus HEAD | Removes duplicate console |
| D4 | Cheap path origins | kind=automation skip | Matches existing skip-origin set |
| D5 | Compact from merge-plan.json | last_merged_pr, compact_requested | Not autopilot loop-state |
| D6 | Sync-point not across iterate | SKILL.md sequence | Iterate worktrees are active agents |
| D7 | Schema 1.1 additive | merge-plan.schema.json | Fail closed on 1.0 |
| D8 | Runtime edges operator-inserted | amend_plan + ci_failure_class | File overlap is insufficient |
| D9 | Iterate preconditions | iterate_preconditions.py | Fail closed on wrong pairing |

## Coverage Summary

- **Requirements traced**: 11/11
- **Tests mapped**: 11 requirements have at least one test
- **Evidence collected**: 0/11 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
