# Design: Harness Engineering Features

**Change ID**: harness-engineering-features
**Status**: Draft

## Design Decisions

### D1: Extend convergence_loop.py rather than new service

**Decision**: Implement review loop improvements in `skills/autopilot/scripts/convergence_loop.py` and `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`.

**Rationale**: The convergence loop already implements the review→synthesize→fix cycle pattern. Adding iteration counting, configurable thresholds, and automatic escalation is a natural extension. Creating a new service would duplicate the review dispatch and consensus matching logic.

**Trade-offs**: Existing convergence_loop callers need to handle new configuration parameters. Accepted because backward compatibility is maintained via defaults.

### D2: CLAUDE.md restructure via file splitting

**Decision**: Split CLAUDE.md into a ~100-line TOC at the root and topic-specific files under `docs/guides/`. Topic files: `workflow.md`, `python-environment.md`, `git-conventions.md`, `skills.md`, `worktree-management.md`, `documentation.md`, `session-completion.md`.

**Rationale**: Follows OpenAI's principle of "give agents a map, not a manual." The current CLAUDE.md is ~130 lines and growing. Splitting now prevents the file from becoming unwieldy. Each topic doc can evolve independently.

**Trade-offs**: Agents must follow links to get details. Accepted because the TOC provides enough context to know *where* to look, which is more valuable than having everything in one place when the file grows beyond comfortable reading size.

### D3: Architecture linters as Python scripts in validate-feature

**Decision**: Implement structural linters as Python scripts under `skills/validate-feature/scripts/linters/` and wire them into the `--phase=architecture` validation phase.

**Rationale**: Linters are read-only analysis tools that fit naturally as validation phase scripts. They produce findings in the same format as other validation phases, enabling integration with the consensus synthesizer.

**Trade-offs**: Not a coordinator service — linters only run when explicitly invoked via validation. Accepted because continuous enforcement is less important than clear, actionable feedback during implementation cycles.

### D4: Failure metadata as shared tag schema in episodic memory

**Decision**: Define a shared capability-gap tag schema in the existing episodic memory system using structured tags: `failure_type:<type>`, `capability_gap:<description>`, `affected_skill:<name>`, `severity:<level>`, plus `source:<emitter>` (one of `self-reported` | `coordinator-emitted` | `session-log` | `transcript-mined`). Multiple emitters write into this schema (see D8/D9/D10); `/improve-harness` is the sole consumer and is source-agnostic.

**Rationale**: The episodic memory system already supports tags with relevance scoring and time-decay. Treating the tag schema as a *contract between emitters and consumers* — rather than as a private convention of the `remember` MCP tool — is the central insight that makes harness self-improvement work. Each emitter has its own bias profile (self-report under-reports struggle; coordinator-emitted misses tool-loop friction; session-log catches what the agent noticed but missed timing; transcript-mined catches everything but is expensive). Cross-referencing sources gives high-confidence signal; relying on any single source has a known blind spot.

**Trade-offs**: 
- (a) Free-text `capability_gap` descriptions may have inconsistent naming across emitters. Accepted because `/improve-harness` normalizes and clusters similar descriptions before reporting.
- (b) Adding `source:*` as a required tag means existing call sites of `remember` that use the failure tag schema must be updated. Accepted because the schema is new in this change; no legacy callers exist outside it.

**Related decisions**: D8 (transcript-mined source), D9 (coordinator-emitted source), D10 (session-log source).

### D5: Evaluator profile via existing profile system

**Decision**: Add a built-in "evaluator" profile to the agent profiles table with `max_file_modifications=0`, `allowed_operations=["read", "review", "evaluate"]`, `blocked_operations=["write", "commit", "push"]`.

**Rationale**: The profile system already supports trust levels and operation restrictions. Adding a dedicated evaluator profile requires only a database seed, not code changes. The work queue already has `agent_type` filtering — adding evaluator type preference is a small extension.

**Trade-offs**: Profile is database-resident, so a migration is needed. Accepted because all other profiles are already database-seeded.

### D6: Session scope as guardrail extension

**Decision**: Extend the guardrails engine to check file paths against session grants when `session_scope_enforcement=true` in the agent's profile.

**Rationale**: The guardrails engine already intercepts destructive operations. Adding scope checking is a natural extension. Session grants already exist (`session_grants.py`) — this connects them to the enforcement layer.

**Trade-offs**: Adds a database query per guardrail check when scope enforcement is active. Accepted because guardrail checks are infrequent relative to other operations.

### D7: Metrics skill uses audit trail queries

**Decision**: Implement `/agent-metrics` as a skill that queries the audit trail via the coordinator's HTTP API, not as a coordinator service itself.

**Rationale**: Metrics reporting is a read-only, infrequent operation that doesn't need to be always-on. A skill can format output for human consumption and integrate with OpenSpec workflows. The audit trail already captures all the raw data needed.

**Trade-offs**: No real-time dashboard — reports are point-in-time snapshots. Accepted because the primary use case is periodic review, not continuous monitoring.

### D8: Session transcript mining via adapter-based skill

**Decision**: Implement a new `/collect-transcripts` skill containing per-harness adapters that normalize raw session transcripts into a common event schema. v1 adapters:
- **`claude_code_cli`** — reads `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` (verified path). Prefers the `@anthropic-ai/claude-agent-sdk` helpers `listSessions()` / `getSessionMessages()` (and Python equivalents) over hand-parsing the JSONL, so Anthropic owns version drift.
- **`claude_code_web`** — implemented as a CLI bridge, not a direct web-API client. Invokes `claude --teleport <session-id>` to pull the cloud session onto local disk, then delegates to `claude_code_cli`. The Anthropic `/v1/sessions` endpoint on `api.anthropic.com` belongs to the *separate* Managed Agents product, not Claude Code web; reverse-engineering claude.ai's private endpoints is explicitly out of scope (third-party tools doing this have repeatedly broken on unannounced API changes).
- **`codex_cli`** — reads `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<timestamp>-<session-id>.jsonl` (default `$CODEX_HOME` = `~/.codex`). Schema is officially versioned via `codex app-server generate-internal-json-schema` (emits `RolloutLine.json`); the adapter pins to a schema version and re-validates on minor bumps. Items are `SessionMeta` | `EventMsg` | `ResponseItem` variants; `ResponseItem.function_call` / `function_call_output` carry tool I/O.
- **`codex_web`** — implemented as a CLI bridge via `codex cloud`, mirroring the `claude_code_web` pattern. Pulls cloud-task transcripts to local disk as standard rollout JSONL, then delegates to `codex_cli`. No direct web-API adapter.
- **`gemini_cli`** — reads `~/.gemini/tmp/<project_hash>/chats/session-<timestamp>-<short_id>.json` (JSONL despite the `.json` extension). Schema lives in `chatRecordingService.ts` and changes opportunistically; the adapter pins to a commit SHA and version-detects via the metadata header. Tool calls in `MessageRecord.toolCalls[]`; content blocks follow Google GenAI `Part` union (`text` | `functionCall` | `functionResponse`).

Raw normalized events are written to disk under `docs/transcripts/<date>/<session-id>.jsonl` (filesystem-as-memory). A cheap-model triage pass (default `claude-haiku-4-5`) scores every session on retry_count, tool_error_count, scope_violation_count, user_correction_count, and a single-shot struggle classification. Sessions above the configurable threshold get a deep read by a stronger model; deep-read findings use D4's tag schema (`failure_type:*`, `capability_gap:*`, `affected_skill:*`, `severity:*`) plus `source:transcript-mined` and are written to episodic memory via the `remember` MCP tool. `/improve-harness` mines the resulting memory entries via the source-agnostic path defined in D4 — transcript mining adds a signal source, not a new consumer.

**Rationale**: D4's tag-based recording depends on agents stopping mid-session to introspect, which is exactly what struggling agents don't do. Coordinator-emitted signals (telemetry/audit) cover patterns visible at the MCP/HTTP boundary but miss everything that happens inside the agent's own tool loop. Raw transcripts are the only source that carries the full unsummarized signal: every retry, every tool error, every user correction, every aborted plan. Mining them with a cheaper triage model keeps the cost shape sane — triage runs on every session, deep analysis runs only on flagged outliers. The two-tier storage (raw on disk, structured findings in DB) mirrors OpenAI's "filesystem as memory" principle: the DB stays small and queryable, while the raw transcripts remain available for re-analysis when the analysis prompt or model improves.

**Trade-offs**:
- (a) Adapter coupling — each new harness version may change its on-disk format or API and require adapter maintenance. Accepted because the common event schema isolates the rest of the pipeline; only the adapter changes when a vendor updates its format.
- (b) Privacy surface — transcripts contain everything including secrets, PII, and customer code. Mitigated by reusing the `session-log` skill's sanitizer (extended to cover tool-call argument blobs and tool-result outputs, which are common accidental-leak sites) before any normalized event leaves the adapter and before any LLM sees the content.
- (c) Cost — cheap-model triage is ~$0.01–0.05 per session at current Haiku 4.5 pricing; deep analysis is ~$0.30–1.00 per flagged session. Mining is default-off in CI; the operator opts in via flag, and a `--dry-run` mode prints the planned cost without making any API calls.
- (d) Cloud-harness sources are CLI-bridged, not direct. Neither Claude Code web nor Codex web exposes a documented transcript API. Routing through `claude --teleport` and `codex cloud` means the web adapters depend on the vendor's CLI being installed and authenticated — a softer surface than a stable HTTP endpoint, but the only one the vendors actually support. All adapters MUST fail soft (log a structured warning and skip) when their source is unavailable, never block the rest of the pipeline.
- (e) Vendor schema drift cadence varies. Claude Code CLI's schema is stable and SDK-wrapped; Codex CLI ships a generated JSON Schema with each release (`RolloutLine.json` — pin to a version); Gemini CLI's `chatRecordingService.ts` changes opportunistically (pin to a commit SHA, version-detect via metadata header). Adapters MUST declare the schema version they target; integration tests run against pinned fixtures.

### D9: Coordinator-side automatic capability-gap emission

**Decision**: Extend `agent-coordinator/src/audit.py::AuditService.log_operation` with a pattern-matcher hook that observes audit entries as they're written and, when struggle-shaped patterns are detected, emits a memory entry under the D4 tag schema with `source:coordinator-emitted`. v1 patterns: (a) same `(agent_id, operation)` pair retried N+ times within a session, (b) two consecutive failed `verify` operations on the same work package, (c) any `guardrails.check` returning a scope-violation result, (d) lock contention exceeding the lock TTL on the same key. Patterns and thresholds live in a per-coordinator config block (`config.yaml: audit.capability_gap_patterns`) so they can be tuned without code changes.

**Rationale**: D4 alone depends on agents stopping mid-task to introspect, which is exactly what struggling agents don't do. The coordinator already sees every operation cross its MCP/HTTP surface — it can detect struggle patterns the agent itself is too busy to notice. Wiring this into `log_operation` rather than a separate background job means the signal is recorded synchronously with the operation that caused it, so there's no race between the failure and the recording. Pattern-matching is intentionally simple (regex/threshold) rather than ML-based to keep the coordinator latency budget intact; the heavyweight pattern analysis lives downstream in `/improve-harness`.

**Trade-offs**:
- (a) Adds a small per-operation cost (one tag-write per detected pattern). Accepted because patterns are rare relative to operations and writes are async-batched via the memory service.
- (b) Pattern false positives create noise in episodic memory. Mitigated by: (i) tunable thresholds in config, (ii) `/improve-harness` ranks by frequency × severity so isolated noise is filtered, (iii) operators can disable specific patterns via config.
- (c) The coordinator can only see what crosses its API surface — pure in-agent struggles (e.g. the agent rewriting the same file 10 times without committing) are invisible. Accepted because D8 (transcript mining) covers that gap.

### D10: Session-log "Capability Gaps Observed" section

**Decision**: Extend the `session-log` skill's `PhaseRecord` dataclass (`skills/session-log/scripts/phase_record.py`) with a new `capability_gaps: list[CapabilityGap]` field. Each `CapabilityGap` has fields matching the D4 tag schema (`failure_type`, `capability_gap`, `affected_skill`, `severity`). The renderer adds a `### Capability Gaps Observed` section to the per-phase markdown block in `session-log.md`, slotted between `### Trade-offs` and `### Relevant Files`. At phase boundaries, the agent fills this section (free-text bullets allowed; structured fields preferred). On `PhaseRecord.write_both()`, the `session-log` skill emits a memory entry per gap with `source:session-log`, keeping the markdown human-readable while populating the same shared tag schema.

**Rationale**: This bridges the gap between "agent self-reports in-line via `remember`" (D4 default) and "agent never reports" (the silent-struggle failure mode). The phase boundary is a natural reflection point — the agent has just summarized what it did, so it's already in introspective mode. Asking for a "Capability Gaps Observed" section costs the agent ~30 seconds and produces structured signal even when the agent forgot to call `remember` during the session. Mirroring the data into both markdown (human-readable) and memory (queryable) means the same content serves humans reading the session-log and the `/improve-harness` skill mining for patterns.

**Trade-offs**:
- (a) Adds a section to the session-log template, which agents may leave empty if no gaps were observed. Accepted; empty is a valid value and is more honest than synthesizing fake gaps.
- (b) Round-trip parsing (markdown ↔ dataclass) must handle the new section. Accepted; the existing `_parse_*` dispatchers in `phase_record.py` use section-headed lookup (`sections.get("Trade-offs", [])` etc.), so adding `sections.get("Capability Gaps Observed", [])` follows the established pattern.
- (c) Duplicate emission risk: an agent might both call `remember` and then list the same gap in the session-log section. Mitigated by `/improve-harness` deduplication keyed on `(capability_gap, affected_skill, session_id)`; the source tag is preserved as a multi-source list when the same gap appears under multiple sources (which is itself useful signal — see D4 rationale).

## Component Interaction

```
CLAUDE.md (TOC) ──→ docs/guides/*.md (topic docs)

Agent claims task ──→ Work Queue ──→ Session Grant (scope) ──→ Guardrails (enforce scope)

Implementation ──→ Review Dispatch ──→ Consensus ──→ Convergence Loop (iterate)
     │                                                       │
     │                              ┌────────────────────────┘
     ▼                              ▼
  Failures ──→ Episodic Memory ──→ /improve-harness (reports)
                    ▲                    │
                    │                    ▼
                    │              /agent-metrics
                    │                    │
                    │                    ▼
                    │              OpenSpec proposals (human-guided)
                    │
  Harness Transcripts ──→ /collect-transcripts
   ├─ claude_code_cli (file)         │
   ├─ claude_code_web (--teleport)──→│
   ├─ codex_cli (file)               ├─→ Sanitize ──→ docs/transcripts/<date>/<id>.jsonl (raw)
   ├─ codex_web (codex cloud)────────│
   └─ gemini_cli (file)              ├─→ Triage (cheap model) ──→ score per session
                                     │
                                     └─→ Deep analyze (flagged sessions) ──→ findings ──┘
                                             (D4 tag schema, source:transcript-mined)

Coordinator audit ──→ pattern matcher ──→ findings ──┘
(D9: source:coordinator-emitted)

session-log "Capability Gaps Observed" section ──→ findings ──┘
(D10: source:session-log)

Validation ──→ --phase=architecture ──→ Structural Linters ──→ Findings
```
