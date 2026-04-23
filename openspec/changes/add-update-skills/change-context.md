# Change Context: add-update-skills

<!-- 3-phase incremental artifact:
     Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design Decision,
       Test(s) planned. Files Changed = "---". Evidence = "---".
     Phase 2 (implementation): Files Changed populated. Tests pass (GREEN).
     Phase 3 (validation): Evidence filled with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-runtime-sync.1 | specs/skill-runtime-sync/spec.md | Canonical-to-runtime skill sync (install.sh wraps) | --- | --- | skills/update-skills/scripts/update_skills.py | test_update_skills.py::test_propagation_and_commit_message, test_noop_when_nothing_changed, test_install_failure_aborts, test_sync_failure_aborts_keeps_install_staged | pass (5 tests) |
| skill-runtime-sync.2 | specs/skill-runtime-sync/spec.md | Push with bounded retry (1s, 2s backoff; explicit origin) | --- | --- | skills/update-skills/scripts/update_skills.py | test_update_skills.py::test_push_success_exits_zero, test_push_retry_exhausted_emits_unpushed_commit | pass (2 tests) |
| skill-runtime-sync.3 | specs/skill-runtime-sync/spec.md | AGENTS.md byte-identity to CLAUDE.md + pre-commit drift guard | --- | --- | .pre-commit-config.yaml, skills/update-skills/scripts/sync_agents_md.py, CLAUDE.md | test_pre_commit_integration.py::test_drift_rejects_commit, test_in_sync_passes_commit, test_pre_commit_config_exists_and_parses | pass (3 tests) |
| skill-runtime-sync.4 | specs/skill-runtime-sync/spec.md | Opt-in SessionStart auto-pull (AGENTIC_AUTO_PULL=1), wired for both Claude Code and Codex | --- | --- | skills/session-bootstrap/scripts/hooks/auto_pull.py, .claude/settings.json, skills/session-bootstrap/scripts/bootstrap-cloud.sh | test_auto_pull.py (all 6) | pass (6 tests) |
| skill-runtime-sync.5 | specs/skill-runtime-sync/spec.md | sync_agents_md.py standalone tool (regenerate / --check / missing source) | --- | --- | skills/update-skills/scripts/sync_agents_md.py | test_sync_agents_md.py (all 8) | pass (8 tests) |
| skill-runtime-sync.6 | specs/skill-runtime-sync/spec.md | install-hooks.sh bootstrap is idempotent | --- | --- | install-hooks.sh, skills/pyproject.toml | test_pre_commit_integration.py::test_install_hooks_script_is_executable | partial (structural test only; end-to-end uv-sync behavior deferred to post-merge env) |

## Coverage Summary

- **Requirements traced**: 6/6
- **Tests mapped**: 6/6 requirements have at least one test
- **Evidence collected**: 5/6 requirements have full pass evidence; 1/6 partial (req .6 has structural test, full uv-sync behavior needs rsync-capable env)
- **Gaps identified**: install-hooks.sh end-to-end test (uv sync + pre-commit install) deferred because dev env lacks rsync for install.sh
- **Deferred items**: Full /update-skills end-to-end smoke in rsync-capable environment (task 5.4 partial)
