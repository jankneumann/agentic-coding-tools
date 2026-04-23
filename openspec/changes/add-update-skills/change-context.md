# Change Context: add-update-skills

<!-- 3-phase incremental artifact:
     Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design Decision,
       Test(s) planned. Files Changed = "---". Evidence = "---".
     Phase 2 (implementation): Files Changed populated. Tests pass (GREEN).
     Phase 3 (validation): Evidence filled with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-runtime-sync.1 | specs/skill-runtime-sync/spec.md | Canonical-to-runtime skill sync (install.sh wraps) | --- | --- | --- | test_update_skills.py::test_propagation, test_noop, test_commit_message, test_sync_failure_aborts, test_install_failure_aborts | --- |
| skill-runtime-sync.2 | specs/skill-runtime-sync/spec.md | Push with bounded retry (1s, 2s backoff; explicit origin) | --- | --- | --- | test_update_skills.py::test_push_success, test_push_retry, test_push_retry_exhausted | --- |
| skill-runtime-sync.3 | specs/skill-runtime-sync/spec.md | AGENTS.md byte-identity to CLAUDE.md + pre-commit drift guard | --- | --- | --- | test_sync_agents_md.py::test_regenerate, test_pre_commit_drift_rejection, test_pre_commit_in_sync_passes | --- |
| skill-runtime-sync.4 | specs/skill-runtime-sync/spec.md | Opt-in SessionStart auto-pull (AGENTIC_AUTO_PULL=1), wired for both Claude Code and Codex | --- | --- | --- | test_auto_pull.py::test_clean_tree_pulls, test_dirty_tree_skips, test_disabled_noop, test_both_runtimes_wired | --- |
| skill-runtime-sync.5 | specs/skill-runtime-sync/spec.md | sync_agents_md.py standalone tool (regenerate / --check / missing source) | --- | --- | --- | test_sync_agents_md.py::test_regenerate_copies_content, test_check_reports_drift, test_check_reports_in_sync, test_missing_source | --- |
| skill-runtime-sync.6 | specs/skill-runtime-sync/spec.md | install-hooks.sh bootstrap is idempotent | --- | --- | --- | test_install_hooks.py::test_first_run, test_idempotent_rerun, test_missing_uv | --- |

## Coverage Summary

- **Requirements traced**: 0/6
- **Tests mapped**: 0 requirements have at least one test
- **Evidence collected**: 0/6 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
