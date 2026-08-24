# Change Context: validate-feature-findings-gate

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| validate-feature-ephemeral.1 | specs/validate-feature-ephemeral/spec.md | Validation runs in a disposable worktree | --- | D1, D4 | skills/validate-feature/scripts/validation_worktree.py | test_clean_ephemeral_run_uses_head_and_removes_scratch; test_scratch_is_removed_when_validation_raises | pass (focused suite) |
| validate-feature-ephemeral.2 | specs/validate-feature-ephemeral/spec.md | Dirty input is explicit and exactly materialized | --- | D2 | skills/validate-feature/scripts/validation_worktree.py | test_dirty_worktree_fails_fast_with_include_dirty_guidance; test_include_dirty_materializes_index_worktree_and_untracked_state; test_cloud_include_dirty_records_exact_tree_without_changing_source | pass (focused suite) |
| validate-feature-ephemeral.3 | specs/validate-feature-ephemeral/spec.md | Only changed durable artifacts survive | --- | D3 | skills/validate-feature/scripts/validation_worktree.py | test_results_are_copied_back_before_teardown_and_no_residue_escapes; test_exception_does_not_restamp_unchanged_preexisting_artifacts | pass (focused suite) |
| validate-feature-ephemeral.4 | specs/validate-feature-ephemeral/spec.md | Validation paths fail closed | --- | D6 | skills/validate-feature/scripts/validation_worktree.py | test_change_id_is_validated_before_paths_are_created; test_change_directory_symlink_escape_is_rejected; test_scratch_root_symlink_escape_is_rejected; test_symlink_artifact_source_is_rejected_and_not_copied; test_symlink_artifact_destination_is_rejected | pass (focused suite) |
| validate-feature-ephemeral.5 | specs/validate-feature-ephemeral/spec.md | Ephemeral phase boundary is executable and fails closed | --- | D3, D4, D6 | skills/validate-feature/scripts/validation_worktree.py; skills/validate-feature/SKILL.md | test_prepare_finalize_cli_is_an_end_to_end_ephemeral_path; test_skill_wires_ephemeral_flags_to_the_canonical_helper; test_documented_shell_boundary_fails_closed_before_eval; test_documented_shell_signal_handler_finalizes_and_exits | pass (focused suite) |
| validate-feature-ephemeral.6 | specs/validate-feature-ephemeral/spec.md | Harness isolation is reused | --- | D5 | skills/validate-feature/scripts/validation_worktree.py | test_cloud_harness_downgrades_to_in_place; test_cloud_harness_still_refuses_dirty_source_without_opt_in | pass (focused suite) |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Validate an exact source identity without a feature branch | Detached Git worktree at source HEAD | No branch or commit side effect |
| D2 | Never silently validate stale HEAD | Dirty refusal plus explicit materialization | Source state remains untouched |
| D3 | Results must survive but residue must not | Three-file, changed-only atomic copy-back allowlist | Small, auditable isolation boundary |
| D4 | Failure must not leak scratch state | Nested finally blocks and scoped teardown | Cleanup runs after pass or exception |
| D5 | Nested isolation is unnecessary in cloud harnesses | Shared environment-profile detection | Matches repository-wide behavior |
| D6 | Copy-back and teardown cross a security boundary | Identifier validation, resolved containment, symlink rejection, registered-worktree verification, and atomic replacement | Filesystem operations fail closed |

## Coverage Summary

- **Requirements traced**: 6/6
- **Tests mapped**: 6 requirements have at least one test
- **Evidence collected**: 6/6 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
