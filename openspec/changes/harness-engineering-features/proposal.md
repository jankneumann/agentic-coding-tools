# Proposal: Harness Engineering Features

**Change ID**: harness-engineering-features
**Status**: Draft
**Created**: 2026-04-08
**Author**: Claude (Opus 4.6)

## Summary

Implement seven features inspired by OpenAI's [Harness Engineering](https://openai.com/index/harness-engineering/) blog post to improve the coordinator and skill infrastructure. The harness engineering philosophy — "Agent = Model + Harness" — identifies that compounding improvements to agent scaffolding, context management, and feedback loops yield exponential returns. This proposal applies those principles to our existing multi-agent coordination system.

## Why

OpenAI demonstrated that a team of 3-7 engineers shipped ~1M lines of code with zero manually-written source code over five months, achieving 3.5 PRs per engineer per day. The key insight: **the fix is never "try harder" — it's always "what capability is missing from the harness?"** Their eight principles (progressive context disclosure, mechanical architecture enforcement, agent-to-agent review loops, generation/evaluation separation, one-task-per-session focus, filesystem-as-memory, and capability-driven self-improvement) map directly onto gaps in our current infrastructure.

Our system already has strong foundations — DAG scheduling, multi-vendor review consensus, episodic memory, trust levels, scope enforcement — but these operate as independent capabilities rather than a unified harness engineering loop. This proposal connects and extends them to create the compounding flywheel that OpenAI describes.

## What Changes

### Feature 1: Agent-to-Agent Review Loops
Extend the existing `convergence_loop.py` and `consensus_synthesizer.py` to implement tighter review-iterate-converge cycles. Currently, review dispatch and consensus happen as discrete steps. This adds: author-agent autonomous response to review findings, configurable convergence thresholds, and automatic escalation to humans only when agent consensus fails after N iterations.

**Existing foundations**: `autopilot/scripts/convergence_loop.py`, `parallel-infrastructure/scripts/consensus_synthesizer.py`, `parallel-infrastructure/scripts/review_dispatcher.py`

### Feature 2: Progressive Context Architecture
Restructure the monolithic CLAUDE.md into a tiered context system: a lightweight (~100-line) table-of-contents entry point pointing to structured, topic-specific docs. This follows the same pattern successfully used in the agentic-newsletter-aggregator project for CLAUDE.md files that have grown too large. OpenAI replaced their 800-line AGENTS.md with a 100-line TOC and saw immediate improvements.

**Existing foundations**: Current CLAUDE.md, `docs/` directory structure

### Feature 3: Mechanical Architecture Enforcement
Add structural linters as a coordinator-integrated validation phase. Dependency direction validators, file-size limits, naming convention checkers, and layer boundary tests — with agent-readable remediation instructions baked into error messages so failed CI becomes self-correcting context. Integrate as a new `--phase=architecture` in `/validate-feature`.

**Existing foundations**: `skills/tech-debt-analysis/scripts/`, `skills/validate-flows/scripts/validate_flows.py`, `skills/refresh-architecture/scripts/`

### Feature 4: Capability Gap Detection & Harness Self-Improvement
Add structured failure pattern recording in episodic memory. A new `/improve-harness` skill analyzes these patterns and generates analysis reports. A companion skill takes reports and creates OpenSpec feature proposals from them with human input for guidance and prioritization — similar to applying `/explore-feature` + `/plan-feature` but grounded in empirical failure data.

**Existing foundations**: `agent-coordinator/src/memory.py` (episodic memory with tags and relevance scoring)

### Feature 5: Generation/Evaluation Separation
Formalize an evaluator role in the agent profile system. Add an `evaluator` agent type with read-only permissions and specialized evaluation prompts. The coordinator's work queue enforces that evaluation tasks are never assigned to the same agent that generated the work.

**Existing foundations**: `agent-coordinator/evaluation/gen_eval/orchestrator.py`, `agent-coordinator/src/profiles.py`, `agent-coordinator/src/session_grants.py`

### Feature 6: Session Focus Enforcement
Add single-task session scoping to the coordinator. When an agent claims a task from the work queue, the coordinator locks that agent to that task's file scope. Attempts to modify files outside scope trigger guardrail warnings. Builds on existing `session_grants.py` and `scope_checker.py`.

**Existing foundations**: `agent-coordinator/src/session_grants.py`, `skills/parallel-infrastructure/scripts/scope_checker.py`, `agent-coordinator/src/guardrails.py`

### Feature 7: Agent Throughput Dashboard & Metrics
Add throughput tracking using the existing audit trail and telemetry: PRs opened, tasks completed, review cycles per PR, time-to-merge, failure rates by agent type, capability gap frequency. Surface via a `/agent-metrics` skill that generates reports from audit data and OpenTelemetry metrics.

**Existing foundations**: `agent-coordinator/src/telemetry.py` (OpenTelemetry/Prometheus), `agent-coordinator/src/audit.py`, `agent-coordinator/evaluation/reports/generator.py`

### Feature 8: Session Transcript Mining
A new `/collect-transcripts` skill ingests raw session transcripts from each supported coding-agent harness via vendor-specific adapters that normalize to a common event schema. v1 adapters: **`claude_code_cli`** (reads `~/.claude/projects/<encoded-cwd>/*.jsonl`, prefers Anthropic Agent SDK helpers over hand-parsing), **`claude_code_web`** (CLI bridge — invokes `claude --teleport` to materialize cloud sessions as local JSONL, then delegates), **`codex_cli`** (reads `$CODEX_HOME/sessions/.../rollout-*.jsonl`, pinned to OpenAI's generated `RolloutLine.json` schema), **`codex_web`** (CLI bridge via `codex cloud`), and **`gemini_cli`** (reads `~/.gemini/tmp/<project_hash>/chats/session-*.json`, pinned to a `chatRecordingService.ts` commit SHA). Neither cloud vendor exposes a documented direct transcript API, so the web adapters route through the vendor's own CLI bridge rather than reverse-engineering private endpoints. Raw normalized events land on disk under `docs/transcripts/<date>/<session-id>.jsonl` (filesystem-as-memory). A cheap-model triage pass scores every session; only flagged outliers get a deep read whose structured findings are written to episodic memory using Feature 4's `capability_gap:*` tag schema with `source:transcript-mined`. `/improve-harness` consumes the resulting memory entries unchanged — transcript mining is a new *signal source*, not a new analysis path. This captures the un-summarized struggle signal (retry counts, tool-error sequences, user corrections, scope-violation attempts) that agent self-reports systematically under-report.

**Existing foundations**: `skills/session-bootstrap/scripts/calibrate_token_proxy.py` (already reads `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`), `skills/session-log/scripts/sanitize_session_log.py` (secret/path redaction reused for transcript sanitization), Feature 4's `/improve-harness` skill (downstream consumer), `agent-coordinator/src/memory.py` (D4 tag schema is the integration point).

### Feature 9: Multi-Source Capability-Gap Signal Pipeline
Broaden Feature 4 from "agent self-tagging via `remember`" to a four-source pipeline writing into a shared D4 tag schema. Sources: (a) agent self-reports via `remember` (existing), (b) coordinator-emitted signals from `audit.py` pattern matching (D9 — retry storms, validation re-failures, scope violations, lock contention) auto-recorded with no agent involvement, (c) session-log "Capability Gaps Observed" structured section at phase boundaries (D10 — agent self-report at a natural reflection point, mined from `session-log.md` and mirrored to memory), and (d) transcript-mined findings (D8/Feature 8). `/improve-harness` consumes the union of all four sources, deduplicates on `(capability_gap, affected_skill, session_id)`, and annotates each finding with the set of sources that surfaced it — cross-source agreement is the strongest signal.

**Existing foundations**: `agent-coordinator/src/audit.py::AuditService.log_operation` (hook point for D9 pattern matcher), `skills/session-log/scripts/phase_record.py` (extension point for D10 `capability_gaps` field), Feature 4's `/improve-harness` skill (consumer; extended to read session-log files and surface source attribution).

## Approaches Considered

### Approach A: Incremental Extension (Recommended)

**Description**: Extend existing infrastructure files and patterns in-place. Each feature adds to existing services (convergence_loop, memory, profiles, scope_checker, telemetry) rather than creating new standalone systems. The CLAUDE.md restructuring happens as a direct refactor.

**Pros**:
- Minimal new code — leverages existing tested foundations
- No new services to deploy or maintain
- Follows established patterns (skill scripts, coordinator services)
- Each feature is independently shippable — can be delivered incrementally
- Lower risk of breaking existing workflows

**Cons**:
- May require careful refactoring of existing code
- Features are somewhat coupled to current architecture decisions
- Harder to parallelize implementation (shared file modifications)

**Effort**: L (large — 7 features, but each individually M or S)

### Approach B: New Harness Layer

**Description**: Create a dedicated `harness/` directory at the repo root containing a unified harness engineering subsystem. New services for context management, architecture enforcement, capability tracking, and metrics. CLAUDE.md becomes a thin pointer to the harness layer.

**Pros**:
- Clean separation of harness concerns from existing infrastructure
- Easier to parallelize implementation (separate directory tree)
- Can design the subsystem holistically rather than incrementally
- More closely mirrors the OpenAI model of "harness as a distinct concern"

**Cons**:
- Significant new code and abstractions
- Risk of duplicating existing functionality
- Another subsystem to maintain alongside coordinator and skills
- Integration with existing services adds complexity

**Effort**: XL (new subsystem + integration layer)

### Approach C: Coordinator-First

**Description**: Implement all features as new coordinator services and MCP tools. The coordinator becomes the single source of truth for all harness engineering capabilities (context serving, architecture rules, capability tracking, metrics, scope enforcement).

**Pros**:
- Single, consistent service interface (MCP tools)
- Strong consistency via PostgreSQL backend
- All capabilities available to all agent types (CLI and cloud)
- Audit trail built-in

**Cons**:
- Increases coordinator surface area significantly (already 12 services, 19 tools)
- Some features (CLAUDE.md restructuring, linter scripts) don't naturally fit as coordinator services
- Heavier deployment footprint
- Coordinator downtime would block more workflows

**Effort**: L (new services + migrations + MCP tools)

### Selected Approach

**Approach A: Incremental Extension** — Selected by user. The incremental approach maximizes reuse of existing foundations. Features like convergence_loop extension, CLAUDE.md restructuring, and scope_checker enhancement are natural evolutions of existing code. The coordinator already has the primitives needed (memory, profiles, work queue, audit) — we just need to wire them together with harness engineering patterns. This approach also allows each feature to ship independently, reducing risk.

## Success Criteria

1. CLAUDE.md reduced to ~100 lines with structured TOC pointing to topic-specific docs
2. Review convergence loop has configurable iteration limit with automatic human escalation
3. At least 5 architectural rules enforced mechanically via linters with agent-readable error messages
4. Failure patterns recorded in episodic memory with structured metadata (failure_type, capability_gap)
5. `/improve-harness` skill generates actionable reports from failure patterns
6. Evaluator agent profile exists with read-only permissions and work-queue role separation
7. Session scope enforcement blocks out-of-scope file modifications via guardrails
8. `/agent-metrics` skill generates throughput reports from audit data
9. `/collect-transcripts` skill ingests at least Claude Code CLI plus one cloud harness (via CLI bridge), runs cheap-model triage over every session, and writes structured findings to episodic memory for sessions above the configurable struggle threshold; `/improve-harness` reports show which signal source each finding came from
10. D4 tag schema includes `source:*` and accepts findings from all four emitters (self-report, coordinator-emitted, session-log, transcript-mined); `/improve-harness` reports include source attribution and a cross-source agreement summary (e.g. "23% of findings surfaced in 2+ sources")

## References

- [Harness Engineering: Leveraging Codex in an Agent-First World](https://openai.com/index/harness-engineering/) — OpenAI, Feb 2026
- [Unrolling the Codex Agent Loop](https://openai.com/index/unrolling-the-codex-agent-loop/) — OpenAI, Jan 2026
- [Unlocking the Codex Harness](https://openai.com/index/unlocking-the-codex-harness/) — OpenAI, Feb 2026
