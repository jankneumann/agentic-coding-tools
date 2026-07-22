# Bug Scrub Report

**Timestamp**: 2026-07-22T14:28:08.367656+00:00
**Sources**: pytest, ruff, mypy, openspec, architecture, security, deferred, markers
**Severity filter**: low
**Total findings**: 3561

## Executive Triage (GitHub + Canonical Test Suites)

This section is a manual cross-check of the raw collectors against the 21 open
GitHub issues, the latest `main` workflows, and the repository's separate `uv`
test environments. The generated JSON remains the unmodified machine-readable
collector output.

### Prioritized Actionable Findings

| Priority | Finding | Evidence | Recommended next action |
|----------|---------|----------|-------------------------|
| high | Both dependency-audit jobs fail on `pyasn1 0.6.3` due to CVE-2026-59885 and CVE-2026-59886; `0.6.4` is fixed. No open issue tracks this recurrence. | [Security run 29872731764](https://github.com/jankneumann/agentic-coding-tools/actions/runs/29872731764) | File a focused security issue, constrain `pyasn1>=0.6.4` in both environments, refresh locks, and rerun both audits. |
| high | `skills/use-railway/scripts/enable-pg-stats.py:149` calls `run_railway_command` without importing it. The restart-required path raises `NameError` after changing PostgreSQL configuration. | Ruff F821 plus source inspection; `run_railway_command` is defined in `skills/use-railway/scripts/dal.py`. | Import the helper and add a test for the restart-required path. |
| medium | Autopilot cross-environment fixtures violate the current archetype schema: 7 failed, 2 passed. | [Issue #260](https://github.com/jankneumann/agentic-coding-tools/issues/260); reproduced with the coordinator environment. | Add required `write_capable` fields and document the intended cross-environment command. |
| medium | Three `docker_manager` tests fail reproducibly on macOS because platform/Colima probes are not fully mocked; Linux CI remains green. | `2025 passed, 3 failed, 1 skipped` in the coordinator unit suite; isolated node IDs reproduce. | Make the tests platform-independent by explicitly patching `sys.platform`, `is_colima_installed`, and `is_colima_running` as appropriate. |
| medium | Dependabot security updates, secret scanning, and push protection are disabled; the new `pyasn1` audit break demonstrates the recurring transitive-CVE gap. | [Issue #219](https://github.com/jankneumann/agentic-coding-tools/issues/219) and repository security settings. | Enable Dependabot security updates and evaluate enabling secret scanning/push protection. |
| medium | Rebase-merging can leave OpenSpec changes unarchived and worktrees pinned. | [Issue #221](https://github.com/jankneumann/agentic-coding-tools/issues/221). | Add post-merge detection against `origin/main`, then automate or prompt for archive cleanup. |
| medium | Cleanup assumes `gh pr merge --delete-branch` deleted the remote branch without verifying it. | [Issue #154](https://github.com/jankneumann/agentic-coding-tools/issues/154). | Verify the remote ref is absent and surface explicit remediation when it remains. |
| medium | The pre-merge gate still parses exact Markdown status formatting rather than a machine-readable contract. | [Issue #158](https://github.com/jankneumann/agentic-coding-tools/issues/158) and current `gate_logic.py`. | Emit and prefer structured gate status, retaining Markdown as presentation/fallback. |

### Open-Issue Hygiene

- [Issue #232](https://github.com/jankneumann/agentic-coding-tools/issues/232)
  is fixed by commit `e949446e` / PR #234 (`joserfc>=1.6.8`) but remains open.
- [Issue #213](https://github.com/jankneumann/agentic-coding-tools/issues/213)
  is fixed by commit `c492f940` / PR #218 but remains open.
- [Issue #167](https://github.com/jankneumann/agentic-coding-tools/issues/167)
  is fixed by commit `a12b063a`: worktree setup now starts from a matching
  `origin/<branch>` ref, but the issue remains open.
- [Issue #150](https://github.com/jankneumann/agentic-coding-tools/issues/150)
  appears obsolete: the current quality-gate instructions dispatch commands
  directly and contain no `tail` pipeline. Verify history, then close or rewrite.
- [Issue #148](https://github.com/jankneumann/agentic-coding-tools/issues/148)
  is tied to an old PR-specific Sonar window and needs dashboard triage rather
  than being treated as a current code failure.

### Validation Results

- Skills canonical suite: **837 passed**.
- Coordinator canonical unit suite: **2025 passed, 3 failed, 1 skipped, 90 deselected**.
- Autopilot cross-environment regression files: **7 failed, 2 passed**.
- Latest normal CI on `main`: **success**.
- Latest Security workflow on `main`: **failure** in both dependency-audit jobs;
  secret-scan job passed.
- OpenSpec strict validation and root mypy collector: no parsed findings.

### Collector Caveats

- The architecture artifact claims 2,233 findings, but its internal timestamp is
  2026-05-30 and its Git SHA is `a2b169ef`, not current `main` (`520a5d63`). The
  collector checks filesystem mtime, which a fresh checkout resets, so it failed
  to emit the required staleness warning. Refresh architecture before planning
  from those findings and fix staleness detection to prefer embedded metadata.
- Root pytest mixed sibling environments and stopped at 113 collection errors.
  The canonical per-project suites above supersede that signal.
- The local security collector skipped because no saved security-review JSON was
  present. The live GitHub Security workflow supplied the current audit signal.
- The 907 deferred items span 44 active/archived changes (385 medium active, 522
  low archived); they are backlog inventory, not 907 independent bugs.
- The 387 root-wide Ruff diagnostics are outside the enforced per-project lint
  baselines. Most are import-order/unused-import noise, but the Railway F821
  finding above is a confirmed runtime defect.

## Summary

### By Severity

| Severity | Count |
|----------|-------|
| high | 89 |
| medium | 2839 |
| low | 633 |

### By Source

| Source | Count |
|--------|-------|
| architecture | 2233 |
| deferred:impl-findings | 1 |
| deferred:open-tasks | 907 |
| markers | 33 |
| ruff | 387 |

## Critical / High Findings

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/archive-roadmap/scripts/archive.py:40
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot-roadmap/scripts/orchestrator.py:25
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot-roadmap/scripts/orchestrator.py:26
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot-roadmap/scripts/orchestrator.py:27
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot-roadmap/scripts/orchestrator.py:43
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot-roadmap/scripts/orchestrator.py:44
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot-roadmap/scripts/policy.py:21
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot-roadmap/scripts/replanner.py:19
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot-roadmap/scripts/replanner.py:20
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/scripts/tests/test_autopilot.py:20
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/scripts/tests/test_convergence_loop.py:20
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/scripts/tests/test_convergence_loop.py:24
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/scripts/tests/test_convergence_loop.py:29
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/tests/test_convergence_escalation.py:38
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/tests/test_convergence_escalation.py:43
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/tests/test_convergence_escalation.py:48
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/tests/test_convergence_metrics.py:38
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/tests/test_convergence_metrics.py:43
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/autopilot/tests/test_convergence_metrics.py:44
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/claude_code_cli.py:28
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/claude_code_cli.py:29
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/claude_code_web.py:29
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/claude_code_web.py:30
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/claude_code_web.py:31
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/codex_cli.py:31
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/codex_cli.py:32
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/codex_web.py:27
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/codex_web.py:28
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/codex_web.py:29
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/gemini_cli.py:33
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/scripts/adapters/gemini_cli.py:34
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/tests/test_deep_analyze.py:23
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/tests/test_deep_analyze.py:24
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/collect-transcripts/tests/test_triage.py:23
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/parallel-infrastructure/scripts/dag_scheduler.py:31
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/parallel-infrastructure/scripts/tests/test_circuit_breaker.py:16
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/parallel-infrastructure/scripts/tests/test_dag_scheduler.py:24
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/parallel-infrastructure/scripts/tests/test_escalation_handler.py:15
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/parallel-infrastructure/scripts/tests/test_integration_orchestrator.py:15
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/parallel-infrastructure/scripts/tests/test_package_executor.py:15
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/parallel-infrastructure/scripts/tests/test_result_validator.py:15
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/parallel-infrastructure/scripts/tests/test_scope_checker.py:14
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/plan-roadmap/scripts/decomposer.py:33
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/plan-roadmap/scripts/renderer.py:24
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/plan-roadmap/scripts/scaffolder.py:20
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/playwright-validator/scripts/findings.py:76
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/playwright-validator/scripts/findings.py:77
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/refresh-architecture/scripts/analyze_python.py:34
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/refresh-architecture/scripts/analyze_python.py:35
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/refresh-architecture/scripts/analyze_python.py:36
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/refresh-architecture/scripts/analyze_python.py:37
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/refresh-architecture/scripts/generate_views.py:34
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/refresh-architecture/scripts/tests/test_analyze_sql_treesitter.py:17
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/refresh-architecture/scripts/tests/test_comment_linker.py:18
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/refresh-architecture/scripts/tests/test_enrich_with_treesitter.py:16
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/refresh-architecture/scripts/tests/test_pattern_reporter.py:18
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/roadmap-runtime/scripts/checkpoint.py:17
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/roadmap-runtime/scripts/context.py:19
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/roadmap-runtime/scripts/context.py:20
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/roadmap-runtime/scripts/learning.py:21
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/roadmap-runtime/scripts/learning.py:22
- **Detail**: Module level import not at top of file

### [HIGH] E741: Ambiguous variable name: `l`

- **Source**: ruff
- **Category**: lint
- **Location**: skills/session-log/scripts/test_extract_session_log.py:92
- **Detail**: Ambiguous variable name: `l`

### [HIGH] E741: Ambiguous variable name: `l`

- **Source**: ruff
- **Category**: lint
- **Location**: skills/session-log/scripts/test_extract_session_log.py:93
- **Detail**: Ambiguous variable name: `l`

### [HIGH] E741: Ambiguous variable name: `l`

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tech-debt-analysis/scripts/analyze_duplication.py:191
- **Detail**: Ambiguous variable name: `l`

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/archive-roadmap/test_archive.py:16
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/archive-roadmap/test_archive.py:18
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/integration/test_prototype_convergence.py:45
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/integration/test_prototype_convergence.py:46
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/integration/test_prototype_convergence.py:47
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/iterate-on-plan/test_prototype_context.py:32
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/iterate-on-plan/test_prototype_recommended.py:24
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/prototype-feature/test_collect_outcomes.py:35
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/prototype-feature/test_collect_outcomes.py:40
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/prototype-feature/test_dispatch_variants.py:33
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/tests/prototype-feature/test_skill_invariants.py:28
- **Detail**: Module level import not at top of file

### [HIGH] E741: Ambiguous variable name: `l`

- **Source**: ruff
- **Category**: lint
- **Location**: skills/use-railway/scripts/analyze-mysql.py:127
- **Detail**: Ambiguous variable name: `l`

### [HIGH] E741: Ambiguous variable name: `l`

- **Source**: ruff
- **Category**: lint
- **Location**: skills/use-railway/scripts/analyze-mysql.py:139
- **Detail**: Ambiguous variable name: `l`

### [HIGH] E741: Ambiguous variable name: `l`

- **Source**: ruff
- **Category**: lint
- **Location**: skills/use-railway/scripts/analyze-redis.py:240
- **Detail**: Ambiguous variable name: `l`

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/validate-feature/scripts/run_architecture_linters.py:28
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/validate-feature/scripts/tests/test_gate_logic.py:23
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/validate-feature/scripts/tests/test_phase_smoke.py:28
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: skills/validate-packages/scripts/validate_schema.py:13
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:26
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:27
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:28
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:29
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:30
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:31
- **Detail**: Module level import not at top of file

### [HIGH] E402: Module level import not at top of file

- **Source**: ruff
- **Category**: lint
- **Location**: tests/test_architecture/test_analysis.py:32
- **Detail**: Module level import not at top of file

## Medium Findings

| Source | Location | Title |
|--------|----------|-------|
| markers | skills/bug-scrub/tests/test_collect_markers.py:60 | FIXME: race condition\n") |
| markers | skills/bug-scrub/tests/test_collect_markers.py:69 | HACK: fragile workaround\n") |
| markers | skills/bug-scrub/tests/test_collect_markers.py:105 | FIXME: second item\n" |
| markers | skills/bug-scrub/tests/test_collect_markers.py:106 | HACK: third item\n" |
| markers | skills/bug-scrub/tests/test_collect_markers.py:135 | FIXME: in b\n") |
| markers | skills/bug-scrub/tests/test_collect_markers.py:292 | FIXME: no git here\n") |
| markers | skills/refresh-architecture/scripts/tests/test_enrich_with_treesitter.py:92 | FIXME: broken") |
| markers | skills/refresh-architecture/scripts/tests/test_comment_linker.py:39 | FIXME: broken", "language": "python", |
| ruff | openspec/changes/add-adaptive-model-router/contracts/generated/models.py:15 | F401: `typing.Any` imported but unused |
| ruff | scripts/ai_dora_snapshot.py:31 | F401: `collections.Counter` imported but unused |
| ruff | scripts/ai_dora_snapshot.py:36 | F401: `typing.Iterable` imported but unused |
| ruff | scripts/impl_review_driver.py:40 | F401: `consensus_synthesizer` imported but unused |
| ruff | skills/agent-metrics/tests/test_agent_metrics.py:12 | F401: `json` imported but unused |
| ruff | skills/agent-metrics/tests/test_agent_metrics.py:17 | F401: `pytest` imported but unused |
| ruff | skills/autopilot/scripts/complexity_gate.py:274 | F841: Local variable `packages` is assigned to but never used |
| ruff | skills/autopilot/tests/test_convergence_escalation.py:25 | F401: `pytest` imported but unused |
| ruff | skills/autopilot/tests/test_convergence_escalation.py:46 | F401: `convergence_loop.ConvergenceResult` imported but unused |
| ruff | skills/autopilot/tests/test_convergence_escalation.py:166 | F841: Local variable `finding` is assigned to but never used |
| ruff | skills/autopilot/tests/test_convergence_escalation.py:734 | F841: Local variable `finding` is assigned to but never used |
| ruff | skills/autopilot/tests/test_convergence_metrics.py:23 | F401: `unittest.mock.call` imported but unused |
| ruff | skills/autopilot/tests/test_convergence_metrics.py:25 | F401: `pytest` imported but unused |
| ruff | skills/autopilot/tests/test_convergence_metrics.py:43 | F401: `convergence_loop.ConvergenceResult` imported but unused |
| ruff | skills/bug-scrub/tests/test_aggregate.py:10 | F401: `aggregate._generate_recommendations` imported but unused |
| ruff | skills/bug-scrub/tests/test_collect_ci.py:17 | F401: `pytest` imported but unused |
| ruff | skills/bug-scrub/tests/test_collect_ci.py:28 | F401: `models.Finding` imported but unused |
| ruff | skills/bug-scrub/tests/test_collect_ci.py:28 | F401: `models.SourceResult` imported but unused |
| ruff | skills/bug-scrub/tests/test_collect_deferred.py:20 | F401: `pytest` imported but unused |
| ruff | skills/bug-scrub/tests/test_collect_deferred.py:29 | F401: `models.Finding` imported but unused |
| ruff | skills/bug-scrub/tests/test_collect_deferred.py:29 | F401: `models.FindingOrigin` imported but unused |
| ruff | skills/bug-scrub/tests/test_collect_reports.py:11 | F401: `pytest` imported but unused |
| ruff | skills/bug-scrub/tests/test_parallel_runner.py:10 | F401: `pytest` imported but unused |
| ruff | skills/changelog-version/scripts/changelog.py:20 | F401: `sys` imported but unused |
| ruff | skills/changelog-version/scripts/changelog.py:22 | F401: `datetime.datetime` imported but unused |
| ruff | skills/changelog-version/tests/test_changelog.py:5 | F401: `textwrap` imported but unused |
| ruff | skills/changelog-version/tests/test_changelog.py:7 | F401: `unittest.mock.patch` imported but unused |
| ruff | skills/changelog-version/tests/test_changelog.py:18 | F401: `changelog.ParsedCommit` imported but unused |
| ruff | skills/collect-transcripts/scripts/adapters/base.py:15 | F401: `typing.Iterator` imported but unused |
| ruff | skills/collect-transcripts/scripts/adapters/claude_code_web.py:23 | F401: `typing.Any` imported but unused |
| ruff | skills/collect-transcripts/scripts/adapters/codex_web.py:16 | F401: `os` imported but unused |
| ruff | skills/collect-transcripts/scripts/adapters/codex_web.py:21 | F401: `typing.Any` imported but unused |
| ruff | skills/collect-transcripts/scripts/adapters/gemini_cli.py:24 | F401: `os` imported but unused |
| ruff | skills/collect-transcripts/scripts/normalize.py:12 | F401: `datetime.datetime` imported but unused |
| ruff | skills/collect-transcripts/scripts/sanitize_events.py:15 | F401: `typing.Any` imported but unused |
| ruff | skills/collect-transcripts/scripts/triage.py:25 | F401: `dataclasses.field` imported but unused |
| ruff | skills/collect-transcripts/scripts/triage.py:287 | F541: f-string without any placeholders |
| ruff | skills/collect-transcripts/tests/test_adapter_base.py:31 | F401: `normalize.SessionSummary` imported but unused |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:13 | F401: `json` imported but unused |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:66 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:76 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:82 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:91 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:106 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:119 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:131 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:142 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:147 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:153 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:160 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_cli.py:173 | F821: Undefined name `ClaudeCodeCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_claude_code_web.py:18 | F401: `pytest` imported but unused |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:52 | F821: Undefined name `CodexCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:64 | F821: Undefined name `CodexCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:68 | F821: Undefined name `CodexCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:75 | F821: Undefined name `CodexCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:82 | F821: Undefined name `CodexCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:99 | F821: Undefined name `CodexCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:112 | F821: Undefined name `CodexCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:113 | F401: `normalize.EventRole` imported but unused |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:123 | F821: Undefined name `CodexCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_codex_cli.py:129 | F821: Undefined name `CodexCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_codex_web.py:15 | F401: `pytest` imported but unused |
| ruff | skills/collect-transcripts/tests/test_deep_analyze.py:18 | F401: `pytest` imported but unused |
| ruff | skills/collect-transcripts/tests/test_end_to_end.py:13 | F401: `pytest` imported but unused |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:54 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:66 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:70 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:77 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:84 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:96 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:107 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:112 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:122 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_gemini_cli.py:127 | F821: Undefined name `GeminiCLIAdapter` |
| ruff | skills/collect-transcripts/tests/test_normalize.py:13 | F401: `json` imported but unused |
| ruff | skills/collect-transcripts/tests/test_normalize.py:17 | F401: `pytest` imported but unused |
| ruff | skills/collect-transcripts/tests/test_sanitize_events.py:16 | F401: `pytest` imported but unused |
| ruff | skills/collect-transcripts/tests/test_triage.py:18 | F401: `pytest` imported but unused |
| ruff | skills/expedite/scripts/tests/test_expedite.py:6 | F401: `datetime.timedelta` imported but unused |
| ruff | skills/explore-feature/tests/test_archive_index.py:17 | F401: `json` imported but unused |
| ruff | skills/fix-scrub/scripts/classify.py:12 | F401: `fix_models.FixTier` imported but unused |
| ruff | skills/fix-scrub/scripts/fix_models.py:12 | F401: `dataclasses.asdict` imported but unused |
| ruff | skills/fix-scrub/scripts/main.py:110 | F541: f-string without any placeholders |
| ruff | skills/fix-scrub/scripts/render_fix_report.py:9 | F401: `typing.Any` imported but unused |
| ruff | skills/fix-scrub/scripts/track_completions.py:13 | F401: `fix_models.Finding` imported but unused |
| ruff | skills/fix-scrub/scripts/track_completions.py:51 | F541: f-string without any placeholders |
| ruff | skills/fix-scrub/tests/test_execute_auto.py:11 | F401: `pytest` imported but unused |
| ruff | skills/fix-scrub/tests/test_parallel_verify.py:13 | F401: `verify.VerificationResult` imported but unused |
| ruff | skills/fix-scrub/tests/test_plan_fixes.py:10 | F401: `pytest` imported but unused |
| ruff | skills/fix-scrub/tests/test_plan_fixes.py:12 | F401: `fix_models.FixGroup` imported but unused |
| ruff | skills/fix-scrub/tests/test_plan_fixes.py:12 | F401: `fix_models.FixPlan` imported but unused |
| ruff | skills/fix-scrub/tests/test_track_completions.py:10 | F401: `pytest` imported but unused |
| ruff | skills/improve-harness/scripts/analyze_failures.py:22 | F401: `datetime.datetime` imported but unused |
| ruff | skills/improve-harness/scripts/analyze_failures.py:22 | F401: `datetime.timedelta` imported but unused |
| ruff | skills/improve-harness/scripts/analyze_failures.py:22 | F401: `datetime.timezone` imported but unused |
| ruff | skills/improve-harness/scripts/analyze_failures.py:391 | F841: Local variable `all_findings` is assigned to but never used |
| ruff | skills/improve-harness/scripts/generate_report.py:14 | F401: `json` imported but unused |
| ruff | skills/improve-harness/scripts/generate_report.py:110 | F541: f-string without any placeholders |
| ruff | skills/improve-harness/scripts/generate_report.py:111 | F541: f-string without any placeholders |
| ruff | skills/improve-harness/scripts/generate_report.py:268 | F541: f-string without any placeholders |
| ruff | skills/improve-harness/scripts/generate_report.py:269 | F541: f-string without any placeholders |
| ruff | skills/improve-harness/tests/test_improve_harness.py:13 | F401: `json` imported but unused |
| ruff | skills/improve-harness/tests/test_improve_harness.py:15 | F401: `textwrap` imported but unused |
| ruff | skills/improve-harness/tests/test_improve_harness.py:16 | F401: `dataclasses.dataclass` imported but unused |
| ruff | skills/improve-harness/tests/test_improve_harness.py:19 | F401: `unittest.mock.AsyncMock` imported but unused |
| ruff | skills/improve-harness/tests/test_improve_harness.py:19 | F401: `unittest.mock.MagicMock` imported but unused |
| ruff | skills/improve-harness/tests/test_improve_harness.py:19 | F401: `unittest.mock.patch` imported but unused |
| ruff | skills/improve-harness/tests/test_improve_harness.py:21 | F401: `pytest` imported but unused |
| ruff | skills/improve-harness/tests/test_multi_source.py:13 | F401: `os` imported but unused |
| ruff | skills/improve-harness/tests/test_multi_source.py:15 | F401: `tempfile` imported but unused |
| ruff | skills/improve-harness/tests/test_multi_source.py:20 | F401: `pytest` imported but unused |
| ruff | skills/improve-harness/tests/test_transcript_source.py:10 | F401: `json` imported but unused |
| ruff | skills/improve-harness/tests/test_transcript_source.py:15 | F401: `pytest` imported but unused |
| ruff | skills/iterate-on-implementation/tests/test_rework_consumption.py:12 | F401: `json` imported but unused |
| ruff | skills/merge-pull-requests/scripts/auto_rollback.py:17 | F401: `_helpers.run_gh_unchecked` imported but unused |
| ruff | skills/merge-pull-requests/scripts/merge_backend.py:15 | F401: `time` imported but unused |
| ruff | skills/merge-pull-requests/scripts/merge_pr.py:40 | F401: `_helpers.safe_author` imported but unused |
| ruff | skills/merge-pull-requests/scripts/merge_pr.py:318 | F841: Local variable `raw` is assigned to but never used |
| ruff | skills/merge-pull-requests/scripts/post_merge_pipeline.py:13 | F401: `json` imported but unused |
| ruff | skills/merge-pull-requests/scripts/post_merge_pipeline.py:15 | F401: `time` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_auto_rebase.py:12 | F401: `json` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_auto_rebase.py:15 | F401: `unittest.mock.MagicMock` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_auto_rebase.py:17 | F401: `pytest` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_auto_rollback.py:16 | F401: `unittest.mock.MagicMock` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_auto_rollback.py:18 | F401: `pytest` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_auto_rollback.py:23 | F401: `auto_rollback.ROLLBACK_MONITOR_MINUTES` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_auto_rollback.py:189 | F841: Local variable `result` is assigned to but never used |
| ruff | skills/merge-pull-requests/scripts/tests/test_force_approval.py:14 | F401: `types` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_integration.py:8 | F401: `json` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_integration.py:11 | F401: `unittest.mock.MagicMock` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_integration.py:13 | F401: `pytest` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_merge_backend.py:16 | F401: `pytest` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_merge_events.py:12 | F401: `tempfile` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_merge_events.py:13 | F401: `datetime.timezone` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_merge_events.py:16 | F401: `pytest` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_merge_metrics.py:10 | F401: `json` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_merge_metrics.py:14 | F401: `pytest` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_merge_watcher.py:13 | F401: `unittest.mock.MagicMock` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_merge_watcher.py:15 | F401: `pytest` imported but unused |
| ruff | skills/merge-pull-requests/scripts/tests/test_merge_watcher.py:85 | F841: Local variable `result` is assigned to but never used |
| ruff | skills/merge-pull-requests/scripts/tests/test_post_merge_pipeline.py:10 | F401: `pytest` imported but unused |
| ruff | skills/parallel-infrastructure/scripts/circuit_breaker.py:30 | F401: `datetime.timedelta` imported but unused |
| ruff | skills/parallel-infrastructure/scripts/tests/test_api_key_resolver.py:8 | F401: `pytest` imported but unused |
| ruff | skills/parallel-infrastructure/scripts/tests/test_api_key_resolver.py:41 | F841: Local variable `resolver` is assigned to but never used |
| ruff | skills/parallel-infrastructure/scripts/tests/test_api_key_resolver.py:62 | F841: Local variable `resolver` is assigned to but never used |
| ruff | skills/parallel-infrastructure/scripts/tests/test_dag_scheduler.py:6 | F401: `textwrap` imported but unused |
| ruff | skills/parallel-infrastructure/scripts/tests/test_package_executor.py:9 | F401: `pytest` imported but unused |
| ruff | skills/parallel-infrastructure/scripts/tests/test_result_validator.py:9 | F401: `pytest` imported but unused |
| ruff | skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py:10 | F401: `pytest` imported but unused |
| ruff | skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py:17 | F401: `review_dispatcher.ReviewResult` imported but unused |
| ruff | skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py:352 | F811: Redefinition of unused `ReviewResult` from line 17: `ReviewResult` redefined here |
| ruff | skills/parallel-infrastructure/scripts/tests/test_scope_checker.py:8 | F401: `pytest` imported but unused |
| ruff | skills/parallel-infrastructure/scripts/variant_descriptor.py:25 | F401: `dataclasses.asdict` imported but unused |
| ruff | skills/parallel-infrastructure/tests/test_vendor_diversity.py:17 | F401: `stat` imported but unused |
| ruff | skills/plan-roadmap/scripts/renderer.py:18 | F401: `typing.Any` imported but unused |
| ruff | skills/plan-roadmap/scripts/renderer.py:26 | F401: `models.RoadmapItem` imported but unused |
| ruff | skills/playwright-validator/scripts/cli.py:45 | F401: `sys` imported but unused |
| ruff | skills/playwright-validator/scripts/findings.py:77 | F401: `typing.Mapping` imported but unused |
| ruff | skills/playwright-validator/scripts/generator.py:28 | F401: `parser.PlaywrightAction` imported but unused |
| ruff | skills/playwright-validator/scripts/generator.py:28 | F401: `parser.PlaywrightAssertion` imported but unused |
| ruff | skills/quick-task/tests/test_quick_task.py:7 | F401: `unittest.mock.MagicMock` imported but unused |
| ruff | skills/quick-task/tests/test_quick_task.py:7 | F401: `unittest.mock.patch` imported but unused |
| ruff | skills/refresh-architecture/scripts/analyze_postgres.py:368 | F841: Local variable `seg_upper` is assigned to but never used |
| ruff | skills/refresh-architecture/scripts/analyze_sql_treesitter.py:262 | F841: Local variable `skip_next` is assigned to but never used |
| ruff | skills/refresh-architecture/scripts/arch_utils/diagnostics.py:10 | F401: `sys` imported but unused |
| ruff | skills/refresh-architecture/scripts/arch_utils/graph_io.py:7 | F401: `sys` imported but unused |
| ruff | skills/refresh-architecture/scripts/diff_architecture.py:22 | F401: `json` imported but unused |
| ruff | skills/refresh-architecture/scripts/generate_views.py:121 | F841: Local variable `node_idx` is assigned to but never used |
| ruff | skills/refresh-architecture/scripts/generate_views.py:174 | F841: Local variable `node_idx` is assigned to but never used |
| ruff | skills/refresh-architecture/scripts/insights/graph_builder.py:19 | F401: `collections.defaultdict` imported but unused |
| ruff | skills/refresh-architecture/scripts/insights/graph_builder.py:25 | F401: `arch_utils.constants.DEPENDENCY_EDGE_TYPES` imported but unused |
| ruff | skills/refresh-architecture/scripts/parallel_zones.py:17 | F401: `collections.deque` imported but unused |
| ruff | skills/refresh-architecture/scripts/rpc_server.py:46 | F401: `dataclasses.field` imported but unused |
| ruff | skills/refresh-architecture/scripts/tests/test_affected_tests.py:32 | F401: `affected_tests.load_graph_with_mtime` imported but unused |
| ruff | skills/refresh-architecture/scripts/tests/test_analyze_sql_treesitter.py:8 | F401: `typing.Any` imported but unused |
| ruff | skills/refresh-architecture/scripts/tests/test_enrich_with_treesitter.py:8 | F401: `typing.Any` imported but unused |
| ruff | skills/refresh-architecture/scripts/tests/test_parallel_zones_packages.py:10 | F401: `pytest` imported but unused |
| ruff | skills/refresh-architecture/scripts/tests/test_pipeline_integration.py:352 | F821: Undefined name `pytest` |
| ruff | skills/session-bootstrap/scripts/calibrate_token_proxy.py:46 | F401: `json` imported but unused |
| ruff | skills/session-log/scripts/test_extract_session_log.py:5 | F401: `tempfile` imported but unused |
| ruff | skills/session-log/scripts/test_sanitize_session_log.py:5 | F401: `pytest` imported but unused |
| ruff | skills/session-log/tests/test_capability_gaps.py:15 | F401: `pytest` imported but unused |
| ruff | skills/session-log/tests/test_memory_tag_conventions.py:16 | F401: `re` imported but unused |
| ruff | skills/session-log/tests/test_sanitize_json_blob.py:13 | F401: `json` imported but unused |
| ruff | skills/session-log/tests/test_sanitize_json_blob.py:17 | F401: `pytest` imported but unused |
| ruff | skills/tech-debt-analysis/scripts/analyze_imports.py:18 | F401: `collections.deque` imported but unused |
| ruff | skills/tech-debt-analysis/tests/test_analyze_complexity.py:8 | F401: `pytest` imported but unused |
| ruff | skills/tech-debt-analysis/tests/test_analyze_complexity.py:14 | F401: `analyze_complexity._function_line_count` imported but unused |
| ruff | skills/tests/agent-coordinator/test_kanban_viz_endpoints.py:28 | F401: `unittest.mock.patch` imported but unused |
| ruff | skills/tests/agent-coordinator/test_kanban_viz_endpoints.py:178 | F841: Local variable `stale_entry` is assigned to but never used |
| ruff | skills/tests/agent-coordinator/test_kanban_viz_endpoints.py:1076 | F841: Local variable `lock_paths` is assigned to but never used |
| ruff | skills/tests/autopilot-roadmap/test_orchestrator.py:8 | F401: `pytest` imported but unused |
| ruff | skills/tests/autopilot-roadmap/test_orchestrator.py:11 | F401: `models.CheckpointPhase` imported but unused |
| ruff | skills/tests/autopilot-roadmap/test_orchestrator.py:141 | F841: Local variable `result` is assigned to but never used |
| ruff | skills/tests/autopilot-roadmap/test_policy.py:7 | F401: `pytest` imported but unused |
| ruff | skills/tests/autopilot-roadmap/test_policy.py:9 | F401: `policy.PolicyDecision` imported but unused |
| ruff | skills/tests/autopilot/test_dispatch_prohibitions.py:17 | F401: `typing.Any` imported but unused |
| ruff | skills/tests/autopilot/test_phase_transitions.py:21 | F401: `pytest` imported but unused |
| ruff | skills/tests/cleanup-feature/test_submodule_teardown.py:189 | F841: Local variable `wt` is assigned to but never used |
| ruff | skills/tests/cleanup-feature/test_sync_submodules.py:13 | F401: `unittest.mock.patch` imported but unused |
| ruff | skills/tests/cleanup-feature/test_sync_submodules.py:22 | F401: `sync_submodules.SyncResult` imported but unused |
| ruff | skills/tests/cleanup-feature/test_sync_submodules.py:106 | F541: f-string without any placeholders |
| ruff | skills/tests/install_sh/test_references_rsync.py:9 | F401: `os` imported but unused |
| ruff | skills/tests/integration/test_prototype_convergence.py:48 | F401: `variant_descriptor.VariantDescriptor` imported but unused |
| ruff | skills/tests/integration/test_prototype_convergence.py:49 | F401: `variant_descriptor.synthesize_variants` imported but unused |
| ruff | skills/tests/iterate-on-plan/test_prototype_context.py:13 | F401: `json` imported but unused |
| ruff | skills/tests/iterate-on-plan/test_prototype_recommended.py:16 | F401: `pytest` imported but unused |
| ruff | skills/tests/phase-record-compaction/test_phase_agent.py:20 | F401: `pytest` imported but unused |
| ruff | skills/tests/plan-roadmap/test_decomposer.py:9 | F401: `pytest` imported but unused |
| ruff | skills/tests/plan-roadmap/test_renderer.py:5 | F401: `pytest` imported but unused |
| ruff | skills/tests/plan-roadmap/test_renderer.py:14 | F401: `models.Scope` imported but unused |
| ruff | skills/tests/plan-roadmap/test_scaffolder.py:7 | F401: `pytest` imported but unused |
| ruff | skills/tests/playwright-validator/test_findings.py:10 | F401: `pytest` imported but unused |
| ruff | skills/tests/playwright-validator/test_generator.py:7 | F401: `pytest` imported but unused |
| ruff | skills/tests/playwright-validator/test_parser.py:7 | F401: `pytest` imported but unused |
| ruff | skills/tests/playwright-validator/test_runner.py:19 | F401: `runner.PlaywrightFailure` imported but unused |
| ruff | skills/tests/prototype-feature/test_dispatch_variants.py:37 | F401: `dispatch_variants.VariantPlan` imported but unused |
| ruff | skills/tests/prototype-feature/test_skill_invariants.py:21 | F401: `pytest` imported but unused |
| ruff | skills/tests/roadmap-runtime/test_checkpoint.py:5 | F401: `pathlib.Path` imported but unused |
| ruff | skills/tests/roadmap-runtime/test_checkpoint.py:10 | F401: `models.Checkpoint` imported but unused |
| ruff | skills/tests/roadmap-runtime/test_checkpoint.py:16 | F401: `models.RoadmapStatus` imported but unused |
| ruff | skills/tests/roadmap-runtime/test_context.py:9 | F401: `yaml` imported but unused |
| ruff | skills/tests/roadmap-runtime/test_learning.py:5 | F401: `pathlib.Path` imported but unused |
| ruff | skills/tests/roadmap-runtime/test_learning.py:7 | F401: `pytest` imported but unused |
| ruff | skills/tests/roadmap-runtime/test_models.py:6 | F401: `pathlib.Path` imported but unused |
| ruff | skills/tests/roadmap-runtime/test_models.py:24 | F401: `models.RoadmapStatus` imported but unused |
| ruff | skills/tests/roadmap-runtime/test_sanitizer.py:5 | F401: `pathlib.Path` imported but unused |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:282 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:291 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:296 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:301 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:313 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:318 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:330 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:349 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:370 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:394 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:405 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:419 | F821: Undefined name `Any` |
| ruff | skills/tests/session-bootstrap/test_check_compact.py:431 | F821: Undefined name `Any` |
| ruff | skills/tests/validate-feature/test_gen_eval_mode_selection.py:20 | F401: `pytest` imported but unused |
| ruff | skills/tests/worktree/test_setup_prototype.py:29 | F401: `worktree` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mongo.py:24 | F401: `os` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mongo.py:25 | F401: `subprocess` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mongo.py:27 | F401: `concurrent.futures.as_completed` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mongo.py:35 | F401: `dal.ProgressTimer` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mongo.py:37 | F401: `dal._analyze_window` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mongo.py:38 | F401: `dal._build_metrics_history` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mongo.py:46 | F401: `dal.run_railway_command` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mysql.py:24 | F401: `os` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mysql.py:25 | F401: `re` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mysql.py:26 | F401: `subprocess` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mysql.py:36 | F401: `dal.ProgressTimer` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mysql.py:38 | F401: `dal._analyze_window` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mysql.py:39 | F401: `dal._build_metrics_history` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mysql.py:50 | F401: `dal.run_railway_command` imported but unused |
| ruff | skills/use-railway/scripts/analyze-mysql.py:602 | F841: Local variable `created_disk` is assigned to but never used |
| ruff | skills/use-railway/scripts/analyze-mysql.py:603 | F841: Local variable `created_total` is assigned to but never used |
| ruff | skills/use-railway/scripts/analyze-postgres.py:28 | F401: `concurrent.futures.as_completed` imported but unused |
| ruff | skills/use-railway/scripts/analyze-postgres.py:36 | F401: `dal.ProgressTimer` imported but unused |
| ruff | skills/use-railway/scripts/analyze-postgres.py:38 | F401: `dal._analyze_window` imported but unused |
| ruff | skills/use-railway/scripts/analyze-postgres.py:39 | F401: `dal._build_metrics_history` imported but unused |
| ruff | skills/use-railway/scripts/analyze-postgres.py:47 | F401: `dal.run_psql_query` imported but unused |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2206 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2207 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2208 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2209 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2210 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2213 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2240 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2241 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2937 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-postgres.py:2939 | F541: f-string without any placeholders |
| ruff | skills/use-railway/scripts/analyze-redis.py:24 | F401: `os` imported but unused |
| ruff | skills/use-railway/scripts/analyze-redis.py:26 | F401: `subprocess` imported but unused |
| ruff | skills/use-railway/scripts/analyze-redis.py:28 | F401: `concurrent.futures.as_completed` imported but unused |
| ruff | skills/use-railway/scripts/analyze-redis.py:36 | F401: `dal.ProgressTimer` imported but unused |
| ruff | skills/use-railway/scripts/analyze-redis.py:38 | F401: `dal._analyze_window` imported but unused |
| ruff | skills/use-railway/scripts/analyze-redis.py:39 | F401: `dal._build_metrics_history` imported but unused |
| ruff | skills/use-railway/scripts/analyze-redis.py:49 | F401: `dal.run_railway_command` imported but unused |
| ruff | skills/use-railway/scripts/dal.py:465 | F401: `datetime.timedelta` imported but unused |
| ruff | skills/use-railway/scripts/enable-pg-stats.py:149 | F821: Undefined name `run_railway_command` |
| ruff | skills/use-railway/scripts/pg-extensions.py:26 | F401: `typing.Any` imported but unused |
| ruff | skills/use-railway/scripts/pg-extensions.py:26 | F401: `typing.Dict` imported but unused |
| ruff | skills/use-railway/scripts/pg-extensions.py:79 | F402: Import `info` from line 28 shadowed by loop variable |
| ruff | skills/use-railway/scripts/pg-extensions.py:334 | F841: Local variable `list_parser` is assigned to but never used |
| ruff | skills/validate-feature/scripts/tests/test_gate_logic.py:16 | F401: `pytest` imported but unused |
| ruff | skills/validate-feature/scripts/tests/test_holdout_gates.py:13 | F401: `json` imported but unused |
| ruff | skills/validate-feature/scripts/tests/test_holdout_gates.py:23 | F401: `rework_report.ACTION_NONE` imported but unused |
| ruff | skills/validate-feature/scripts/tests/test_neon_branch.py:20 | F401: `unittest.mock.call` imported but unused |
| ruff | skills/validate-feature/scripts/tests/test_neon_branch.py:35 | F401: `environments.protocol.TestEnvironment` imported but unused |
| ruff | skills/validate-feature/scripts/tests/test_pg_dump_seed.py:16 | F401: `unittest.mock.call` imported but unused |
| ruff | skills/validate-feature/scripts/tests/test_phase_smoke.py:16 | F401: `os` imported but unused |
| ruff | skills/validate-feature/scripts/tests/test_run_architecture_linters.py:18 | F401: `pytest` imported but unused |
| ruff | skills/worktree/scripts/tests/test_worktree.py:4 | F401: `json` imported but unused |
| ruff | tests/test_architecture/test_analysis.py:313 | F841: Local variable `functions_by_name` is assigned to but never used |
| ruff | tests/test_architecture/test_analysis.py:838 | F841: Local variable `report` is assigned to but never used |
| architecture | coordination_api.py:2372 | [reachability] Entrypoint 'gen_eval_list_scenarios' has no downstream dependencies |
| architecture | coordination_api.py:2695 | [reachability] Entrypoint 'get_sync_points_status' has no downstream dependencies |
| architecture | coordination_api.py:2708 | [reachability] Entrypoint 'get_active_worktrees' has no downstream dependencies |
| architecture | coordination_api.py:3086 | [reachability] Entrypoint 'live' has no downstream dependencies |
| architecture | coordination_mcp.py:2986 | [reachability] Entrypoint 'get_gen_eval_coverage' has no downstream dependencies |
| architecture | coordination_mcp.py:3018 | [reachability] Entrypoint 'get_gen_eval_report' has no downstream dependencies |
| architecture | coordination_mcp.py:3065 | [reachability] Entrypoint 'coordinate_file_edit' has no downstream dependencies |
| architecture | coordination_mcp.py:3087 | [reachability] Entrypoint 'start_work_session' has no downstream dependencies |
| architecture | coordination_api.py:2521 | [disconnected_flow] Backend route 'request_permission_endpoint' has no frontend callers |
| architecture | coordination_api.py:1363 | [disconnected_flow] Backend route 'check_policy' has no frontend callers |
| architecture | coordination_api.py:2560 | [disconnected_flow] Backend route 'request_approval_endpoint' has no frontend callers |
| architecture | coordination_mcp.py:3018 | [disconnected_flow] Backend route 'get_gen_eval_report' has no frontend callers |
| architecture | coordination_api.py:2479 | [disconnected_flow] Backend route 'search_issues' has no frontend callers |
| architecture | coordination_api.py:1816 | [disconnected_flow] Backend route 'remove_from_merge_queue_endpoint' has no frontend callers |
| architecture | coordination_mcp.py:2683 | [disconnected_flow] Backend route 'get_current_profile' has no frontend callers |
| architecture | coordination_api.py:2892 | [disconnected_flow] Backend route 'kick_agent' has no frontend callers |
| architecture | coordination_api.py:3091 | [disconnected_flow] Backend route 'ready' has no frontend callers |
| architecture | coordination_api.py:1492 | [disconnected_flow] Backend route 'list_pending_approvals' has no frontend callers |
| architecture | coordination_mcp.py:2624 | [disconnected_flow] Backend route 'get_recent_memories' has no frontend callers |
| architecture | coordination_api.py:1129 | [disconnected_flow] Backend route 'comment_issue' has no frontend callers |
| architecture | coordination_api.py:970 | [disconnected_flow] Backend route 'create_issue' has no frontend callers |
| architecture | coordination_api.py:1530 | [disconnected_flow] Backend route 'list_policy_versions_endpoint' has no frontend callers |
| architecture | coordination_api.py:1443 | [disconnected_flow] Backend route 'release_ports' has no frontend callers |
| architecture | coordination_api.py:1839 | [disconnected_flow] Backend route 'compose_train_endpoint' has no frontend callers |
| architecture | coordination_api.py:1197 | [disconnected_flow] Backend route 'get_my_profile' has no frontend callers |
| architecture | coordination_api.py:2753 | [disconnected_flow] Backend route 'stream_work_events' has no frontend callers |
| architecture | coordination_api.py:1452 | [disconnected_flow] Backend route 'port_status' has no frontend callers |
| architecture | coordination_api.py:1893 | [disconnected_flow] Backend route 'eject_from_train_endpoint' has no frontend callers |
| architecture | coordination_api.py:779 | [disconnected_flow] Backend route 'query_memories' has no frontend callers |
| architecture | coordination_mcp.py:3087 | [disconnected_flow] Backend route 'start_work_session' has no frontend callers |
| architecture | coordination_api.py:2658 | [disconnected_flow] Backend route 'help_overview' has no frontend callers |
| architecture | coordination_api.py:1751 | [disconnected_flow] Backend route 'get_next_merge_endpoint' has no frontend callers |
| architecture | coordination_api.py:2856 | [disconnected_flow] Backend route 'force_release_lock' has no frontend callers |
| architecture | coordination_api.py:1329 | [disconnected_flow] Backend route 'read_handoff' has no frontend callers |
| architecture | coordination_api.py:2034 | [disconnected_flow] Backend route 'resolve_archetype_for_phase_endpoint' has no frontend callers |
| architecture | coordination_api.py:2372 | [disconnected_flow] Backend route 'gen_eval_list_scenarios' has no frontend callers |
| architecture | coordination_mcp.py:2748 | [disconnected_flow] Backend route 'get_active_features_resource' has no frontend callers |
| architecture | coordination_api.py:3086 | [disconnected_flow] Backend route 'live' has no frontend callers |
| architecture | coordination_api.py:1972 | [disconnected_flow] Backend route 'report_spec_result_endpoint' has no frontend callers |
| architecture | coordination_api.py:656 | [disconnected_flow] Backend route 'acquire_lock' has no frontend callers |
| architecture | coordination_api.py:1695 | [disconnected_flow] Backend route 'enqueue_merge_endpoint' has no frontend callers |
| architecture | coordination_api.py:1942 | [disconnected_flow] Backend route 'get_train_status_endpoint' has no frontend callers |
| architecture | coordination_mcp.py:2525 | [disconnected_flow] Backend route 'get_current_locks' has no frontend callers |
| architecture | coordination_api.py:1301 | [disconnected_flow] Backend route 'write_handoff' has no frontend callers |
| architecture | coordination_api.py:1728 | [disconnected_flow] Backend route 'get_merge_queue_endpoint' has no frontend callers |
| architecture | coordination_api.py:2720 | [disconnected_flow] Backend route 'mint_events_token' has no frontend callers |
| architecture | coordination_api.py:2708 | [disconnected_flow] Backend route 'get_active_worktrees' has no frontend callers |
| architecture | coordination_api.py:1623 | [disconnected_flow] Backend route 'get_feature_endpoint' has no frontend callers |
| architecture | coordination_api.py:1031 | [disconnected_flow] Backend route 'blocked_issues_early' has no frontend callers |
| architecture | coordination_api.py:1048 | [disconnected_flow] Backend route 'show_issue' has no frontend callers |
| architecture | coordination_api.py:2011 | [disconnected_flow] Backend route 'affected_tests_endpoint' has no frontend callers |
| architecture | coordination_api.py:2107 | [disconnected_flow] Backend route 'report_status' has no frontend callers |
| architecture | coordination_api.py:722 | [disconnected_flow] Backend route 'check_lock_status' has no frontend callers |
| architecture | coordination_api.py:1772 | [disconnected_flow] Backend route 'run_pre_merge_checks_endpoint' has no frontend callers |
| architecture | coordination_api.py:3103 | [disconnected_flow] Backend route 'health' has no frontend callers |
| architecture | coordination_api.py:2308 | [disconnected_flow] Backend route 'discovery_heartbeat' has no frontend callers |
| architecture | coordination_api.py:1227 | [disconnected_flow] Backend route 'get_agent_dispatch_configs' has no frontend callers |
| architecture | coordination_api.py:3013 | [disconnected_flow] Backend route 'put_saved_view' has no frontend callers |
| architecture | coordination_api.py:1562 | [disconnected_flow] Backend route 'register_feature_endpoint' has no frontend callers |
| architecture | coordination_api.py:1671 | [disconnected_flow] Backend route 'analyze_feature_conflicts_endpoint' has no frontend callers |
| architecture | coordination_api.py:693 | [disconnected_flow] Backend route 'release_lock' has no frontend callers |
| architecture | coordination_api.py:2243 | [disconnected_flow] Backend route 'discovery_register' has no frontend callers |
| architecture | coordination_api.py:2695 | [disconnected_flow] Backend route 'get_sync_points_status' has no frontend callers |
| architecture | coordination_api.py:747 | [disconnected_flow] Backend route 'store_memory' has no frontend callers |
| architecture | coordination_api.py:1065 | [disconnected_flow] Backend route 'update_issue' has no frontend callers |
| architecture | coordination_api.py:2400 | [disconnected_flow] Backend route 'gen_eval_validate' has no frontend callers |
| architecture | coordination_api.py:1421 | [disconnected_flow] Backend route 'allocate_ports' has no frontend callers |
| architecture | coordination_mcp.py:2592 | [disconnected_flow] Backend route 'get_pending_work' has no frontend callers |
| architecture | coordination_api.py:1390 | [disconnected_flow] Backend route 'validate_cedar_policy' has no frontend callers |
| architecture | coordination_api.py:1596 | [disconnected_flow] Backend route 'deregister_feature_endpoint' has no frontend callers |
| architecture | coordination_api.py:2189 | [disconnected_flow] Backend route 'test_notification' has no frontend callers |
| architecture | coordination_api.py:1647 | [disconnected_flow] Backend route 'list_active_features_endpoint' has no frontend callers |
| architecture | coordination_mcp.py:2780 | [disconnected_flow] Backend route 'get_merge_queue_resource' has no frontend callers |
| architecture | coordination_api.py:923 | [disconnected_flow] Backend route 'get_task_endpoint' has no frontend callers |
| architecture | coordination_api.py:2804 | [disconnected_flow] Backend route 'patch_issue_labels' has no frontend callers |
| architecture | coordination_api.py:888 | [disconnected_flow] Backend route 'submit_work' has no frontend callers |
| architecture | coordination_api.py:1097 | [disconnected_flow] Backend route 'close_issue' has no frontend callers |
| architecture | coordination_api.py:2335 | [disconnected_flow] Backend route 'discovery_cleanup' has no frontend callers |
| architecture | coordination_mcp.py:2551 | [disconnected_flow] Backend route 'get_recent_handoffs' has no frontend callers |
| architecture | coordination_api.py:2449 | [disconnected_flow] Backend route 'gen_eval_run' has no frontend callers |
| architecture | coordination_api.py:822 | [disconnected_flow] Backend route 'claim_work' has no frontend callers |
| architecture | coordination_api.py:1004 | [disconnected_flow] Backend route 'list_issues' has no frontend callers |
| architecture | coordination_api.py:2226 | [disconnected_flow] Backend route 'notifications_status' has no frontend callers |
| architecture | coordination_api.py:2274 | [disconnected_flow] Backend route 'discovery_agents' has no frontend callers |
| architecture | coordination_mcp.py:3065 | [disconnected_flow] Backend route 'coordinate_file_edit' has no frontend callers |
| architecture | coordination_api.py:1151 | [disconnected_flow] Backend route 'check_guardrails' has no frontend callers |
| architecture | coordination_api.py:2495 | [disconnected_flow] Backend route 'ready_issues' has no frontend callers |
| architecture | coordination_mcp.py:2653 | [disconnected_flow] Backend route 'get_guardrail_patterns' has no frontend callers |
| architecture | coordination_api.py:1543 | [disconnected_flow] Backend route 'rollback_policy_endpoint' has no frontend callers |
| architecture | coordination_api.py:3050 | [disconnected_flow] Backend route 'post_kanban_audit' has no frontend callers |
| architecture | coordination_api.py:2668 | [disconnected_flow] Backend route 'help_topic' has no frontend callers |
| architecture | coordination_api.py:2599 | [disconnected_flow] Backend route 'check_approval_endpoint' has no frontend callers |
| architecture | coordination_mcp.py:2719 | [disconnected_flow] Backend route 'get_recent_audit' has no frontend callers |
| architecture | coordination_api.py:1241 | [disconnected_flow] Backend route 'query_audit' has no frontend callers |
| architecture | coordination_mcp.py:2986 | [disconnected_flow] Backend route 'get_gen_eval_coverage' has no frontend callers |
| architecture | coordination_api.py:856 | [disconnected_flow] Backend route 'complete_work' has no frontend callers |
| architecture | coordination_api.py:1503 | [disconnected_flow] Backend route 'decide_approval' has no frontend callers |
| architecture | coordination_api.py:2424 | [disconnected_flow] Backend route 'gen_eval_create' has no frontend callers |
| architecture | coordination_api.py:1797 | [disconnected_flow] Backend route 'mark_merged_endpoint' has no frontend callers |
| architecture | agents_config.py:322 | [test_coverage] Function 'PollConfig' has no corresponding test references |
| architecture | agents_config.py:340 | [test_coverage] Function 'ModeConfig' has no corresponding test references |
| architecture | agents_config.py:349 | [test_coverage] Function 'CliConfig' has no corresponding test references |
| architecture | agents_config.py:364 | [test_coverage] Function 'SdkConfig' has no corresponding test references |
| architecture | agents_config.py:381 | [test_coverage] Function 'AgentEntry' has no corresponding test references |
| architecture | agents_config.py:404 | [test_coverage] Function 'EscalationConfig' has no corresponding test references |
| architecture | agents_config.py:418 | [test_coverage] Function 'ArchetypeConfig' has no corresponding test references |
| architecture | agents_config.py:432 | [test_coverage] Function 'PhaseMappingEntry' has no corresponding test references |
| architecture | agents_config.py:446 | [test_coverage] Function 'ResolvedArchetype' has no corresponding test references |
| architecture | agents_config.py:460 | [test_coverage] Function 'ProviderModelMappingError' has no corresponding test references |
| architecture | approval.py:15 | [test_coverage] Function 'ApprovalRequest' has no corresponding test references |
| architecture | approval.py:32 | [test_coverage] Function 'ApprovalService' has no corresponding test references |
| architecture | audit.py:18 | [test_coverage] Function 'AuditEntry' has no corresponding test references |
| architecture | audit.py:56 | [test_coverage] Function 'AuditResult' has no corresponding test references |
| architecture | audit.py:72 | [test_coverage] Function 'AuditService' has no corresponding test references |
| architecture | audit.py:179 | [test_coverage] Function 'AuditTimer' has no corresponding test references |
| architecture | config.py:50 | [test_coverage] Function 'SupabaseConfig' has no corresponding test references |
| architecture | config.py:75 | [test_coverage] Function 'AgentConfig' has no corresponding test references |
| architecture | config.py:99 | [test_coverage] Function 'LockConfig' has no corresponding test references |
| architecture | config.py:113 | [test_coverage] Function 'PostgresConfig' has no corresponding test references |
| architecture | config.py:130 | [test_coverage] Function 'DatabaseConfig' has no corresponding test references |
| architecture | config.py:145 | [test_coverage] Function 'GuardrailsConfig' has no corresponding test references |
| architecture | config.py:165 | [test_coverage] Function 'ProfilesConfig' has no corresponding test references |
| architecture | config.py:189 | [test_coverage] Function 'AuditConfig' has no corresponding test references |
| architecture | config.py:204 | [test_coverage] Function 'NetworkPolicyConfig' has no corresponding test references |
| architecture | config.py:217 | [test_coverage] Function 'PolicyEngineConfig' has no corresponding test references |
| architecture | config.py:241 | [test_coverage] Function 'OpenBaoConfig' has no corresponding test references |
| architecture | config.py:323 | [test_coverage] Function 'ObservabilityConfig' has no corresponding test references |
| architecture | config.py:340 | [test_coverage] Function 'LangfuseConfig' has no corresponding test references |
| architecture | config.py:374 | [test_coverage] Function 'PortAllocatorConfig' has no corresponding test references |
| architecture | config.py:393 | [test_coverage] Function 'ApiConfig' has no corresponding test references |
| architecture | config.py:448 | [test_coverage] Function 'ApprovalConfig' has no corresponding test references |
| architecture | config.py:471 | [test_coverage] Function 'PolicySyncConfig' has no corresponding test references |
| architecture | config.py:493 | [test_coverage] Function 'RiskScoringConfig' has no corresponding test references |
| architecture | config.py:520 | [test_coverage] Function 'SessionGrantsConfig' has no corresponding test references |
| architecture | config.py:574 | [test_coverage] Function 'Config' has no corresponding test references |
| architecture | coordination_api.py:31 | [test_coverage] Function 'LockAcquireRequest' has no corresponding test references |
| architecture | coordination_api.py:40 | [test_coverage] Function 'LockReleaseRequest' has no corresponding test references |
| architecture | coordination_api.py:45 | [test_coverage] Function 'MemoryStoreRequest' has no corresponding test references |
| architecture | coordination_api.py:56 | [test_coverage] Function 'MemoryQueryRequest' has no corresponding test references |
| architecture | coordination_api.py:63 | [test_coverage] Function 'WorkClaimRequest' has no corresponding test references |
| architecture | coordination_api.py:69 | [test_coverage] Function 'WorkCompleteRequest' has no corresponding test references |
| architecture | coordination_api.py:77 | [test_coverage] Function 'WorkSubmitRequest' has no corresponding test references |
| architecture | coordination_api.py:86 | [test_coverage] Function 'WorkGetTaskRequest' has no corresponding test references |
| architecture | coordination_api.py:90 | [test_coverage] Function 'IssueCreateRequest' has no corresponding test references |
| architecture | coordination_api.py:101 | [test_coverage] Function 'IssueListRequest' has no corresponding test references |
| architecture | coordination_api.py:110 | [test_coverage] Function 'IssueUpdateRequest' has no corresponding test references |
| architecture | coordination_api.py:121 | [test_coverage] Function 'IssueCloseRequest' has no corresponding test references |
| architecture | coordination_api.py:127 | [test_coverage] Function 'IssueCommentRequest' has no corresponding test references |
| architecture | coordination_api.py:132 | [test_coverage] Function 'GuardrailsCheckRequest' has no corresponding test references |
| architecture | coordination_api.py:137 | [test_coverage] Function 'AuditQueryParams' has no corresponding test references |
| architecture | coordination_api.py:143 | [test_coverage] Function 'HandoffWriteRequest' has no corresponding test references |
| architecture | coordination_api.py:155 | [test_coverage] Function 'HandoffReadRequest' has no corresponding test references |
| architecture | coordination_api.py:160 | [test_coverage] Function 'PolicyCheckRequest' has no corresponding test references |
| architecture | coordination_api.py:168 | [test_coverage] Function 'PolicyValidateRequest' has no corresponding test references |
| architecture | coordination_api.py:172 | [test_coverage] Function 'PortAllocateRequest' has no corresponding test references |
| architecture | coordination_api.py:176 | [test_coverage] Function 'PortReleaseRequest' has no corresponding test references |
| architecture | coordination_api.py:180 | [test_coverage] Function 'ApprovalDecisionRequest' has no corresponding test references |
| architecture | coordination_api.py:186 | [test_coverage] Function 'PolicyRollbackRequest' has no corresponding test references |
| architecture | coordination_api.py:190 | [test_coverage] Function 'FeatureRegisterRequest' has no corresponding test references |
| architecture | coordination_api.py:200 | [test_coverage] Function 'FeatureDeregisterRequest' has no corresponding test references |
| architecture | coordination_api.py:205 | [test_coverage] Function 'FeatureConflictsRequest' has no corresponding test references |
| architecture | coordination_api.py:210 | [test_coverage] Function 'StatusReportRequest' has no corresponding test references |
| architecture | coordination_api.py:233 | [test_coverage] Function 'ResolveForPhaseRequest' has no corresponding test references |
| architecture | coordination_api.py:255 | [test_coverage] Function 'MergeQueueEnqueueRequest' has no corresponding test references |
| architecture | coordination_api.py:260 | [test_coverage] Function 'DiscoveryRegisterRequest' has no corresponding test references |
| architecture | coordination_api.py:270 | [test_coverage] Function 'DiscoveryHeartbeatRequest' has no corresponding test references |
| architecture | coordination_api.py:276 | [test_coverage] Function 'DiscoveryCleanupRequest' has no corresponding test references |
| architecture | coordination_api.py:282 | [test_coverage] Function 'GenEvalValidateRequest' has no corresponding test references |
| architecture | coordination_api.py:286 | [test_coverage] Function 'GenEvalCreateRequest' has no corresponding test references |
| architecture | coordination_api.py:294 | [test_coverage] Function 'GenEvalRunRequest' has no corresponding test references |
| architecture | coordination_api.py:300 | [test_coverage] Function 'IssueSearchRequest' has no corresponding test references |
| architecture | coordination_api.py:307 | [test_coverage] Function 'IssueReadyRequest' has no corresponding test references |
| architecture | coordination_api.py:314 | [test_coverage] Function 'PermissionRequestRequest' has no corresponding test references |
| architecture | coordination_api.py:321 | [test_coverage] Function 'ApprovalSubmitRequest' has no corresponding test references |
| architecture | coordination_api.py:330 | [test_coverage] Function 'MergeTrainEjectRequest' has no corresponding test references |
| architecture | coordination_api.py:335 | [test_coverage] Function 'MergeTrainReportResultRequest' has no corresponding test references |
| architecture | coordination_api.py:341 | [test_coverage] Function 'AffectedTestsRequest' has no corresponding test references |
| architecture | coordination_api.py:347 | [test_coverage] Function 'EventsAuthRequest' has no corresponding test references |
| architecture | coordination_api.py:352 | [test_coverage] Function 'PatchLabelsRequest' has no corresponding test references |
| architecture | coordination_api.py:357 | [test_coverage] Function 'KickAgentRequest' has no corresponding test references |
| architecture | coordination_api.py:371 | [test_coverage] Function 'SavedViewRequest' has no corresponding test references |
| architecture | coordination_api.py:375 | [test_coverage] Function 'KanbanAuditRequest' has no corresponding test references |
| architecture | db.py:25 | [test_coverage] Function 'DatabaseClient' has no corresponding test references |
| architecture | db.py:73 | [test_coverage] Function 'SupabaseClient' has no corresponding test references |
| architecture | db_postgres.py:78 | [test_coverage] Function 'DirectPostgresClient' has no corresponding test references |
| architecture | discovery.py:20 | [test_coverage] Function 'AgentInfo' has no corresponding test references |
| architecture | discovery.py:61 | [test_coverage] Function 'RegisterResult' has no corresponding test references |
| architecture | discovery.py:76 | [test_coverage] Function 'DiscoverResult' has no corresponding test references |
| architecture | discovery.py:88 | [test_coverage] Function 'HeartbeatResult' has no corresponding test references |
| architecture | discovery.py:105 | [test_coverage] Function 'CleanupResult' has no corresponding test references |
| architecture | discovery.py:121 | [test_coverage] Function 'DiscoveryService' has no corresponding test references |
| architecture | event_bus.py:37 | [test_coverage] Function 'CoordinatorEvent' has no corresponding test references |
| architecture | event_bus.py:110 | [test_coverage] Function 'EventBusService' has no corresponding test references |
| architecture | feature_flags.py:61 | [test_coverage] Function 'FlagsConfigError' has no corresponding test references |
| architecture | feature_flags.py:69 | [test_coverage] Function 'InvalidFlagNameError' has no corresponding test references |
| architecture | feature_flags.py:79 | [test_coverage] Function 'Flag' has no corresponding test references |
| architecture | feature_flags.py:153 | [test_coverage] Function 'FeatureFlagService' has no corresponding test references |
| architecture | feature_registry.py:26 | [test_coverage] Function 'Feasibility' has no corresponding test references |
| architecture | feature_registry.py:35 | [test_coverage] Function 'Feature' has no corresponding test references |
| architecture | feature_registry.py:75 | [test_coverage] Function 'RegisterResult' has no corresponding test references |
| architecture | feature_registry.py:94 | [test_coverage] Function 'DeregisterResult' has no corresponding test references |
| architecture | feature_registry.py:113 | [test_coverage] Function 'ConflictReport' has no corresponding test references |
| architecture | feature_registry.py:124 | [test_coverage] Function 'FeatureRegistryService' has no corresponding test references |
| architecture | git_adapter.py:51 | [test_coverage] Function 'InvalidRefNameError' has no corresponding test references |
| architecture | git_adapter.py:55 | [test_coverage] Function 'GitVersionError' has no corresponding test references |
| architecture | git_adapter.py:65 | [test_coverage] Function 'MergeTreeResult' has no corresponding test references |
| architecture | git_adapter.py:79 | [test_coverage] Function 'FastForwardResult' has no corresponding test references |
| architecture | git_adapter.py:88 | [test_coverage] Function 'ChangedFiles' has no corresponding test references |
| architecture | git_adapter.py:102 | [test_coverage] Function 'GitAdapter' has no corresponding test references |
| architecture | git_adapter.py:176 | [test_coverage] Function 'SubprocessGitAdapter' has no corresponding test references |
| architecture | github_coordination.py:30 | [test_coverage] Function 'BranchInfo' has no corresponding test references |
| architecture | github_coordination.py:61 | [test_coverage] Function 'LabelLock' has no corresponding test references |
| architecture | github_coordination.py:69 | [test_coverage] Function 'WebhookSyncResult' has no corresponding test references |
| architecture | github_coordination.py:89 | [test_coverage] Function 'GitHubCoordinationService' has no corresponding test references |
| architecture | guardrails.py:140 | [test_coverage] Function 'GuardrailPattern' has no corresponding test references |
| architecture | guardrails.py:161 | [test_coverage] Function 'GuardrailViolation' has no corresponding test references |
| architecture | guardrails.py:184 | [test_coverage] Function 'GuardrailResult' has no corresponding test references |
| architecture | guardrails.py:203 | [test_coverage] Function 'GuardrailsService' has no corresponding test references |
| architecture | handoffs.py:22 | [test_coverage] Function 'HandoffDocument' has no corresponding test references |
| architecture | handoffs.py:59 | [test_coverage] Function 'WriteHandoffResult' has no corresponding test references |
| architecture | handoffs.py:80 | [test_coverage] Function 'ReadHandoffResult' has no corresponding test references |
| architecture | handoffs.py:93 | [test_coverage] Function 'HandoffService' has no corresponding test references |
| architecture | help_service.py:20 | [test_coverage] Function 'HelpTopic' has no corresponding test references |
| architecture | http_proxy.py:92 | [test_coverage] Function 'HttpProxyConfig' has no corresponding test references |
| architecture | issue_service.py:47 | [test_coverage] Function 'Issue' has no corresponding test references |
| architecture | issue_service.py:154 | [test_coverage] Function 'Comment' has no corresponding test references |
| architecture | issue_service.py:186 | [test_coverage] Function 'IssueService' has no corresponding test references |
| architecture | kanban_viz_files.py:107 | [test_coverage] Function 'SchemaValidationError' has no corresponding test references |
| architecture | langfuse_middleware.py:29 | [test_coverage] Function 'LangfuseTracingMiddleware' has no corresponding test references |
| architecture | locks.py:89 | [test_coverage] Function 'Lock' has no corresponding test references |
| architecture | locks.py:119 | [test_coverage] Function 'LockResult' has no corresponding test references |
| architecture | locks.py:149 | [test_coverage] Function 'LockService' has no corresponding test references |
| architecture | memory.py:20 | [test_coverage] Function 'EpisodicMemory' has no corresponding test references |
| architecture | memory.py:56 | [test_coverage] Function 'MemoryResult' has no corresponding test references |
| architecture | memory.py:75 | [test_coverage] Function 'RecallResult' has no corresponding test references |
| architecture | memory.py:89 | [test_coverage] Function 'MemoryService' has no corresponding test references |
| architecture | merge_queue.py:37 | [test_coverage] Function 'MergeStatus' has no corresponding test references |
| architecture | merge_queue.py:49 | [test_coverage] Function 'PreMergeCheckResult' has no corresponding test references |
| architecture | merge_queue.py:60 | [test_coverage] Function 'MergeQueueEntry' has no corresponding test references |
| architecture | merge_queue.py:88 | [test_coverage] Function 'MergeQueueService' has no corresponding test references |
| architecture | merge_train.py:69 | [test_coverage] Function 'TrainAuthorizationError' has no corresponding test references |
| architecture | merge_train.py:77 | [test_coverage] Function 'TrainDeadlockError' has no corresponding test references |
| architecture | merge_train.py:92 | [test_coverage] Function 'PartitionResult' has no corresponding test references |
| architecture | merge_train.py:622 | [test_coverage] Function 'EjectResult' has no corresponding test references |
| architecture | merge_train.py:851 | [test_coverage] Function '_MergeNode' has no corresponding test references |
| architecture | merge_train.py:868 | [test_coverage] Function 'WaveMergeResult' has no corresponding test references |
| architecture | merge_train.py:1121 | [test_coverage] Function 'CrashRecoveryResult' has no corresponding test references |
| architecture | merge_train_service.py:115 | [test_coverage] Function 'MergeTrainService' has no corresponding test references |
| architecture | merge_train_service.py:419 | [test_coverage] Function 'MergeTrainSweeper' has no corresponding test references |
| architecture | merge_train_types.py:58 | [test_coverage] Function 'MergeTrainStatus' has no corresponding test references |
| architecture | merge_train_types.py:98 | [test_coverage] Function 'TrainEntry' has no corresponding test references |
| architecture | merge_train_types.py:151 | [test_coverage] Function 'TrainPartition' has no corresponding test references |
| architecture | merge_train_types.py:169 | [test_coverage] Function 'CrossPartitionEntry' has no corresponding test references |
| architecture | merge_train_types.py:183 | [test_coverage] Function 'TrainComposition' has no corresponding test references |
| architecture | network_policies.py:15 | [test_coverage] Function 'AccessDecision' has no corresponding test references |
| architecture | network_policies.py:33 | [test_coverage] Function 'NetworkPolicyService' has no corresponding test references |
| architecture | notifications/base.py:11 | [test_coverage] Function 'NotificationChannel' has no corresponding test references |
| architecture | notifications/base.py:29 | [test_coverage] Function 'GmailChannelFake' has no corresponding test references |
| architecture | notifications/gmail.py:46 | [test_coverage] Function 'GmailChannel' has no corresponding test references |
| architecture | notifications/notifier.py:30 | [test_coverage] Function 'NotifierService' has no corresponding test references |
| architecture | notifications/telegram.py:20 | [test_coverage] Function 'TelegramChannel' has no corresponding test references |
| architecture | notifications/webhook.py:18 | [test_coverage] Function 'WebhookChannel' has no corresponding test references |
| architecture | policy_engine.py:83 | [test_coverage] Function 'PolicyDecision' has no corresponding test references |
| architecture | policy_engine.py:101 | [test_coverage] Function 'ValidationResult' has no corresponding test references |
| architecture | policy_engine.py:108 | [test_coverage] Function 'NativePolicyEngine' has no corresponding test references |
| architecture | policy_engine.py:454 | [test_coverage] Function 'CedarPolicyEngine' has no corresponding test references |
| architecture | policy_sync.py:17 | [test_coverage] Function 'PolicySyncService' has no corresponding test references |
| architecture | policy_sync.py:37 | [test_coverage] Function 'PgListenNotifyPolicySyncService' has no corresponding test references |
| architecture | port_allocator.py:24 | [test_coverage] Function 'PortAllocation' has no corresponding test references |
| architecture | port_allocator.py:52 | [test_coverage] Function 'PortAllocatorService' has no corresponding test references |
| architecture | profiles.py:20 | [test_coverage] Function 'AgentProfile' has no corresponding test references |
| architecture | profiles.py:53 | [test_coverage] Function 'ProfileResult' has no corresponding test references |
| architecture | profiles.py:77 | [test_coverage] Function 'OperationCheck' has no corresponding test references |
| architecture | profiles.py:91 | [test_coverage] Function 'ProfilesService' has no corresponding test references |
| architecture | refresh_rpc_client.py:59 | [test_coverage] Function 'RefreshClientUnavailable' has no corresponding test references |
| architecture | refresh_rpc_client.py:78 | [test_coverage] Function '_Runner' has no corresponding test references |
| architecture | refresh_rpc_client.py:124 | [test_coverage] Function 'RefreshRpcClient' has no corresponding test references |
| architecture | risk_scorer.py:33 | [test_coverage] Function 'RiskScore' has no corresponding test references |
| architecture | risk_scorer.py:41 | [test_coverage] Function 'RiskScorer' has no corresponding test references |
| architecture | session_grants.py:14 | [test_coverage] Function 'PermissionGrant' has no corresponding test references |
| architecture | session_grants.py:27 | [test_coverage] Function 'SessionGrantService' has no corresponding test references |
| architecture | sse_log_redaction.py:31 | [test_coverage] Function '_TokenRedactionFilter' has no corresponding test references |
| architecture | teams.py:48 | [test_coverage] Function 'AgentDefinition' has no corresponding test references |
| architecture | teams.py:58 | [test_coverage] Function 'TeamsConfig' has no corresponding test references |
| architecture | telemetry.py:210 | [test_coverage] Function '_NoOpSpan' has no corresponding test references |
| architecture | watchdog.py:31 | [test_coverage] Function 'WatchdogService' has no corresponding test references |
| architecture | work_queue.py:68 | [test_coverage] Function 'Task' has no corresponding test references |
| architecture | work_queue.py:120 | [test_coverage] Function 'ClaimResult' has no corresponding test references |
| architecture | work_queue.py:157 | [test_coverage] Function 'CompleteResult' has no corresponding test references |
| architecture | work_queue.py:180 | [test_coverage] Function 'SubmitResult' has no corresponding test references |
| architecture | work_queue.py:198 | [test_coverage] Function 'WorkQueueService' has no corresponding test references |
| architecture | agents_config.py:463 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | agents_config.py:484 | [test_coverage] Function '_default_agents_path' has no corresponding test references |
| architecture | agents_config.py:488 | [test_coverage] Function '_default_secrets_path' has no corresponding test references |
| architecture | agents_config.py:492 | [test_coverage] Function 'load_agents_config' has no corresponding test references |
| architecture | agents_config.py:545 | [test_coverage] Function '_parse_mode' has no corresponding test references |
| architecture | agents_config.py:618 | [test_coverage] Function '_resolve_api_key_from_openbao' has no corresponding test references |
| architecture | agents_config.py:669 | [test_coverage] Function 'get_api_key_identities' has no corresponding test references |
| architecture | agents_config.py:726 | [test_coverage] Function 'get_mcp_env' has no corresponding test references |
| architecture | agents_config.py:764 | [test_coverage] Function 'get_agents_config' has no corresponding test references |
| architecture | agents_config.py:780 | [test_coverage] Function 'get_agent_config' has no corresponding test references |
| architecture | agents_config.py:788 | [test_coverage] Function 'reset_agents_config' has no corresponding test references |
| architecture | agents_config.py:798 | [test_coverage] Function 'get_dispatch_configs' has no corresponding test references |
| architecture | agents_config.py:864 | [test_coverage] Function 'get_agent_isolation' has no corresponding test references |
| architecture | agents_config.py:880 | [test_coverage] Function '_default_archetypes_path' has no corresponding test references |
| architecture | agents_config.py:884 | [test_coverage] Function 'load_archetypes_config' has no corresponding test references |
| architecture | agents_config.py:967 | [test_coverage] Function 'get_archetype' has no corresponding test references |
| architecture | agents_config.py:981 | [test_coverage] Function 'get_phase_mapping' has no corresponding test references |
| architecture | agents_config.py:993 | [test_coverage] Function 'reset_archetypes_config' has no corresponding test references |
| architecture | agents_config.py:1001 | [test_coverage] Function '_normalize_provider_model_map' has no corresponding test references |
| architecture | agents_config.py:1028 | [test_coverage] Function 'get_provider_model_map' has no corresponding test references |
| architecture | agents_config.py:1035 | [test_coverage] Function 'resolve_provider_model' has no corresponding test references |
| architecture | agents_config.py:1079 | [test_coverage] Function 'compose_prompt' has no corresponding test references |
| architecture | agents_config.py:1095 | [test_coverage] Function '_unique_dir_prefixes' has no corresponding test references |
| architecture | agents_config.py:1114 | [test_coverage] Function 'resolve_model' has no corresponding test references |
| architecture | agents_config.py:1143 | [test_coverage] Function '_finalize' has no corresponding test references |
| architecture | agents_config.py:1196 | [test_coverage] Function 'resolve_archetype_for_phase' has no corresponding test references |
| architecture | approval.py:35 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | approval.py:39 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | approval.py:44 | [test_coverage] Function 'submit_request' has no corresponding test references |
| architecture | approval.py:89 | [test_coverage] Function 'check_request' has no corresponding test references |
| architecture | approval.py:99 | [test_coverage] Function 'decide_request' has no corresponding test references |
| architecture | approval.py:137 | [test_coverage] Function 'expire_stale_requests' has no corresponding test references |
| architecture | approval.py:154 | [test_coverage] Function 'list_pending' has no corresponding test references |
| architecture | approval.py:166 | [test_coverage] Function '_row_to_request' has no corresponding test references |
| architecture | approval.py:186 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | approval.py:199 | [test_coverage] Function 'get_approval_service' has no corresponding test references |
| architecture | approval.py:207 | [test_coverage] Function 'reset_approval_service' has no corresponding test references |
| architecture | audit.py:34 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | audit.py:64 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | audit.py:75 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | audit.py:79 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | audit.py:84 | [test_coverage] Function 'log_operation' has no corresponding test references |
| architecture | audit.py:124 | [test_coverage] Function '_insert_audit_entry' has no corresponding test references |
| architecture | audit.py:132 | [test_coverage] Function 'query' has no corresponding test references |
| architecture | audit.py:174 | [test_coverage] Function 'timed' has no corresponding test references |
| architecture | audit.py:182 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | audit.py:187 | [test_coverage] Function '__aenter__' has no corresponding test references |
| architecture | audit.py:191 | [test_coverage] Function '__aexit__' has no corresponding test references |
| architecture | audit.py:210 | [test_coverage] Function 'get_audit_service' has no corresponding test references |
| architecture | config.py:58 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:83 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:106 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:121 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:137 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:152 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:173 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:196 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:210 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:226 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:263 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:274 | [test_coverage] Function 'is_enabled' has no corresponding test references |
| architecture | config.py:278 | [test_coverage] Function 'create_client' has no corresponding test references |
| architecture | config.py:331 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:360 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:383 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:405 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:537 | [test_coverage] Function '_default_workdir_root' has no corresponding test references |
| architecture | config.py:552 | [test_coverage] Function 'resolve_workdir_path' has no corresponding test references |
| architecture | config.py:610 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | config.py:665 | [test_coverage] Function 'get_config' has no corresponding test references |
| architecture | config.py:673 | [test_coverage] Function 'reset_config' has no corresponding test references |
| architecture | coordination_api.py:385 | [test_coverage] Function 'verify_api_key' has no corresponding test references |
| architecture | coordination_api.py:423 | [test_coverage] Function 'resolve_identity' has no corresponding test references |
| architecture | coordination_api.py:453 | [test_coverage] Function 'authorize_operation' has no corresponding test references |
| architecture | coordination_api.py:474 | [test_coverage] Function 'resolve_trust_level' has no corresponding test references |
| architecture | coordination_api.py:495 | [test_coverage] Function 'create_coordination_api' has no corresponding test references |
| architecture | coordination_api.py:517 | [test_coverage] Function 'lifespan' has no corresponding test references |
| architecture | coordination_api.py:656 | [test_coverage] Function 'acquire_lock' has no corresponding test references |
| architecture | coordination_api.py:693 | [test_coverage] Function 'release_lock' has no corresponding test references |
| architecture | coordination_api.py:722 | [test_coverage] Function 'check_lock_status' has no corresponding test references |
| architecture | coordination_api.py:747 | [test_coverage] Function 'store_memory' has no corresponding test references |
| architecture | coordination_api.py:779 | [test_coverage] Function 'query_memories' has no corresponding test references |
| architecture | coordination_api.py:822 | [test_coverage] Function 'claim_work' has no corresponding test references |
| architecture | coordination_api.py:856 | [test_coverage] Function 'complete_work' has no corresponding test references |
| architecture | coordination_api.py:888 | [test_coverage] Function 'submit_work' has no corresponding test references |
| architecture | coordination_api.py:923 | [test_coverage] Function 'get_task_endpoint' has no corresponding test references |
| architecture | coordination_api.py:970 | [test_coverage] Function 'create_issue' has no corresponding test references |
| architecture | coordination_api.py:1004 | [test_coverage] Function 'list_issues' has no corresponding test references |
| architecture | coordination_api.py:1031 | [test_coverage] Function 'blocked_issues_early' has no corresponding test references |
| architecture | coordination_api.py:1048 | [test_coverage] Function 'show_issue' has no corresponding test references |
| architecture | coordination_api.py:1065 | [test_coverage] Function 'update_issue' has no corresponding test references |
| architecture | coordination_api.py:1097 | [test_coverage] Function 'close_issue' has no corresponding test references |
| architecture | coordination_api.py:1129 | [test_coverage] Function 'comment_issue' has no corresponding test references |
| architecture | coordination_api.py:1151 | [test_coverage] Function 'check_guardrails' has no corresponding test references |
| architecture | coordination_api.py:1197 | [test_coverage] Function 'get_my_profile' has no corresponding test references |
| architecture | coordination_api.py:1227 | [test_coverage] Function 'get_agent_dispatch_configs' has no corresponding test references |
| architecture | coordination_api.py:1241 | [test_coverage] Function 'query_audit' has no corresponding test references |
| architecture | coordination_api.py:1301 | [test_coverage] Function 'write_handoff' has no corresponding test references |
| architecture | coordination_api.py:1329 | [test_coverage] Function 'read_handoff' has no corresponding test references |
| architecture | coordination_api.py:1363 | [test_coverage] Function 'check_policy' has no corresponding test references |
| architecture | coordination_api.py:1390 | [test_coverage] Function 'validate_cedar_policy' has no corresponding test references |
| architecture | coordination_api.py:1421 | [test_coverage] Function 'allocate_ports' has no corresponding test references |
| architecture | coordination_api.py:1443 | [test_coverage] Function 'release_ports' has no corresponding test references |
| architecture | coordination_api.py:1452 | [test_coverage] Function 'port_status' has no corresponding test references |
| architecture | coordination_api.py:1474 | [test_coverage] Function '_approval_to_dict' has no corresponding test references |
| architecture | coordination_api.py:1492 | [test_coverage] Function 'list_pending_approvals' has no corresponding test references |
| architecture | coordination_api.py:1503 | [test_coverage] Function 'decide_approval' has no corresponding test references |
| architecture | coordination_api.py:1530 | [test_coverage] Function 'list_policy_versions_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1543 | [test_coverage] Function 'rollback_policy_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1562 | [test_coverage] Function 'register_feature_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1596 | [test_coverage] Function 'deregister_feature_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1623 | [test_coverage] Function 'get_feature_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1647 | [test_coverage] Function 'list_active_features_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1671 | [test_coverage] Function 'analyze_feature_conflicts_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1695 | [test_coverage] Function 'enqueue_merge_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1728 | [test_coverage] Function 'get_merge_queue_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1751 | [test_coverage] Function 'get_next_merge_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1772 | [test_coverage] Function 'run_pre_merge_checks_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1797 | [test_coverage] Function 'mark_merged_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1816 | [test_coverage] Function 'remove_from_merge_queue_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1839 | [test_coverage] Function 'compose_train_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1893 | [test_coverage] Function 'eject_from_train_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1942 | [test_coverage] Function 'get_train_status_endpoint' has no corresponding test references |
| architecture | coordination_api.py:1972 | [test_coverage] Function 'report_spec_result_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2011 | [test_coverage] Function 'affected_tests_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2034 | [test_coverage] Function 'resolve_archetype_for_phase_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2107 | [test_coverage] Function 'report_status' has no corresponding test references |
| architecture | coordination_api.py:2189 | [test_coverage] Function 'test_notification' has no corresponding test references |
| architecture | coordination_api.py:2226 | [test_coverage] Function 'notifications_status' has no corresponding test references |
| architecture | coordination_api.py:2243 | [test_coverage] Function 'discovery_register' has no corresponding test references |
| architecture | coordination_api.py:2274 | [test_coverage] Function 'discovery_agents' has no corresponding test references |
| architecture | coordination_api.py:2308 | [test_coverage] Function 'discovery_heartbeat' has no corresponding test references |
| architecture | coordination_api.py:2335 | [test_coverage] Function 'discovery_cleanup' has no corresponding test references |
| architecture | coordination_api.py:2372 | [test_coverage] Function 'gen_eval_list_scenarios' has no corresponding test references |
| architecture | coordination_api.py:2400 | [test_coverage] Function 'gen_eval_validate' has no corresponding test references |
| architecture | coordination_api.py:2424 | [test_coverage] Function 'gen_eval_create' has no corresponding test references |
| architecture | coordination_api.py:2449 | [test_coverage] Function 'gen_eval_run' has no corresponding test references |
| architecture | coordination_api.py:2479 | [test_coverage] Function 'search_issues' has no corresponding test references |
| architecture | coordination_api.py:2495 | [test_coverage] Function 'ready_issues' has no corresponding test references |
| architecture | coordination_api.py:2521 | [test_coverage] Function 'request_permission_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2560 | [test_coverage] Function 'request_approval_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2599 | [test_coverage] Function 'check_approval_endpoint' has no corresponding test references |
| architecture | coordination_api.py:2630 | [test_coverage] Function '_database_health' has no corresponding test references |
| architecture | coordination_api.py:2658 | [test_coverage] Function 'help_overview' has no corresponding test references |
| architecture | coordination_api.py:2668 | [test_coverage] Function 'help_topic' has no corresponding test references |
| architecture | coordination_api.py:2695 | [test_coverage] Function 'get_sync_points_status' has no corresponding test references |
| architecture | coordination_api.py:2708 | [test_coverage] Function 'get_active_worktrees' has no corresponding test references |
| architecture | coordination_api.py:2720 | [test_coverage] Function 'mint_events_token' has no corresponding test references |
| architecture | coordination_api.py:2753 | [test_coverage] Function 'stream_work_events' has no corresponding test references |
| architecture | coordination_api.py:2804 | [test_coverage] Function 'patch_issue_labels' has no corresponding test references |
| architecture | coordination_api.py:2856 | [test_coverage] Function 'force_release_lock' has no corresponding test references |
| architecture | coordination_api.py:2892 | [test_coverage] Function 'kick_agent' has no corresponding test references |
| architecture | coordination_api.py:3013 | [test_coverage] Function 'put_saved_view' has no corresponding test references |
| architecture | coordination_api.py:3050 | [test_coverage] Function 'post_kanban_audit' has no corresponding test references |
| architecture | coordination_api.py:3086 | [test_coverage] Function 'live' has no corresponding test references |
| architecture | coordination_api.py:3091 | [test_coverage] Function 'ready' has no corresponding test references |
| architecture | coordination_api.py:3103 | [test_coverage] Function 'health' has no corresponding test references |
| architecture | coordination_api.py:3117 | [test_coverage] Function 'main' has no corresponding test references |
| architecture | coordination_cli.py:22 | [test_coverage] Function '_run' has no corresponding test references |
| architecture | coordination_cli.py:27 | [test_coverage] Function '_output' has no corresponding test references |
| architecture | coordination_cli.py:46 | [test_coverage] Function '_print_dict' has no corresponding test references |
| architecture | coordination_cli.py:70 | [test_coverage] Function '_error' has no corresponding test references |
| architecture | coordination_cli.py:81 | [test_coverage] Function 'cmd_health' has no corresponding test references |
| architecture | coordination_cli.py:108 | [test_coverage] Function 'cmd_feature_register' has no corresponding test references |
| architecture | coordination_cli.py:131 | [test_coverage] Function 'cmd_feature_deregister' has no corresponding test references |
| architecture | coordination_cli.py:148 | [test_coverage] Function 'cmd_feature_show' has no corresponding test references |
| architecture | coordination_cli.py:169 | [test_coverage] Function 'cmd_feature_list' has no corresponding test references |
| architecture | coordination_cli.py:189 | [test_coverage] Function 'cmd_feature_conflicts' has no corresponding test references |
| architecture | coordination_cli.py:210 | [test_coverage] Function 'cmd_mq_enqueue' has no corresponding test references |
| architecture | coordination_cli.py:229 | [test_coverage] Function 'cmd_mq_status' has no corresponding test references |
| architecture | coordination_cli.py:248 | [test_coverage] Function 'cmd_mq_next' has no corresponding test references |
| architecture | coordination_cli.py:265 | [test_coverage] Function 'cmd_mq_check' has no corresponding test references |
| architecture | coordination_cli.py:280 | [test_coverage] Function 'cmd_mq_merged' has no corresponding test references |
| architecture | coordination_cli.py:289 | [test_coverage] Function 'cmd_mq_remove' has no corresponding test references |
| architecture | coordination_cli.py:301 | [test_coverage] Function 'cmd_lock_acquire' has no corresponding test references |
| architecture | coordination_cli.py:322 | [test_coverage] Function 'cmd_lock_release' has no corresponding test references |
| architecture | coordination_cli.py:338 | [test_coverage] Function 'cmd_lock_status' has no corresponding test references |
| architecture | coordination_cli.py:361 | [test_coverage] Function 'cmd_work_submit' has no corresponding test references |
| architecture | coordination_cli.py:378 | [test_coverage] Function 'cmd_work_claim' has no corresponding test references |
| architecture | coordination_cli.py:398 | [test_coverage] Function 'cmd_work_complete' has no corresponding test references |
| architecture | coordination_cli.py:418 | [test_coverage] Function 'cmd_work_get' has no corresponding test references |
| architecture | coordination_cli.py:441 | [test_coverage] Function 'cmd_handoff_write' has no corresponding test references |
| architecture | coordination_cli.py:457 | [test_coverage] Function 'cmd_handoff_read' has no corresponding test references |
| architecture | coordination_cli.py:481 | [test_coverage] Function 'cmd_memory_store' has no corresponding test references |
| architecture | coordination_cli.py:499 | [test_coverage] Function 'cmd_memory_query' has no corresponding test references |
| architecture | coordination_cli.py:524 | [test_coverage] Function 'cmd_guardrails_check' has no corresponding test references |
| architecture | coordination_cli.py:545 | [test_coverage] Function 'cmd_audit_query' has no corresponding test references |
| architecture | coordination_cli.py:571 | [test_coverage] Function 'cmd_help' has no corresponding test references |
| architecture | coordination_cli.py:648 | [test_coverage] Function 'build_parser' has no corresponding test references |
| architecture | coordination_cli.py:834 | [test_coverage] Function 'main' has no corresponding test references |
| architecture | coordination_mcp.py:67 | [test_coverage] Function 'get_agent_id' has no corresponding test references |
| architecture | coordination_mcp.py:72 | [test_coverage] Function 'get_agent_type' has no corresponding test references |
| architecture | coordination_mcp.py:83 | [test_coverage] Function 'acquire_lock' has no corresponding test references |
| architecture | coordination_mcp.py:137 | [test_coverage] Function 'release_lock' has no corresponding test references |
| architecture | coordination_mcp.py:165 | [test_coverage] Function 'check_locks' has no corresponding test references |
| architecture | coordination_mcp.py:201 | [test_coverage] Function 'get_work' has no corresponding test references |
| architecture | coordination_mcp.py:244 | [test_coverage] Function 'complete_work' has no corresponding test references |
| architecture | coordination_mcp.py:292 | [test_coverage] Function 'submit_work' has no corresponding test references |
| architecture | coordination_mcp.py:357 | [test_coverage] Function 'get_task' has no corresponding test references |
| architecture | coordination_mcp.py:413 | [test_coverage] Function 'issue_create' has no corresponding test references |
| architecture | coordination_mcp.py:491 | [test_coverage] Function 'issue_list' has no corresponding test references |
| architecture | coordination_mcp.py:548 | [test_coverage] Function 'issue_show' has no corresponding test references |
| architecture | coordination_mcp.py:575 | [test_coverage] Function 'issue_update' has no corresponding test references |
| architecture | coordination_mcp.py:643 | [test_coverage] Function 'issue_close' has no corresponding test references |
| architecture | coordination_mcp.py:696 | [test_coverage] Function 'issue_comment' has no corresponding test references |
| architecture | coordination_mcp.py:731 | [test_coverage] Function 'issue_ready' has no corresponding test references |
| architecture | coordination_mcp.py:773 | [test_coverage] Function 'issue_blocked' has no corresponding test references |
| architecture | coordination_mcp.py:801 | [test_coverage] Function 'issue_search' has no corresponding test references |
| architecture | coordination_mcp.py:844 | [test_coverage] Function 'write_handoff' has no corresponding test references |
| architecture | coordination_mcp.py:907 | [test_coverage] Function 'read_handoff' has no corresponding test references |
| architecture | coordination_mcp.py:972 | [test_coverage] Function 'register_session' has no corresponding test references |
| architecture | coordination_mcp.py:1018 | [test_coverage] Function 'discover_agents' has no corresponding test references |
| architecture | coordination_mcp.py:1071 | [test_coverage] Function 'heartbeat' has no corresponding test references |
| architecture | coordination_mcp.py:1095 | [test_coverage] Function 'cleanup_dead_agents' has no corresponding test references |
| architecture | coordination_mcp.py:1134 | [test_coverage] Function 'remember' has no corresponding test references |
| architecture | coordination_mcp.py:1189 | [test_coverage] Function 'recall' has no corresponding test references |
| architecture | coordination_mcp.py:1249 | [test_coverage] Function 'check_guardrails' has no corresponding test references |
| architecture | coordination_mcp.py:1320 | [test_coverage] Function 'get_my_profile' has no corresponding test references |
| architecture | coordination_mcp.py:1357 | [test_coverage] Function 'get_agent_dispatch_configs' has no corresponding test references |
| architecture | coordination_mcp.py:1381 | [test_coverage] Function 'query_audit' has no corresponding test references |
| architecture | coordination_mcp.py:1436 | [test_coverage] Function 'check_policy' has no corresponding test references |
| architecture | coordination_mcp.py:1483 | [test_coverage] Function 'validate_cedar_policy' has no corresponding test references |
| architecture | coordination_mcp.py:1527 | [test_coverage] Function 'allocate_ports' has no corresponding test references |
| architecture | coordination_mcp.py:1576 | [test_coverage] Function 'release_ports' has no corresponding test references |
| architecture | coordination_mcp.py:1603 | [test_coverage] Function 'ports_status' has no corresponding test references |
| architecture | coordination_mcp.py:1648 | [test_coverage] Function 'request_approval' has no corresponding test references |
| architecture | coordination_mcp.py:1680 | [test_coverage] Function 'check_approval' has no corresponding test references |
| architecture | coordination_mcp.py:1706 | [test_coverage] Function 'list_policy_versions' has no corresponding test references |
| architecture | coordination_mcp.py:1726 | [test_coverage] Function 'request_permission' has no corresponding test references |
| architecture | coordination_mcp.py:1759 | [test_coverage] Function 'register_feature' has no corresponding test references |
| architecture | coordination_mcp.py:1815 | [test_coverage] Function 'deregister_feature' has no corresponding test references |
| architecture | coordination_mcp.py:1850 | [test_coverage] Function 'get_feature' has no corresponding test references |
| architecture | coordination_mcp.py:1884 | [test_coverage] Function 'list_active_features' has no corresponding test references |
| architecture | coordination_mcp.py:1914 | [test_coverage] Function 'analyze_feature_conflicts' has no corresponding test references |
| architecture | coordination_mcp.py:1955 | [test_coverage] Function 'enqueue_merge' has no corresponding test references |
| architecture | coordination_mcp.py:1996 | [test_coverage] Function 'get_merge_queue' has no corresponding test references |
| architecture | coordination_mcp.py:2025 | [test_coverage] Function 'get_next_merge' has no corresponding test references |
| architecture | coordination_mcp.py:2054 | [test_coverage] Function 'run_pre_merge_checks' has no corresponding test references |
| architecture | coordination_mcp.py:2084 | [test_coverage] Function 'mark_merged' has no corresponding test references |
| architecture | coordination_mcp.py:2106 | [test_coverage] Function 'remove_from_merge_queue' has no corresponding test references |
| architecture | coordination_mcp.py:2131 | [test_coverage] Function '_current_trust_level' has no corresponding test references |
| architecture | coordination_mcp.py:2146 | [test_coverage] Function 'compose_train' has no corresponding test references |
| architecture | coordination_mcp.py:2205 | [test_coverage] Function 'eject_from_train' has no corresponding test references |
| architecture | coordination_mcp.py:2263 | [test_coverage] Function 'get_train_status' has no corresponding test references |
| architecture | coordination_mcp.py:2296 | [test_coverage] Function 'report_spec_result' has no corresponding test references |
| architecture | coordination_mcp.py:2339 | [test_coverage] Function 'affected_tests' has no corresponding test references |
| architecture | coordination_mcp.py:2377 | [test_coverage] Function 'report_status' has no corresponding test references |
| architecture | coordination_mcp.py:2478 | [test_coverage] Function 'help' has no corresponding test references |
| architecture | coordination_mcp.py:2525 | [test_coverage] Function 'get_current_locks' has no corresponding test references |
| architecture | coordination_mcp.py:2551 | [test_coverage] Function 'get_recent_handoffs' has no corresponding test references |
| architecture | coordination_mcp.py:2592 | [test_coverage] Function 'get_pending_work' has no corresponding test references |
| architecture | coordination_mcp.py:2624 | [test_coverage] Function 'get_recent_memories' has no corresponding test references |
| architecture | coordination_mcp.py:2653 | [test_coverage] Function 'get_guardrail_patterns' has no corresponding test references |
| architecture | coordination_mcp.py:2683 | [test_coverage] Function 'get_current_profile' has no corresponding test references |
| architecture | coordination_mcp.py:2719 | [test_coverage] Function 'get_recent_audit' has no corresponding test references |
| architecture | coordination_mcp.py:2748 | [test_coverage] Function 'get_active_features_resource' has no corresponding test references |
| architecture | coordination_mcp.py:2780 | [test_coverage] Function 'get_merge_queue_resource' has no corresponding test references |
| architecture | coordination_mcp.py:2810 | [test_coverage] Function 'list_scenarios' has no corresponding test references |
| architecture | coordination_mcp.py:2854 | [test_coverage] Function 'validate_scenario' has no corresponding test references |
| architecture | coordination_mcp.py:2889 | [test_coverage] Function 'create_scenario' has no corresponding test references |
| architecture | coordination_mcp.py:2940 | [test_coverage] Function 'run_gen_eval' has no corresponding test references |
| architecture | coordination_mcp.py:2986 | [test_coverage] Function 'get_gen_eval_coverage' has no corresponding test references |
| architecture | coordination_mcp.py:3018 | [test_coverage] Function 'get_gen_eval_report' has no corresponding test references |
| architecture | coordination_mcp.py:3065 | [test_coverage] Function 'coordinate_file_edit' has no corresponding test references |
| architecture | coordination_mcp.py:3087 | [test_coverage] Function 'start_work_session' has no corresponding test references |
| architecture | coordination_mcp.py:3109 | [test_coverage] Function 'main' has no corresponding test references |
| architecture | db.py:32 | [test_coverage] Function 'rpc' has no corresponding test references |
| architecture | db.py:36 | [test_coverage] Function 'query' has no corresponding test references |
| architecture | db.py:45 | [test_coverage] Function 'insert' has no corresponding test references |
| architecture | db.py:54 | [test_coverage] Function 'update' has no corresponding test references |
| architecture | db.py:64 | [test_coverage] Function 'delete' has no corresponding test references |
| architecture | db.py:68 | [test_coverage] Function 'close' has no corresponding test references |
| architecture | db.py:80 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | db.py:85 | [test_coverage] Function 'config' has no corresponding test references |
| architecture | db.py:96 | [test_coverage] Function 'client' has no corresponding test references |
| architecture | db.py:101 | [test_coverage] Function '_headers' has no corresponding test references |
| architecture | db.py:109 | [test_coverage] Function 'rpc' has no corresponding test references |
| architecture | db.py:130 | [test_coverage] Function 'query' has no corresponding test references |
| architecture | db.py:154 | [test_coverage] Function 'insert' has no corresponding test references |
| architecture | db.py:184 | [test_coverage] Function 'update' has no corresponding test references |
| architecture | db.py:217 | [test_coverage] Function 'delete' has no corresponding test references |
| architecture | db.py:237 | [test_coverage] Function 'close' has no corresponding test references |
| architecture | db.py:244 | [test_coverage] Function 'create_db_client' has no corresponding test references |
| architecture | db.py:271 | [test_coverage] Function 'get_db' has no corresponding test references |
| architecture | db.py:279 | [test_coverage] Function 'close_db' has no corresponding test references |
| architecture | db.py:287 | [test_coverage] Function 'reset_db' has no corresponding test references |
| architecture | db_postgres.py:25 | [test_coverage] Function '_coerce_filter_value' has no corresponding test references |
| architecture | db_postgres.py:46 | [test_coverage] Function '_validate_identifier' has no corresponding test references |
| architecture | db_postgres.py:54 | [test_coverage] Function '_validate_select_clause' has no corresponding test references |
| architecture | db_postgres.py:66 | [test_coverage] Function '_serialize_for_asyncpg' has no corresponding test references |
| architecture | db_postgres.py:85 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | db_postgres.py:89 | [test_coverage] Function '_get_pool' has no corresponding test references |
| architecture | db_postgres.py:98 | [test_coverage] Function 'rpc' has no corresponding test references |
| architecture | db_postgres.py:128 | [test_coverage] Function 'query' has no corresponding test references |
| architecture | db_postgres.py:217 | [test_coverage] Function 'insert' has no corresponding test references |
| architecture | db_postgres.py:245 | [test_coverage] Function 'update' has no corresponding test references |
| architecture | db_postgres.py:287 | [test_coverage] Function 'delete' has no corresponding test references |
| architecture | db_postgres.py:309 | [test_coverage] Function 'close' has no corresponding test references |
| architecture | discovery.py:38 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:39 | [test_coverage] Function 'parse_dt' has no corresponding test references |
| architecture | discovery.py:68 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:82 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:96 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:113 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | discovery.py:124 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | discovery.py:128 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | discovery.py:133 | [test_coverage] Function 'register' has no corresponding test references |
| architecture | discovery.py:184 | [test_coverage] Function 'discover' has no corresponding test references |
| architecture | discovery.py:208 | [test_coverage] Function 'heartbeat' has no corresponding test references |
| architecture | discovery.py:266 | [test_coverage] Function 'cleanup_dead_agents' has no corresponding test references |
| architecture | discovery.py:309 | [test_coverage] Function 'get_discovery_service' has no corresponding test references |
| architecture | docker_manager.py:29 | [test_coverage] Function 'is_colima_installed' has no corresponding test references |
| architecture | docker_manager.py:34 | [test_coverage] Function 'is_colima_running' has no corresponding test references |
| architecture | docker_manager.py:47 | [test_coverage] Function '_ensure_colima_vm' has no corresponding test references |
| architecture | docker_manager.py:100 | [test_coverage] Function 'detect_runtime' has no corresponding test references |
| architecture | docker_manager.py:168 | [test_coverage] Function 'is_container_running' has no corresponding test references |
| architecture | docker_manager.py:182 | [test_coverage] Function 'start_container' has no corresponding test references |
| architecture | docker_manager.py:267 | [test_coverage] Function 'wait_for_healthy' has no corresponding test references |
| architecture | event_bus.py:50 | [test_coverage] Function '__post_init__' has no corresponding test references |
| architecture | event_bus.py:57 | [test_coverage] Function 'to_json' has no corresponding test references |
| architecture | event_bus.py:71 | [test_coverage] Function 'from_json' has no corresponding test references |
| architecture | event_bus.py:96 | [test_coverage] Function 'classify_urgency' has no corresponding test references |
| architecture | event_bus.py:119 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | event_bus.py:140 | [test_coverage] Function 'running' has no corresponding test references |
| architecture | event_bus.py:144 | [test_coverage] Function 'failed' has no corresponding test references |
| architecture | event_bus.py:148 | [test_coverage] Function 'on_event' has no corresponding test references |
| architecture | event_bus.py:159 | [test_coverage] Function 'off_event' has no corresponding test references |
| architecture | event_bus.py:188 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | event_bus.py:206 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | event_bus.py:225 | [test_coverage] Function 'restart' has no corresponding test references |
| architecture | event_bus.py:230 | [test_coverage] Function '_listen_loop' has no corresponding test references |
| architecture | event_bus.py:262 | [test_coverage] Function '_connect_and_listen' has no corresponding test references |
| architecture | event_bus.py:275 | [test_coverage] Function '_notification_handler' has no corresponding test references |
| architecture | event_bus.py:306 | [test_coverage] Function '_dispatch' has no corresponding test references |
| architecture | event_bus.py:329 | [test_coverage] Function '_safe_callback' has no corresponding test references |
| architecture | event_bus.py:343 | [test_coverage] Function 'get_event_bus' has no corresponding test references |
| architecture | event_bus.py:351 | [test_coverage] Function 'reset_event_bus' has no corresponding test references |
| architecture | event_stream.py:46 | [test_coverage] Function '_get_signing_key' has no corresponding test references |
| architecture | event_stream.py:51 | [test_coverage] Function '_signing_key_or_503' has no corresponding test references |
| architecture | event_stream.py:64 | [test_coverage] Function 'mint_events_token' has no corresponding test references |
| architecture | event_stream.py:111 | [test_coverage] Function 'validate_events_token' has no corresponding test references |
| architecture | event_stream.py:153 | [test_coverage] Function '_prune_nonces' has no corresponding test references |
| architecture | event_stream.py:163 | [test_coverage] Function '_build_snapshot' has no corresponding test references |
| architecture | event_stream.py:203 | [test_coverage] Function 'sse_event_generator' has no corresponding test references |
| architecture | event_stream.py:232 | [test_coverage] Function '_normalize_status' has no corresponding test references |
| architecture | event_stream.py:237 | [test_coverage] Function '_make_transition' has no corresponding test references |
| architecture | event_stream.py:258 | [test_coverage] Function '_make_audit' has no corresponding test references |
| architecture | event_stream.py:271 | [test_coverage] Function '_on_task_event' has no corresponding test references |
| architecture | event_stream.py:276 | [test_coverage] Function '_on_audit_event' has no corresponding test references |
| architecture | feature_flags.py:89 | [test_coverage] Function 'is_enabled' has no corresponding test references |
| architecture | feature_flags.py:92 | [test_coverage] Function 'to_yaml_dict' has no corresponding test references |
| architecture | feature_flags.py:106 | [test_coverage] Function 'from_yaml_dict' has no corresponding test references |
| architecture | feature_flags.py:107 | [test_coverage] Function '_parse' has no corresponding test references |
| architecture | feature_flags.py:129 | [test_coverage] Function 'normalize_flag_name' has no corresponding test references |
| architecture | feature_flags.py:164 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | feature_flags.py:173 | [test_coverage] Function 'load' has no corresponding test references |
| architecture | feature_flags.py:183 | [test_coverage] Function '_load_unlocked' has no corresponding test references |
| architecture | feature_flags.py:242 | [test_coverage] Function '_get_registry' has no corresponding test references |
| architecture | feature_flags.py:250 | [test_coverage] Function 'resolve_flag' has no corresponding test references |
| architecture | feature_flags.py:283 | [test_coverage] Function 'is_enabled' has no corresponding test references |
| architecture | feature_flags.py:287 | [test_coverage] Function 'check_undeclared_env_vars' has no corresponding test references |
| architecture | feature_flags.py:308 | [test_coverage] Function 'create_flag' has no corresponding test references |
| architecture | feature_flags.py:347 | [test_coverage] Function 'enable_flag' has no corresponding test references |
| architecture | feature_flags.py:363 | [test_coverage] Function '_write_registry' has no corresponding test references |
| architecture | feature_flags.py:393 | [test_coverage] Function 'get_feature_flag_service' has no corresponding test references |
| architecture | feature_flags.py:402 | [test_coverage] Function 'reset_feature_flag_service' has no corresponding test references |
| architecture | feature_flags.py:409 | [test_coverage] Function 'create_flag' has no corresponding test references |
| architecture | feature_flags.py:417 | [test_coverage] Function 'enable_flag' has no corresponding test references |
| architecture | feature_flags.py:421 | [test_coverage] Function 'resolve_flag' has no corresponding test references |
| architecture | feature_flags.py:425 | [test_coverage] Function 'is_enabled' has no corresponding test references |
| architecture | feature_registry.py:51 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | feature_registry.py:52 | [test_coverage] Function 'parse_dt' has no corresponding test references |
| architecture | feature_registry.py:84 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | feature_registry.py:103 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | feature_registry.py:131 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | feature_registry.py:135 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | feature_registry.py:140 | [test_coverage] Function 'register' has no corresponding test references |
| architecture | feature_registry.py:198 | [test_coverage] Function 'deregister' has no corresponding test references |
| architecture | feature_registry.py:233 | [test_coverage] Function 'get_feature' has no corresponding test references |
| architecture | feature_registry.py:248 | [test_coverage] Function 'get_active_features' has no corresponding test references |
| architecture | feature_registry.py:260 | [test_coverage] Function 'analyze_conflicts' has no corresponding test references |
| architecture | feature_registry.py:320 | [test_coverage] Function 'get_feature_registry_service' has no corresponding test references |
| architecture | git_adapter.py:108 | [test_coverage] Function 'create_speculative_ref' has no corresponding test references |
| architecture | git_adapter.py:115 | [test_coverage] Function 'delete_speculative_refs' has no corresponding test references |
| architecture | git_adapter.py:117 | [test_coverage] Function 'fast_forward_main' has no corresponding test references |
| architecture | git_adapter.py:119 | [test_coverage] Function 'get_changed_files' has no corresponding test references |
| architecture | git_adapter.py:121 | [test_coverage] Function 'list_speculative_refs' has no corresponding test references |
| architecture | git_adapter.py:129 | [test_coverage] Function 'validate_speculative_ref_name' has no corresponding test references |
| architecture | git_adapter.py:143 | [test_coverage] Function 'validate_branch_name' has no corresponding test references |
| architecture | git_adapter.py:159 | [test_coverage] Function 'parse_git_version' has no corresponding test references |
| architecture | git_adapter.py:183 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | git_adapter.py:189 | [test_coverage] Function '_ensure_git_version' has no corresponding test references |
| architecture | git_adapter.py:212 | [test_coverage] Function '_run' has no corresponding test references |
| architecture | git_adapter.py:225 | [test_coverage] Function 'create_speculative_ref' has no corresponding test references |
| architecture | git_adapter.py:317 | [test_coverage] Function 'delete_speculative_refs' has no corresponding test references |
| architecture | git_adapter.py:342 | [test_coverage] Function 'fast_forward_main' has no corresponding test references |
| architecture | git_adapter.py:372 | [test_coverage] Function 'get_changed_files' has no corresponding test references |
| architecture | git_adapter.py:406 | [test_coverage] Function 'list_speculative_refs' has no corresponding test references |
| architecture | git_adapter.py:426 | [test_coverage] Function '_parse_conflict_files' has no corresponding test references |
| architecture | github_coordination.py:39 | [test_coverage] Function 'parse' has no corresponding test references |
| architecture | github_coordination.py:79 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | github_coordination.py:92 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | github_coordination.py:96 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | github_coordination.py:101 | [test_coverage] Function 'parse_lock_labels' has no corresponding test references |
| architecture | github_coordination.py:121 | [test_coverage] Function 'parse_branch' has no corresponding test references |
| architecture | github_coordination.py:132 | [test_coverage] Function 'sync_label_locks' has no corresponding test references |
| architecture | github_coordination.py:212 | [test_coverage] Function 'sync_branch_tracking' has no corresponding test references |
| architecture | github_coordination.py:265 | [test_coverage] Function 'handle_push_webhook' has no corresponding test references |
| architecture | github_coordination.py:294 | [test_coverage] Function 'handle_issues_webhook' has no corresponding test references |
| architecture | github_coordination.py:328 | [test_coverage] Function 'get_github_coordination_service' has no corresponding test references |
| architecture | guardrails.py:27 | [test_coverage] Function '_ensure_guardrail_instruments' has no corresponding test references |
| architecture | guardrails.py:49 | [test_coverage] Function 'reset_guardrail_instruments' has no corresponding test references |
| architecture | guardrails.py:150 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | guardrails.py:172 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | guardrails.py:192 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | guardrails.py:206 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | guardrails.py:212 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | guardrails.py:217 | [test_coverage] Function '_load_patterns' has no corresponding test references |
| architecture | guardrails.py:243 | [test_coverage] Function 'check_operation' has no corresponding test references |
| architecture | guardrails.py:379 | [test_coverage] Function 'get_guardrails_service' has no corresponding test references |
| architecture | handoffs.py:37 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | handoffs.py:67 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | handoffs.py:86 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | handoffs.py:96 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | handoffs.py:100 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | handoffs.py:105 | [test_coverage] Function 'write' has no corresponding test references |
| architecture | handoffs.py:187 | [test_coverage] Function 'read' has no corresponding test references |
| architecture | handoffs.py:226 | [test_coverage] Function 'get_recent' has no corresponding test references |
| architecture | handoffs.py:249 | [test_coverage] Function 'get_handoff_service' has no corresponding test references |
| architecture | help_service.py:40 | [test_coverage] Function '_register' has no corresponding test references |
| architecture | help_service.py:611 | [test_coverage] Function 'get_help_overview' has no corresponding test references |
| architecture | help_service.py:632 | [test_coverage] Function 'get_help_topic' has no corresponding test references |
| architecture | help_service.py:655 | [test_coverage] Function 'list_topic_names' has no corresponding test references |
| architecture | http_proxy.py:41 | [test_coverage] Function '_validate_url' has no corresponding test references |
| architecture | http_proxy.py:104 | [test_coverage] Function 'from_env' has no corresponding test references |
| architecture | http_proxy.py:141 | [test_coverage] Function 'probe_database' has no corresponding test references |
| architecture | http_proxy.py:165 | [test_coverage] Function 'probe_http_api' has no corresponding test references |
| architecture | http_proxy.py:181 | [test_coverage] Function 'select_transport' has no corresponding test references |
| architecture | http_proxy.py:212 | [test_coverage] Function 'init_client' has no corresponding test references |
| architecture | http_proxy.py:223 | [test_coverage] Function 'get_config' has no corresponding test references |
| architecture | http_proxy.py:230 | [test_coverage] Function 'get_client' has no corresponding test references |
| architecture | http_proxy.py:237 | [test_coverage] Function 'shutdown_client' has no corresponding test references |
| architecture | http_proxy.py:245 | [test_coverage] Function '_build_default_headers' has no corresponding test references |
| architecture | http_proxy.py:257 | [test_coverage] Function '_error_response' has no corresponding test references |
| architecture | http_proxy.py:264 | [test_coverage] Function '_request' has no corresponding test references |
| architecture | http_proxy.py:332 | [test_coverage] Function '_agent_identity' has no corresponding test references |
| architecture | http_proxy.py:350 | [test_coverage] Function 'proxy_acquire_lock' has no corresponding test references |
| architecture | http_proxy.py:365 | [test_coverage] Function 'proxy_release_lock' has no corresponding test references |
| architecture | http_proxy.py:374 | [test_coverage] Function 'proxy_check_locks' has no corresponding test references |
| architecture | http_proxy.py:425 | [test_coverage] Function 'proxy_get_work' has no corresponding test references |
| architecture | http_proxy.py:436 | [test_coverage] Function 'proxy_complete_work' has no corresponding test references |
| architecture | http_proxy.py:453 | [test_coverage] Function 'proxy_submit_work' has no corresponding test references |
| architecture | http_proxy.py:472 | [test_coverage] Function 'proxy_get_task' has no corresponding test references |
| architecture | http_proxy.py:486 | [test_coverage] Function 'proxy_issue_create' has no corresponding test references |
| architecture | http_proxy.py:511 | [test_coverage] Function 'proxy_issue_list' has no corresponding test references |
| architecture | http_proxy.py:532 | [test_coverage] Function 'proxy_issue_show' has no corresponding test references |
| architecture | http_proxy.py:537 | [test_coverage] Function 'proxy_issue_update' has no corresponding test references |
| architecture | http_proxy.py:562 | [test_coverage] Function 'proxy_issue_close' has no corresponding test references |
| architecture | http_proxy.py:577 | [test_coverage] Function 'proxy_issue_comment' has no corresponding test references |
| architecture | http_proxy.py:590 | [test_coverage] Function 'proxy_issue_search' has no corresponding test references |
| architecture | http_proxy.py:603 | [test_coverage] Function 'proxy_issue_ready' has no corresponding test references |
| architecture | http_proxy.py:616 | [test_coverage] Function 'proxy_issue_blocked' has no corresponding test references |
| architecture | http_proxy.py:626 | [test_coverage] Function 'proxy_write_handoff' has no corresponding test references |
| architecture | http_proxy.py:647 | [test_coverage] Function 'proxy_read_handoff' has no corresponding test references |
| architecture | http_proxy.py:665 | [test_coverage] Function 'proxy_register_session' has no corresponding test references |
| architecture | http_proxy.py:680 | [test_coverage] Function 'proxy_discover_agents' has no corresponding test references |
| architecture | http_proxy.py:693 | [test_coverage] Function 'proxy_heartbeat' has no corresponding test references |
| architecture | http_proxy.py:699 | [test_coverage] Function 'proxy_cleanup_dead_agents' has no corresponding test references |
| architecture | http_proxy.py:715 | [test_coverage] Function 'proxy_remember' has no corresponding test references |
| architecture | http_proxy.py:736 | [test_coverage] Function 'proxy_recall' has no corresponding test references |
| architecture | http_proxy.py:758 | [test_coverage] Function 'proxy_check_guardrails' has no corresponding test references |
| architecture | http_proxy.py:771 | [test_coverage] Function 'proxy_get_my_profile' has no corresponding test references |
| architecture | http_proxy.py:776 | [test_coverage] Function 'proxy_get_agent_dispatch_configs' has no corresponding test references |
| architecture | http_proxy.py:781 | [test_coverage] Function 'proxy_query_audit' has no corresponding test references |
| architecture | http_proxy.py:800 | [test_coverage] Function 'proxy_check_policy' has no corresponding test references |
| architecture | http_proxy.py:815 | [test_coverage] Function 'proxy_validate_cedar_policy' has no corresponding test references |
| architecture | http_proxy.py:824 | [test_coverage] Function 'proxy_list_policy_versions' has no corresponding test references |
| architecture | http_proxy.py:836 | [test_coverage] Function 'proxy_request_permission' has no corresponding test references |
| architecture | http_proxy.py:849 | [test_coverage] Function 'proxy_request_approval' has no corresponding test references |
| architecture | http_proxy.py:864 | [test_coverage] Function 'proxy_check_approval' has no corresponding test references |
| architecture | http_proxy.py:874 | [test_coverage] Function 'proxy_allocate_ports' has no corresponding test references |
| architecture | http_proxy.py:883 | [test_coverage] Function 'proxy_release_ports' has no corresponding test references |
| architecture | http_proxy.py:892 | [test_coverage] Function 'proxy_ports_status' has no corresponding test references |
| architecture | http_proxy.py:909 | [test_coverage] Function 'proxy_register_feature' has no corresponding test references |
| architecture | http_proxy.py:930 | [test_coverage] Function 'proxy_deregister_feature' has no corresponding test references |
| architecture | http_proxy.py:943 | [test_coverage] Function 'proxy_get_feature' has no corresponding test references |
| architecture | http_proxy.py:948 | [test_coverage] Function 'proxy_list_active_features' has no corresponding test references |
| architecture | http_proxy.py:953 | [test_coverage] Function 'proxy_analyze_feature_conflicts' has no corresponding test references |
| architecture | http_proxy.py:971 | [test_coverage] Function 'proxy_enqueue_merge' has no corresponding test references |
| architecture | http_proxy.py:984 | [test_coverage] Function 'proxy_get_merge_queue' has no corresponding test references |
| architecture | http_proxy.py:989 | [test_coverage] Function 'proxy_get_next_merge' has no corresponding test references |
| architecture | http_proxy.py:994 | [test_coverage] Function 'proxy_run_pre_merge_checks' has no corresponding test references |
| architecture | http_proxy.py:1003 | [test_coverage] Function 'proxy_mark_merged' has no corresponding test references |
| architecture | http_proxy.py:1012 | [test_coverage] Function 'proxy_remove_from_merge_queue' has no corresponding test references |
| architecture | http_proxy.py:1022 | [test_coverage] Function 'proxy_report_status' has no corresponding test references |
| architecture | http_proxy.py:1049 | [test_coverage] Function 'proxy_list_scenarios' has no corresponding test references |
| architecture | http_proxy.py:1073 | [test_coverage] Function 'proxy_validate_scenario' has no corresponding test references |
| architecture | http_proxy.py:1082 | [test_coverage] Function 'proxy_create_scenario' has no corresponding test references |
| architecture | http_proxy.py:1101 | [test_coverage] Function 'proxy_run_gen_eval' has no corresponding test references |
| architecture | issue_service.py:72 | [test_coverage] Function 'from_row' has no corresponding test references |
| architecture | issue_service.py:73 | [test_coverage] Function 'parse_dt' has no corresponding test references |
| architecture | issue_service.py:108 | [test_coverage] Function 'to_dict' has no corresponding test references |
| architecture | issue_service.py:164 | [test_coverage] Function 'from_row' has no corresponding test references |
| architecture | issue_service.py:176 | [test_coverage] Function 'to_dict' has no corresponding test references |
| architecture | issue_service.py:189 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | issue_service.py:193 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | issue_service.py:198 | [test_coverage] Function 'create' has no corresponding test references |
| architecture | issue_service.py:251 | [test_coverage] Function 'list_issues' has no corresponding test references |
| architecture | issue_service.py:306 | [test_coverage] Function 'show' has no corresponding test references |
| architecture | issue_service.py:344 | [test_coverage] Function 'update' has no corresponding test references |
| architecture | issue_service.py:410 | [test_coverage] Function 'close' has no corresponding test references |
| architecture | issue_service.py:453 | [test_coverage] Function 'comment' has no corresponding test references |
| architecture | issue_service.py:479 | [test_coverage] Function 'ready' has no corresponding test references |
| architecture | issue_service.py:525 | [test_coverage] Function 'blocked' has no corresponding test references |
| architecture | issue_service.py:554 | [test_coverage] Function 'search' has no corresponding test references |
| architecture | issue_service.py:594 | [test_coverage] Function 'get_issue_service' has no corresponding test references |
| architecture | kanban_viz_files.py:69 | [test_coverage] Function '_load_schema' has no corresponding test references |
| architecture | kanban_viz_files.py:115 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | kanban_viz_files.py:124 | [test_coverage] Function '_validate_against' has no corresponding test references |
| architecture | kanban_viz_files.py:135 | [test_coverage] Function '_validate_slug' has no corresponding test references |
| architecture | kanban_viz_files.py:142 | [test_coverage] Function '_git_sha' has no corresponding test references |
| architecture | kanban_viz_files.py:156 | [test_coverage] Function '_atomic_write' has no corresponding test references |
| architecture | kanban_viz_files.py:171 | [test_coverage] Function 'write_saved_view' has no corresponding test references |
| architecture | kanban_viz_files.py:211 | [test_coverage] Function 'write_audit_event' has no corresponding test references |
| architecture | langfuse_middleware.py:44 | [test_coverage] Function 'dispatch' has no corresponding test references |
| architecture | langfuse_middleware.py:98 | [test_coverage] Function '_resolve_agent_id' has no corresponding test references |
| architecture | langfuse_middleware.py:114 | [test_coverage] Function '_finalize_trace' has no corresponding test references |
| architecture | langfuse_tracing.py:30 | [test_coverage] Function '_is_enabled' has no corresponding test references |
| architecture | langfuse_tracing.py:34 | [test_coverage] Function 'init_langfuse' has no corresponding test references |
| architecture | langfuse_tracing.py:79 | [test_coverage] Function 'get_langfuse' has no corresponding test references |
| architecture | langfuse_tracing.py:84 | [test_coverage] Function 'shutdown_langfuse' has no corresponding test references |
| architecture | langfuse_tracing.py:102 | [test_coverage] Function 'create_trace' has no corresponding test references |
| architecture | langfuse_tracing.py:130 | [test_coverage] Function 'create_span' has no corresponding test references |
| architecture | langfuse_tracing.py:153 | [test_coverage] Function 'end_span' has no corresponding test references |
| architecture | langfuse_tracing.py:175 | [test_coverage] Function 'trace_operation' has no corresponding test references |
| architecture | langfuse_tracing.py:229 | [test_coverage] Function 'reset_langfuse' has no corresponding test references |
| architecture | locks.py:29 | [test_coverage] Function '_get_instruments' has no corresponding test references |
| architecture | locks.py:58 | [test_coverage] Function '_ensure_instruments' has no corresponding test references |
| architecture | locks.py:81 | [test_coverage] Function 'is_valid_lock_key' has no corresponding test references |
| architecture | locks.py:101 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | locks.py:102 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | locks.py:131 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | locks.py:152 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | locks.py:156 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | locks.py:161 | [test_coverage] Function 'acquire' has no corresponding test references |
| architecture | locks.py:276 | [test_coverage] Function 'release' has no corresponding test references |
| architecture | locks.py:341 | [test_coverage] Function 'check' has no corresponding test references |
| architecture | locks.py:368 | [test_coverage] Function 'extend' has no corresponding test references |
| architecture | locks.py:392 | [test_coverage] Function 'is_locked' has no corresponding test references |
| architecture | locks.py:404 | [test_coverage] Function 'force_release' has no corresponding test references |
| architecture | locks.py:465 | [test_coverage] Function 'get_lock_service' has no corresponding test references |
| architecture | memory.py:35 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | memory.py:65 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | memory.py:81 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | memory.py:92 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | memory.py:96 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | memory.py:101 | [test_coverage] Function 'remember' has no corresponding test references |
| architecture | memory.py:181 | [test_coverage] Function 'recall' has no corresponding test references |
| architecture | memory.py:219 | [test_coverage] Function 'get_memory_service' has no corresponding test references |
| architecture | merge_queue.py:73 | [test_coverage] Function 'from_feature' has no corresponding test references |
| architecture | merge_queue.py:99 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | merge_queue.py:108 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | merge_queue.py:114 | [test_coverage] Function 'registry' has no corresponding test references |
| architecture | merge_queue.py:119 | [test_coverage] Function 'enqueue' has no corresponding test references |
| architecture | merge_queue.py:210 | [test_coverage] Function 'get_queue' has no corresponding test references |
| architecture | merge_queue.py:246 | [test_coverage] Function 'get_next_to_merge' has no corresponding test references |
| architecture | merge_queue.py:260 | [test_coverage] Function 'run_pre_merge_checks' has no corresponding test references |
| architecture | merge_queue.py:349 | [test_coverage] Function 'mark_merged' has no corresponding test references |
| architecture | merge_queue.py:376 | [test_coverage] Function 'remove_from_queue' has no corresponding test references |
| architecture | merge_queue.py:404 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | merge_queue.py:417 | [test_coverage] Function 'get_merge_queue_service' has no corresponding test references |
| architecture | merge_train.py:114 | [test_coverage] Function '_entry_prefix_set' has no corresponding test references |
| architecture | merge_train.py:137 | [test_coverage] Function '_find_cycles_in_cross_partition_graph' has no corresponding test references |
| architecture | merge_train.py:176 | [test_coverage] Function '_dfs' has no corresponding test references |
| architecture | merge_train.py:212 | [test_coverage] Function 'compute_partitions' has no corresponding test references |
| architecture | merge_train.py:294 | [test_coverage] Function '_speculative_ref_name' has no corresponding test references |
| architecture | merge_train.py:299 | [test_coverage] Function '_sort_entries_by_priority' has no corresponding test references |
| architecture | merge_train.py:304 | [test_coverage] Function '_handle_conflict' has no corresponding test references |
| architecture | merge_train.py:318 | [test_coverage] Function '_handle_speculative_success' has no corresponding test references |
| architecture | merge_train.py:339 | [test_coverage] Function 'compose_train' has no corresponding test references |
| architecture | merge_train.py:445 | [test_coverage] Function '_speculate' has no corresponding test references |
| architecture | merge_train.py:547 | [test_coverage] Function '_declared_namespaces' has no corresponding test references |
| architecture | merge_train.py:557 | [test_coverage] Function 'validate_post_speculation_claims' has no corresponding test references |
| architecture | merge_train.py:644 | [test_coverage] Function '_caller_is_authorized_to_eject' has no corresponding test references |
| architecture | merge_train.py:659 | [test_coverage] Function 'eject_from_train' has no corresponding test references |
| architecture | merge_train.py:768 | [test_coverage] Function 'reset_blocked_entry' has no corresponding test references |
| architecture | merge_train.py:811 | [test_coverage] Function 'reset_abandoned_entry' has no corresponding test references |
| architecture | merge_train.py:884 | [test_coverage] Function '_build_merge_graph' has no corresponding test references |
| architecture | merge_train.py:974 | [test_coverage] Function '_compute_wave_order' has no corresponding test references |
| architecture | merge_train.py:1017 | [test_coverage] Function 'execute_wave_merge' has no corresponding test references |
| architecture | merge_train.py:1137 | [test_coverage] Function '_group_refs_by_train_id' has no corresponding test references |
| architecture | merge_train.py:1157 | [test_coverage] Function 'cleanup_orphaned_speculative_refs' has no corresponding test references |
| architecture | merge_train.py:1206 | [test_coverage] Function 'gc_aged_speculative_refs' has no corresponding test references |
| architecture | merge_train_service.py:66 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | merge_train_service.py:77 | [test_coverage] Function '_feature_to_train_entry' has no corresponding test references |
| architecture | merge_train_service.py:123 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | merge_train_service.py:138 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | merge_train_service.py:144 | [test_coverage] Function 'registry' has no corresponding test references |
| architecture | merge_train_service.py:150 | [test_coverage] Function 'git_adapter' has no corresponding test references |
| architecture | merge_train_service.py:160 | [test_coverage] Function 'refresh_client' has no corresponding test references |
| architecture | merge_train_service.py:167 | [test_coverage] Function '_load_entries' has no corresponding test references |
| architecture | merge_train_service.py:177 | [test_coverage] Function '_save_entry' has no corresponding test references |
| architecture | merge_train_service.py:197 | [test_coverage] Function '_persist_entries' has no corresponding test references |
| architecture | merge_train_service.py:208 | [test_coverage] Function '_probe_and_maybe_refresh' has no corresponding test references |
| architecture | merge_train_service.py:256 | [test_coverage] Function 'compose_train' has no corresponding test references |
| architecture | merge_train_service.py:288 | [test_coverage] Function 'eject_from_train' has no corresponding test references |
| architecture | merge_train_service.py:338 | [test_coverage] Function 'get_train_status' has no corresponding test references |
| architecture | merge_train_service.py:343 | [test_coverage] Function 'report_spec_result' has no corresponding test references |
| architecture | merge_train_service.py:396 | [test_coverage] Function 'get_merge_train_service' has no corresponding test references |
| architecture | merge_train_service.py:404 | [test_coverage] Function 'reset_merge_train_service' has no corresponding test references |
| architecture | merge_train_service.py:438 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | merge_train_service.py:457 | [test_coverage] Function 'service' has no corresponding test references |
| architecture | merge_train_service.py:463 | [test_coverage] Function 'running' has no corresponding test references |
| architecture | merge_train_service.py:466 | [test_coverage] Function 'run_once' has no corresponding test references |
| architecture | merge_train_service.py:484 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | merge_train_service.py:494 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | merge_train_service.py:506 | [test_coverage] Function '_loop' has no corresponding test references |
| architecture | merge_train_service.py:521 | [test_coverage] Function 'get_merge_train_sweeper' has no corresponding test references |
| architecture | merge_train_service.py:529 | [test_coverage] Function 'reset_merge_train_sweeper' has no corresponding test references |
| architecture | merge_train_types.py:127 | [test_coverage] Function 'is_terminal' has no corresponding test references |
| architecture | merge_train_types.py:130 | [test_coverage] Function 'to_metadata_dict' has no corresponding test references |
| architecture | merge_train_types.py:162 | [test_coverage] Function 'all_passed' has no corresponding test references |
| architecture | merge_train_types.py:202 | [test_coverage] Function 'new_train_id' has no corresponding test references |
| architecture | merge_train_types.py:206 | [test_coverage] Function 'all_entries' has no corresponding test references |
| architecture | merge_train_types.py:213 | [test_coverage] Function 'total_entry_count' has no corresponding test references |
| architecture | merge_train_types.py:252 | [test_coverage] Function 'file_path_to_namespaces' has no corresponding test references |
| architecture | merge_train_types.py:287 | [test_coverage] Function 'claim_prefix' has no corresponding test references |
| architecture | migrations.py:35 | [test_coverage] Function 'discover_migrations' has no corresponding test references |
| architecture | migrations.py:50 | [test_coverage] Function '_checksum' has no corresponding test references |
| architecture | migrations.py:55 | [test_coverage] Function 'run_migrations' has no corresponding test references |
| architecture | migrations.py:146 | [test_coverage] Function 'ensure_schema' has no corresponding test references |
| architecture | network_policies.py:24 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | network_policies.py:36 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | network_policies.py:40 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | network_policies.py:45 | [test_coverage] Function 'check_domain' has no corresponding test references |
| architecture | network_policies.py:85 | [test_coverage] Function 'get_network_policy_service' has no corresponding test references |
| architecture | notifications/base.py:16 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/base.py:20 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/base.py:24 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/base.py:34 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/base.py:37 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/base.py:41 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/base.py:44 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/gmail.py:55 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/gmail.py:71 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/gmail.py:128 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/gmail.py:143 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/gmail.py:148 | [test_coverage] Function 'start_imap_listener' has no corresponding test references |
| architecture | notifications/gmail.py:214 | [test_coverage] Function 'stop_imap_listener' has no corresponding test references |
| architecture | notifications/gmail.py:222 | [test_coverage] Function '_process_imap_message' has no corresponding test references |
| architecture | notifications/gmail.py:348 | [test_coverage] Function '_send_reply_email' has no corresponding test references |
| architecture | notifications/gmail.py:368 | [test_coverage] Function '_render' has no corresponding test references |
| architecture | notifications/gmail.py:380 | [test_coverage] Function '_thread_message_id' has no corresponding test references |
| architecture | notifications/gmail.py:387 | [test_coverage] Function 'get_gmail_channel' has no corresponding test references |
| architecture | notifications/notifier.py:33 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/notifier.py:38 | [test_coverage] Function 'register_channel' has no corresponding test references |
| architecture | notifications/notifier.py:43 | [test_coverage] Function 'enabled' has no corresponding test references |
| architecture | notifications/notifier.py:47 | [test_coverage] Function 'start_digest_loop' has no corresponding test references |
| architecture | notifications/notifier.py:54 | [test_coverage] Function 'stop_digest_loop' has no corresponding test references |
| architecture | notifications/notifier.py:67 | [test_coverage] Function '_digest_loop' has no corresponding test references |
| architecture | notifications/notifier.py:77 | [test_coverage] Function '_flush_digest' has no corresponding test references |
| architecture | notifications/notifier.py:110 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/notifier.py:169 | [test_coverage] Function '_send_with_retry' has no corresponding test references |
| architecture | notifications/notifier.py:208 | [test_coverage] Function '_passes_filter' has no corresponding test references |
| architecture | notifications/notifier.py:223 | [test_coverage] Function 'get_notifier' has no corresponding test references |
| architecture | notifications/notifier.py:231 | [test_coverage] Function 'reset_notifier' has no corresponding test references |
| architecture | notifications/relay.py:29 | [test_coverage] Function 'extract_token' has no corresponding test references |
| architecture | notifications/relay.py:39 | [test_coverage] Function 'parse_reply' has no corresponding test references |
| architecture | notifications/relay.py:72 | [test_coverage] Function 'validate_sender' has no corresponding test references |
| architecture | notifications/relay.py:82 | [test_coverage] Function 'clean_reply_body' has no corresponding test references |
| architecture | notifications/relay.py:109 | [test_coverage] Function 'route_reply' has no corresponding test references |
| architecture | notifications/telegram.py:28 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/telegram.py:39 | [test_coverage] Function 'client' has no corresponding test references |
| architecture | notifications/telegram.py:44 | [test_coverage] Function '_api_url' has no corresponding test references |
| architecture | notifications/telegram.py:47 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/telegram.py:106 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/telegram.py:122 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/telegram.py:126 | [test_coverage] Function '_escape_markdown' has no corresponding test references |
| architecture | notifications/telegram.py:131 | [test_coverage] Function '_format_message' has no corresponding test references |
| architecture | notifications/telegram.py:148 | [test_coverage] Function 'get_telegram_channel' has no corresponding test references |
| architecture | notifications/templates.py:10 | [test_coverage] Function '_esc' has no corresponding test references |
| architecture | notifications/templates.py:15 | [test_coverage] Function '_sanitize_header' has no corresponding test references |
| architecture | notifications/templates.py:46 | [test_coverage] Function '_wrap' has no corresponding test references |
| architecture | notifications/templates.py:56 | [test_coverage] Function '_change_label' has no corresponding test references |
| architecture | notifications/templates.py:61 | [test_coverage] Function '_field' has no corresponding test references |
| architecture | notifications/templates.py:71 | [test_coverage] Function 'render_approval_email' has no corresponding test references |
| architecture | notifications/templates.py:100 | [test_coverage] Function 'render_status_email' has no corresponding test references |
| architecture | notifications/templates.py:119 | [test_coverage] Function 'render_escalation_email' has no corresponding test references |
| architecture | notifications/templates.py:147 | [test_coverage] Function 'render_stale_agent_email' has no corresponding test references |
| architecture | notifications/templates.py:165 | [test_coverage] Function 'render_digest_email' has no corresponding test references |
| architecture | notifications/webhook.py:26 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | notifications/webhook.py:37 | [test_coverage] Function 'client' has no corresponding test references |
| architecture | notifications/webhook.py:42 | [test_coverage] Function 'send' has no corresponding test references |
| architecture | notifications/webhook.py:83 | [test_coverage] Function 'test' has no corresponding test references |
| architecture | notifications/webhook.py:109 | [test_coverage] Function 'supports_reply' has no corresponding test references |
| architecture | notifications/webhook.py:113 | [test_coverage] Function 'get_webhook_channel' has no corresponding test references |
| architecture | policy_engine.py:29 | [test_coverage] Function '_ensure_policy_instruments' has no corresponding test references |
| architecture | policy_engine.py:92 | [test_coverage] Function 'allow' has no corresponding test references |
| architecture | policy_engine.py:96 | [test_coverage] Function 'deny' has no corresponding test references |
| architecture | policy_engine.py:115 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | policy_engine.py:119 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | policy_engine.py:124 | [test_coverage] Function 'check_operation' has no corresponding test references |
| architecture | policy_engine.py:165 | [test_coverage] Function '_do_check_operation' has no corresponding test references |
| architecture | policy_engine.py:350 | [test_coverage] Function 'check_network_access' has no corresponding test references |
| architecture | policy_engine.py:373 | [test_coverage] Function 'list_policy_versions' has no corresponding test references |
| architecture | policy_engine.py:392 | [test_coverage] Function 'rollback_policy' has no corresponding test references |
| architecture | policy_engine.py:418 | [test_coverage] Function '_log_policy_decision' has no corresponding test references |
| architecture | policy_engine.py:464 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | policy_engine.py:480 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | policy_engine.py:485 | [test_coverage] Function '_load_default_policies' has no corresponding test references |
| architecture | policy_engine.py:499 | [test_coverage] Function '_load_schema' has no corresponding test references |
| architecture | policy_engine.py:517 | [test_coverage] Function '_load_policies' has no corresponding test references |
| architecture | policy_engine.py:572 | [test_coverage] Function '_build_entity' has no corresponding test references |
| architecture | policy_engine.py:609 | [test_coverage] Function '_build_resource_entity' has no corresponding test references |
| architecture | policy_engine.py:636 | [test_coverage] Function '_determine_resource_type' has no corresponding test references |
| architecture | policy_engine.py:648 | [test_coverage] Function 'check_operation' has no corresponding test references |
| architecture | policy_engine.py:689 | [test_coverage] Function '_do_check_operation' has no corresponding test references |
| architecture | policy_engine.py:778 | [test_coverage] Function 'check_network_access' has no corresponding test references |
| architecture | policy_engine.py:797 | [test_coverage] Function 'validate_policy' has no corresponding test references |
| architecture | policy_engine.py:818 | [test_coverage] Function 'list_policies' has no corresponding test references |
| architecture | policy_engine.py:837 | [test_coverage] Function 'invalidate_cache' has no corresponding test references |
| architecture | policy_engine.py:842 | [test_coverage] Function 'list_policy_versions' has no corresponding test references |
| architecture | policy_engine.py:861 | [test_coverage] Function 'rollback_policy' has no corresponding test references |
| architecture | policy_engine.py:888 | [test_coverage] Function '_log_policy_decision' has no corresponding test references |
| architecture | policy_engine.py:928 | [test_coverage] Function 'get_policy_engine' has no corresponding test references |
| architecture | policy_engine.py:945 | [test_coverage] Function 'reset_policy_engine' has no corresponding test references |
| architecture | policy_engine.py:951 | [test_coverage] Function 'reset_policy_instruments' has no corresponding test references |
| architecture | policy_sync.py:21 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | policy_sync.py:25 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | policy_sync.py:29 | [test_coverage] Function 'on_policy_change' has no corresponding test references |
| architecture | policy_sync.py:45 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | policy_sync.py:60 | [test_coverage] Function 'running' has no corresponding test references |
| architecture | policy_sync.py:64 | [test_coverage] Function 'on_policy_change' has no corresponding test references |
| architecture | policy_sync.py:67 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | policy_sync.py:79 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | policy_sync.py:93 | [test_coverage] Function '_listen_loop' has no corresponding test references |
| architecture | policy_sync.py:121 | [test_coverage] Function '_connect_and_listen' has no corresponding test references |
| architecture | policy_sync.py:127 | [test_coverage] Function '_notification_handler' has no corresponding test references |
| architecture | policy_sync.py:149 | [test_coverage] Function '_safe_callback' has no corresponding test references |
| architecture | policy_sync.py:163 | [test_coverage] Function 'get_policy_sync_service' has no corresponding test references |
| architecture | policy_sync.py:171 | [test_coverage] Function 'reset_policy_sync_service' has no corresponding test references |
| architecture | port_allocator.py:37 | [test_coverage] Function 'env_snippet' has no corresponding test references |
| architecture | port_allocator.py:55 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | port_allocator.py:74 | [test_coverage] Function 'allocate' has no corresponding test references |
| architecture | port_allocator.py:132 | [test_coverage] Function 'release' has no corresponding test references |
| architecture | port_allocator.py:141 | [test_coverage] Function 'status' has no corresponding test references |
| architecture | port_allocator.py:151 | [test_coverage] Function '_cleanup_expired' has no corresponding test references |
| architecture | port_allocator.py:166 | [test_coverage] Function '_compose_project_name' has no corresponding test references |
| architecture | port_allocator.py:178 | [test_coverage] Function 'get_port_allocator' has no corresponding test references |
| architecture | port_allocator.py:189 | [test_coverage] Function 'reset_port_allocator' has no corresponding test references |
| architecture | profile_loader.py:64 | [test_coverage] Function 'deep_merge' has no corresponding test references |
| architecture | profile_loader.py:87 | [test_coverage] Function '_load_secrets_file' has no corresponding test references |
| architecture | profile_loader.py:114 | [test_coverage] Function '_load_secrets_openbao' has no corresponding test references |
| architecture | profile_loader.py:159 | [test_coverage] Function '_load_secrets' has no corresponding test references |
| architecture | profile_loader.py:171 | [test_coverage] Function 'resolve_dynamic_dsn' has no corresponding test references |
| architecture | profile_loader.py:231 | [test_coverage] Function 'interpolate' has no corresponding test references |
| architecture | profile_loader.py:239 | [test_coverage] Function '_replace' has no corresponding test references |
| architecture | profile_loader.py:260 | [test_coverage] Function '_interpolate_tree' has no corresponding test references |
| architecture | profile_loader.py:277 | [test_coverage] Function '_resolve_profile' has no corresponding test references |
| architecture | profile_loader.py:311 | [test_coverage] Function '_flatten' has no corresponding test references |
| architecture | profile_loader.py:323 | [test_coverage] Function '_inject_env' has no corresponding test references |
| architecture | profile_loader.py:339 | [test_coverage] Function 'load_profile' has no corresponding test references |
| architecture | profile_loader.py:372 | [test_coverage] Function 'apply_profile' has no corresponding test references |
| architecture | profiles.py:36 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | profiles.py:63 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | profiles.py:84 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | profiles.py:94 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | profiles.py:99 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | profiles.py:104 | [test_coverage] Function 'get_profile' has no corresponding test references |
| architecture | profiles.py:153 | [test_coverage] Function 'check_operation' has no corresponding test references |
| architecture | profiles.py:214 | [test_coverage] Function '_log_denial' has no corresponding test references |
| architecture | profiles.py:237 | [test_coverage] Function 'get_profiles_service' has no corresponding test references |
| architecture | refresh_rpc_client.py:69 | [test_coverage] Function '__repr__' has no corresponding test references |
| architecture | refresh_rpc_client.py:85 | [test_coverage] Function '__call__' has no corresponding test references |
| architecture | refresh_rpc_client.py:134 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | refresh_rpc_client.py:150 | [test_coverage] Function 'is_graph_stale' has no corresponding test references |
| architecture | refresh_rpc_client.py:164 | [test_coverage] Function 'trigger_refresh' has no corresponding test references |
| architecture | refresh_rpc_client.py:174 | [test_coverage] Function 'get_refresh_status' has no corresponding test references |
| architecture | refresh_rpc_client.py:183 | [test_coverage] Function '_invoke' has no corresponding test references |
| architecture | refresh_rpc_client.py:277 | [test_coverage] Function 'compute_affected_tests' has no corresponding test references |
| architecture | risk_scorer.py:44 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | risk_scorer.py:56 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | risk_scorer.py:61 | [test_coverage] Function 'compute_score' has no corresponding test references |
| architecture | risk_scorer.py:108 | [test_coverage] Function 'get_violation_count' has no corresponding test references |
| architecture | risk_scorer.py:125 | [test_coverage] Function '_trust_factor' has no corresponding test references |
| architecture | risk_scorer.py:130 | [test_coverage] Function '_operation_factor' has no corresponding test references |
| architecture | risk_scorer.py:141 | [test_coverage] Function '_resource_factor' has no corresponding test references |
| architecture | risk_scorer.py:152 | [test_coverage] Function '_violation_factor' has no corresponding test references |
| architecture | risk_scorer.py:161 | [test_coverage] Function '_session_age_factor' has no corresponding test references |
| architecture | risk_scorer.py:174 | [test_coverage] Function 'get_risk_scorer' has no corresponding test references |
| architecture | risk_scorer.py:182 | [test_coverage] Function 'reset_risk_scorer' has no corresponding test references |
| architecture | session_grants.py:30 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | session_grants.py:34 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | session_grants.py:39 | [test_coverage] Function 'request_grant' has no corresponding test references |
| architecture | session_grants.py:70 | [test_coverage] Function 'get_active_grants' has no corresponding test references |
| architecture | session_grants.py:78 | [test_coverage] Function 'has_grant' has no corresponding test references |
| architecture | session_grants.py:86 | [test_coverage] Function 'revoke_grants' has no corresponding test references |
| architecture | session_grants.py:100 | [test_coverage] Function '_row_to_grant' has no corresponding test references |
| architecture | session_grants.py:113 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | session_grants.py:125 | [test_coverage] Function 'get_session_grant_service' has no corresponding test references |
| architecture | session_grants.py:133 | [test_coverage] Function 'reset_session_grant_service' has no corresponding test references |
| architecture | sse_log_redaction.py:39 | [test_coverage] Function 'filter' has no corresponding test references |
| architecture | sse_log_redaction.py:58 | [test_coverage] Function '_scrub' has no corresponding test references |
| architecture | sse_log_redaction.py:64 | [test_coverage] Function 'install_token_redaction_filter' has no corresponding test references |
| architecture | sse_log_redaction.py:79 | [test_coverage] Function 'redact_token' has no corresponding test references |
| architecture | status.py:12 | [test_coverage] Function 'generate_token' has no corresponding test references |
| architecture | status.py:17 | [test_coverage] Function 'store_token' has no corresponding test references |
| architecture | status.py:52 | [test_coverage] Function 'validate_token' has no corresponding test references |
| architecture | status.py:80 | [test_coverage] Function 'lookup_token_failure' has no corresponding test references |
| architecture | status.py:100 | [test_coverage] Function 'cleanup_expired_tokens' has no corresponding test references |
| architecture | sync_points.py:35 | [test_coverage] Function '_parse_iso' has no corresponding test references |
| architecture | sync_points.py:45 | [test_coverage] Function '_load_registry' has no corresponding test references |
| architecture | sync_points.py:60 | [test_coverage] Function '_check_active_worktrees' has no corresponding test references |
| architecture | sync_points.py:81 | [test_coverage] Function 'get_sync_points_status' has no corresponding test references |
| architecture | teams.py:69 | [test_coverage] Function 'from_file' has no corresponding test references |
| architecture | teams.py:93 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | teams.py:129 | [test_coverage] Function 'get_agent' has no corresponding test references |
| architecture | teams.py:143 | [test_coverage] Function 'get_agents_with_capability' has no corresponding test references |
| architecture | teams.py:154 | [test_coverage] Function 'validate' has no corresponding test references |
| architecture | teams.py:180 | [test_coverage] Function 'get_teams_config' has no corresponding test references |
| architecture | teams.py:200 | [test_coverage] Function 'reset_teams_config' has no corresponding test references |
| architecture | telemetry.py:33 | [test_coverage] Function '_metrics_enabled' has no corresponding test references |
| architecture | telemetry.py:37 | [test_coverage] Function '_traces_enabled' has no corresponding test references |
| architecture | telemetry.py:41 | [test_coverage] Function '_prometheus_enabled' has no corresponding test references |
| architecture | telemetry.py:45 | [test_coverage] Function 'init_telemetry' has no corresponding test references |
| architecture | telemetry.py:74 | [test_coverage] Function '_init_metrics' has no corresponding test references |
| architecture | telemetry.py:138 | [test_coverage] Function '_init_traces' has no corresponding test references |
| architecture | telemetry.py:185 | [test_coverage] Function 'get_lock_meter' has no corresponding test references |
| architecture | telemetry.py:190 | [test_coverage] Function 'get_queue_meter' has no corresponding test references |
| architecture | telemetry.py:195 | [test_coverage] Function 'get_policy_meter' has no corresponding test references |
| architecture | telemetry.py:200 | [test_coverage] Function 'get_tracer' has no corresponding test references |
| architecture | telemetry.py:213 | [test_coverage] Function 'set_attribute' has no corresponding test references |
| architecture | telemetry.py:216 | [test_coverage] Function 'set_status' has no corresponding test references |
| architecture | telemetry.py:219 | [test_coverage] Function 'record_exception' has no corresponding test references |
| architecture | telemetry.py:222 | [test_coverage] Function '__enter__' has no corresponding test references |
| architecture | telemetry.py:225 | [test_coverage] Function '__exit__' has no corresponding test references |
| architecture | telemetry.py:232 | [test_coverage] Function 'start_span' has no corresponding test references |
| architecture | telemetry.py:245 | [test_coverage] Function 'get_prometheus_app' has no corresponding test references |
| architecture | telemetry.py:267 | [test_coverage] Function 'reset_telemetry' has no corresponding test references |
| architecture | watchdog.py:34 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | watchdog.py:55 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | watchdog.py:61 | [test_coverage] Function 'running' has no corresponding test references |
| architecture | watchdog.py:64 | [test_coverage] Function 'start' has no corresponding test references |
| architecture | watchdog.py:72 | [test_coverage] Function 'stop' has no corresponding test references |
| architecture | watchdog.py:84 | [test_coverage] Function 'run_once' has no corresponding test references |
| architecture | watchdog.py:93 | [test_coverage] Function '_loop' has no corresponding test references |
| architecture | watchdog.py:107 | [test_coverage] Function '_check_stale_agents' has no corresponding test references |
| architecture | watchdog.py:166 | [test_coverage] Function '_check_aging_approvals' has no corresponding test references |
| architecture | watchdog.py:207 | [test_coverage] Function '_check_expiring_locks' has no corresponding test references |
| architecture | watchdog.py:235 | [test_coverage] Function '_cleanup_expired_tokens' has no corresponding test references |
| architecture | watchdog.py:252 | [test_coverage] Function '_check_event_bus_health' has no corresponding test references |
| architecture | watchdog.py:275 | [test_coverage] Function '_check_vendor_health' has no corresponding test references |
| architecture | watchdog.py:346 | [test_coverage] Function '_emit_event' has no corresponding test references |
| architecture | watchdog.py:391 | [test_coverage] Function 'get_watchdog' has no corresponding test references |
| architecture | watchdog.py:399 | [test_coverage] Function 'reset_watchdog' has no corresponding test references |
| architecture | work_queue.py:30 | [test_coverage] Function '_ensure_instruments' has no corresponding test references |
| architecture | work_queue.py:88 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | work_queue.py:89 | [test_coverage] Function 'parse_dt' has no corresponding test references |
| architecture | work_queue.py:133 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | work_queue.py:166 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | work_queue.py:187 | [test_coverage] Function 'from_dict' has no corresponding test references |
| architecture | work_queue.py:201 | [test_coverage] Function '__init__' has no corresponding test references |
| architecture | work_queue.py:205 | [test_coverage] Function 'db' has no corresponding test references |
| architecture | work_queue.py:210 | [test_coverage] Function '_resolve_trust_level' has no corresponding test references |
| architecture | work_queue.py:225 | [test_coverage] Function 'claim' has no corresponding test references |
| architecture | work_queue.py:442 | [test_coverage] Function 'complete' has no corresponding test references |
| architecture | work_queue.py:593 | [test_coverage] Function 'submit' has no corresponding test references |
| architecture | work_queue.py:729 | [test_coverage] Function 'get_pending' has no corresponding test references |
| architecture | work_queue.py:753 | [test_coverage] Function 'get_task' has no corresponding test references |
| architecture | work_queue.py:765 | [test_coverage] Function 'get_my_tasks' has no corresponding test references |
| architecture | work_queue.py:789 | [test_coverage] Function 'cancel_task_convention' has no corresponding test references |
| architecture | work_queue.py:822 | [test_coverage] Function 'get_work_queue_service' has no corresponding test references |
| architecture | work_queue.py:830 | [test_coverage] Function 'reset_instruments' has no corresponding test references |
| architecture | worktrees_view.py:24 | [test_coverage] Function '_repo_root' has no corresponding test references |
| architecture | worktrees_view.py:29 | [test_coverage] Function '_parse_dt' has no corresponding test references |
| architecture | worktrees_view.py:41 | [test_coverage] Function 'get_active_worktrees' has no corresponding test references |
| architecture | __init__.py:1 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1 | [orphan] 'agents_config' is unreachable from any entrypoint or test |
| architecture | approval.py:1 | [orphan] 'approval' is unreachable from any entrypoint or test |
| architecture | assurance.py:1 | [orphan] 'assurance' is unreachable from any entrypoint or test |
| architecture | audit.py:1 | [orphan] 'audit' is unreachable from any entrypoint or test |
| architecture | config.py:1 | [orphan] 'config' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:1 | [orphan] 'coordination_api' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:1 | [orphan] 'coordination_cli' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1 | [orphan] 'coordination_mcp' is unreachable from any entrypoint or test |
| architecture | db.py:1 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:1 | [orphan] 'db_postgres' is unreachable from any entrypoint or test |
| architecture | discovery.py:1 | [orphan] 'discovery' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:1 | [orphan] 'docker_manager' is unreachable from any entrypoint or test |
| architecture | event_bus.py:1 | [orphan] 'event_bus' is unreachable from any entrypoint or test |
| architecture | event_stream.py:1 | [orphan] 'event_stream' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:1 | [orphan] 'feature_flags' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:1 | [orphan] 'feature_registry' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:1 | [orphan] 'git_adapter' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:1 | [orphan] 'github_coordination' is unreachable from any entrypoint or test |
| architecture | guardrails.py:1 | [orphan] 'guardrails' is unreachable from any entrypoint or test |
| architecture | handoffs.py:1 | [orphan] 'handoffs' is unreachable from any entrypoint or test |
| architecture | help_service.py:1 | [orphan] 'help_service' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1 | [orphan] 'http_proxy' is unreachable from any entrypoint or test |
| architecture | issue_service.py:1 | [orphan] 'issue_service' is unreachable from any entrypoint or test |
| architecture | kanban_viz_files.py:1 | [orphan] 'kanban_viz_files' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:1 | [orphan] 'langfuse_middleware' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:1 | [orphan] 'langfuse_tracing' is unreachable from any entrypoint or test |
| architecture | locks.py:1 | [orphan] 'locks' is unreachable from any entrypoint or test |
| architecture | memory.py:1 | [orphan] 'memory' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:1 | [orphan] 'merge_queue' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1 | [orphan] 'merge_train' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:1 | [orphan] 'merge_train_service' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:1 | [orphan] 'merge_train_types' is unreachable from any entrypoint or test |
| architecture | migrations.py:1 | [orphan] 'migrations' is unreachable from any entrypoint or test |
| architecture | network_policies.py:1 | [orphan] 'network_policies' is unreachable from any entrypoint or test |
| architecture | notifications/__init__.py:1 | [orphan] 'notifications' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:1 | [orphan] 'notifications.base' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:1 | [orphan] 'notifications.gmail' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:1 | [orphan] 'notifications.notifier' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:1 | [orphan] 'notifications.relay' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:1 | [orphan] 'notifications.telegram' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:1 | [orphan] 'notifications.templates' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:1 | [orphan] 'notifications.webhook' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:1 | [orphan] 'policy_engine' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:1 | [orphan] 'policy_sync' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:1 | [orphan] 'port_allocator' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:1 | [orphan] 'profile_loader' is unreachable from any entrypoint or test |
| architecture | profiles.py:1 | [orphan] 'profiles' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:1 | [orphan] 'refresh_rpc_client' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:1 | [orphan] 'risk_scorer' is unreachable from any entrypoint or test |
| architecture | session_grants.py:1 | [orphan] 'session_grants' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:1 | [orphan] 'sse_log_redaction' is unreachable from any entrypoint or test |
| architecture | status.py:1 | [orphan] 'status' is unreachable from any entrypoint or test |
| architecture | sync_points.py:1 | [orphan] 'sync_points' is unreachable from any entrypoint or test |
| architecture | teams.py:1 | [orphan] 'teams' is unreachable from any entrypoint or test |
| architecture | telemetry.py:1 | [orphan] 'telemetry' is unreachable from any entrypoint or test |
| architecture | watchdog.py:1 | [orphan] 'watchdog' is unreachable from any entrypoint or test |
| architecture | work_queue.py:1 | [orphan] 'work_queue' is unreachable from any entrypoint or test |
| architecture | worktrees_view.py:1 | [orphan] 'worktrees_view' is unreachable from any entrypoint or test |
| architecture | agents_config.py:322 | [orphan] 'PollConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:340 | [orphan] 'ModeConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:349 | [orphan] 'CliConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:364 | [orphan] 'SdkConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:381 | [orphan] 'AgentEntry' is unreachable from any entrypoint or test |
| architecture | agents_config.py:404 | [orphan] 'EscalationConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:418 | [orphan] 'ArchetypeConfig' is unreachable from any entrypoint or test |
| architecture | agents_config.py:432 | [orphan] 'PhaseMappingEntry' is unreachable from any entrypoint or test |
| architecture | agents_config.py:446 | [orphan] 'ResolvedArchetype' is unreachable from any entrypoint or test |
| architecture | agents_config.py:460 | [orphan] 'ProviderModelMappingError' is unreachable from any entrypoint or test |
| architecture | approval.py:15 | [orphan] 'ApprovalRequest' is unreachable from any entrypoint or test |
| architecture | approval.py:32 | [orphan] 'ApprovalService' is unreachable from any entrypoint or test |
| architecture | audit.py:18 | [orphan] 'AuditEntry' is unreachable from any entrypoint or test |
| architecture | audit.py:56 | [orphan] 'AuditResult' is unreachable from any entrypoint or test |
| architecture | audit.py:72 | [orphan] 'AuditService' is unreachable from any entrypoint or test |
| architecture | audit.py:179 | [orphan] 'AuditTimer' is unreachable from any entrypoint or test |
| architecture | config.py:50 | [orphan] 'SupabaseConfig' is unreachable from any entrypoint or test |
| architecture | config.py:75 | [orphan] 'AgentConfig' is unreachable from any entrypoint or test |
| architecture | config.py:99 | [orphan] 'LockConfig' is unreachable from any entrypoint or test |
| architecture | config.py:113 | [orphan] 'PostgresConfig' is unreachable from any entrypoint or test |
| architecture | config.py:130 | [orphan] 'DatabaseConfig' is unreachable from any entrypoint or test |
| architecture | config.py:145 | [orphan] 'GuardrailsConfig' is unreachable from any entrypoint or test |
| architecture | config.py:165 | [orphan] 'ProfilesConfig' is unreachable from any entrypoint or test |
| architecture | config.py:189 | [orphan] 'AuditConfig' is unreachable from any entrypoint or test |
| architecture | config.py:204 | [orphan] 'NetworkPolicyConfig' is unreachable from any entrypoint or test |
| architecture | config.py:217 | [orphan] 'PolicyEngineConfig' is unreachable from any entrypoint or test |
| architecture | config.py:241 | [orphan] 'OpenBaoConfig' is unreachable from any entrypoint or test |
| architecture | config.py:323 | [orphan] 'ObservabilityConfig' is unreachable from any entrypoint or test |
| architecture | config.py:340 | [orphan] 'LangfuseConfig' is unreachable from any entrypoint or test |
| architecture | config.py:374 | [orphan] 'PortAllocatorConfig' is unreachable from any entrypoint or test |
| architecture | config.py:393 | [orphan] 'ApiConfig' is unreachable from any entrypoint or test |
| architecture | config.py:448 | [orphan] 'ApprovalConfig' is unreachable from any entrypoint or test |
| architecture | config.py:471 | [orphan] 'PolicySyncConfig' is unreachable from any entrypoint or test |
| architecture | config.py:493 | [orphan] 'RiskScoringConfig' is unreachable from any entrypoint or test |
| architecture | config.py:520 | [orphan] 'SessionGrantsConfig' is unreachable from any entrypoint or test |
| architecture | config.py:574 | [orphan] 'Config' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:31 | [orphan] 'LockAcquireRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:40 | [orphan] 'LockReleaseRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:45 | [orphan] 'MemoryStoreRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:56 | [orphan] 'MemoryQueryRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:63 | [orphan] 'WorkClaimRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:69 | [orphan] 'WorkCompleteRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:77 | [orphan] 'WorkSubmitRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:86 | [orphan] 'WorkGetTaskRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:90 | [orphan] 'IssueCreateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:101 | [orphan] 'IssueListRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:110 | [orphan] 'IssueUpdateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:121 | [orphan] 'IssueCloseRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:127 | [orphan] 'IssueCommentRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:132 | [orphan] 'GuardrailsCheckRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:137 | [orphan] 'AuditQueryParams' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:143 | [orphan] 'HandoffWriteRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:155 | [orphan] 'HandoffReadRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:160 | [orphan] 'PolicyCheckRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:168 | [orphan] 'PolicyValidateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:172 | [orphan] 'PortAllocateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:176 | [orphan] 'PortReleaseRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:180 | [orphan] 'ApprovalDecisionRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:186 | [orphan] 'PolicyRollbackRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:190 | [orphan] 'FeatureRegisterRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:200 | [orphan] 'FeatureDeregisterRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:205 | [orphan] 'FeatureConflictsRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:210 | [orphan] 'StatusReportRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:233 | [orphan] 'ResolveForPhaseRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:255 | [orphan] 'MergeQueueEnqueueRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:260 | [orphan] 'DiscoveryRegisterRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:270 | [orphan] 'DiscoveryHeartbeatRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:276 | [orphan] 'DiscoveryCleanupRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:282 | [orphan] 'GenEvalValidateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:286 | [orphan] 'GenEvalCreateRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:294 | [orphan] 'GenEvalRunRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:300 | [orphan] 'IssueSearchRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:307 | [orphan] 'IssueReadyRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:314 | [orphan] 'PermissionRequestRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:321 | [orphan] 'ApprovalSubmitRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:330 | [orphan] 'MergeTrainEjectRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:335 | [orphan] 'MergeTrainReportResultRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:341 | [orphan] 'AffectedTestsRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:347 | [orphan] 'EventsAuthRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:352 | [orphan] 'PatchLabelsRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:357 | [orphan] 'KickAgentRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:371 | [orphan] 'SavedViewRequest' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:375 | [orphan] 'KanbanAuditRequest' is unreachable from any entrypoint or test |
| architecture | db.py:25 | [orphan] 'DatabaseClient' is unreachable from any entrypoint or test |
| architecture | db.py:73 | [orphan] 'SupabaseClient' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:78 | [orphan] 'DirectPostgresClient' is unreachable from any entrypoint or test |
| architecture | discovery.py:20 | [orphan] 'AgentInfo' is unreachable from any entrypoint or test |
| architecture | discovery.py:61 | [orphan] 'RegisterResult' is unreachable from any entrypoint or test |
| architecture | discovery.py:76 | [orphan] 'DiscoverResult' is unreachable from any entrypoint or test |
| architecture | discovery.py:88 | [orphan] 'HeartbeatResult' is unreachable from any entrypoint or test |
| architecture | discovery.py:105 | [orphan] 'CleanupResult' is unreachable from any entrypoint or test |
| architecture | discovery.py:121 | [orphan] 'DiscoveryService' is unreachable from any entrypoint or test |
| architecture | event_bus.py:37 | [orphan] 'CoordinatorEvent' is unreachable from any entrypoint or test |
| architecture | event_bus.py:110 | [orphan] 'EventBusService' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:61 | [orphan] 'FlagsConfigError' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:69 | [orphan] 'InvalidFlagNameError' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:79 | [orphan] 'Flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:153 | [orphan] 'FeatureFlagService' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:26 | [orphan] 'Feasibility' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:35 | [orphan] 'Feature' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:75 | [orphan] 'RegisterResult' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:94 | [orphan] 'DeregisterResult' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:113 | [orphan] 'ConflictReport' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:124 | [orphan] 'FeatureRegistryService' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:51 | [orphan] 'InvalidRefNameError' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:55 | [orphan] 'GitVersionError' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:65 | [orphan] 'MergeTreeResult' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:79 | [orphan] 'FastForwardResult' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:88 | [orphan] 'ChangedFiles' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:102 | [orphan] 'GitAdapter' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:176 | [orphan] 'SubprocessGitAdapter' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:30 | [orphan] 'BranchInfo' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:61 | [orphan] 'LabelLock' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:69 | [orphan] 'WebhookSyncResult' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:89 | [orphan] 'GitHubCoordinationService' is unreachable from any entrypoint or test |
| architecture | guardrails.py:140 | [orphan] 'GuardrailPattern' is unreachable from any entrypoint or test |
| architecture | guardrails.py:161 | [orphan] 'GuardrailViolation' is unreachable from any entrypoint or test |
| architecture | guardrails.py:184 | [orphan] 'GuardrailResult' is unreachable from any entrypoint or test |
| architecture | guardrails.py:203 | [orphan] 'GuardrailsService' is unreachable from any entrypoint or test |
| architecture | handoffs.py:22 | [orphan] 'HandoffDocument' is unreachable from any entrypoint or test |
| architecture | handoffs.py:59 | [orphan] 'WriteHandoffResult' is unreachable from any entrypoint or test |
| architecture | handoffs.py:80 | [orphan] 'ReadHandoffResult' is unreachable from any entrypoint or test |
| architecture | handoffs.py:93 | [orphan] 'HandoffService' is unreachable from any entrypoint or test |
| architecture | help_service.py:20 | [orphan] 'HelpTopic' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:92 | [orphan] 'HttpProxyConfig' is unreachable from any entrypoint or test |
| architecture | issue_service.py:47 | [orphan] 'Issue' is unreachable from any entrypoint or test |
| architecture | issue_service.py:154 | [orphan] 'Comment' is unreachable from any entrypoint or test |
| architecture | issue_service.py:186 | [orphan] 'IssueService' is unreachable from any entrypoint or test |
| architecture | kanban_viz_files.py:107 | [orphan] 'SchemaValidationError' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:29 | [orphan] 'LangfuseTracingMiddleware' is unreachable from any entrypoint or test |
| architecture | locks.py:89 | [orphan] 'Lock' is unreachable from any entrypoint or test |
| architecture | locks.py:119 | [orphan] 'LockResult' is unreachable from any entrypoint or test |
| architecture | locks.py:149 | [orphan] 'LockService' is unreachable from any entrypoint or test |
| architecture | memory.py:20 | [orphan] 'EpisodicMemory' is unreachable from any entrypoint or test |
| architecture | memory.py:56 | [orphan] 'MemoryResult' is unreachable from any entrypoint or test |
| architecture | memory.py:75 | [orphan] 'RecallResult' is unreachable from any entrypoint or test |
| architecture | memory.py:89 | [orphan] 'MemoryService' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:37 | [orphan] 'MergeStatus' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:49 | [orphan] 'PreMergeCheckResult' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:60 | [orphan] 'MergeQueueEntry' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:88 | [orphan] 'MergeQueueService' is unreachable from any entrypoint or test |
| architecture | merge_train.py:69 | [orphan] 'TrainAuthorizationError' is unreachable from any entrypoint or test |
| architecture | merge_train.py:77 | [orphan] 'TrainDeadlockError' is unreachable from any entrypoint or test |
| architecture | merge_train.py:92 | [orphan] 'PartitionResult' is unreachable from any entrypoint or test |
| architecture | merge_train.py:622 | [orphan] 'EjectResult' is unreachable from any entrypoint or test |
| architecture | merge_train.py:851 | [orphan] '_MergeNode' is unreachable from any entrypoint or test |
| architecture | merge_train.py:868 | [orphan] 'WaveMergeResult' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1121 | [orphan] 'CrashRecoveryResult' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:115 | [orphan] 'MergeTrainService' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:419 | [orphan] 'MergeTrainSweeper' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:58 | [orphan] 'MergeTrainStatus' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:98 | [orphan] 'TrainEntry' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:151 | [orphan] 'TrainPartition' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:169 | [orphan] 'CrossPartitionEntry' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:183 | [orphan] 'TrainComposition' is unreachable from any entrypoint or test |
| architecture | network_policies.py:15 | [orphan] 'AccessDecision' is unreachable from any entrypoint or test |
| architecture | network_policies.py:33 | [orphan] 'NetworkPolicyService' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:11 | [orphan] 'NotificationChannel' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:29 | [orphan] 'GmailChannelFake' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:46 | [orphan] 'GmailChannel' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:30 | [orphan] 'NotifierService' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:20 | [orphan] 'TelegramChannel' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:18 | [orphan] 'WebhookChannel' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:83 | [orphan] 'PolicyDecision' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:101 | [orphan] 'ValidationResult' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:108 | [orphan] 'NativePolicyEngine' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:454 | [orphan] 'CedarPolicyEngine' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:17 | [orphan] 'PolicySyncService' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:37 | [orphan] 'PgListenNotifyPolicySyncService' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:24 | [orphan] 'PortAllocation' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:52 | [orphan] 'PortAllocatorService' is unreachable from any entrypoint or test |
| architecture | profiles.py:20 | [orphan] 'AgentProfile' is unreachable from any entrypoint or test |
| architecture | profiles.py:53 | [orphan] 'ProfileResult' is unreachable from any entrypoint or test |
| architecture | profiles.py:77 | [orphan] 'OperationCheck' is unreachable from any entrypoint or test |
| architecture | profiles.py:91 | [orphan] 'ProfilesService' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:59 | [orphan] 'RefreshClientUnavailable' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:78 | [orphan] '_Runner' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:124 | [orphan] 'RefreshRpcClient' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:33 | [orphan] 'RiskScore' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:41 | [orphan] 'RiskScorer' is unreachable from any entrypoint or test |
| architecture | session_grants.py:14 | [orphan] 'PermissionGrant' is unreachable from any entrypoint or test |
| architecture | session_grants.py:27 | [orphan] 'SessionGrantService' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:31 | [orphan] '_TokenRedactionFilter' is unreachable from any entrypoint or test |
| architecture | teams.py:48 | [orphan] 'AgentDefinition' is unreachable from any entrypoint or test |
| architecture | teams.py:58 | [orphan] 'TeamsConfig' is unreachable from any entrypoint or test |
| architecture | telemetry.py:210 | [orphan] '_NoOpSpan' is unreachable from any entrypoint or test |
| architecture | watchdog.py:31 | [orphan] 'WatchdogService' is unreachable from any entrypoint or test |
| architecture | work_queue.py:68 | [orphan] 'Task' is unreachable from any entrypoint or test |
| architecture | work_queue.py:120 | [orphan] 'ClaimResult' is unreachable from any entrypoint or test |
| architecture | work_queue.py:157 | [orphan] 'CompleteResult' is unreachable from any entrypoint or test |
| architecture | work_queue.py:180 | [orphan] 'SubmitResult' is unreachable from any entrypoint or test |
| architecture | work_queue.py:198 | [orphan] 'WorkQueueService' is unreachable from any entrypoint or test |
| architecture | agents_config.py:463 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | agents_config.py:618 | [orphan] '_resolve_api_key_from_openbao' is unreachable from any entrypoint or test |
| architecture | agents_config.py:669 | [orphan] 'get_api_key_identities' is unreachable from any entrypoint or test |
| architecture | agents_config.py:726 | [orphan] 'get_mcp_env' is unreachable from any entrypoint or test |
| architecture | agents_config.py:780 | [orphan] 'get_agent_config' is unreachable from any entrypoint or test |
| architecture | agents_config.py:788 | [orphan] 'reset_agents_config' is unreachable from any entrypoint or test |
| architecture | agents_config.py:864 | [orphan] 'get_agent_isolation' is unreachable from any entrypoint or test |
| architecture | agents_config.py:880 | [orphan] '_default_archetypes_path' is unreachable from any entrypoint or test |
| architecture | agents_config.py:884 | [orphan] 'load_archetypes_config' is unreachable from any entrypoint or test |
| architecture | agents_config.py:967 | [orphan] 'get_archetype' is unreachable from any entrypoint or test |
| architecture | agents_config.py:981 | [orphan] 'get_phase_mapping' is unreachable from any entrypoint or test |
| architecture | agents_config.py:993 | [orphan] 'reset_archetypes_config' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1001 | [orphan] '_normalize_provider_model_map' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1028 | [orphan] 'get_provider_model_map' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1035 | [orphan] 'resolve_provider_model' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1079 | [orphan] 'compose_prompt' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1095 | [orphan] '_unique_dir_prefixes' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1114 | [orphan] 'resolve_model' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1143 | [orphan] '_finalize' is unreachable from any entrypoint or test |
| architecture | agents_config.py:1196 | [orphan] 'resolve_archetype_for_phase' is unreachable from any entrypoint or test |
| architecture | approval.py:35 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | approval.py:39 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | approval.py:44 | [orphan] 'submit_request' is unreachable from any entrypoint or test |
| architecture | approval.py:89 | [orphan] 'check_request' is unreachable from any entrypoint or test |
| architecture | approval.py:99 | [orphan] 'decide_request' is unreachable from any entrypoint or test |
| architecture | approval.py:137 | [orphan] 'expire_stale_requests' is unreachable from any entrypoint or test |
| architecture | approval.py:154 | [orphan] 'list_pending' is unreachable from any entrypoint or test |
| architecture | approval.py:166 | [orphan] '_row_to_request' is unreachable from any entrypoint or test |
| architecture | approval.py:186 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | approval.py:207 | [orphan] 'reset_approval_service' is unreachable from any entrypoint or test |
| architecture | audit.py:34 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | audit.py:64 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | audit.py:75 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | audit.py:79 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | audit.py:84 | [orphan] 'log_operation' is unreachable from any entrypoint or test |
| architecture | audit.py:124 | [orphan] '_insert_audit_entry' is unreachable from any entrypoint or test |
| architecture | audit.py:132 | [orphan] 'query' is unreachable from any entrypoint or test |
| architecture | audit.py:174 | [orphan] 'timed' is unreachable from any entrypoint or test |
| architecture | audit.py:182 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | audit.py:187 | [orphan] '__aenter__' is unreachable from any entrypoint or test |
| architecture | audit.py:191 | [orphan] '__aexit__' is unreachable from any entrypoint or test |
| architecture | config.py:58 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:83 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:106 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:121 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:137 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:152 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:173 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:196 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:210 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:226 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:263 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:274 | [orphan] 'is_enabled' is unreachable from any entrypoint or test |
| architecture | config.py:278 | [orphan] 'create_client' is unreachable from any entrypoint or test |
| architecture | config.py:331 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:360 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:383 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:405 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:610 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | config.py:673 | [orphan] 'reset_config' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:385 | [orphan] 'verify_api_key' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:495 | [orphan] 'create_coordination_api' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:517 | [orphan] 'lifespan' is unreachable from any entrypoint or test |
| architecture | coordination_api.py:3117 | [orphan] 'main' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:22 | [orphan] '_run' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:27 | [orphan] '_output' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:46 | [orphan] '_print_dict' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:70 | [orphan] '_error' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:81 | [orphan] 'cmd_health' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:108 | [orphan] 'cmd_feature_register' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:131 | [orphan] 'cmd_feature_deregister' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:148 | [orphan] 'cmd_feature_show' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:169 | [orphan] 'cmd_feature_list' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:189 | [orphan] 'cmd_feature_conflicts' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:210 | [orphan] 'cmd_mq_enqueue' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:229 | [orphan] 'cmd_mq_status' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:248 | [orphan] 'cmd_mq_next' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:265 | [orphan] 'cmd_mq_check' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:280 | [orphan] 'cmd_mq_merged' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:289 | [orphan] 'cmd_mq_remove' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:301 | [orphan] 'cmd_lock_acquire' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:322 | [orphan] 'cmd_lock_release' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:338 | [orphan] 'cmd_lock_status' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:361 | [orphan] 'cmd_work_submit' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:378 | [orphan] 'cmd_work_claim' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:398 | [orphan] 'cmd_work_complete' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:418 | [orphan] 'cmd_work_get' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:441 | [orphan] 'cmd_handoff_write' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:457 | [orphan] 'cmd_handoff_read' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:481 | [orphan] 'cmd_memory_store' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:499 | [orphan] 'cmd_memory_query' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:524 | [orphan] 'cmd_guardrails_check' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:545 | [orphan] 'cmd_audit_query' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:571 | [orphan] 'cmd_help' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:648 | [orphan] 'build_parser' is unreachable from any entrypoint or test |
| architecture | coordination_cli.py:834 | [orphan] 'main' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:67 | [orphan] 'get_agent_id' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:72 | [orphan] 'get_agent_type' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:83 | [orphan] 'acquire_lock' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:137 | [orphan] 'release_lock' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:165 | [orphan] 'check_locks' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:201 | [orphan] 'get_work' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:244 | [orphan] 'complete_work' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:292 | [orphan] 'submit_work' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:357 | [orphan] 'get_task' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:413 | [orphan] 'issue_create' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:491 | [orphan] 'issue_list' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:548 | [orphan] 'issue_show' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:575 | [orphan] 'issue_update' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:643 | [orphan] 'issue_close' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:696 | [orphan] 'issue_comment' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:731 | [orphan] 'issue_ready' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:773 | [orphan] 'issue_blocked' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:801 | [orphan] 'issue_search' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:844 | [orphan] 'write_handoff' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:907 | [orphan] 'read_handoff' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:972 | [orphan] 'register_session' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1018 | [orphan] 'discover_agents' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1071 | [orphan] 'heartbeat' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1095 | [orphan] 'cleanup_dead_agents' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1134 | [orphan] 'remember' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1189 | [orphan] 'recall' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1249 | [orphan] 'check_guardrails' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1320 | [orphan] 'get_my_profile' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1357 | [orphan] 'get_agent_dispatch_configs' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1381 | [orphan] 'query_audit' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1436 | [orphan] 'check_policy' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1483 | [orphan] 'validate_cedar_policy' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1527 | [orphan] 'allocate_ports' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1576 | [orphan] 'release_ports' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1603 | [orphan] 'ports_status' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1648 | [orphan] 'request_approval' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1680 | [orphan] 'check_approval' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1706 | [orphan] 'list_policy_versions' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1726 | [orphan] 'request_permission' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1759 | [orphan] 'register_feature' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1815 | [orphan] 'deregister_feature' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1850 | [orphan] 'get_feature' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1884 | [orphan] 'list_active_features' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1914 | [orphan] 'analyze_feature_conflicts' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1955 | [orphan] 'enqueue_merge' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:1996 | [orphan] 'get_merge_queue' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2025 | [orphan] 'get_next_merge' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2054 | [orphan] 'run_pre_merge_checks' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2084 | [orphan] 'mark_merged' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2106 | [orphan] 'remove_from_merge_queue' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2131 | [orphan] '_current_trust_level' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2146 | [orphan] 'compose_train' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2205 | [orphan] 'eject_from_train' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2263 | [orphan] 'get_train_status' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2296 | [orphan] 'report_spec_result' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2339 | [orphan] 'affected_tests' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2377 | [orphan] 'report_status' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2478 | [orphan] 'help' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2810 | [orphan] 'list_scenarios' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2854 | [orphan] 'validate_scenario' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2889 | [orphan] 'create_scenario' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:2940 | [orphan] 'run_gen_eval' is unreachable from any entrypoint or test |
| architecture | coordination_mcp.py:3109 | [orphan] 'main' is unreachable from any entrypoint or test |
| architecture | db.py:32 | [orphan] 'rpc' is unreachable from any entrypoint or test |
| architecture | db.py:36 | [orphan] 'query' is unreachable from any entrypoint or test |
| architecture | db.py:45 | [orphan] 'insert' is unreachable from any entrypoint or test |
| architecture | db.py:54 | [orphan] 'update' is unreachable from any entrypoint or test |
| architecture | db.py:64 | [orphan] 'delete' is unreachable from any entrypoint or test |
| architecture | db.py:68 | [orphan] 'close' is unreachable from any entrypoint or test |
| architecture | db.py:80 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | db.py:85 | [orphan] 'config' is unreachable from any entrypoint or test |
| architecture | db.py:96 | [orphan] 'client' is unreachable from any entrypoint or test |
| architecture | db.py:101 | [orphan] '_headers' is unreachable from any entrypoint or test |
| architecture | db.py:109 | [orphan] 'rpc' is unreachable from any entrypoint or test |
| architecture | db.py:130 | [orphan] 'query' is unreachable from any entrypoint or test |
| architecture | db.py:154 | [orphan] 'insert' is unreachable from any entrypoint or test |
| architecture | db.py:184 | [orphan] 'update' is unreachable from any entrypoint or test |
| architecture | db.py:217 | [orphan] 'delete' is unreachable from any entrypoint or test |
| architecture | db.py:237 | [orphan] 'close' is unreachable from any entrypoint or test |
| architecture | db.py:279 | [orphan] 'close_db' is unreachable from any entrypoint or test |
| architecture | db.py:287 | [orphan] 'reset_db' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:25 | [orphan] '_coerce_filter_value' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:46 | [orphan] '_validate_identifier' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:54 | [orphan] '_validate_select_clause' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:66 | [orphan] '_serialize_for_asyncpg' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:85 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:89 | [orphan] '_get_pool' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:98 | [orphan] 'rpc' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:128 | [orphan] 'query' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:217 | [orphan] 'insert' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:245 | [orphan] 'update' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:287 | [orphan] 'delete' is unreachable from any entrypoint or test |
| architecture | db_postgres.py:309 | [orphan] 'close' is unreachable from any entrypoint or test |
| architecture | discovery.py:38 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:39 | [orphan] 'parse_dt' is unreachable from any entrypoint or test |
| architecture | discovery.py:68 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:82 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:96 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:113 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | discovery.py:124 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | discovery.py:128 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | discovery.py:133 | [orphan] 'register' is unreachable from any entrypoint or test |
| architecture | discovery.py:184 | [orphan] 'discover' is unreachable from any entrypoint or test |
| architecture | discovery.py:208 | [orphan] 'heartbeat' is unreachable from any entrypoint or test |
| architecture | discovery.py:266 | [orphan] 'cleanup_dead_agents' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:29 | [orphan] 'is_colima_installed' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:34 | [orphan] 'is_colima_running' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:47 | [orphan] '_ensure_colima_vm' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:100 | [orphan] 'detect_runtime' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:168 | [orphan] 'is_container_running' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:182 | [orphan] 'start_container' is unreachable from any entrypoint or test |
| architecture | docker_manager.py:267 | [orphan] 'wait_for_healthy' is unreachable from any entrypoint or test |
| architecture | event_bus.py:50 | [orphan] '__post_init__' is unreachable from any entrypoint or test |
| architecture | event_bus.py:57 | [orphan] 'to_json' is unreachable from any entrypoint or test |
| architecture | event_bus.py:71 | [orphan] 'from_json' is unreachable from any entrypoint or test |
| architecture | event_bus.py:119 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | event_bus.py:140 | [orphan] 'running' is unreachable from any entrypoint or test |
| architecture | event_bus.py:144 | [orphan] 'failed' is unreachable from any entrypoint or test |
| architecture | event_bus.py:148 | [orphan] 'on_event' is unreachable from any entrypoint or test |
| architecture | event_bus.py:159 | [orphan] 'off_event' is unreachable from any entrypoint or test |
| architecture | event_bus.py:188 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | event_bus.py:206 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | event_bus.py:225 | [orphan] 'restart' is unreachable from any entrypoint or test |
| architecture | event_bus.py:230 | [orphan] '_listen_loop' is unreachable from any entrypoint or test |
| architecture | event_bus.py:262 | [orphan] '_connect_and_listen' is unreachable from any entrypoint or test |
| architecture | event_bus.py:275 | [orphan] '_notification_handler' is unreachable from any entrypoint or test |
| architecture | event_bus.py:306 | [orphan] '_dispatch' is unreachable from any entrypoint or test |
| architecture | event_bus.py:329 | [orphan] '_safe_callback' is unreachable from any entrypoint or test |
| architecture | event_bus.py:351 | [orphan] 'reset_event_bus' is unreachable from any entrypoint or test |
| architecture | event_stream.py:64 | [orphan] 'mint_events_token' is unreachable from any entrypoint or test |
| architecture | event_stream.py:153 | [orphan] '_prune_nonces' is unreachable from any entrypoint or test |
| architecture | event_stream.py:271 | [orphan] '_on_task_event' is unreachable from any entrypoint or test |
| architecture | event_stream.py:276 | [orphan] '_on_audit_event' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:89 | [orphan] 'is_enabled' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:92 | [orphan] 'to_yaml_dict' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:106 | [orphan] 'from_yaml_dict' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:107 | [orphan] '_parse' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:129 | [orphan] 'normalize_flag_name' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:164 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:173 | [orphan] 'load' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:183 | [orphan] '_load_unlocked' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:242 | [orphan] '_get_registry' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:250 | [orphan] 'resolve_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:283 | [orphan] 'is_enabled' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:287 | [orphan] 'check_undeclared_env_vars' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:308 | [orphan] 'create_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:347 | [orphan] 'enable_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:363 | [orphan] '_write_registry' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:393 | [orphan] 'get_feature_flag_service' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:402 | [orphan] 'reset_feature_flag_service' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:409 | [orphan] 'create_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:417 | [orphan] 'enable_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:421 | [orphan] 'resolve_flag' is unreachable from any entrypoint or test |
| architecture | feature_flags.py:425 | [orphan] 'is_enabled' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:51 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:52 | [orphan] 'parse_dt' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:84 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:103 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:131 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:135 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:140 | [orphan] 'register' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:198 | [orphan] 'deregister' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:233 | [orphan] 'get_feature' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:248 | [orphan] 'get_active_features' is unreachable from any entrypoint or test |
| architecture | feature_registry.py:260 | [orphan] 'analyze_conflicts' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:108 | [orphan] 'create_speculative_ref' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:115 | [orphan] 'delete_speculative_refs' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:117 | [orphan] 'fast_forward_main' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:119 | [orphan] 'get_changed_files' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:121 | [orphan] 'list_speculative_refs' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:129 | [orphan] 'validate_speculative_ref_name' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:143 | [orphan] 'validate_branch_name' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:159 | [orphan] 'parse_git_version' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:183 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:189 | [orphan] '_ensure_git_version' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:212 | [orphan] '_run' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:225 | [orphan] 'create_speculative_ref' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:317 | [orphan] 'delete_speculative_refs' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:342 | [orphan] 'fast_forward_main' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:372 | [orphan] 'get_changed_files' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:406 | [orphan] 'list_speculative_refs' is unreachable from any entrypoint or test |
| architecture | git_adapter.py:426 | [orphan] '_parse_conflict_files' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:39 | [orphan] 'parse' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:79 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:92 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:96 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:101 | [orphan] 'parse_lock_labels' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:121 | [orphan] 'parse_branch' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:132 | [orphan] 'sync_label_locks' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:212 | [orphan] 'sync_branch_tracking' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:265 | [orphan] 'handle_push_webhook' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:294 | [orphan] 'handle_issues_webhook' is unreachable from any entrypoint or test |
| architecture | github_coordination.py:328 | [orphan] 'get_github_coordination_service' is unreachable from any entrypoint or test |
| architecture | guardrails.py:27 | [orphan] '_ensure_guardrail_instruments' is unreachable from any entrypoint or test |
| architecture | guardrails.py:49 | [orphan] 'reset_guardrail_instruments' is unreachable from any entrypoint or test |
| architecture | guardrails.py:150 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | guardrails.py:172 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | guardrails.py:192 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | guardrails.py:206 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | guardrails.py:212 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | guardrails.py:217 | [orphan] '_load_patterns' is unreachable from any entrypoint or test |
| architecture | guardrails.py:243 | [orphan] 'check_operation' is unreachable from any entrypoint or test |
| architecture | handoffs.py:37 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | handoffs.py:67 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | handoffs.py:86 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | handoffs.py:96 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | handoffs.py:100 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | handoffs.py:105 | [orphan] 'write' is unreachable from any entrypoint or test |
| architecture | handoffs.py:187 | [orphan] 'read' is unreachable from any entrypoint or test |
| architecture | handoffs.py:226 | [orphan] 'get_recent' is unreachable from any entrypoint or test |
| architecture | help_service.py:40 | [orphan] '_register' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:41 | [orphan] '_validate_url' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:104 | [orphan] 'from_env' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:141 | [orphan] 'probe_database' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:165 | [orphan] 'probe_http_api' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:181 | [orphan] 'select_transport' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:212 | [orphan] 'init_client' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:223 | [orphan] 'get_config' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:230 | [orphan] 'get_client' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:237 | [orphan] 'shutdown_client' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:245 | [orphan] '_build_default_headers' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:257 | [orphan] '_error_response' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:264 | [orphan] '_request' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:332 | [orphan] '_agent_identity' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:350 | [orphan] 'proxy_acquire_lock' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:365 | [orphan] 'proxy_release_lock' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:374 | [orphan] 'proxy_check_locks' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:425 | [orphan] 'proxy_get_work' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:436 | [orphan] 'proxy_complete_work' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:453 | [orphan] 'proxy_submit_work' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:472 | [orphan] 'proxy_get_task' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:486 | [orphan] 'proxy_issue_create' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:511 | [orphan] 'proxy_issue_list' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:532 | [orphan] 'proxy_issue_show' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:537 | [orphan] 'proxy_issue_update' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:562 | [orphan] 'proxy_issue_close' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:577 | [orphan] 'proxy_issue_comment' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:590 | [orphan] 'proxy_issue_search' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:603 | [orphan] 'proxy_issue_ready' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:616 | [orphan] 'proxy_issue_blocked' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:626 | [orphan] 'proxy_write_handoff' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:647 | [orphan] 'proxy_read_handoff' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:665 | [orphan] 'proxy_register_session' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:680 | [orphan] 'proxy_discover_agents' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:693 | [orphan] 'proxy_heartbeat' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:699 | [orphan] 'proxy_cleanup_dead_agents' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:715 | [orphan] 'proxy_remember' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:736 | [orphan] 'proxy_recall' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:758 | [orphan] 'proxy_check_guardrails' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:771 | [orphan] 'proxy_get_my_profile' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:776 | [orphan] 'proxy_get_agent_dispatch_configs' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:781 | [orphan] 'proxy_query_audit' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:800 | [orphan] 'proxy_check_policy' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:815 | [orphan] 'proxy_validate_cedar_policy' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:824 | [orphan] 'proxy_list_policy_versions' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:836 | [orphan] 'proxy_request_permission' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:849 | [orphan] 'proxy_request_approval' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:864 | [orphan] 'proxy_check_approval' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:874 | [orphan] 'proxy_allocate_ports' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:883 | [orphan] 'proxy_release_ports' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:892 | [orphan] 'proxy_ports_status' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:909 | [orphan] 'proxy_register_feature' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:930 | [orphan] 'proxy_deregister_feature' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:943 | [orphan] 'proxy_get_feature' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:948 | [orphan] 'proxy_list_active_features' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:953 | [orphan] 'proxy_analyze_feature_conflicts' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:971 | [orphan] 'proxy_enqueue_merge' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:984 | [orphan] 'proxy_get_merge_queue' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:989 | [orphan] 'proxy_get_next_merge' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:994 | [orphan] 'proxy_run_pre_merge_checks' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1003 | [orphan] 'proxy_mark_merged' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1012 | [orphan] 'proxy_remove_from_merge_queue' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1022 | [orphan] 'proxy_report_status' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1049 | [orphan] 'proxy_list_scenarios' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1073 | [orphan] 'proxy_validate_scenario' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1082 | [orphan] 'proxy_create_scenario' is unreachable from any entrypoint or test |
| architecture | http_proxy.py:1101 | [orphan] 'proxy_run_gen_eval' is unreachable from any entrypoint or test |
| architecture | issue_service.py:72 | [orphan] 'from_row' is unreachable from any entrypoint or test |
| architecture | issue_service.py:73 | [orphan] 'parse_dt' is unreachable from any entrypoint or test |
| architecture | issue_service.py:108 | [orphan] 'to_dict' is unreachable from any entrypoint or test |
| architecture | issue_service.py:164 | [orphan] 'from_row' is unreachable from any entrypoint or test |
| architecture | issue_service.py:176 | [orphan] 'to_dict' is unreachable from any entrypoint or test |
| architecture | issue_service.py:189 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | issue_service.py:193 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | issue_service.py:198 | [orphan] 'create' is unreachable from any entrypoint or test |
| architecture | issue_service.py:251 | [orphan] 'list_issues' is unreachable from any entrypoint or test |
| architecture | issue_service.py:306 | [orphan] 'show' is unreachable from any entrypoint or test |
| architecture | issue_service.py:344 | [orphan] 'update' is unreachable from any entrypoint or test |
| architecture | issue_service.py:410 | [orphan] 'close' is unreachable from any entrypoint or test |
| architecture | issue_service.py:453 | [orphan] 'comment' is unreachable from any entrypoint or test |
| architecture | issue_service.py:479 | [orphan] 'ready' is unreachable from any entrypoint or test |
| architecture | issue_service.py:525 | [orphan] 'blocked' is unreachable from any entrypoint or test |
| architecture | issue_service.py:554 | [orphan] 'search' is unreachable from any entrypoint or test |
| architecture | kanban_viz_files.py:69 | [orphan] '_load_schema' is unreachable from any entrypoint or test |
| architecture | kanban_viz_files.py:115 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:44 | [orphan] 'dispatch' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:98 | [orphan] '_resolve_agent_id' is unreachable from any entrypoint or test |
| architecture | langfuse_middleware.py:114 | [orphan] '_finalize_trace' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:30 | [orphan] '_is_enabled' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:34 | [orphan] 'init_langfuse' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:79 | [orphan] 'get_langfuse' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:84 | [orphan] 'shutdown_langfuse' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:102 | [orphan] 'create_trace' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:130 | [orphan] 'create_span' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:153 | [orphan] 'end_span' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:175 | [orphan] 'trace_operation' is unreachable from any entrypoint or test |
| architecture | langfuse_tracing.py:229 | [orphan] 'reset_langfuse' is unreachable from any entrypoint or test |
| architecture | locks.py:29 | [orphan] '_get_instruments' is unreachable from any entrypoint or test |
| architecture | locks.py:58 | [orphan] '_ensure_instruments' is unreachable from any entrypoint or test |
| architecture | locks.py:81 | [orphan] 'is_valid_lock_key' is unreachable from any entrypoint or test |
| architecture | locks.py:101 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | locks.py:102 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | locks.py:131 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | locks.py:152 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | locks.py:156 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | locks.py:161 | [orphan] 'acquire' is unreachable from any entrypoint or test |
| architecture | locks.py:276 | [orphan] 'release' is unreachable from any entrypoint or test |
| architecture | locks.py:341 | [orphan] 'check' is unreachable from any entrypoint or test |
| architecture | locks.py:368 | [orphan] 'extend' is unreachable from any entrypoint or test |
| architecture | locks.py:392 | [orphan] 'is_locked' is unreachable from any entrypoint or test |
| architecture | locks.py:404 | [orphan] 'force_release' is unreachable from any entrypoint or test |
| architecture | memory.py:35 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | memory.py:65 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | memory.py:81 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | memory.py:92 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | memory.py:96 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | memory.py:101 | [orphan] 'remember' is unreachable from any entrypoint or test |
| architecture | memory.py:181 | [orphan] 'recall' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:73 | [orphan] 'from_feature' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:99 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:108 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:114 | [orphan] 'registry' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:119 | [orphan] 'enqueue' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:210 | [orphan] 'get_queue' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:246 | [orphan] 'get_next_to_merge' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:260 | [orphan] 'run_pre_merge_checks' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:349 | [orphan] 'mark_merged' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:376 | [orphan] 'remove_from_queue' is unreachable from any entrypoint or test |
| architecture | merge_queue.py:404 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | merge_train.py:114 | [orphan] '_entry_prefix_set' is unreachable from any entrypoint or test |
| architecture | merge_train.py:137 | [orphan] '_find_cycles_in_cross_partition_graph' is unreachable from any entrypoint or test |
| architecture | merge_train.py:176 | [orphan] '_dfs' is unreachable from any entrypoint or test |
| architecture | merge_train.py:212 | [orphan] 'compute_partitions' is unreachable from any entrypoint or test |
| architecture | merge_train.py:294 | [orphan] '_speculative_ref_name' is unreachable from any entrypoint or test |
| architecture | merge_train.py:299 | [orphan] '_sort_entries_by_priority' is unreachable from any entrypoint or test |
| architecture | merge_train.py:304 | [orphan] '_handle_conflict' is unreachable from any entrypoint or test |
| architecture | merge_train.py:318 | [orphan] '_handle_speculative_success' is unreachable from any entrypoint or test |
| architecture | merge_train.py:339 | [orphan] 'compose_train' is unreachable from any entrypoint or test |
| architecture | merge_train.py:445 | [orphan] '_speculate' is unreachable from any entrypoint or test |
| architecture | merge_train.py:547 | [orphan] '_declared_namespaces' is unreachable from any entrypoint or test |
| architecture | merge_train.py:557 | [orphan] 'validate_post_speculation_claims' is unreachable from any entrypoint or test |
| architecture | merge_train.py:644 | [orphan] '_caller_is_authorized_to_eject' is unreachable from any entrypoint or test |
| architecture | merge_train.py:659 | [orphan] 'eject_from_train' is unreachable from any entrypoint or test |
| architecture | merge_train.py:768 | [orphan] 'reset_blocked_entry' is unreachable from any entrypoint or test |
| architecture | merge_train.py:811 | [orphan] 'reset_abandoned_entry' is unreachable from any entrypoint or test |
| architecture | merge_train.py:884 | [orphan] '_build_merge_graph' is unreachable from any entrypoint or test |
| architecture | merge_train.py:974 | [orphan] '_compute_wave_order' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1017 | [orphan] 'execute_wave_merge' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1137 | [orphan] '_group_refs_by_train_id' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1157 | [orphan] 'cleanup_orphaned_speculative_refs' is unreachable from any entrypoint or test |
| architecture | merge_train.py:1206 | [orphan] 'gc_aged_speculative_refs' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:66 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:77 | [orphan] '_feature_to_train_entry' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:123 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:138 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:144 | [orphan] 'registry' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:150 | [orphan] 'git_adapter' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:160 | [orphan] 'refresh_client' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:167 | [orphan] '_load_entries' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:177 | [orphan] '_save_entry' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:197 | [orphan] '_persist_entries' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:208 | [orphan] '_probe_and_maybe_refresh' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:256 | [orphan] 'compose_train' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:288 | [orphan] 'eject_from_train' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:338 | [orphan] 'get_train_status' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:343 | [orphan] 'report_spec_result' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:404 | [orphan] 'reset_merge_train_service' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:438 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:457 | [orphan] 'service' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:463 | [orphan] 'running' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:466 | [orphan] 'run_once' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:484 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:494 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:506 | [orphan] '_loop' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:521 | [orphan] 'get_merge_train_sweeper' is unreachable from any entrypoint or test |
| architecture | merge_train_service.py:529 | [orphan] 'reset_merge_train_sweeper' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:127 | [orphan] 'is_terminal' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:130 | [orphan] 'to_metadata_dict' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:162 | [orphan] 'all_passed' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:202 | [orphan] 'new_train_id' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:206 | [orphan] 'all_entries' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:213 | [orphan] 'total_entry_count' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:252 | [orphan] 'file_path_to_namespaces' is unreachable from any entrypoint or test |
| architecture | merge_train_types.py:287 | [orphan] 'claim_prefix' is unreachable from any entrypoint or test |
| architecture | migrations.py:35 | [orphan] 'discover_migrations' is unreachable from any entrypoint or test |
| architecture | migrations.py:50 | [orphan] '_checksum' is unreachable from any entrypoint or test |
| architecture | migrations.py:55 | [orphan] 'run_migrations' is unreachable from any entrypoint or test |
| architecture | migrations.py:146 | [orphan] 'ensure_schema' is unreachable from any entrypoint or test |
| architecture | network_policies.py:24 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | network_policies.py:36 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | network_policies.py:40 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | network_policies.py:45 | [orphan] 'check_domain' is unreachable from any entrypoint or test |
| architecture | network_policies.py:85 | [orphan] 'get_network_policy_service' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:16 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:20 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:24 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:34 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:37 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:41 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/base.py:44 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:55 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:71 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:128 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:143 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:148 | [orphan] 'start_imap_listener' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:214 | [orphan] 'stop_imap_listener' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:222 | [orphan] '_process_imap_message' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:348 | [orphan] '_send_reply_email' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:368 | [orphan] '_render' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:380 | [orphan] '_thread_message_id' is unreachable from any entrypoint or test |
| architecture | notifications/gmail.py:387 | [orphan] 'get_gmail_channel' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:33 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:38 | [orphan] 'register_channel' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:43 | [orphan] 'enabled' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:47 | [orphan] 'start_digest_loop' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:54 | [orphan] 'stop_digest_loop' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:67 | [orphan] '_digest_loop' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:77 | [orphan] '_flush_digest' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:110 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:169 | [orphan] '_send_with_retry' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:208 | [orphan] '_passes_filter' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:223 | [orphan] 'get_notifier' is unreachable from any entrypoint or test |
| architecture | notifications/notifier.py:231 | [orphan] 'reset_notifier' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:29 | [orphan] 'extract_token' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:39 | [orphan] 'parse_reply' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:72 | [orphan] 'validate_sender' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:82 | [orphan] 'clean_reply_body' is unreachable from any entrypoint or test |
| architecture | notifications/relay.py:109 | [orphan] 'route_reply' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:28 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:39 | [orphan] 'client' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:44 | [orphan] '_api_url' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:47 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:106 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:122 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:126 | [orphan] '_escape_markdown' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:131 | [orphan] '_format_message' is unreachable from any entrypoint or test |
| architecture | notifications/telegram.py:148 | [orphan] 'get_telegram_channel' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:10 | [orphan] '_esc' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:15 | [orphan] '_sanitize_header' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:46 | [orphan] '_wrap' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:56 | [orphan] '_change_label' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:61 | [orphan] '_field' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:71 | [orphan] 'render_approval_email' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:100 | [orphan] 'render_status_email' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:119 | [orphan] 'render_escalation_email' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:147 | [orphan] 'render_stale_agent_email' is unreachable from any entrypoint or test |
| architecture | notifications/templates.py:165 | [orphan] 'render_digest_email' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:26 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:37 | [orphan] 'client' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:42 | [orphan] 'send' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:83 | [orphan] 'test' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:109 | [orphan] 'supports_reply' is unreachable from any entrypoint or test |
| architecture | notifications/webhook.py:113 | [orphan] 'get_webhook_channel' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:29 | [orphan] '_ensure_policy_instruments' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:92 | [orphan] 'allow' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:96 | [orphan] 'deny' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:115 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:119 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:124 | [orphan] 'check_operation' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:165 | [orphan] '_do_check_operation' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:350 | [orphan] 'check_network_access' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:373 | [orphan] 'list_policy_versions' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:392 | [orphan] 'rollback_policy' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:418 | [orphan] '_log_policy_decision' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:464 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:480 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:485 | [orphan] '_load_default_policies' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:499 | [orphan] '_load_schema' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:517 | [orphan] '_load_policies' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:572 | [orphan] '_build_entity' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:609 | [orphan] '_build_resource_entity' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:636 | [orphan] '_determine_resource_type' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:648 | [orphan] 'check_operation' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:689 | [orphan] '_do_check_operation' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:778 | [orphan] 'check_network_access' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:797 | [orphan] 'validate_policy' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:818 | [orphan] 'list_policies' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:837 | [orphan] 'invalidate_cache' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:842 | [orphan] 'list_policy_versions' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:861 | [orphan] 'rollback_policy' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:888 | [orphan] '_log_policy_decision' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:945 | [orphan] 'reset_policy_engine' is unreachable from any entrypoint or test |
| architecture | policy_engine.py:951 | [orphan] 'reset_policy_instruments' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:21 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:25 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:29 | [orphan] 'on_policy_change' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:45 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:60 | [orphan] 'running' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:64 | [orphan] 'on_policy_change' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:67 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:79 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:93 | [orphan] '_listen_loop' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:121 | [orphan] '_connect_and_listen' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:127 | [orphan] '_notification_handler' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:149 | [orphan] '_safe_callback' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:163 | [orphan] 'get_policy_sync_service' is unreachable from any entrypoint or test |
| architecture | policy_sync.py:171 | [orphan] 'reset_policy_sync_service' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:37 | [orphan] 'env_snippet' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:55 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:74 | [orphan] 'allocate' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:132 | [orphan] 'release' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:141 | [orphan] 'status' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:151 | [orphan] '_cleanup_expired' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:166 | [orphan] '_compose_project_name' is unreachable from any entrypoint or test |
| architecture | port_allocator.py:189 | [orphan] 'reset_port_allocator' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:64 | [orphan] 'deep_merge' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:114 | [orphan] '_load_secrets_openbao' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:159 | [orphan] '_load_secrets' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:171 | [orphan] 'resolve_dynamic_dsn' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:239 | [orphan] '_replace' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:260 | [orphan] '_interpolate_tree' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:277 | [orphan] '_resolve_profile' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:311 | [orphan] '_flatten' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:323 | [orphan] '_inject_env' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:339 | [orphan] 'load_profile' is unreachable from any entrypoint or test |
| architecture | profile_loader.py:372 | [orphan] 'apply_profile' is unreachable from any entrypoint or test |
| architecture | profiles.py:36 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | profiles.py:63 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | profiles.py:84 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | profiles.py:94 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | profiles.py:99 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | profiles.py:104 | [orphan] 'get_profile' is unreachable from any entrypoint or test |
| architecture | profiles.py:153 | [orphan] 'check_operation' is unreachable from any entrypoint or test |
| architecture | profiles.py:214 | [orphan] '_log_denial' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:69 | [orphan] '__repr__' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:85 | [orphan] '__call__' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:134 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:150 | [orphan] 'is_graph_stale' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:164 | [orphan] 'trigger_refresh' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:174 | [orphan] 'get_refresh_status' is unreachable from any entrypoint or test |
| architecture | refresh_rpc_client.py:183 | [orphan] '_invoke' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:44 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:56 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:61 | [orphan] 'compute_score' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:108 | [orphan] 'get_violation_count' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:125 | [orphan] '_trust_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:130 | [orphan] '_operation_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:141 | [orphan] '_resource_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:152 | [orphan] '_violation_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:161 | [orphan] '_session_age_factor' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:174 | [orphan] 'get_risk_scorer' is unreachable from any entrypoint or test |
| architecture | risk_scorer.py:182 | [orphan] 'reset_risk_scorer' is unreachable from any entrypoint or test |
| architecture | session_grants.py:30 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | session_grants.py:34 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | session_grants.py:39 | [orphan] 'request_grant' is unreachable from any entrypoint or test |
| architecture | session_grants.py:70 | [orphan] 'get_active_grants' is unreachable from any entrypoint or test |
| architecture | session_grants.py:78 | [orphan] 'has_grant' is unreachable from any entrypoint or test |
| architecture | session_grants.py:86 | [orphan] 'revoke_grants' is unreachable from any entrypoint or test |
| architecture | session_grants.py:100 | [orphan] '_row_to_grant' is unreachable from any entrypoint or test |
| architecture | session_grants.py:113 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | session_grants.py:133 | [orphan] 'reset_session_grant_service' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:39 | [orphan] 'filter' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:58 | [orphan] '_scrub' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:64 | [orphan] 'install_token_redaction_filter' is unreachable from any entrypoint or test |
| architecture | sse_log_redaction.py:79 | [orphan] 'redact_token' is unreachable from any entrypoint or test |
| architecture | status.py:12 | [orphan] 'generate_token' is unreachable from any entrypoint or test |
| architecture | status.py:17 | [orphan] 'store_token' is unreachable from any entrypoint or test |
| architecture | status.py:52 | [orphan] 'validate_token' is unreachable from any entrypoint or test |
| architecture | status.py:80 | [orphan] 'lookup_token_failure' is unreachable from any entrypoint or test |
| architecture | status.py:100 | [orphan] 'cleanup_expired_tokens' is unreachable from any entrypoint or test |
| architecture | sync_points.py:35 | [orphan] '_parse_iso' is unreachable from any entrypoint or test |
| architecture | sync_points.py:45 | [orphan] '_load_registry' is unreachable from any entrypoint or test |
| architecture | sync_points.py:60 | [orphan] '_check_active_worktrees' is unreachable from any entrypoint or test |
| architecture | sync_points.py:81 | [orphan] 'get_sync_points_status' is unreachable from any entrypoint or test |
| architecture | teams.py:69 | [orphan] 'from_file' is unreachable from any entrypoint or test |
| architecture | teams.py:93 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | teams.py:129 | [orphan] 'get_agent' is unreachable from any entrypoint or test |
| architecture | teams.py:143 | [orphan] 'get_agents_with_capability' is unreachable from any entrypoint or test |
| architecture | teams.py:180 | [orphan] 'get_teams_config' is unreachable from any entrypoint or test |
| architecture | teams.py:200 | [orphan] 'reset_teams_config' is unreachable from any entrypoint or test |
| architecture | telemetry.py:33 | [orphan] '_metrics_enabled' is unreachable from any entrypoint or test |
| architecture | telemetry.py:37 | [orphan] '_traces_enabled' is unreachable from any entrypoint or test |
| architecture | telemetry.py:41 | [orphan] '_prometheus_enabled' is unreachable from any entrypoint or test |
| architecture | telemetry.py:45 | [orphan] 'init_telemetry' is unreachable from any entrypoint or test |
| architecture | telemetry.py:74 | [orphan] '_init_metrics' is unreachable from any entrypoint or test |
| architecture | telemetry.py:138 | [orphan] '_init_traces' is unreachable from any entrypoint or test |
| architecture | telemetry.py:185 | [orphan] 'get_lock_meter' is unreachable from any entrypoint or test |
| architecture | telemetry.py:190 | [orphan] 'get_queue_meter' is unreachable from any entrypoint or test |
| architecture | telemetry.py:195 | [orphan] 'get_policy_meter' is unreachable from any entrypoint or test |
| architecture | telemetry.py:200 | [orphan] 'get_tracer' is unreachable from any entrypoint or test |
| architecture | telemetry.py:213 | [orphan] 'set_attribute' is unreachable from any entrypoint or test |
| architecture | telemetry.py:216 | [orphan] 'set_status' is unreachable from any entrypoint or test |
| architecture | telemetry.py:219 | [orphan] 'record_exception' is unreachable from any entrypoint or test |
| architecture | telemetry.py:222 | [orphan] '__enter__' is unreachable from any entrypoint or test |
| architecture | telemetry.py:225 | [orphan] '__exit__' is unreachable from any entrypoint or test |
| architecture | telemetry.py:232 | [orphan] 'start_span' is unreachable from any entrypoint or test |
| architecture | telemetry.py:245 | [orphan] 'get_prometheus_app' is unreachable from any entrypoint or test |
| architecture | telemetry.py:267 | [orphan] 'reset_telemetry' is unreachable from any entrypoint or test |
| architecture | watchdog.py:34 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | watchdog.py:55 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | watchdog.py:61 | [orphan] 'running' is unreachable from any entrypoint or test |
| architecture | watchdog.py:64 | [orphan] 'start' is unreachable from any entrypoint or test |
| architecture | watchdog.py:72 | [orphan] 'stop' is unreachable from any entrypoint or test |
| architecture | watchdog.py:84 | [orphan] 'run_once' is unreachable from any entrypoint or test |
| architecture | watchdog.py:93 | [orphan] '_loop' is unreachable from any entrypoint or test |
| architecture | watchdog.py:107 | [orphan] '_check_stale_agents' is unreachable from any entrypoint or test |
| architecture | watchdog.py:166 | [orphan] '_check_aging_approvals' is unreachable from any entrypoint or test |
| architecture | watchdog.py:207 | [orphan] '_check_expiring_locks' is unreachable from any entrypoint or test |
| architecture | watchdog.py:235 | [orphan] '_cleanup_expired_tokens' is unreachable from any entrypoint or test |
| architecture | watchdog.py:252 | [orphan] '_check_event_bus_health' is unreachable from any entrypoint or test |
| architecture | watchdog.py:275 | [orphan] '_check_vendor_health' is unreachable from any entrypoint or test |
| architecture | watchdog.py:346 | [orphan] '_emit_event' is unreachable from any entrypoint or test |
| architecture | watchdog.py:391 | [orphan] 'get_watchdog' is unreachable from any entrypoint or test |
| architecture | watchdog.py:399 | [orphan] 'reset_watchdog' is unreachable from any entrypoint or test |
| architecture | work_queue.py:30 | [orphan] '_ensure_instruments' is unreachable from any entrypoint or test |
| architecture | work_queue.py:88 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | work_queue.py:89 | [orphan] 'parse_dt' is unreachable from any entrypoint or test |
| architecture | work_queue.py:133 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | work_queue.py:166 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | work_queue.py:187 | [orphan] 'from_dict' is unreachable from any entrypoint or test |
| architecture | work_queue.py:201 | [orphan] '__init__' is unreachable from any entrypoint or test |
| architecture | work_queue.py:205 | [orphan] 'db' is unreachable from any entrypoint or test |
| architecture | work_queue.py:210 | [orphan] '_resolve_trust_level' is unreachable from any entrypoint or test |
| architecture | work_queue.py:225 | [orphan] 'claim' is unreachable from any entrypoint or test |
| architecture | work_queue.py:442 | [orphan] 'complete' is unreachable from any entrypoint or test |
| architecture | work_queue.py:593 | [orphan] 'submit' is unreachable from any entrypoint or test |
| architecture | work_queue.py:729 | [orphan] 'get_pending' is unreachable from any entrypoint or test |
| architecture | work_queue.py:753 | [orphan] 'get_task' is unreachable from any entrypoint or test |
| architecture | work_queue.py:765 | [orphan] 'get_my_tasks' is unreachable from any entrypoint or test |
| architecture | work_queue.py:789 | [orphan] 'cancel_task_convention' is unreachable from any entrypoint or test |
| architecture | work_queue.py:830 | [orphan] 'reset_instruments' is unreachable from any entrypoint or test |
| architecture | worktrees_view.py:24 | [orphan] '_repo_root' is unreachable from any entrypoint or test |
| architecture | worktrees_view.py:29 | [orphan] '_parse_dt' is unreachable from any entrypoint or test |
| architecture | worktrees_view.py:41 | [orphan] 'get_active_worktrees' is unreachable from any entrypoint or test |
| deferred:open-tasks | N/A | 2.1 Write integration tests for routing migrations — additive-only, idempotent re-apply [S] |
| deferred:open-tasks | N/A | 2.2 Create migration `00X_model_routing.sql` per DB contract [S] |
| deferred:open-tasks | N/A | 2.3 Write tests for catalog service — CRUD, no-external-call read path, staleness flag [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.4 Implement `src/model_routing/catalog.py` — catalog service over routing tables [M] |
| deferred:open-tasks | N/A | 2.5 Write tests for OpenRouter refresher — price update, failure keeps rows, staleness [M] |
| deferred:open-tasks | N/A | 2.6 Implement OpenRouter REST refresher with standing-key auth [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.7 Write tests for local endpoint health probe — unhealthy exclusion, latency capture [S] |
| deferred:open-tasks | N/A | 2.8 Implement local endpoint registration plus health probe [S] |
| deferred:open-tasks | N/A | 2.9 Write tests for spend/counterfactual ledger — actual vs baseline, estimate labelling [M] |
| deferred:open-tasks | N/A | 2.10 Implement `src/model_routing/ledger.py` — spend accrual, counterfactual computation [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.11 Wire refresher, probes, ledger rollup into WatchdogService schedules [S] |
| deferred:open-tasks | N/A | 3.4 Implement Cedar feasibility policies plus vendor attribute schema [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.7 Write tests for routing API endpoints plus MCP tool parity [M] |
| deferred:open-tasks | N/A | 3.8 Expose resolver via HTTP endpoints plus MCP tool [M] |
| deferred:open-tasks | N/A | 3.9 Write tests for archetype delegation — flag off equals static result; timeout fallback signal [M] |
| deferred:open-tasks | N/A | 3.10 Implement `ROUTING_ADAPTIVE` delegation in `agents_config.resolve_archetype_for_phase` [S] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.11 Add `endpoint_kind`/`base_url` fields to agents.yaml schema with validation [S] |
| deferred:open-tasks | N/A | 4.6 Enforce exploration gating in roadmap dispatch path [S] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 5.4 Wire learning-log writers to POST `/routing/feedback` (best-effort, non-blocking) [S] |
| deferred:open-tasks | N/A | 5.5 Write tests for gen-eval calibration seeding of local-model priors [S] |
| deferred:open-tasks | N/A | 5.6 Implement gen-eval calibration suite runner seeding local priors [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 6.1 Write tests for ToS monitor — hash diff emits signal, vendor freeze until ack [S] |
| deferred:open-tasks | N/A | 6.2 Implement ToS monitor probe [S] |
| deferred:open-tasks | N/A | 6.3 Write tests for model canary — fingerprint drift invalidates posteriors [S] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 6.4 Implement model canary probe [S] |
| deferred:open-tasks | N/A | 6.5 Write tests for tripwire evaluation — economic kill, posture-flip signals [M] |
| deferred:open-tasks | N/A | 6.7 Write tests for quota probe — quota-axi JSON normalized to signal, resilience down-rank, graceful degrade [S] |
| deferred:open-tasks | N/A | 6.8 Implement optional quota probe (quota-axi subprocess adapter, off by default) [S] |
| deferred:open-tasks | N/A | 6.6 Implement tripwire evaluator with posture flips as signals [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope, verify quota probe degrades cleanly |
| deferred:open-tasks | N/A | 7.1 Write component tests for usage dashboard — scoreboard render, estimate labelling [M] |
| deferred:open-tasks | N/A | 7.2 Scaffold `apps/usage-viz` from kanban-viz conventions (auth, SSE/poll hooks) [M] |
| deferred:open-tasks | N/A | 7.3 Implement spend, savings, scoreboard, exploration burn-down views [M] |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 7.4 Write tests for routing telemetry emission — fallback label present [S] |
| deferred:open-tasks | N/A | 7.5 Emit routing OTel measurements on `coordinator.signal` meter [S] |
| deferred:open-tasks | N/A | 8.1 Run full test suite across coordinator plus skills venvs [S] |
| deferred:open-tasks | N/A | 8.2 E2E: flag-on routed quick-task to local endpoint; flag-off parity check [M] |
| deferred:open-tasks | N/A | 8.3 Archive absorbed changes with superseded-by pointers (`cross-vendor-arbitrage-instrument`, `usage-stats-multi-model` |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 8.4 Register OpenRouter MCP server in `.mcp.json` as dev-time tool with setup docs [XS] |
| deferred:open-tasks | N/A | 8.5 Write ADR for adaptive routing placement plus objective-profile semantics [S] |
| deferred:open-tasks | N/A | 0.1 (S) Confirm the `add-adaptive-model-router` ledger + policy interfaces this consumes |
| deferred:open-tasks | N/A | 1.1 (S) Validate `contracts/openapi/v1.yaml`; generate Pydantic models into |
| deferred:open-tasks | N/A | Checkpoint: openapi validates, models import |
| deferred:open-tasks | N/A | 2.1 (S) Write a smoke test that starts the gateway container and asserts `/health` + |
| deferred:open-tasks | N/A | 2.2 (M) Add `docker/llm-gateway/` — pinned LiteLLM proxy compose service + |
| deferred:open-tasks | N/A | Checkpoint: gateway starts; embedding round-trips against a test upstream |
| deferred:open-tasks | N/A | 3.1 (M) Write tests for `llm_gateway.py` — trust-bounded issuance, vault-unavailable |
| deferred:open-tasks | N/A | 3.2 (M) Implement `agent-coordinator/src/llm_gateway.py` — DI service over (vault, gateway |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope (agent-coordinator only) |
| deferred:open-tasks | N/A | 3.3 (S) Write surface tests — flag off hides MCP tools + 404s HTTP routes; op-kind |
| deferred:open-tasks | N/A | 3.4 (S) Register `issue_llm_key/revoke_llm_key/get_llm_budget/get_llm_spend` in |
| deferred:open-tasks | N/A | Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.1 (S) Migration test — `llm_gateway_keys` additive shape; asserts NO spend columns |
| deferred:open-tasks | N/A | 4.2 (S) Add additive migration `NNN_llm_gateway_keys.sql` |
| deferred:open-tasks | N/A | 4.3 (M) Wire the gateway spend callback → router ledger; buffer-and-reconcile on ledger |
| deferred:open-tasks | N/A | 5.1 (S) Repoint `code_search.py`'s embedder at the gateway `/embeddings` behind a config |
| deferred:open-tasks | N/A | 5.2 (S) Docs: `docs/guides/llm-gateway.md` — control/data-plane split, the coverage |
| deferred:open-tasks | N/A | 5.3 (M) End-to-end (where a gateway + model are reachable): issue a key, embed via the |
| deferred:open-tasks | N/A | Checkpoint: suite green, diff maps to tasks, scope verified |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | 1.1 Write tests for the merge-plan schema and its producer |
| deferred:open-tasks | N/A | 1.2 Add `build_plan.py` (or extend the analysis round) to emit `merge-plan.json` from `discover_prs` + `check_staleness` |
| deferred:open-tasks | N/A | 1.3 Derive dependency edges from file overlap + base-branch relationships between PR nodes |
| deferred:open-tasks | N/A | 1.4 Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.1 Write tests for the `merge-plan.md` renderer (fidelity + non-mutation) |
| deferred:open-tasks | N/A | 2.2 Implement the `merge-plan.md` renderer as a pure projection of `merge-plan.json` |
| deferred:open-tasks | N/A | 3.1 Write tests for tier selection degrading to the file when no coordinator is available |
| deferred:open-tasks | N/A | 3.2 Wire plan storage to `merge_backend.py` detection so file tier is authoritative absent a coordinator; stub the coord |
| deferred:open-tasks | N/A | 3.3 Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.1 Write tests for `--execute <plan> --pr <n>`: live re-check, gate halt, security-backstop deferral, outcome write-bac |
| deferred:open-tasks | N/A | 4.2 Implement `--execute --pr <n>` in the skill entrypoint: load plan, re-check live PR/CI, refresh if stale, run `vendo |
| deferred:open-tasks | N/A | 4.3 On successful merge, flag downstream nodes (`needs_revalidation=true`) and recompute mergeability before executing a |
| deferred:open-tasks | N/A | 4.4 Enforce canonical `skills/...` helper paths in the executor (no `.claude/skills` mirror dependence) |
| deferred:open-tasks | N/A | 4.5 Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 5.1 Write tests for inserting a discovered prerequisite node and for the comment-addressing delegation hand-off |
| deferred:open-tasks | N/A | 5.2 Implement plan amendment: insert prerequisite node + edges with a reason; block affected nodes until it merges |
| deferred:open-tasks | N/A | 5.3 Implement the comment-addressing seam: record unresolved comments on the node and offer delegation to `iterate-on-im |
| deferred:open-tasks | N/A | 5.4 Checkpoint: run tests, review diff, verify scope |
| deferred:open-tasks | N/A | 6.1 Update `merge-pull-requests/SKILL.md`: document the plan artifact, `--execute --pr <n>`, gates, and the fresh-contex |
| deferred:open-tasks | N/A | 6.2 Sync runtime mirrors (`bash skills/install.sh --mode rsync --force --deps none --python-tools none`) and run the ski |
| deferred:open-tasks | N/A | P2.1 Coordinator system-of-record: model plan nodes as `work_queue` (`task_type=pr_merge`, `blockedBy`) + `merge_queue`  |
| deferred:open-tasks | N/A | P2.2 Event-driven re-validation over `event_bus` LISTEN/NOTIFY (design.md D4) |
| deferred:open-tasks | N/A | P2.3 Cross-host dispatch of per-PR executors with worktree isolation (design.md D5) |
| deferred:open-tasks | N/A | P2.4 Auth scoping for cloud-SDK plan endpoints (design.md D10) |
| deferred:open-tasks | N/A | P2.5 Automated comment-addressing via worktree-isolated sub-agents (out of scope here; design.md D8) |
| deferred:open-tasks | N/A | 0.1 Create `skills/references/prioritization-frameworks.md` |
| deferred:open-tasks | N/A | 0.2 Extend the proposal template with optional discovery sections |
| deferred:open-tasks | N/A | 0.3 Extend the roadmap schema/templates with optional `outcome` / `okr` fields |
| deferred:open-tasks | N/A | 0.4 Create the 12 new test dirs (each with a placeholder `test_skill_md.py` containing a |
| deferred:open-tasks | N/A | 0.5 Stub the "Product discovery" group in `docs/skills-catalogue.md` |
| deferred:open-tasks | N/A | 1.1.1 Tests for `create-prd` and `opportunity-solution-tree` |
| deferred:open-tasks | N/A | 1.1.2 Author `skills/create-prd/SKILL.md` (output renders as a valid `proposal.md`) |
| deferred:open-tasks | N/A | 1.1.3 Author `skills/opportunity-solution-tree/SKILL.md` (leaves = change candidates) |
| deferred:open-tasks | N/A | 1.2.1 Tests for `prioritize-features` and `identify-assumptions` |
| deferred:open-tasks | N/A | 1.2.2 Author `skills/prioritize-features/SKILL.md` (cites `references/prioritization-frameworks.md`) |
| deferred:open-tasks | N/A | 1.2.3 Author `skills/identify-assumptions/SKILL.md` |
| deferred:open-tasks | N/A | 1.3.1 Tests for `strategy-red-team` and `pre-mortem` |
| deferred:open-tasks | N/A | 1.3.2 Author `skills/strategy-red-team/SKILL.md` (findings in `iterate-on-plan` shape) |
| deferred:open-tasks | N/A | 1.3.3 Author `skills/pre-mortem/SKILL.md` |
| deferred:open-tasks | N/A | 1.4.1 Tests for `user-stories` and `test-scenarios` |
| deferred:open-tasks | N/A | 1.4.2 Author `skills/user-stories/SKILL.md` (output includes WHEN/THEN blocks) |
| deferred:open-tasks | N/A | 1.4.3 Author `skills/test-scenarios/SKILL.md` |
| deferred:open-tasks | N/A | 1.5.1 Tests for `intended-vs-implemented` (user-invocable) and `shipping-artifacts` (infra, exempt) |
| deferred:open-tasks | N/A | 1.5.2 Author `skills/intended-vs-implemented/SKILL.md` |
| deferred:open-tasks | N/A | 1.5.3 Author `skills/shipping-artifacts/SKILL.md` (`user_invocable: false`, no tail block) |
| deferred:open-tasks | N/A | 1.6.1 Tests for `outcome-roadmap` and `brainstorm-okrs` |
| deferred:open-tasks | N/A | 1.6.2 Author `skills/outcome-roadmap/SKILL.md` |
| deferred:open-tasks | N/A | 1.6.3 Author `skills/brainstorm-okrs/SKILL.md` |
| deferred:open-tasks | N/A | 2.1.1 Wire `explore-feature/SKILL.md` to consume `opportunity-solution-tree` output + outcome framing |
| deferred:open-tasks | N/A | 2.1.2 Wire `plan-feature/SKILL.md` Gate-1 discovery to incorporate `identify-assumptions` + `strategy-red-team` |
| deferred:open-tasks | N/A | 2.1.3 Wire seam 1 producer→consumer: `plan-roadmap`, `plan-feature`, and the proposal template consume `create-prd` / `o |
| deferred:open-tasks | N/A | 2.1.4 Wire seam 3's `iterate-on-plan` consumer: `iterate-on-plan/SKILL.md` consumes `pre-mortem` findings (using the exi |
| deferred:open-tasks | N/A | 2.1.5 Wire seam 4: `plan-feature` spec generation and `validate-feature` consume `user-stories` / `test-scenarios` so ge |
| deferred:open-tasks | N/A | 2.2.1 Wire `prioritize-proposals/SKILL.md` to compose `prioritize-features` scoring axes |
| deferred:open-tasks | N/A | 2.3.1 Wire `validate-feature/SKILL.md` (+ a note in the OpenSpec verification workflow docs under `docs/guides/` — there |
| deferred:open-tasks | N/A | 2.3.2 Wire `autopilot-roadmap` / `roadmap-runtime` to reference optional `okr` fields |
| deferred:open-tasks | N/A | 3.1 Run `skills/install.sh --mode rsync` dry run; confirm all 12 skills + the reference install |
| deferred:open-tasks | N/A | 3.2 Confirm every new skill's `related:` targets resolve (install warns on none) |
| deferred:open-tasks | N/A | 3.3 `cd skills && uv run pytest skills/tests/<12 new dirs>` green |
| deferred:open-tasks | N/A | 3.4 Fill the 12 rows in the `docs/skills-catalogue.md` "Product discovery" group; update counts |
| deferred:open-tasks | N/A | 3.5 `openspec validate add-product-management-skills --strict` passes |
| deferred:open-tasks | N/A | 3.6 Write the session log (decisions, deviations) per the session-log skill |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | 6.1 Orchestrator review |
| deferred:open-tasks | N/A | 6.2 Merge |
| deferred:open-tasks | N/A | 1.1 Write tests for the skill-inventory scanner |
| deferred:open-tasks | N/A | 1.2 Implement `skill_scanner.py` |
| deferred:open-tasks | N/A | 1.3 Write tests for the spec-inventory scanner |
| deferred:open-tasks | N/A | 1.4 Implement `spec_scanner.py` |
| deferred:open-tasks | N/A | 1.5 Write tests for the docs-inventory scanner |
| deferred:open-tasks | N/A | 1.6 Implement `docs_scanner.py` |
| deferred:open-tasks | N/A | 2.1 Write tests for the marker-insertion engine |
| deferred:open-tasks | N/A | 2.2 Implement `marker_engine.py` |
| deferred:open-tasks | N/A | 2.3 Write tests for per-target renderers |
| deferred:open-tasks | N/A | 2.4 Implement `renderers.py` (readme, claude_md, catalogue) |
| deferred:open-tasks | N/A | 3.1 Write tests for the cross-link checker |
| deferred:open-tasks | N/A | 3.2 Implement `link_checker.py` |
| deferred:open-tasks | N/A | 3.3 Write tests for the CLI and exit codes |
| deferred:open-tasks | N/A | 3.4 Implement `sync_docs.py` (CLI entry point) |
| deferred:open-tasks | N/A | 3.5 Write tests for the JSON report |
| deferred:open-tasks | N/A | 3.6 Implement `report_writer.py` |
| deferred:open-tasks | N/A | 4.1 Author `skills/update-documentation/SKILL.md` |
| deferred:open-tasks | N/A | 4.2 Update `.githooks/pre-commit` |
| deferred:open-tasks | N/A | 4.3 Update `.githooks/post-merge` |
| deferred:open-tasks | N/A | 4.4 Wire `/cleanup-feature` pre-merge gate |
| deferred:open-tasks | N/A | 4.5 Expose `/validate-feature --phase docs` |
| deferred:open-tasks | N/A | 4.6 Run the skill against the live repo and commit the resulting sync |
| deferred:open-tasks | N/A | 4.7 Update `docs/skills-catalogue.md:165` note |
| deferred:open-tasks | N/A | 1.1 Write tests for `annotations.py`: record construction, 240-char text truncation, artifact-header population, round-t |
| deferred:open-tasks | N/A | 1.2 Implement `skills/shared/plan_review/annotations.py` — `Annotation` dataclass, `append(change_id, record)` (running  |
| deferred:open-tasks | N/A | 2.1 Write tests for `render.py`: proposal.md + `specs/**/spec.md` deltas + tasks.md → HTML with a `data-plan-anchor` on  |
| deferred:open-tasks | N/A | 2.2 Implement `skills/shared/plan_review/render.py` — parse the change's `proposal.md`, its `specs/**/spec.md` delta req |
| deferred:open-tasks | N/A | 3.1 Write tests for `server.py`: loopback binding, long-poll returns queued annotations, a terminal `complete` event end |
| deferred:open-tasks | N/A | 3.2 Implement `skills/shared/plan_review/server.py` — serve the artifact on `127.0.0.1`; require a per-session random to |
| deferred:open-tasks | N/A | 4.1 Wire `--visual-review` into `plan-feature` **after `tasks.md` is generated (Step 6)** so the task DAG is populated:  |
| deferred:open-tasks | N/A | 4.2 Teach `parallel-review-plan` to attach `plan-annotations.json` (when present) to reviewer context |
| deferred:open-tasks | N/A | 4.3 Update `skills/plan-feature/SKILL.md` and `skills/parallel-review-plan/SKILL.md` docs; run `skills/install.sh` to re |
| deferred:open-tasks | N/A | 5.1 Integration test: full loop on a fixture change — render, queue two annotations (one anchored, one text-range), poll |
| deferred:open-tasks | N/A | 5.2 Run `openspec validate add-visual-plan-review --strict`; run skill test suite; update this change's `session-log.md` |
| deferred:open-tasks | N/A | G1 Confirm the `warning`-severity layout policy (Decision D / D4): warnings render normally and are surfaced as annotati |
| deferred:open-tasks | N/A | 0.1 Write characterization test for `convergence_loop.converge()` capturing |
| deferred:open-tasks | N/A | 0.2 Write unit tests for the `refine-core` primitive surface (iterate, |
| deferred:open-tasks | N/A | 0.3 Extract `refine_core.py` in `skills/parallel-infrastructure/scripts/` |
| deferred:open-tasks | N/A | 0.4 Re-point `convergence_loop.converge()` to delegate to `refine-core`; |
| deferred:open-tasks | N/A | 0.5 Checkpoint: run convergence + refine-core tests, review diff, verify |
| deferred:open-tasks | N/A | 1.1 Write tests for `post-commit` hook behavior: enqueues on commit, exits |
| deferred:open-tasks | N/A | 1.2 Write tests for the ambient review runner: single-vendor dispatch, |
| deferred:open-tasks | N/A | 1.3 Add `ambient` to the `review_type` enum in |
| deferred:open-tasks | N/A | 1.4 Implement `.githooks/post-commit` mirroring the `post-merge` resolution |
| deferred:open-tasks | N/A | 1.5 Implement the ambient review runner (single-vendor dispatch via the |
| deferred:open-tasks | N/A | 1.6 Wire the kill-switch (`REVIEW_AMBIENT=0` / config flag) and update the |
| deferred:open-tasks | N/A | 1.7 Checkpoint: run hook + runner tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.1 Write tests for ledger read/write: local-first source of truth, write |
| deferred:open-tasks | N/A | 2.2 Write tests for lifecycle transitions (`open`→`addressed`→`retired`) |
| deferred:open-tasks | N/A | 2.3 Author `contracts/review-ledger.schema.json` and a ledger-entry model [S] |
| deferred:open-tasks | N/A | 2.4 Implement the ledger library: local-first store, stable-id keying, |
| deferred:open-tasks | N/A | 2.5 Implement `compact` re-verification reusing `consensus_synthesizer` |
| deferred:open-tasks | N/A | 2.6 Checkpoint: run ledger + compact tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.7 Write test for gate skills reading the ledger as warm context without |
| deferred:open-tasks | N/A | 2.8 Wire gate-time review skills to load outstanding ledger findings as |
| deferred:open-tasks | N/A | 3.1 Write tests for the standalone refine entry point: runs over a commit |
| deferred:open-tasks | N/A | 3.2 Implement the standalone refine entry point over `refine-core`, |
| deferred:open-tasks | N/A | 3.3 Checkpoint: run refine tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.1 Write tests for issue sync: blocking confirmed finding files one issue, |
| deferred:open-tasks | N/A | 4.2 Implement issue sync over the GitHub MCP tools: file on |
| deferred:open-tasks | N/A | 4.3 Checkpoint: run issue-sync tests, review diff, verify scope |
| deferred:open-tasks | N/A | 5.1 Write component tests for the ledger swimlane: renders cards by |
| deferred:open-tasks | N/A | 5.2 Add the SSE event payload for ledger changes (server side) [S] |
| deferred:open-tasks | N/A | 5.3 Implement the review-ledger swimlane component in `apps/kanban-viz` [M] |
| deferred:open-tasks | N/A | 5.4 Checkpoint: run kanban-viz tests, review diff, verify scope |
| deferred:open-tasks | N/A | 6.1 End-to-end test: commit → ambient review → ledger → compact → issue |
| deferred:open-tasks | N/A | 6.2 Document the ambient-review-ledger workflow including the kill-switch |
| deferred:open-tasks | N/A | 6.3 Checkpoint: full test suite, review cumulative diff, verify scope |
| deferred:open-tasks | N/A | 5.1 Pilot `--format=toon` behind a flag on the tabular list commands and A/B the token delta vs. JSON |
| deferred:open-tasks | N/A | 5.2 Update any human-facing docs / skill prompts that show example `feature list` output to reflect the envelope |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Live multi-vendor execution on the GX10 (real CLIs + keys) — nightly |
| deferred:open-tasks | N/A | 10-scenario suite + nightly cadence + `/improve-harness` wiring |
| deferred:open-tasks | N/A | Incident auto-seeding (`auto-seed-scenarios-from-incidents`) |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | 6.4 Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | 1.1 Validate the four contract schemas parse as JSON Schema 2020-12 and add a schema-lint test |
| deferred:open-tasks | N/A | 1.2 Add fixture instances (one valid + one invalid) per contract schema for downstream tests to reuse |
| deferred:open-tasks | N/A | 1.3 Checkpoint: run schema-lint + fixtures, review diff, verify scope (contracts/ only) |
| deferred:open-tasks | N/A | 2.1 Write tests for `arbitrage_signal` recording — five families, async non-blocking, no-op when disabled |
| deferred:open-tasks | N/A | 2.2 Create `agent-coordinator/src/arbitrage_signal.py` — record via `AuditService.log_operation` (operation `arbitrage.s |
| deferred:open-tasks | N/A | 2.3 Register the `coordinator.signal` OTel meter in `telemetry.py` and emit labelled measurements (vendor/model/modality |
| deferred:open-tasks | N/A | 2.4 Checkpoint: run coordinator unit tests, review diff, verify scope |
| deferred:open-tasks | N/A | 2.5 Write tests for the kill-switch flag `ARBITRAGE_INSTRUMENT_ENABLED` — default off no-ops recording + telemetry |
| deferred:open-tasks | N/A | 2.6 Implement the feature-flag gate in `arbitrage_signal` and a shared `is_enabled()` helper |
| deferred:open-tasks | N/A | 2.7 Write tests for Cedar eligibility — programmatic-ineligible vendor rejected; eligibility change takes effect without |
| deferred:open-tasks | N/A | 2.8 Extend `cedar/schema.cedarschema` with Agent attributes `vendor` / `modality` / `data_residency` and add `forbid()`  |
| deferred:open-tasks | N/A | 2.9 Add eligibility values to `agents.yaml` / `agent_profiles.metadata` (mutable, NOTIFY-invalidated) — Claude lead-elig |
| deferred:open-tasks | N/A | 2.10 Checkpoint: run coordinator unit + policy tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.1 Write tests for the ToS monitor — changed content hash emits a compliance signal; unchanged emits none |
| deferred:open-tasks | N/A | 3.2 Create `agent-coordinator/src/probes/tos_monitor.py` — fetch + hash + diff the configured automation-clause URLs; re |
| deferred:open-tasks | N/A | 3.3 Write tests for the model canary — changed fingerprint emits a quality_drift signal |
| deferred:open-tasks | N/A | 3.4 Create `agent-coordinator/src/probes/model_canary.py` — fixed prompt per model, fingerprint response, record signal  |
| deferred:open-tasks | N/A | 3.5 Checkpoint: run probe tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.6 Register both probes as `WatchdogService` periodic jobs; verify they do not schedule when the instrument flag is off |
| deferred:open-tasks | N/A | 4.1 Write tests for the cost ledger — actual + counterfactual recorded; missing usage flagged estimated; headline metric |
| deferred:open-tasks | N/A | 4.2 Create `skills/vendor-arbitrage/scripts/ledger.py` + `eligibility.py` — load the versioned pricing/eligibility confi |
| deferred:open-tasks | N/A | 4.3 Write tests for the static-priority router — cheapest eligible tier; spill on 429; provenance recorded; rejects infe |
| deferred:open-tasks | N/A | 4.4 Create `skills/vendor-arbitrage/scripts/router.py` — `select_assignment(work_unit, feasible_set)`; feasibility via c |
| deferred:open-tasks | N/A | 4.5 Checkpoint: run skill tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.6 Write tests for tripwires — ToS-diff freezes a vendor; economic-kill fires below maintenance threshold; each writes  |
| deferred:open-tasks | N/A | 4.7 Create `skills/vendor-arbitrage/scripts/tripwires.py` — declarative thresholds; flip posture flag (vendor freeze) ho |
| deferred:open-tasks | N/A | 4.8 Write tests for the digest — reports net savings with/without estimates and lists fired tripwires |
| deferred:open-tasks | N/A | 4.9 Create `skills/vendor-arbitrage/scripts/digest.py` + `SKILL.md` — assemble the landscape report from the signal subs |
| deferred:open-tasks | N/A | 4.10 Checkpoint: run skill tests, review diff, verify scope |
| deferred:open-tasks | N/A | 5.1 Write an end-to-end test: feature-flag off ⇒ dispatch identical to baseline; flag on ⇒ a routed unit produces a ledg |
| deferred:open-tasks | N/A | 5.2 Cross-reference the new spec: mark the `observability` cost requirement fulfilled and the `symphony` `token-rate-lim |
| deferred:open-tasks | N/A | 5.3 Wire the `vendor-arbitrage` skill into `skills/install.sh` sync and add the kill-switch flag to docs |
| deferred:open-tasks | N/A | 5.4 Checkpoint: run full suite (coordinator + skills), `openspec validate --strict`, review cumulative diff, verify no s |
| deferred:open-tasks | N/A | 8.1 Run full `validate-feature` end-to-end on the sample frontend: deploy → smoke → gen-eval (Playwright path) → securit |
| deferred:open-tasks | N/A | 8.3 Verify `harness-engineering-features` rebases cleanly: cherry-pick its open commits onto this branch's HEAD and conf |
| deferred:open-tasks | N/A | 10.3 Commit on `openspec/fix-autopilot-archetype-and-apply-outcome` with subject `fix(autopilot): introduce validator ar |
| deferred:open-tasks | N/A | 10.4 Push to origin. (Left for the orchestrator.) |
| deferred:open-tasks | N/A | 11.1 (Out of scope for the change; done after merge:) update `docs/parallel-agentic-development.md` with the new dispatc |
| deferred:open-tasks | N/A | 11.2 (Out of scope:) consider whether structural enforcement of the loop-state.json contract (filesystem permissions, gi |
| deferred:open-tasks | N/A | 11.3 (Out of scope:) consider whether harness-silent-no-op detection (separate failure mode noted in proposal "Out of Sc |
| deferred:open-tasks | N/A | 6.1 Commit on `openspec/fix-compact-hook-phase-boundary-detection` with subject `fix(session-bootstrap): gate compact-ho |
| deferred:open-tasks | N/A | 6.2 Push to origin. |
| deferred:open-tasks | N/A | 6.3 (Out of scope for this change — done after merge to main:) update `docs/lessons-learned.md` if the gate semantics su |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | Planning |
| deferred:open-tasks | N/A | Implementation |
| deferred:open-tasks | N/A | Testing |
| deferred:open-tasks | N/A | Review |
| deferred:open-tasks | N/A | Done |
| deferred:open-tasks | N/A | Define detailed requirements |
| deferred:open-tasks | N/A | Implement core functionality |
| deferred:open-tasks | N/A | Write tests |
| deferred:open-tasks | N/A | Update documentation |
| deferred:open-tasks | N/A | Review and merge |
| deferred:open-tasks | N/A | 0.1 (S) Validate `contracts/db/schema.sql`, `contracts/openapi/v1.yaml`, |
| deferred:open-tasks | N/A | 1.1 (S) Write migration test: applying `026_usage_stats.sql` creates |
| deferred:open-tasks | N/A | 1.2 (S) Create `agent-coordinator/database/migrations/026_usage_stats.sql` |
| deferred:open-tasks | N/A | 1.3 (M) Write tests for `UsageRecord` schema + `record_hash` stability and |
| deferred:open-tasks | N/A | 1.4 (M) Implement `collector/schema.py` (`UsageRecord` + `record_hash`) and |
| deferred:open-tasks | N/A | Checkpoint: run migration + schema/pricing tests, review diff, verify scope |
| deferred:open-tasks | N/A | 1.5 (M) Write tests for the Claude adapter against fixture JSONL |
| deferred:open-tasks | N/A | 1.6 (M) Implement `collector/adapters/base.py` (adapter protocol + |
| deferred:open-tasks | N/A | 1.7 (M) Write tests for `collector/store.py`: incremental watermark resume, |
| deferred:open-tasks | N/A | 1.8 (M) Implement `collector/store.py` (watermark, dedupe, spool) and the |
| deferred:open-tasks | N/A | Checkpoint: run collector test suite, review diff, verify scope |
| deferred:open-tasks | N/A | 2.1 (M) Write API tests: `/usage/ingest` idempotent batch, `/usage/summary` |
| deferred:open-tasks | N/A | 2.2 (M) Implement `/usage/*` routes in `coordination_api.py` (reuse Bearer |
| deferred:open-tasks | N/A | 2.3 (S) Add `GET /events/usage` SSE endpoint (Bearer-auth, optional |
| deferred:open-tasks | N/A | Checkpoint: run API + SSE tests, review diff, verify scope |
| deferred:open-tasks | N/A | 3.1 (M) Scaffold `apps/usage-stats/` from the kanban-viz Vite/TS config; |
| deferred:open-tasks | N/A | 3.2 (M) Implement `useUsage.ts` (Bearer fetch, SSE primary, polling |
| deferred:open-tasks | N/A | 3.3 (M) Write component tests, then implement chart components |
| deferred:open-tasks | N/A | Checkpoint: run frontend test suite, typecheck, review diff, verify scope |
| deferred:open-tasks | N/A | 4.1 (S) Write a test that the session-end hook invokes the collector and |
| deferred:open-tasks | N/A | 4.2 (S) Wire collector invocation into session-end (`skills/session-bootstrap` |
| deferred:open-tasks | N/A | 4.3 (M) Write Codex adapter tests against fixture `rollout-*.jsonl` |
| deferred:open-tasks | N/A | Checkpoint: run hook + Codex tests, review diff, verify scope |
| deferred:open-tasks | N/A | 4.4 (M) Write Gemini adapter tests against fixture `telemetry.log` OTEL |
| deferred:open-tasks | N/A | 4.5 (S) Implement `collector/adapters/antigravity.py` as an explicit |
| deferred:open-tasks | N/A | 5.1 (M) Merge packages; run full backend + frontend suites; end-to-end |
| deferred:open-tasks | N/A | 5.2 (S) Document at `docs/usage-stats/README.md` (collector run, vendor |
| deferred:open-tasks | N/A | Checkpoint: full suite green, review cumulative diff, verify all scopes |
| deferred:open-tasks | N/A | 1.1 Write contract test at two levels: (a) `review-findings.schema.json` is |
| deferred:open-tasks | N/A | 1.2 Add a new self-contained |
| deferred:open-tasks | N/A | 1.3 Write test for shared `emit_finding()` and `record_phase_status()` |
| deferred:open-tasks | N/A | 1.4 Implement `emit_finding()` + `record_phase_status()` (e.g. |
| deferred:open-tasks | N/A | 1.5 Write test for the fixability classifier: mechanical finding-types |
| deferred:open-tasks | N/A | 1.6 Implement the classifier with a mechanical-type allowlist; default |
| deferred:open-tasks | N/A | 1.7 Write test for the narrow single-finding auto-fix step: one `auto-fix` |
| deferred:open-tasks | N/A | 1.8 Implement the narrow single-finding fixer: map a finding class to its |
| deferred:open-tasks | N/A | 1.9 Write test: the report renderer produces `validation-report.md` from |
| deferred:open-tasks | N/A | 1.10 Refactor SKILL.md §11/§12 report step to render from the findings file; |
| deferred:open-tasks | N/A | 1.C **Checkpoint**: `pytest skills/tests/validate-feature/` green; a sample |
| deferred:open-tasks | N/A | 2.1 Write test for the critical-subset runner: it executes only `smoke`, spec |
| deferred:open-tasks | N/A | 2.2 Implement the critical-subset runner reusing the existing phase scripts |
| deferred:open-tasks | N/A | 2.3 Write tests for wiring + inert-until-enabled + kill-switch: (a) fresh |
| deferred:open-tasks | N/A | 2.4 Add the `.githooks/pre-push` hook (inert no-op unless the |
| deferred:open-tasks | N/A | 2.5 Document the gate (install, kill-switch, `--no-verify`) in SKILL.md and |
| deferred:open-tasks | N/A | 2.C **Checkpoint**: with the hook installed, a drifted `tasks.md` blocks a |
| deferred:open-tasks | N/A | 3.1 Write test: on a clean tree `--ephemeral` runs in a scratch worktree |
| deferred:open-tasks | N/A | 3.2 Implement `--ephemeral` (+ `--include-dirty`) over the `worktree` skill |
| deferred:open-tasks | N/A | 3.3 Write test: under a stubbed cloud-harness `detect()`, `--ephemeral` |
| deferred:open-tasks | N/A | 3.4 Implement the cloud-harness fallback via `environment_profile.detect()`. |
| deferred:open-tasks | N/A | 3.C **Checkpoint**: after an `--ephemeral` run, `git status` on the branch |
| deferred:open-tasks | N/A | 4.1 Write test for the `triage_state` apply/render path: `approve` / `fix` / |
| deferred:open-tasks | N/A | 4.2 Implement the shared `triage_state` apply/render path (single source for |
| deferred:open-tasks | N/A | 4.3 Write test for `--auto` / `-y`: deterministic defaults — resolved |
| deferred:open-tasks | N/A | 4.4 Implement `--triage` (AskUserQuestion in-harness / CLI prompt loop) and |
| deferred:open-tasks | N/A | 4.5 Document `--triage` / `--auto` and the fixability/triage_state lifecycle in SKILL.md. |
| deferred:open-tasks | N/A | 4.C **Checkpoint**: a triage session marks a finding `skip`; a re-run skips |
| deferred:open-tasks | N/A | 5.1 Run `openspec validate validate-feature-findings-gate --strict` and fix |
| deferred:open-tasks | N/A | 5.2 Update `skills/validate-feature/SKILL.md` argument list + phase table to |
| deferred:open-tasks | N/A | 5.3 Sync runtime skill copies via `install.sh` (per CLAUDE.md skills guide). |

## Low / Info Findings

- **Low**: 633 findings
- **Info**: 0 findings

_(See JSON report for full details)_

## Recommendations

1. Run /fix-scrub --tier auto for quick lint fixes
2. Consolidate deferred items into a follow-up proposal
3. Consider running /fix-scrub --dry-run to preview remediation plan
