# Tasks: Harness Engineering Features

**Change ID**: harness-engineering-features
**Status**: Draft

## Phase 1: Foundation — Context Architecture & Memory Schema

- [ ] 1.1 Write tests for CLAUDE.md restructuring — verify TOC links resolve, topic docs exist, line count constraint
  **Spec scenarios**: harness-engineering.2 (CLAUDE.md as context map), harness-engineering.2 (topic docs self-contained)
  **Design decisions**: D2 (CLAUDE.md restructure via file splitting)
  **Dependencies**: None

- [ ] 1.2 Restructure CLAUDE.md — split into ~100-line TOC + topic docs under `docs/guides/`
  **Files**: `CLAUDE.md`, `docs/guides/workflow.md`, `docs/guides/python-environment.md`, `docs/guides/git-conventions.md`, `docs/guides/skills.md`, `docs/guides/worktree-management.md`, `docs/guides/documentation.md`, `docs/guides/session-completion.md`
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for failure metadata recording — verify structured tags, deduplication, query by failure_type
  **Spec scenarios**: harness-engineering.4 (structured failure recording)
  **Design decisions**: D4 (failure metadata as episodic memory tags)
  **Dependencies**: None

- [ ] 1.4 Extend episodic memory tag conventions — add failure_type, capability_gap, affected_skill, severity tag prefixes to memory service documentation and validation
  **Files**: `agent-coordinator/src/memory.py`, `docs/guides/memory-conventions.md`
  **Dependencies**: 1.3

## Phase 2: Coordinator Extensions — Profiles, Scope, Work Queue

- [ ] 2.1 Write tests for evaluator profile — verify read-only permissions, operation restrictions, work queue role filtering
  **Spec scenarios**: harness-engineering.5 (evaluator profile definition), harness-engineering.5 (work queue role separation)
  **Design decisions**: D5 (evaluator profile via existing profile system)
  **Dependencies**: None

- [ ] 2.2 Add evaluator agent profile — database migration seeding evaluator profile, work queue agent_type preference logic
  **Files**: `agent-coordinator/supabase/migrations/017_evaluator_profile.sql`, `agent-coordinator/src/work_queue.py`, `agent-coordinator/src/profiles.py`
  **Dependencies**: 2.1

- [ ] 2.3 Write tests for session scope enforcement — verify scope grant on task claim, out-of-scope detection, warning format
  **Spec scenarios**: harness-engineering.6 (scope lock on task claim), harness-engineering.6 (out-of-scope blocked)
  **Design decisions**: D6 (session scope as guardrail extension)
  **Dependencies**: None

- [ ] 2.4 Implement session scope enforcement — extend guardrails to check file paths against session grants, connect work queue claim to session grant creation
  **Files**: `agent-coordinator/src/guardrails.py`, `agent-coordinator/src/session_grants.py`, `agent-coordinator/src/work_queue.py`
  **Dependencies**: 2.3

## Phase 3: Review Loop Enhancement

- [ ] 3.1 Write tests for convergence loop iteration control — verify iteration counting, configurable max, auto-escalation
  **Spec scenarios**: harness-engineering.1 (converges within limit), harness-engineering.1 (escalates on consensus failure)
  **Design decisions**: D1 (extend convergence_loop.py)
  **Dependencies**: None

- [ ] 3.2 Extend convergence_loop.py — add iteration counter, configurable max_iterations, automatic escalation on exhaustion, convergence metrics recording
  **Files**: `skills/auto-dev-loop/scripts/convergence_loop.py`, `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`
  **Dependencies**: 3.1

- [ ] 3.3 Write tests for convergence metrics recording — verify episodic memory entries with iteration count, vendor agreement rate
  **Spec scenarios**: harness-engineering.1 (records convergence metrics)
  **Design decisions**: D4 (failure metadata as episodic memory tags)
  **Dependencies**: 1.4, 3.2

- [ ] 3.4 Add convergence metrics to episodic memory — record iteration count, findings per iteration, convergence status, time elapsed, vendor agreement rate
  **Files**: `skills/auto-dev-loop/scripts/convergence_loop.py`
  **Dependencies**: 3.3

## Phase 4: Architecture Enforcement & Validation

- [ ] 4.1 Write tests for structural linters — dependency direction, file-size, naming conventions
  **Spec scenarios**: harness-engineering.3 (dependency direction), harness-engineering.3 (file-size), harness-engineering.3 (naming conventions)
  **Design decisions**: D3 (architecture linters as Python scripts)
  **Dependencies**: None

- [ ] 4.2 Implement structural linters — dependency direction validator, file-size checker, naming convention enforcer under `skills/validate-feature/scripts/linters/`
  **Files**: `skills/validate-feature/scripts/linters/dependency_direction.py`, `skills/validate-feature/scripts/linters/file_size.py`, `skills/validate-feature/scripts/linters/naming_conventions.py`, `skills/validate-feature/scripts/linters/__init__.py`
  **Dependencies**: 4.1

- [ ] 4.3 Integrate linters into validate-feature —  wire linters into `--phase=architecture`, format output as review-findings
  **Files**: `skills/validate-feature/SKILL.md`, `skills/validate-feature/scripts/run_architecture_linters.py`
  **Dependencies**: 4.2

## Phase 5: New Skills — Improve Harness & Agent Metrics

- [ ] 5.1 Write tests for /improve-harness skill — verify failure pattern querying, grouping, ranking, report format
  **Spec scenarios**: harness-engineering.4 (failure pattern analysis), harness-engineering.4 (report-to-feature pipeline)
  **Design decisions**: D4 (failure metadata as episodic memory tags)
  **Dependencies**: 1.4

- [ ] 5.2 Create /improve-harness skill — query episodic memory for failure patterns, group by capability_gap, rank by frequency/severity, generate structured report, support creating OpenSpec proposals from findings
  **Files**: `skills/improve-harness/SKILL.md`, `skills/improve-harness/scripts/analyze_failures.py`, `skills/improve-harness/scripts/generate_report.py`
  **Dependencies**: 5.1

- [ ] 5.3 Write tests for /agent-metrics skill — verify audit trail queries, throughput calculations, failure rate computation
  **Spec scenarios**: harness-engineering.7 (throughput report), harness-engineering.7 (failure rate analysis), harness-engineering.7 (capability gap frequency)
  **Design decisions**: D7 (metrics skill uses audit trail queries)
  **Dependencies**: None

- [ ] 5.4 Create /agent-metrics skill — query audit trail and episodic memory, compute throughput metrics, generate markdown reports
  **Files**: `skills/agent-metrics/SKILL.md`, `skills/agent-metrics/scripts/query_metrics.py`, `skills/agent-metrics/scripts/generate_dashboard.py`
  **Dependencies**: 5.3

## Phase 6: Integration & Documentation

- [ ] 6.1 Update docs and run skills install — sync new skills to runtime copies, update docs/lessons-learned.md with harness engineering patterns
  **Files**: `docs/lessons-learned.md`, `docs/parallel-agentic-development.md`
  **Dependencies**: All previous tasks

- [ ] 6.2 Run full validation — `openspec validate`, test suite, linter checks on all modified files
  **Dependencies**: 6.1
