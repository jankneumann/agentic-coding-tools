# Change Context: conditional-worktree-generation

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|--------------|-----------------|---------------|---------|----------|
| worktree-isolation.1 | specs/worktree/spec.md Req 1 | Every worktree.py subcommand consults EnvironmentProfile.detect(); write ops no-op when isolation_provided=true | --- | D1, D3, D5 | skills/worktree/scripts/worktree.py; skills/shared/environment_profile.py | test_environment_aware.py::TestSetupShortCircuit, TestWriteOpsShortCircuit; test_environment_profile.py (full module) | --- |
| worktree-isolation.2 | specs/worktree/spec.md Req 1 Scenario 1 | Local single-agent run creates a worktree by default | --- | D1 | skills/shared/environment_profile.py; skills/worktree/scripts/worktree.py | test_environment_aware.py::TestLocalBackwardCompat::test_local_setup_creates_worktree | --- |
| worktree-isolation.3 | specs/worktree/spec.md Req 1 Scenario 2 | Cloud harness short-circuits setup with toplevel path and current branch | --- | D3, D5 | skills/worktree/scripts/worktree.py cmd_setup | test_environment_aware.py::TestSetupShortCircuit::test_cloud_setup_emits_toplevel_and_current_branch, test_cloud_setup_survives_branch_already_checked_out | --- |
| worktree-isolation.4 | specs/worktree/spec.md Req 1 Scenario 3 | teardown/pin/unpin/heartbeat/gc no-op under cloud mode | --- | D3 | skills/worktree/scripts/worktree.py (all write cmds) | test_environment_aware.py::TestWriteOpsShortCircuit (5 test cases) | --- |
| worktree-isolation.5 | specs/worktree/spec.md Req 1 Scenario 4 | Read-only introspection (list/status/resolve-branch) continues to function under cloud mode | --- | D4 | skills/worktree/scripts/worktree.py (unchanged for these commands) | test_worktree.py::TestCmdStatus, TestCmdList, TestCmdResolveBranch (regression suite — still green) | --- |
| worktree-isolation.6 | specs/worktree/spec.md Req 2 | Detection precedence: env var > coordinator > heuristic > default | --- | D2, D6, D7 | skills/shared/environment_profile.py | test_environment_profile.py::TestPrecedence (3 test cases), TestEnvVarLayer, TestCoordinatorLayer, TestHeuristicLayer | --- |
| worktree-isolation.7 | specs/worktree/spec.md Req 3 | OPENSPEC_BRANCH_OVERRIDE remains orthogonal to new signal | --- | D2 | skills/shared/environment_profile.py (does NOT read OPENSPEC_BRANCH_OVERRIDE); skills/worktree/scripts/worktree.py (unchanged resolve_branch) | test_environment_aware.py::TestOrthogonalBranchOverride::test_branch_override_alone_creates_worktree | --- |
| worktree-isolation.8 | specs/worktree/spec.md Req 4 | merge_worktrees.py short-circuits under cloud mode with PR guidance | --- | D8 | skills/worktree/scripts/merge_worktrees.py main() | test_merge_cloud_mode.py::TestMergeCloudShortCircuit (2 test cases), TestMergeLocalBackwardCompat::test_merge_proceeds_normally_under_local_mode | --- |
| worktree-isolation.9 | specs/worktree/spec.md Req 5 Scenario 1 | Existing local single-agent plan-feature run unchanged | --- | --- | skills/worktree/scripts/worktree.py (backward-compat path retained) | test_worktree.py (full regression suite — 64 tests green) | --- |
| worktree-isolation.10 | specs/worktree/spec.md Req 5 Scenario 2 | Existing local-parallel implement-feature run unchanged | --- | --- | skills/worktree/scripts/worktree.py (backward-compat path retained) | test_worktree.py (full regression suite — 64 tests green) | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 (EnvironmentProfile helper location) | Pure, testable, reusable; avoids coupling env detection to git plumbing | `skills/shared/environment_profile.py` module with `EnvironmentProfile` dataclass and `detect()` function | Extracting to `skills/shared/` lets future callers (validate-feature, etc.) reuse without circular imports through worktree module |
| D2 (Precedence: env var > coordinator > heuristic > default) | Explicit operator intent > automated detection > conservative default | Three-layer function chain in `detect()` with testing hooks for each layer | Matches Gate-1 user answer; explicit env var always wins to support operator overrides |
| D3 (No-op under isolation, not error) | Transparent upgrade: existing SKILL.md call sites work unchanged | Every `cmd_*` in worktree.py and `main()` in merge_worktrees.py begins with `if _short_circuit_if_isolated(op): return 0` | Erroring would break unconditional `worktree.py setup` calls in plan/implement/cleanup skills |
| D4 (Read-only ops pass through) | list/status/resolve-branch are needed for introspection in both modes | No code change for `cmd_list`, `cmd_status`, `cmd_resolve_branch` | They don't mutate `.git-worktrees/` state, so short-circuiting would break operator debugging |
| D5 (cmd_setup emits toplevel + current-branch) | Downstream `cd "$WORKTREE_PATH"` must be a no-op in cloud mode | `cmd_setup` runs `git rev-parse --show-toplevel` + `git branch --show-current` and echoes them before returning | Shell callers do `eval "$(worktree.py setup …)"` + `cd "$WORKTREE_PATH"`; this keeps them working without any SKILL.md change |
| D6 (Conservative heuristic markers only) | Hostname patterns are brittle in local dev containers | Heuristic checks only `/.dockerenv`, `KUBERNETES_SERVICE_HOST`, `CODESPACES=true` | Rejected regex matching on HOSTNAME because local dev containers match arbitrary patterns |
| D7 (Coordinator layer is optional and non-blocking) | No hard dependency on coordinator for worktree.py to function | 500ms urlopen timeout + broad exception handler that falls through silently | Coordinator may be unreachable, down, or simply not deployed in sequential/local-parallel workflows |
| D8 (merge_worktrees.py exits 0 with guidance, not error) | /cleanup-feature calls merge_worktrees.py unconditionally | main() checks detect() before calling merge_packages; prints PR-integration guidance and returns 0 | Erroring would break cleanup flows; one-container-per-package means each package pushes its own branch and PR is the integration point |

## Review Findings Summary

(Not applicable — implementation done sequentially within a single cloud container rather than dispatching per-package parallel review agents.)

## Coverage Summary

- **Requirements traced**: 10/10 (all spec scenarios mapped to tests and implementation files)
- **Tests mapped**: 10/10 requirements have at least one dedicated test (116 total test cases across env profile + worktree + merge)
- **Evidence collected**: 0/10 — Evidence column populated after CI/validation run (Phase 3)
- **Gaps identified**: Phase 5 (wp-coordinator-ext) deferred to follow-up PR — adding the optional `isolation_provided` field to the agent-coordinator discovery schema requires coordination with the coordinator team and is non-blocking: the heuristic and env-var layers cover the immediate need.
- **Deferred items**: (1) agent-coordinator isolation_provided field registration; (2) harness-side `AGENT_EXECUTION_ENV=cloud` injection (owned by cloud-harness repo, not this one — until then, `/.dockerenv` heuristic fires correctly as safety net).
