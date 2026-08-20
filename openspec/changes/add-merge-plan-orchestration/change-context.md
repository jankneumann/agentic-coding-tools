# Change Context: add-merge-plan-orchestration

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| merge-pull-requests.1 | `specs/merge-pull-requests/spec.md` | Emit schema-valid JSON and faithful Markdown plans with complete PR analysis state and dependency edges. | `contracts/schemas/merge-plan.schema.json` | D1, D2, D3 | `skills/merge-pull-requests/contracts/merge-plan.schema.json`; `skills/merge-pull-requests/scripts/merge_plan.py`; `skills/merge-pull-requests/scripts/build_plan.py`; `skills/merge-pull-requests/scripts/render_plan.py` | `skills/merge-pull-requests/scripts/tests/test_merge_plan_contract.py`, `test_build_plan.py`, `test_merge_plan_renderer.py` | --- |
| merge-pull-requests.2 | `specs/merge-pull-requests/spec.md` | Execute one planned PR after live re-checks, gates, review, merge, outcome persistence, and downstream invalidation. | `contracts/schemas/merge-plan.schema.json` | D2, D5, D6, D9 | `skills/merge-pull-requests/scripts/execute_plan.py`; `skills/merge-pull-requests/scripts/plan_storage.py` | `skills/merge-pull-requests/scripts/tests/test_execute_plan.py` | --- |
| merge-pull-requests.3 | `specs/merge-pull-requests/spec.md` | Insert discovered prerequisites without removing existing plan nodes. | `contracts/schemas/merge-plan.schema.json` | D7 | `skills/merge-pull-requests/scripts/merge_plan.py` | `skills/merge-pull-requests/scripts/tests/test_plan_amendment.py` | --- |
| merge-pull-requests.4 | `specs/merge-pull-requests/spec.md` | Record unresolved comments and return a delegation hand-off without modifying PR code. | `contracts/schemas/merge-plan.schema.json` | D8 | `skills/merge-pull-requests/scripts/execute_plan.py` | `skills/merge-pull-requests/scripts/tests/test_execute_plan.py` | --- |
| merge-infrastructure.1 | `specs/merge-infrastructure/spec.md` | Use file authority without a coordinator, render without mutation, and isolate definition fields from live state. | `contracts/schemas/merge-plan.schema.json` | D1, D3 | `skills/merge-pull-requests/scripts/plan_storage.py`; `skills/merge-pull-requests/scripts/render_plan.py` | `skills/merge-pull-requests/scripts/tests/test_plan_storage.py`, `test_merge_plan_renderer.py` | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Definition and live state have different lifecycles. | `merge_plan.py` validates and updates node state without changing definitions. | Keeps operator-reviewed topology stable across execution updates. |
| D2 | Merge ordering is a DAG and downstream nodes must be revalidated. | `build_plan.py` derives edges; `execute_plan.py` invalidates transitive dependants. | Makes stale mergeability explicit after main advances. |
| D3 | Coordinator is optional and the file tier is the Phase-1 authority. | `plan_storage.py` selects file storage on missing queue capability and exposes the Phase-2 coordinator seam. | Preserves solo/offline operation. |
| D5 | Only the merge operation is serialized. | Execution delegates the actual merge to the existing `merge_pr.py` guard path. | Reuses established safety checks. |
| D6 | Human gates and security checks fail closed. | `execute_plan.py` requires an explicit gate approval and preserves pending state on a security failure. | Prevents plan metadata from bypassing policy. |
| D7 | Plans must accept newly discovered blockers. | `amend_plan()` appends a validated prerequisite and dependency edges. | Supports changing risk information without rebuilding the cohort. |
| D8 | Comment resolution is delegated, not automated. | Executor persists the comment summary and returns workflow commands. | Avoids unsafe branch mutation in the merge context. |
| D9 | Runtime helpers must not depend on generated mirrors. | Scripts resolve siblings from canonical `skills/merge-pull-requests/scripts`. | Runtime mirrors may be absent or regenerated. |
| D10 | Coordinator auth scoping belongs to Phase 2. | Coordinator plan storage raises an explicit `NotImplementedError`. | Avoids implying unsupported multi-host safety. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 5/5
- **Tests mapped**: 5 requirements have at least one test
- **Evidence collected**: 0/5 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: Phase 2 coordinator storage, event delivery, cross-host dispatch, auth scoping, and automated comment-addressing are recorded in `deferred-tasks.md`.
