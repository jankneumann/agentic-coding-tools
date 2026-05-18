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
  **Files**: `agent-coordinator/database/migrations/017_evaluator_profile.sql`, `agent-coordinator/src/work_queue.py`, `agent-coordinator/src/profiles.py`
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
  **Files**: `skills/autopilot/scripts/convergence_loop.py`, `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`
  **Dependencies**: 3.1

- [ ] 3.3 Write tests for convergence metrics recording — verify episodic memory entries with iteration count, vendor agreement rate
  **Spec scenarios**: harness-engineering.1 (records convergence metrics)
  **Design decisions**: D4 (failure metadata as episodic memory tags)
  **Dependencies**: 1.4, 3.2

- [ ] 3.4 Add convergence metrics to episodic memory — record iteration count, findings per iteration, convergence status, time elapsed, vendor agreement rate
  **Files**: `skills/autopilot/scripts/convergence_loop.py`
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

## Phase 6: Session Transcript Mining

- [ ] 6.1 Write tests for normalized event schema and adapter base class — fixture-based round-trip tests per adapter (fixtures live under `skills/collect-transcripts/tests/fixtures/<harness>/`)
  **Spec scenarios**: harness-engineering.8 (adapter discovers and normalizes)
  **Design decisions**: D8 (transcript ingestion via adapter-based skill)
  **Dependencies**: 1.4 (memory tag conventions)

- [ ] 6.2 Define normalized event schema + adapter base class
  **Files**: `skills/collect-transcripts/SKILL.md`, `skills/collect-transcripts/references/event-schema.md`, `skills/collect-transcripts/scripts/adapters/base.py`, `skills/collect-transcripts/scripts/normalize.py`
  **Dependencies**: 6.1

- [ ] 6.3 Implement Claude Code CLI adapter
  **Files**: `skills/collect-transcripts/scripts/adapters/claude_code_cli.py`, `skills/collect-transcripts/tests/test_claude_code_cli.py`
  **Notes**: Reads `~/.claude/projects/<urlencoded-cwd>/<session-id>.jsonl`. Reuse the path-discovery pattern from `skills/session-bootstrap/scripts/calibrate_token_proxy.py::_discover_newest_transcript` (path verified — already used in token calibration).
  **Dependencies**: 6.2

- [ ] 6.4 Implement Claude Code web adapter
  **Files**: `skills/collect-transcripts/scripts/adapters/claude_code_web.py`, `skills/collect-transcripts/tests/test_claude_code_web.py`
  **Notes**: Fetches sessions via the Anthropic Claude Code web API. Endpoint surface must be verified against current API docs before locking the contract. Must fail soft on auth missing or endpoint absent (spec: "Adapter fails soft on source unavailability").
  **Dependencies**: 6.2

- [ ] 6.5 Implement Codex CLI adapter
  **Files**: `skills/collect-transcripts/scripts/adapters/codex_cli.py`, `skills/collect-transcripts/tests/test_codex_cli.py`
  **Notes**: Reads from `~/.codex/sessions/` (verify path on current Codex CLI version before implementation). Tool calls use OpenAI `function_call`/`function_response` blocks — normalize to the common event schema's `tool_use` / `tool_result` events.
  **Dependencies**: 6.2

- [ ] 6.6 Implement Codex web adapter (best-effort)
  **Files**: `skills/collect-transcripts/scripts/adapters/codex_web.py`, `skills/collect-transcripts/tests/test_codex_web.py`
  **Notes**: Investigate availability of an OpenAI Codex web transcript-fetch endpoint. If no stable endpoint exists at v1 ship time, ship as a stub that fails soft with a documented fallback (CLI export → process via `codex_cli` adapter). Decision must be captured in the adapter's docstring.
  **Dependencies**: 6.2

- [ ] 6.7 Implement Gemini CLI adapter
  **Files**: `skills/collect-transcripts/scripts/adapters/gemini_cli.py`, `skills/collect-transcripts/tests/test_gemini_cli.py`
  **Notes**: Reads Gemini CLI session history (verify path on current version — has changed across Gemini CLI releases). Normalize Gemini `parts` array format to the common event schema.
  **Dependencies**: 6.2

- [ ] 6.8 Extend sanitizer for transcript-specific structures
  **Files**: `skills/session-log/scripts/sanitize_session_log.py`, `skills/collect-transcripts/scripts/sanitize_events.py`, `skills/session-log/tests/test_sanitize_session_log.py`
  **Notes**: Add coverage for tool-call argument blobs and tool-result outputs — common accidental-leak sites that the existing session-log sanitizer doesn't target. Existing redaction rules (secrets, high-entropy strings, env paths) must continue passing.
  **Spec scenarios**: harness-engineering.8 (sanitization precedes any LLM analysis)
  **Dependencies**: 6.2

- [ ] 6.9 Implement triage pass with dry-run mode
  **Files**: `skills/collect-transcripts/scripts/triage.py`, `skills/collect-transcripts/tests/test_triage.py`
  **Notes**: Cheap-model scoring with configurable model (default `claude-haiku-4-5`) and configurable struggle threshold. `--dry-run` mode prints planned per-session and total cost without making any API calls. Default-off in CI.
  **Spec scenarios**: harness-engineering.8 (triage scores every ingested session), harness-engineering.8 (mining is opt-in)
  **Dependencies**: 6.2, 6.8

- [ ] 6.10 Implement deep-analysis writer
  **Files**: `skills/collect-transcripts/scripts/deep_analyze.py`, `skills/collect-transcripts/tests/test_deep_analyze.py`
  **Notes**: Emits findings under the D4 tag schema with an additional `source:transcript-mined` tag. Uses the coordinator's `remember` MCP tool.
  **Spec scenarios**: harness-engineering.8 (deep analysis runs on flagged sessions only)
  **Dependencies**: 1.4, 6.9

- [ ] 6.11 Wire `/improve-harness` to surface transcript-sourced findings
  **Files**: `skills/improve-harness/scripts/analyze_failures.py`, `skills/improve-harness/scripts/generate_report.py`, `skills/improve-harness/tests/`
  **Notes**: Add a "Source" column (self-reported / coordinator-emitted / transcript-mined) to the report and a summary of the share each source contributed, so operators can see which signals dominate.
  **Spec scenarios**: harness-engineering.8 (improve-harness surfaces transcript-sourced findings)
  **Dependencies**: 5.2, 6.10

## Phase 7: Integration & Documentation

- [ ] 7.1 Update docs and run skills install — sync new skills to runtime copies, update docs/lessons-learned.md with harness engineering patterns including transcript-mining design notes
  **Files**: `docs/lessons-learned.md`, `docs/parallel-agentic-development.md`
  **Dependencies**: All previous tasks

- [ ] 7.2 Run full validation — `openspec validate`, test suite, linter checks on all modified files
  **Dependencies**: 7.1
