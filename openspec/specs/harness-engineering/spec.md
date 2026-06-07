# harness-engineering Specification

## Purpose
TBD - created by archiving change harness-engineering-features. Update Purpose after archive.
## Requirements
### Requirement: Agent-to-Agent Review Loop Convergence

The convergence loop SHALL support autonomous review-iterate-converge cycles where author agents fix review findings without human intervention until agent consensus is reached or the iteration limit is exhausted.

#### Scenario: Review loop converges within iteration limit
WHEN a work package completes implementation
AND the convergence loop dispatches reviews to 2+ vendor agents
AND all review findings have disposition "fix" or "accept"
THEN the author agent SHALL automatically apply fixes for "fix" findings
AND re-submit for review
AND the loop SHALL terminate when no new "fix" findings are raised
AND the maximum iteration count SHALL be configurable (default: 3)

#### Scenario: Review loop escalates on consensus failure
WHEN the convergence loop reaches the maximum iteration count
AND unresolved findings with disposition "fix" or "escalate" remain
THEN the loop SHALL escalate to human review
AND the escalation SHALL include a summary of unresolved findings with iteration history

#### Scenario: Review loop records convergence metrics
WHEN a review loop completes (converged or escalated)
THEN the system SHALL record in episodic memory: iteration count, findings per iteration, convergence status, time elapsed, and vendor agreement rate

### Requirement: Progressive Context Architecture

The CLAUDE.md file SHALL be restructured into a lightweight table-of-contents (~100 lines) that points to topic-specific documentation files, following the progressive disclosure principle.

#### Scenario: CLAUDE.md serves as a context map
WHEN an agent reads CLAUDE.md
THEN the file SHALL contain no more than 120 lines
AND each section SHALL be a brief summary (2-3 lines) with a link to the detailed doc
AND the detailed docs SHALL live under `docs/guides/` with descriptive filenames

#### Scenario: Topic docs are self-contained
WHEN an agent follows a link from CLAUDE.md to a topic doc
THEN the topic doc SHALL contain complete, actionable guidance for that topic
AND the topic doc SHALL NOT require reading other topic docs to be understood

### Requirement: Mechanical Architecture Enforcement

The validation system SHALL enforce architectural rules via automated linters with agent-readable remediation instructions in error messages.

#### Scenario: Dependency direction validation
WHEN a linter runs against the codebase
THEN it SHALL detect and report violations of the dependency direction rules between architectural layers (e.g., skills importing from coordinator internals)
AND the error message SHALL include the violation, the rule, and a specific fix suggestion

#### Scenario: File-size enforcement
WHEN a linter detects a file exceeding the configured maximum line count
THEN it SHALL report the violation with a suggestion for how to decompose the file

#### Scenario: Naming convention enforcement
WHEN a linter detects naming convention violations (skill directories, script files, schema files)
THEN it SHALL report the violation with the correct naming pattern

#### Scenario: Architecture phase integration
WHEN `/validate-feature --phase=architecture` is invoked
THEN the structural linters SHALL run as part of the validation pipeline
AND findings SHALL be formatted as review-findings compatible with the consensus synthesizer

### Requirement: Capability Gap Detection

The system SHALL record capability-gap signals from four sources — agent self-report, coordinator-emitted patterns, session-log structured sections, and transcript mining — into a shared tag schema in episodic memory, and the `/improve-harness` skill SHALL consume the union of all sources with deduplication and source attribution.

#### Scenario: Structured failure recording schema
WHEN any emitter records a capability-gap signal
THEN it SHALL use the shared episodic-memory tag schema: failure_type (enum: scope_violation, verification_failed, lock_unavailable, timeout, convergence_failed, context_exhaustion), capability_gap (free text describing what was missing), suggested_improvement (free text), affected_skill (skill name), severity (low/medium/high/critical), AND source (enum: self-reported, coordinator-emitted, session-log, transcript-mined)

#### Scenario: Agent self-reports a capability gap
WHEN an agent encounters a task failure and invokes the `remember` MCP tool with capability-gap metadata
THEN the entry SHALL be recorded with `source:self-reported`

#### Scenario: Coordinator auto-emits capability gaps via LLM classifier
WHEN the coordinator's audit-triage background task drains a batch of audit entries from its in-memory ring buffer
THEN it SHALL resolve the classifier model via the archetype system in `agent-coordinator/archetypes.yaml` (default archetype `analyst`, default provider `claude_code`, both configurable) using `agents_config.resolve_model()`
AND it SHALL compose the classifier system prompt via `agents_config.compose_prompt(archetype, task_prompt)` so the archetype's base prompt is preserved
AND it SHALL invoke the classifier with strict output-schema enforcement so emitted findings always parse (invalid responses dropped with a warning, never written to memory)
AND for each capability gap the classifier identifies, the coordinator SHALL emit a memory entry under the shared tag schema with `source:coordinator-emitted` plus a `prompt_version:N` tag
AND it SHALL NOT require any agent involvement
AND the classifier archetype, provider, batch size, batch interval, and prompt version SHALL be configurable via `agent-coordinator/config.yaml: audit.capability_gap_triage.*`
AND the hot path (`AuditService.log_operation`) SHALL NOT block on LLM calls — only ring-buffer push happens synchronously

#### Scenario: Session-log captures agent-observed gaps at phase boundaries
WHEN an agent writes a session-log phase entry via the `session-log` skill
AND the entry contains a `### Capability Gaps Observed` section with one or more gaps listed
THEN the skill SHALL emit one memory entry per gap with `source:session-log`
AND the markdown section SHALL be preserved in `openspec/changes/<change-id>/session-log.md` as human-readable record
AND an empty `### Capability Gaps Observed` section SHALL be a valid no-op (no memory entries emitted)

#### Scenario: /improve-harness consumes all sources with deduplication
WHEN `/improve-harness` is invoked
THEN it SHALL query episodic memory for capability_gap entries across ALL source values within a configurable time window (default: 30 days)
AND it SHALL ALSO scan `openspec/changes/**/session-log.md` for `### Capability Gaps Observed` sections (covering gaps not yet mirrored to memory)
AND it SHALL deduplicate findings on (capability_gap, affected_skill, session_id), preserving the set of sources that surfaced each finding
AND group by capability_gap
AND rank by frequency and severity
AND generate a structured report with recommendations

#### Scenario: Report includes source attribution
WHEN `/improve-harness` generates a report
THEN each finding SHALL be annotated with the set of sources that surfaced it (one or more of: self-reported, coordinator-emitted, session-log, transcript-mined)
AND the report SHALL include a summary line stating what fraction of findings surfaced in 2 or more sources (cross-source agreement is the strongest signal)

#### Scenario: Report handles empty capability-gap data
WHEN `/improve-harness` is invoked
AND episodic memory contains zero capability_gap entries within the time window
AND no `openspec/changes/**/session-log.md` files contain Capability Gaps Observed sections
THEN the skill SHALL report "No capability gaps recorded in the last N days" with a suggestion to verify that emitters (self-report, coordinator, session-log, transcript) are configured and active
AND exit with a zero status code

#### Scenario: Report-to-feature pipeline
WHEN an improvement report identifies a high-priority capability gap
THEN the user SHALL be able to invoke a skill that takes the report finding and creates an OpenSpec change proposal from it
AND the skill SHALL pre-populate the proposal with context from the failure patterns, affected skills, suggested improvements, AND the set of sources that surfaced the gap

### Requirement: Generation-Evaluation Separation

The agent profile system SHALL support a formal evaluator role that enforces separation between code generation and code evaluation.

#### Scenario: Evaluator profile definition
WHEN an evaluator agent profile is created
THEN it SHALL have read-only file permissions (no write_allow scope)
AND it SHALL have a specialized evaluation prompt template
AND it SHALL be assignable to review tasks in the work queue

#### Scenario: Work queue role separation
WHEN an evaluation task is submitted to the work queue
THEN the coordinator SHALL NOT assign it to the same agent_id that generated the work being evaluated
AND the coordinator SHALL prefer agents with the "evaluator" agent_type

#### Scenario: No evaluator agent available
WHEN an evaluation task is submitted to the work queue
AND no agent with the "evaluator" agent_type is registered or available
THEN the coordinator SHALL fall back to assigning the task to any non-author agent
AND the task metadata SHALL include a flag indicating evaluator-preferred but fallback-assigned

### Requirement: Session Focus Enforcement

The coordinator SHALL enforce single-task session scoping, preventing agents from modifying files outside their claimed task's scope.

#### Scenario: Scope lock on task claim
WHEN an agent claims a task from the work queue
AND the task has defined file scope (write_allow, deny)
THEN the coordinator SHALL record the scope as a session grant
AND subsequent guardrail checks for that agent SHALL validate file paths against the scope

#### Scenario: Out-of-scope modification blocked
WHEN an agent attempts to modify a file outside its session scope
AND the guardrails check is invoked
THEN the check SHALL return a warning with the scope violation details
AND the warning SHALL include the task's declared scope and a suggestion to request scope expansion

### Requirement: Agent Throughput Dashboard

The system SHALL provide an `/agent-metrics` skill that generates throughput and quality reports from audit data and telemetry.

#### Scenario: Throughput report generation
WHEN `/agent-metrics` is invoked with a time range
THEN it SHALL query the audit trail for: tasks completed, tasks failed, PRs opened, review cycles per PR, average time-to-merge
AND format the results as a structured markdown report

#### Scenario: Failure rate analysis
WHEN `/agent-metrics --failures` is invoked
THEN it SHALL query episodic memory for failure patterns
AND compute failure rates by agent type, skill, and failure_type
AND highlight trends (increasing/decreasing failure rates)

#### Scenario: Capability gap frequency
WHEN `/agent-metrics --gaps` is invoked
THEN it SHALL query episodic memory for capability_gap entries
AND rank gaps by frequency
AND cross-reference with `/improve-harness` reports if available

### Requirement: Session Transcript Mining

The system SHALL ingest raw session transcripts from supported coding-agent harnesses via vendor-specific adapters, normalize them to a common event schema, triage them with a cheap model, and write structured findings to episodic memory for consumption by `/improve-harness`.

#### Scenario: Adapter discovers and normalizes transcripts
WHEN the `/collect-transcripts` skill is invoked with a harness adapter selected
THEN the adapter SHALL enumerate available sessions from its source (filesystem path or harness API)
AND emit a sequence of normalized events per session conforming to `skills/collect-transcripts/references/event-schema.md`
AND write the normalized event stream to `docs/transcripts/<date>/<session-id>.jsonl`

#### Scenario: Adapter fails soft on source unavailability
WHEN a transcript source is unavailable (path missing, API endpoint absent, authentication missing, harness not installed)
THEN the adapter SHALL log a structured warning identifying the harness and the reason
AND exit with a non-fatal status that does not block other adapters or the downstream analysis pipeline

#### Scenario: Sanitization precedes any LLM analysis
WHEN normalized events are produced
THEN the sanitizer SHALL redact secrets, high-entropy strings, and environment-specific paths from event payloads (including tool-call arguments and tool-result outputs) BEFORE the events are passed to triage or deep-analysis models
AND the sanitizer SHALL be the one used by the `session-log` skill, extended as needed for transcript-specific structures

#### Scenario: Triage scores every ingested session
WHEN normalized transcripts are written
THEN a triage pass SHALL resolve its model via the archetype system (default archetype `analyst`, configurable via `skills/collect-transcripts/config.yaml: triage.archetype` and `provider`)
AND run the resolved model over each session
AND produce a score covering: retry_count, tool_error_count, scope_violation_count, user_correction_count, and a single-shot struggle classification
AND persist the score under the session id alongside the normalized transcript

#### Scenario: Deep analysis runs on flagged sessions
WHEN a session triage score exceeds the configured struggle threshold
THEN a deep-read analysis SHALL resolve its model via the archetype system (default archetype `reviewer`, configurable via `skills/collect-transcripts/config.yaml: deep_analysis.archetype` and `provider`)
AND run the resolved model over the normalized transcript
AND emit findings using the failure-recording tag schema (`failure_type:*`, `capability_gap:*`, `affected_skill:*`, `severity:*`) from the Capability Gap Detection requirement
AND write the findings to episodic memory via the `remember` MCP tool with `source:transcript-mined` as an additional tag

#### Scenario: Mining is opt-in
WHEN the skill runs in a CI context or without an explicit `--enable` flag
THEN no LLM API calls SHALL be made and no episodic memory entries SHALL be written
AND the skill SHALL print a dry-run plan (per-adapter session counts, estimated triage cost, estimated deep-analysis cost given the configured threshold) and exit zero

#### Scenario: Improve-harness surfaces transcript-sourced findings
WHEN `/improve-harness` generates a report
AND episodic memory contains entries tagged `source:transcript-mined`
THEN the entries SHALL flow through the unified multi-source pipeline defined in the Capability Gap Detection requirement
AND each transcript-mined finding SHALL appear in the report with `transcript-mined` in its source set
AND findings that also appear via other sources for the same `(capability_gap, affected_skill, session_id)` SHALL be reported once with the multi-source list (counting toward the cross-source agreement summary)

#### Scenario: Web adapter routes through vendor CLI bridge
WHEN the `claude_code_web` or `codex_web` adapter is invoked
THEN it SHALL invoke the vendor's documented CLI bridge command (`claude --teleport` or `codex cloud`) to materialize the cloud session as local JSONL
AND it SHALL delegate parsing to the corresponding CLI adapter (`claude_code_cli` or `codex_cli`)
AND it SHALL NOT make direct HTTP requests to undocumented vendor backend endpoints
AND it SHALL fail soft (log a structured warning identifying the missing dependency and skip) if the vendor CLI is not installed or not authenticated

