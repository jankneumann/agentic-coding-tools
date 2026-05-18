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

### D4: Failure metadata as episodic memory tags

**Decision**: Record capability gaps via the existing `remember` MCP tool using structured tags: `failure_type:<type>`, `capability_gap:<description>`, `affected_skill:<name>`, `severity:<level>`.

**Rationale**: The episodic memory system already supports tags with relevance scoring and time-decay. Using structured tags avoids schema changes while enabling the `/improve-harness` skill to query patterns via `recall` with tag filters.

**Trade-offs**: Free-text capability_gap descriptions may have inconsistent naming. Accepted because the `/improve-harness` report skill can normalize and cluster similar descriptions.

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

**Decision**: Implement a new `/collect-transcripts` skill containing per-harness adapters that normalize raw session transcripts into a common event schema. v1 adapters: Claude Code CLI, Claude Code on the web, Codex CLI, Codex on the web (best-effort — adapter ships as a stub with documented fallback if no stable transcript endpoint exists at v1 ship time), and Gemini CLI. Raw normalized events are written to disk under `docs/transcripts/<date>/<session-id>.jsonl` (filesystem-as-memory). A cheap-model triage pass (default `claude-haiku-4-5`) scores every session on retry_count, tool_error_count, scope_violation_count, user_correction_count, and a single-shot struggle classification. Sessions above the configurable threshold get a deep read by a stronger model; deep-read findings use D4's tag schema (`failure_type:*`, `capability_gap:*`, `affected_skill:*`, `severity:*`) and are written to episodic memory via the `remember` MCP tool. `/improve-harness` mines the resulting memory entries with no changes to its existing analysis path — transcript mining adds a signal source, not a new consumer.

**Rationale**: D4's tag-based recording depends on agents stopping mid-session to introspect, which is exactly what struggling agents don't do. Coordinator-emitted signals (telemetry/audit) cover patterns visible at the MCP/HTTP boundary but miss everything that happens inside the agent's own tool loop. Raw transcripts are the only source that carries the full unsummarized signal: every retry, every tool error, every user correction, every aborted plan. Mining them with a cheaper triage model keeps the cost shape sane — triage runs on every session, deep analysis runs only on flagged outliers. The two-tier storage (raw on disk, structured findings in DB) mirrors OpenAI's "filesystem as memory" principle: the DB stays small and queryable, while the raw transcripts remain available for re-analysis when the analysis prompt or model improves.

**Trade-offs**:
- (a) Adapter coupling — each new harness version may change its on-disk format or API and require adapter maintenance. Accepted because the common event schema isolates the rest of the pipeline; only the adapter changes when a vendor updates its format.
- (b) Privacy surface — transcripts contain everything including secrets, PII, and customer code. Mitigated by reusing the `session-log` skill's sanitizer (extended to cover tool-call argument blobs and tool-result outputs, which are common accidental-leak sites) before any normalized event leaves the adapter and before any LLM sees the content.
- (c) Cost — cheap-model triage is ~$0.01–0.05 per session at current Haiku 4.5 pricing; deep analysis is ~$0.30–1.00 per flagged session. Mining is default-off in CI; the operator opts in via flag, and a `--dry-run` mode prints the planned cost without making any API calls.
- (d) Cloud-harness API uncertainty — Claude Code web has session APIs but they evolve; Codex web may not expose a stable transcript endpoint at v1 ship time. Adapters MUST fail soft (log a structured warning and skip) when their source isn't available, never block the rest of the pipeline. Best-effort adapters can ship as stubs.

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
  (Claude CLI/web,             │
   Codex CLI/web,              ├─→ Sanitize ──→ docs/transcripts/<date>/<id>.jsonl (raw)
   Gemini CLI)                 │
                               ├─→ Triage (cheap model) ──→ score per session
                               │
                               └─→ Deep analyze (flagged sessions) ──→ findings ──┘
                                       (D4 tag schema)

Validation ──→ --phase=architecture ──→ Structural Linters ──→ Findings
```
