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

Raw normalized events are written to disk under `docs/transcripts/<date>/<session-id>.jsonl` (filesystem-as-memory). Model selection goes through the **archetype system** (`agent-coordinator/archetypes.yaml`) for provider-agnostic, configurable resolution: triage uses the **`analyst`** archetype (standard tier — sonnet / gpt-5.4 / gemini-3-flash), deep-read uses the **`reviewer`** archetype (premium tier — opus / gpt-5.5 / gemini-3.1-pro-preview). Both are configurable via `skills/collect-transcripts/config.yaml: { triage.archetype, deep_analysis.archetype, provider }`. The triage pass scores every session on retry_count, tool_error_count, scope_violation_count, user_correction_count, and a single-shot struggle classification. Sessions above the configurable threshold get a deep read; findings use D4's tag schema (`failure_type:*`, `capability_gap:*`, `affected_skill:*`, `severity:*`) plus `source:transcript-mined` and are written to episodic memory via the `remember` MCP tool. v1 prioritizes accuracy and signal over cost; downshifting archetypes (analyst → runner for triage; reviewer → analyst for deep-read) once the prompts are proven is a config edit, not a redesign. `/improve-harness` mines the resulting memory entries via the source-agnostic path defined in D4 — transcript mining adds a signal source, not a new consumer.

**Rationale**: D4's tag-based recording depends on agents stopping mid-session to introspect, which is exactly what struggling agents don't do. Coordinator-emitted signals (telemetry/audit) cover patterns visible at the MCP/HTTP boundary but miss everything that happens inside the agent's own tool loop. Raw transcripts are the only source that carries the full unsummarized signal: every retry, every tool error, every user correction, every aborted plan. Mining them with a cheaper triage model keeps the cost shape sane — triage runs on every session, deep analysis runs only on flagged outliers. The two-tier storage (raw on disk, structured findings in DB) mirrors OpenAI's "filesystem as memory" principle: the DB stays small and queryable, while the raw transcripts remain available for re-analysis when the analysis prompt or model improves.

**Trade-offs**:
- (a) Adapter coupling — each new harness version may change its on-disk format or API and require adapter maintenance. Accepted because the common event schema isolates the rest of the pipeline; only the adapter changes when a vendor updates its format.
- (b) Privacy surface — transcripts contain everything including secrets, PII, and customer code. Mitigated by reusing the `session-log` skill's sanitizer (extended to cover tool-call argument blobs and tool-result outputs, which are common accidental-leak sites) before any normalized event leaves the adapter and before any LLM sees the content.
- (c) Run-time cost is meaningful at analyst/reviewer archetype pricing. v1 accepts this explicitly to maximize accuracy and signal density; cost optimization (downshifting archetypes, raising the deep-analysis threshold, gating to specific harnesses) is a config tuning exercise once the prompts are proven, not a redesign. Mining remains default-off in CI; the operator opts in via flag, and `--dry-run` prints the planned operation without making any API calls.
- (d) Cloud-harness sources are CLI-bridged, not direct. Neither Claude Code web nor Codex web exposes a documented transcript API. Routing through `claude --teleport` and `codex cloud` means the web adapters depend on the vendor's CLI being installed and authenticated — a softer surface than a stable HTTP endpoint, but the only one the vendors actually support. All adapters MUST fail soft (log a structured warning and skip) when their source is unavailable, never block the rest of the pipeline.
- (e) Vendor schema drift cadence varies. Claude Code CLI's schema is stable and SDK-wrapped; Codex CLI ships a generated JSON Schema with each release (`RolloutLine.json` — pin to a version); Gemini CLI's `chatRecordingService.ts` changes opportunistically (pin to a commit SHA, version-detect via metadata header). Adapters MUST declare the schema version they target; integration tests run against pinned fixtures.

### D9: Coordinator-side automatic capability-gap emission via LLM classifier

**Decision**: Add an audit-triage subsystem to the coordinator that classifies struggle signals using an LLM classifier — NOT regex/threshold pattern matching. v1 prioritizes accuracy and recall over cost and latency. Model selection goes through the existing **archetype system** in `agent-coordinator/archetypes.yaml` for provider-agnostic, configurable model resolution: the default archetype is **`analyst`** (resolves to `sonnet` / `gpt-5.4` / `gemini-3-flash` depending on configured provider). The classifier prompt is composed via `agents_config.compose_prompt(archetype, task_prompt)` so the archetype's base system prompt ("You are a codebase analyst. Read thoroughly, synthesize findings concisely, and identify patterns, gaps, and conflicts. Report structured findings without making changes.") is layered with the audit-window classifier task prompt. The hot path: `AuditService.log_operation` pushes each audit entry into an in-memory ring buffer keyed by `(agent_id, session_id)` with no LLM involvement (microsecond cost). A background task (`agent-coordinator/src/audit_triage.py`) drains the buffer on a configurable cadence and resolves the model via `agents_config.resolve_model(archetype, package_metadata={}, provider=<configured>)`. Findings emit under the D4 tag schema with `source:coordinator-emitted`. Configuration lives in `agent-coordinator/config.yaml` under `audit.capability_gap_triage.*` (`enabled`, `archetype` — default `analyst`, `provider` — default `claude_code`, `batch_size`, `batch_interval_minutes`, `prompt_version`). The LLM client is a provider-aware abstraction (the coordinator already supports multiple providers via `model_aliases`), not a hardcoded `anthropic` import. Cost optimization (switching `archetype` to `runner` for the economy tier, raising `batch_size`, gating by agent profile) is a config flip, not a redesign.

**Rationale**: A regex/threshold pattern matcher is the wrong tool — it can only recognize struggle shapes we already named (retry storm, repeated verify failure, scope violation, lock contention). The whole point of the multi-source pipeline is to **discover capability gaps we haven't named yet**. An LLM classifier reads the audit window semantically and can flag novel patterns ("agent retried the same MCP tool with progressively narrower scopes — looks like it was guessing at a permission boundary"; "agent claimed a task, made no progress for 40 minutes, then released it — looks like context exhaustion mid-task"). Recall is the controlling metric: `/improve-harness` already dedupes on `(capability_gap, affected_skill, session_id)` and ranks by frequency × severity downstream, so over-emission is filtered cheaply, but **under-emission is invisible and unrecoverable** — a missed gap never becomes a proposal. Using a strong model by default (Sonnet 4.6, with Opus 4.7 available via config for the most subtle cases) maximizes the chance that the gap that actually mattered ends up in the report. Hot/cold path split is a side benefit: the synchronous coordinator path is bounded by a ring buffer push regardless of which model the classifier uses.

**Trade-offs**:
- (a) Adds an LLM-client dependency to the coordinator. Previously the coordinator was orchestrator-only (no LLM calls). The LLM client is provider-agnostic — it dispatches to the SDK matching the resolved `model_aliases.<provider>` entry — so this is one abstraction added, not one vendor SDK pinned in. Accepted because the alternative (subprocess to a sibling worker per batch) adds operational complexity for marginal benefit; one extra dep is cheaper than one extra service to schedule and monitor.
- (b) Run-time cost is meaningful at `analyst` (standard tier) pricing and grows with audit volume. Accepted explicitly for v1: optimizing accuracy and signal density is the priority; cost can be tuned later by (i) switching `audit.capability_gap_triage.archetype` from `analyst` to `runner` (economy tier) once the prompt is proven, (ii) raising `batch_size` to amortize fewer calls, or (iii) gating triage to specific agent profiles. None of these require code changes — the archetype system makes this a single yaml edit.
- (c) Classifier latency is decoupled from the originating operation — a struggle pattern that happens at 14:03 may not be recorded until 14:13 (next batch interval). Accepted because `/improve-harness` operates on time windows of days, not minutes; a 10-min lag is invisible at that resolution.
- (d) The classifier prompt is in the trusted path for what counts as a capability gap. Mitigated by versioning the classifier prompt under `agent-coordinator/src/audit_triage_prompts/` with a `prompt_version:N` tag on every emitted finding, so prompt iterations can be A/B compared via `/improve-harness` over time. Prompts are also subject to ordinary code review on change.
- (e) LLM output is unstructured by default. The classifier MUST be invoked with strict output schema enforcement (tool-use JSON schema or constrained generation) so emitted findings always parse — invalid responses are dropped with a warning, never written to memory.

### D10: Session-log "Capability Gaps Observed" section

**Decision**: Extend the `session-log` skill's `PhaseRecord` dataclass (`skills/session-log/scripts/phase_record.py`) with a new `capability_gaps: list[CapabilityGap]` field. Each `CapabilityGap` has fields matching the D4 tag schema (`failure_type`, `capability_gap`, `affected_skill`, `severity`). The renderer adds a `### Capability Gaps Observed` section to the per-phase markdown block in `session-log.md`, slotted between `### Trade-offs` and `### Relevant Files`. At phase boundaries, the agent fills this section (free-text bullets allowed; structured fields preferred). On `PhaseRecord.write_both()`, the `session-log` skill emits a memory entry per gap with `source:session-log`, keeping the markdown human-readable while populating the same shared tag schema.

**Rationale**: This bridges the gap between "agent self-reports in-line via `remember`" (D4 default) and "agent never reports" (the silent-struggle failure mode). The phase boundary is a natural reflection point — the agent has just summarized what it did, so it's already in introspective mode. Asking for a "Capability Gaps Observed" section costs the agent ~30 seconds and produces structured signal even when the agent forgot to call `remember` during the session. Mirroring the data into both markdown (human-readable) and memory (queryable) means the same content serves humans reading the session-log and the `/improve-harness` skill mining for patterns.

**Trade-offs**:
- (a) Adds a section to the session-log template, which agents may leave empty if no gaps were observed. Accepted; empty is a valid value and is more honest than synthesizing fake gaps.
- (b) Round-trip parsing (markdown ↔ dataclass) must handle the new section. Accepted; the existing `_parse_*` dispatchers in `phase_record.py` use section-headed lookup (`sections.get("Trade-offs", [])` etc.), so adding `sections.get("Capability Gaps Observed", [])` follows the established pattern.
- (c) Duplicate emission risk: an agent might both call `remember` and then list the same gap in the session-log section. Mitigated by `/improve-harness` deduplication keyed on `(capability_gap, affected_skill, session_id)`; the source tag is preserved as a multi-source list when the same gap appears under multiple sources (which is itself useful signal — see D4 rationale).

### D11: Separate classifier prompts for audit-triage and transcript-triage

**Decision**: Maintain separate classifier prompt files for the audit-triage subsystem (`agent-coordinator/src/audit_triage_prompts/v<N>.md`) and the transcript-mining triage + deep-analysis (`skills/collect-transcripts/prompts/triage_v<N>.md`, `skills/collect-transcripts/prompts/deep_analysis_v<N>.md`), even though all of them resolve their model through the same archetype (`analyst` for triage, `reviewer` for deep-analysis).

**Rationale**: The input shapes differ substantially. Audit triage sees structured coordinator operation records (`operation`, `parameters`, `result`, `duration_ms`, `success`, `error_message`) — the prompt needs to know about `acquire_lock`, `claim_work`, `verify`, `guardrails.check`, etc. and what struggle looks like for each. Transcript triage sees raw agent/tool turn sequences from a harness — the prompt needs to know about retry loops, user corrections, tool-error sequences, scope-violation attempts inside the agent's tool loop. A unified prompt would either dilute domain-specific guidance with universal hedges, or accumulate conditional branches per source — both worse than two focused prompts. The cross-cutting consistency that matters (model tier, base system prompt, output schema, `prompt_version:N` tagging) is already shared via the archetype layer; sharing the task prompt would not add value.

**Trade-offs**:
- (a) Two prompt files to maintain and evolve independently. Accepted because both are versioned (`v1`, `v2`, ...) and code-reviewed on change, and both emit `prompt_version:N` tags so `/improve-harness` can A/B compare across versions even on the same source.
- (b) If we later discover the prompts converge naturally, unifying is a refactor — not a redesign — and the `prompt_version` tag preserves the historical signal.

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

Coordinator audit ──→ ring buffer ──→ LLM classifier (analyst archetype) ──→ findings ──┘
(D9: source:coordinator-emitted, prompt_version:N)

session-log "Capability Gaps Observed" section ──→ findings ──┘
(D10: source:session-log)

Validation ──→ --phase=architecture ──→ Structural Linters ──→ Findings
```
