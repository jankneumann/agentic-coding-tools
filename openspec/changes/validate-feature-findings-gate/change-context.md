# Change Context: validate-feature-findings-gate

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| validate-feature-ephemeral.1 | specs/validate-feature-ephemeral/spec.md | Validation runs in a disposable worktree | --- | D1, D4 | skills/validate-feature/scripts/validation_worktree.py | test_validation_worktree.py::test_clean_ephemeral_run_uses_head_and_removes_scratch; test_validation_worktree.py::test_scratch_is_removed_when_validation_raises | --- |
| validate-feature-ephemeral.2 | specs/validate-feature-ephemeral/spec.md | Dirty input is explicit and exactly materialized | --- | D2 | skills/validate-feature/scripts/validation_worktree.py | test_validation_worktree.py::test_dirty_worktree_fails_fast_with_include_dirty_guidance; test_validation_worktree.py::test_include_dirty_materializes_index_worktree_and_untracked_state | --- |
| validate-feature-ephemeral.3 | specs/validate-feature-ephemeral/spec.md | Only durable artifacts survive | --- | D3 | skills/validate-feature/scripts/validation_worktree.py | test_validation_worktree.py::test_results_are_copied_back_before_teardown_and_no_residue_escapes | --- |
| validate-feature-ephemeral.4 | specs/validate-feature-ephemeral/spec.md | Harness isolation is reused | --- | D5 | skills/validate-feature/scripts/validation_worktree.py | test_validation_worktree.py::test_cloud_harness_downgrades_to_in_place | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Validate an exact source identity without a feature branch | Detached Git worktree at source HEAD | No branch or commit side effect |
| D2 | Never silently validate stale HEAD | Dirty refusal plus explicit materialization | Source state remains untouched |
| D3 | Results must survive but residue must not | Two-file copy-back allowlist | Small, auditable isolation boundary |
| D4 | Failure must not leak scratch state | Nested finally blocks and scoped teardown | Cleanup runs after pass or exception |
| D5 | Nested isolation is unnecessary in cloud harnesses | Shared environment-profile detection | Matches repository-wide behavior |

## Coverage Summary

- **Requirements traced**: 4/4
- **Tests mapped**: 4 requirements have at least one test
- **Evidence collected**: 0/4 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
