# Tasks: Harness Engineering Features

**Change ID**: harness-engineering-features
**Status**: Draft

## Phase 1: Foundation — Context Architecture & Memory Schema

- [x] 1.1 Write tests for CLAUDE.md restructuring — verify TOC links resolve, topic docs exist, line count constraint
  **Spec scenarios**: harness-engineering.2 (CLAUDE.md as context map), harness-engineering.2 (topic docs self-contained)
  **Design decisions**: D2 (CLAUDE.md restructure via file splitting)
  **Dependencies**: None

- [x] 1.2 Restructure CLAUDE.md — split into ~100-line TOC + topic docs under `docs/guides/`
  **Files**: `CLAUDE.md`, `docs/guides/workflow.md`, `docs/guides/python-environment.md`, `docs/guides/git-conventions.md`, `docs/guides/skills.md`, `docs/guides/worktree-management.md`, `docs/guides/documentation.md`, `docs/guides/session-completion.md`
  **Dependencies**: 1.1

- [x] 1.3 Write tests for failure metadata recording — verify structured tags, deduplication, query by failure_type
  **Spec scenarios**: harness-engineering.4 (structured failure recording)
  **Design decisions**: D4 (failure metadata as episodic memory tags)
  **Dependencies**: None

- [x] 1.4 Extend episodic memory tag conventions — add failure_type, capability_gap, affected_skill, severity, AND source tag prefixes to memory service documentation and validation. Document the source vocabulary: `self-reported` | `coordinator-emitted` | `session-log` | `transcript-mined`.
  **Files**: `agent-coordinator/src/memory.py`, `docs/guides/memory-conventions.md`
  **Dependencies**: 1.3

- [x] 1.5 Write tests for session-log Capability Gaps section — verify PhaseRecord round-trip (markdown ↔ dataclass), section appears between Trade-offs and Relevant Files, empty section parses to empty list, memory emission on `write_both()`
  **Spec scenarios**: harness-engineering.4 (session-log Capability Gaps Observed section)
  **Design decisions**: D10 (session-log Capability Gaps section)
  **Dependencies**: 1.3

- [x] 1.6 Extend session-log PhaseRecord with Capability Gaps section — add `CapabilityGap` dataclass and `capability_gaps: list[CapabilityGap]` field to `PhaseRecord`; extend renderer to emit `### Capability Gaps Observed` between Trade-offs and Relevant Files; extend `_parse_*` dispatchers to extract it; on `write_both()`, emit one memory entry per gap with `source:session-log` tag
  **Files**: `skills/session-log/scripts/phase_record.py`, `skills/session-log/scripts/extract_session_log.py`, `skills/session-log/SKILL.md`
  **Dependencies**: 1.4, 1.5

## Phase 2: Coordinator Extensions — Profiles, Scope, Work Queue

- [x] 2.1 Write tests for evaluator profile — verify read-only permissions, operation restrictions, work queue role filtering
  **Spec scenarios**: harness-engineering.5 (evaluator profile definition), harness-engineering.5 (work queue role separation)
  **Design decisions**: D5 (evaluator profile via existing profile system)
  **Dependencies**: None

- [x] 2.2 Add evaluator agent profile — database migration seeding evaluator profile, work queue agent_type preference logic
  **Files**: `agent-coordinator/database/migrations/026_evaluator_profile.sql`, `agent-coordinator/src/work_queue.py`, `agent-coordinator/src/profiles.py`
  **Dependencies**: 2.1

- [x] 2.3 Write tests for session scope enforcement — verify scope grant on task claim, out-of-scope detection, warning format
  **Spec scenarios**: harness-engineering.6 (scope lock on task claim), harness-engineering.6 (out-of-scope blocked)
  **Design decisions**: D6 (session scope as guardrail extension)
  **Dependencies**: None

- [x] 2.4 Implement session scope enforcement — extend guardrails to check file paths against session grants, connect work queue claim to session grant creation
  **Files**: `agent-coordinator/src/guardrails.py`, `agent-coordinator/src/session_grants.py`, `agent-coordinator/src/work_queue.py`
  **Dependencies**: 2.3

- [x] 2.5 Write tests for coordinator-side audit-triage LLM classifier — fixture-driven tests with mocked LLM responses covering (i) ring-buffer push from `log_operation` adds zero latency on the hot path, (ii) background task drains the buffer on cadence (mocked clock), (iii) classifier model is resolved via `agents_config.resolve_model(archetype, package_metadata={}, provider=...)` using the configured archetype/provider, (iv) system prompt is composed via `agents_config.compose_prompt(archetype, task_prompt)`, (v) classifier output with valid schema produces memory entries with `source:coordinator-emitted` + `prompt_version:N`, (vi) classifier output with invalid schema is dropped with a warning and NOT written to memory, (vii) archetype defaults to `analyst` and provider defaults to `claude_code`, both overridable via config. Use a stub LLM client that returns canned responses — no real API calls in CI.
  **Spec scenarios**: harness-engineering.4 (coordinator auto-emits capability gaps via LLM classifier)
  **Design decisions**: D9 (coordinator-side automatic capability-gap emission via LLM classifier)
  **Dependencies**: 1.4

- [x] 2.6 Implement coordinator-side audit-triage LLM classifier — extend `AuditService.log_operation` to push each audit entry into an in-memory ring buffer keyed by `(agent_id, session_id)` (hot path, no LLM); create `agent-coordinator/src/audit_triage.py` background task that drains the buffer on configurable cadence; resolve the classifier model via `agents_config.resolve_model()` against the configured archetype (default `analyst`) + provider (default `claude_code`); compose the prompt via `agents_config.compose_prompt(archetype, task_prompt)` where `task_prompt` is loaded from `agent-coordinator/src/audit_triage_prompts/v1.md` (versioned, code-reviewed); invoke with strict output-schema enforcement; valid findings get emitted to memory with `source:coordinator-emitted` + `prompt_version:1`; invalid responses are dropped with a warning. The LLM client SHALL dispatch to the provider matching the resolved archetype provider (claude_code → anthropic SDK, codex → openai SDK, gemini → google-genai SDK) — no hardcoded vendor lock-in. Config knobs in `config.yaml: audit.capability_gap_triage.*` (`enabled`, `archetype`, `provider`, `batch_size`, `batch_interval_minutes`, `prompt_version`). Default-off in CI, default-on in production.
  **Files**: `agent-coordinator/src/audit.py`, `agent-coordinator/src/audit_triage.py`, `agent-coordinator/src/audit_triage_prompts/v1.md`, `agent-coordinator/src/memory.py`, `agent-coordinator/config.yaml.example`, `agent-coordinator/pyproject.toml`, `agent-coordinator/tests/test_audit_capability_gaps.py`
  **Notes**: Reuses the existing archetype infrastructure in `agent-coordinator/src/agents_config.py` and `agent-coordinator/archetypes.yaml` — do NOT introduce a parallel model-selection path. The audit-triage task prompt lives at `agent-coordinator/src/audit_triage_prompts/v1.md` and is kept SEPARATE from the transcript-mining prompts (see D11) — do NOT attempt to unify them.
  **Dependencies**: 1.4, 2.5

## Phase 3: Review Loop Enhancement

**Note**: `convergence_loop.py` already has durable per-round checkpoints, `max_rounds` parameter (default 3), 3-point stall detection, and `ConvergenceResult` with `escalate_findings`. This phase extends the existing infrastructure rather than building from scratch. **Coordination risk**: PR #195 (ambient-review-ledger) plans to extract `refine-core` from this same file — landing order must be coordinated.

- [x] 3.1 Write tests for human escalation pathway and author-agent autonomous response — verify that when `reason="max_rounds"` or `reason="disagreement"`, the loop produces a structured escalation summary; verify that `fix_callback` is invoked per round and that author-agent responses to "fix" findings trigger re-review
  **Spec scenarios**: harness-engineering.1 (converges within limit), harness-engineering.1 (escalates on consensus failure)
  **Design decisions**: D1 (extend convergence_loop.py)
  **Dependencies**: None

- [x] 3.2 Add human escalation pathway and configurable convergence thresholds — extend `converge()` to accept `escalation_callback` for structured human escalation when `reason` is "max_rounds" or "disagreement"; make `BLOCKING_CRITICALITIES` and stall detection window configurable via parameters rather than hardcoded; wire `fix_callback` into an author-agent autonomous response pattern
  **Files**: `skills/autopilot/scripts/convergence_loop.py`, `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`
  **Dependencies**: 3.1

- [x] 3.3 Write tests for convergence metrics recording — verify episodic memory entries with iteration count, vendor agreement rate, convergence status
  **Spec scenarios**: harness-engineering.1 (records convergence metrics)
  **Design decisions**: D4 (failure metadata as episodic memory tags)
  **Dependencies**: 1.4, 3.2

- [x] 3.4 Add convergence metrics to episodic memory — after each `converge()` call completes, invoke `memory_callback` with structured metrics: rounds completed, findings per round, final convergence status, time elapsed, vendor agreement rate, and escalation count
  **Files**: `skills/autopilot/scripts/convergence_loop.py`
  **Dependencies**: 3.3

## Phase 4: Architecture Enforcement & Validation

- [x] 4.1 Write tests for structural linters — dependency direction, file-size, naming conventions
  **Spec scenarios**: harness-engineering.3 (dependency direction), harness-engineering.3 (file-size), harness-engineering.3 (naming conventions)
  **Design decisions**: D3 (architecture linters as Python scripts)
  **Dependencies**: None

- [x] 4.2 Implement structural linters — dependency direction validator, file-size checker, naming convention enforcer under `skills/validate-feature/scripts/linters/`
  **Files**: `skills/validate-feature/scripts/linters/dependency_direction.py`, `skills/validate-feature/scripts/linters/file_size.py`, `skills/validate-feature/scripts/linters/naming_conventions.py`, `skills/validate-feature/scripts/linters/__init__.py`
  **Dependencies**: 4.1

- [x] 4.3 Extend existing architecture phase with structural linters — the `--phase=architecture` already runs `validate_flows.py` for cross-layer flow validation; extend it to also invoke structural linters (dependency direction, file-size, naming) and merge both sets of findings into a single review-findings output
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

- [ ] 5.5 Write tests for multi-source mining and source attribution in /improve-harness — verify reader pulls from BOTH episodic memory (all `source:*` values) AND `session-log.md` "Capability Gaps Observed" sections under `openspec/changes/*/session-log.md`; verify dedup on `(capability_gap, affected_skill, session_id)` keeps a multi-source list; verify report includes per-finding source attribution and a summary line (e.g. "23% of findings surfaced in 2+ sources")
  **Spec scenarios**: harness-engineering.4 (/improve-harness multi-source mining), harness-engineering.4 (source attribution in report)
  **Design decisions**: D4 (shared tag schema with `source:*`), D10 (session-log as source)
  **Dependencies**: 5.1

- [ ] 5.6 Extend /improve-harness for multi-source mining and source attribution — `analyze_failures.py` reads memory entries AND scans `openspec/changes/**/session-log.md` for Capability Gaps Observed sections; dedupes findings keyed on `(capability_gap, affected_skill, session_id)` keeping a multi-source list; `generate_report.py` adds a Source column (and a cross-source-agreement summary). This is the shared machinery that Phase 6 transcript mining and D9 coordinator emission both plug into.
  **Files**: `skills/improve-harness/scripts/analyze_failures.py`, `skills/improve-harness/scripts/generate_report.py`, `skills/improve-harness/SKILL.md`
  **Dependencies**: 5.2, 5.5, 1.6, 2.6

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
  **Path**: `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` — `<encoded-cwd>` is the absolute cwd with every non-alphanumeric char replaced by `-` (e.g. `/Users/me/proj` → `-Users-me-proj`). Verified — already used in `skills/session-bootstrap/scripts/calibrate_token_proxy.py::_discover_newest_transcript`.
  **Schema**: JSONL one event per line; top-level `type`, `uuid`, `parentUuid`, `timestamp`, `sessionId`, `cwd`, `gitBranch`, `version`. Message events nest content blocks under `message.content[]` with `type` ∈ `text` | `thinking` | `tool_use` (`id`, `name`, `input`) | `tool_result` (`tool_use_id`). User vs assistant distinguished by top-level `type`. Token usage at `message.usage.{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}`.
  **Preferred API**: Use `@anthropic-ai/claude-agent-sdk`'s `listSessions()` / `getSessionMessages()` (and Python equivalents) over hand-parsing the JSONL — Anthropic owns version drift then. Hand-parsing is the fallback only.
  **Citation**: https://code.claude.com/docs/en/agent-sdk/sessions
  **Dependencies**: 6.2

- [ ] 6.4 Implement Claude Code web adapter (CLI bridge)
  **Files**: `skills/collect-transcripts/scripts/adapters/claude_code_web.py`, `skills/collect-transcripts/tests/test_claude_code_web.py`
  **Approach**: NOT a direct web-API client. Implementation invokes `claude --teleport <session-id>` to pull the cloud session onto local disk, then delegates to the `claude_code_cli` adapter. The Anthropic `/v1/sessions` endpoint on `api.anthropic.com` belongs to the *separate* Managed Agents product, not Claude Code web; reverse-engineering claude.ai's private endpoints is explicitly out of scope (third-party tools doing this have repeatedly broken on unannounced API changes — see https://github.com/simonw/claude-code-transcripts).
  **Discovery**: Session ID is available in `CLAUDE_CODE_REMOTE_SESSION_ID` env var (with `cse_` prefix; URL form uses `session_` prefix).
  **Fail-soft**: skip with warning if `claude` CLI not on PATH, if `--teleport` exits non-zero, or if no session ID is supplied.
  **Citation**: https://code.claude.com/docs/en/claude-code-on-the-web
  **Dependencies**: 6.2, 6.3

- [ ] 6.5 Implement Codex CLI adapter
  **Files**: `skills/collect-transcripts/scripts/adapters/codex_cli.py`, `skills/collect-transcripts/tests/test_codex_cli.py`
  **Path**: `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<timestamp>-<session-id>.jsonl` (default `$CODEX_HOME` = `~/.codex`). Note: `~/.codex/history.jsonl` is command history only — NOT the rollout transcript.
  **Schema**: JSONL, one `RolloutLine` per line. Each line is a `RolloutItem` enum variant: `SessionMeta` (header — `session_id`, `source`, `timestamp`, `model_provider`), `EventMsg` (UI replay events incl. `UserMessage`), `ResponseItem` (the full Responses-API turn — `message`, `function_call` with `name`/`arguments`/`call_id`, `function_call_output` matching `call_id`, `reasoning`). Distinguish: user msg = `EventMsg::UserMessage` OR `ResponseItem::message` with `role:"user"`; assistant text = `ResponseItem::message` with `role:"assistant"`; tool call = `ResponseItem::function_call`; tool result = `ResponseItem::function_call_output`.
  **Schema versioning**: Pin to a specific `RolloutLine.json` schema version, validate on load. Schema is emitted by `codex app-server generate-internal-json-schema`; re-validate on minor Codex CLI bumps.
  **Citations**: https://github.com/openai/codex/discussions/3827 ; https://github.com/openai/codex/pull/3380 ; https://github.com/openai/codex/pull/14434
  **Dependencies**: 6.2

- [ ] 6.6 Implement Codex web adapter (CLI bridge)
  **Files**: `skills/collect-transcripts/scripts/adapters/codex_web.py`, `skills/collect-transcripts/tests/test_codex_web.py`
  **Approach**: NOT a direct web-API client. The `chatgpt.com/backend-api/codex/*` endpoints are undocumented and ChatGPT-cookie-authed. Implementation invokes `codex cloud` to pull cloud-task transcripts onto local disk (where they land as standard rollout JSONL) and then delegates to the `codex_cli` adapter. Mirrors the `claude_code_web` pattern exactly.
  **Fail-soft**: skip with warning if `codex` CLI not on PATH, if not authenticated, or if `codex cloud` returns no sessions.
  **Citations**: https://developers.openai.com/codex/cloud ; https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
  **Dependencies**: 6.2, 6.5

- [ ] 6.7 Implement Gemini CLI adapter
  **Files**: `skills/collect-transcripts/scripts/adapters/gemini_cli.py`, `skills/collect-transcripts/tests/test_gemini_cli.py`
  **Path**: `~/.gemini/tmp/<project_hash>/chats/session-YYYY-MM-DDTHH-mm-<short_id>.json` (JSONL despite the `.json` extension). `<project_hash>` derived from project root path. Related sibling paths: `~/.gemini/tmp/<project_hash>/checkpoints/` (checkpoint conversation data), `~/.gemini/history/<project_hash>/` (shadow git of file state).
  **Schema**: Initial metadata record: `{sessionId, projectHash, startTime, lastUpdated, summary?, directories?, kind?:'main'|'subagent', messages:[]}`. Per-message: `MessageRecord {id, timestamp, type:'user'|'gemini', content:PartListUnion, displayContent?, toolCalls?:ToolCallRecord[], thoughts?, tokens?, model?}`. Updates appear as `{$set:{...}}`, branches as `{$rewindTo:messageId}`. `content` follows Google GenAI `Part` union (`text`, `functionCall`, `functionResponse`, `inlineData`). Tool calls in `toolCalls[]` with `displayName`, `description`, args, result.
  **Schema versioning**: Pin to a `chatRecordingService.ts` commit SHA; version-detect via the metadata header. Path moved from `~/.gemini/sessions/` to `~/.gemini/tmp/<hash>/chats/` during 2025 — assume further moves and guard with path-discovery logic.
  **Citations**: https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/session-management.md ; https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/chatRecordingService.ts
  **Dependencies**: 6.2

- [ ] 6.8 Extend sanitizer for transcript-specific structures
  **Files**: `skills/session-log/scripts/sanitize_session_log.py`, `skills/collect-transcripts/scripts/sanitize_events.py`, `skills/session-log/tests/test_sanitize_session_log.py`
  **Notes**: Add coverage for tool-call argument blobs and tool-result outputs — common accidental-leak sites that the existing session-log sanitizer doesn't target. Existing redaction rules (secrets, high-entropy strings, env paths) must continue passing.
  **Spec scenarios**: harness-engineering.8 (sanitization precedes any LLM analysis)
  **Dependencies**: 6.2

- [ ] 6.9 Implement triage pass with dry-run mode
  **Files**: `skills/collect-transcripts/scripts/triage.py`, `skills/collect-transcripts/tests/test_triage.py`, `skills/collect-transcripts/config.yaml.example`
  **Notes**: Triage model is resolved via the archetype system — default `archetype: analyst`, default `provider: claude_code`, both configurable via `skills/collect-transcripts/config.yaml: triage.{archetype, provider}`. Resolution uses `agents_config.resolve_model()` from the coordinator (skills can import directly OR call coordinator HTTP `/archetypes/resolve_for_phase` — pick whichever fits the skill's runtime). System prompt composed via `agents_config.compose_prompt(archetype, task_prompt)` where `task_prompt` lives in `skills/collect-transcripts/prompts/triage_v1.md` and is kept SEPARATE from the coordinator's audit-triage prompt (see D11). Configurable struggle threshold. `--dry-run` mode prints planned per-session and total estimated operation count without making any API calls. Default-off in CI.
  **Spec scenarios**: harness-engineering.8 (triage scores every ingested session), harness-engineering.8 (mining is opt-in)
  **Dependencies**: 6.2, 6.8

- [ ] 6.10 Implement deep-analysis writer
  **Files**: `skills/collect-transcripts/scripts/deep_analyze.py`, `skills/collect-transcripts/tests/test_deep_analyze.py`
  **Notes**: Deep-analysis model resolved via archetype system — default `archetype: reviewer` (premium tier), default `provider: claude_code`, both configurable via `skills/collect-transcripts/config.yaml: deep_analysis.{archetype, provider}`. Same `agents_config.resolve_model()` + `compose_prompt()` pattern as the triage task. Task prompt lives in `skills/collect-transcripts/prompts/deep_analysis_v1.md` — kept SEPARATE from the coordinator's audit-triage prompt and from the transcript-triage prompt (see D11). Emits findings under the D4 tag schema with `source:transcript-mined`. Uses the coordinator's `remember` MCP tool.
  **Spec scenarios**: harness-engineering.8 (deep analysis runs on flagged sessions only)
  **Dependencies**: 1.4, 6.9

- [ ] 6.11 Verify `/improve-harness` surfaces transcript-sourced findings end-to-end
  **Files**: `skills/improve-harness/tests/test_transcript_source.py`, `skills/collect-transcripts/tests/test_end_to_end.py`
  **Notes**: The source-attribution and multi-source-mining machinery was already built in Task 5.6. This task is the *end-to-end verification* that transcript-mined findings flow through unchanged: feed a fixture transcript through triage + deep-analyze, then run `/improve-harness` and assert the resulting report contains the finding with `source:transcript-mined` in its source list.
  **Spec scenarios**: harness-engineering.8 (improve-harness surfaces transcript-sourced findings)
  **Dependencies**: 5.6, 6.10

## Phase 7: Integration & Documentation

- [ ] 7.1 Update docs and run skills install — sync new skills to runtime copies, update docs/lessons-learned.md with harness engineering patterns including transcript-mining design notes
  **Files**: `docs/lessons-learned.md`, `docs/parallel-agentic-development.md`
  **Dependencies**: All previous tasks

- [ ] 7.2 Run full validation — `openspec validate`, test suite, linter checks on all modified files
  **Dependencies**: 7.1
