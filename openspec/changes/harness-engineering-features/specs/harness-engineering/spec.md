# Harness Engineering Features — Specification

**Spec ID**: harness-engineering
**Change ID**: harness-engineering-features
**Status**: Draft

## ADDED Requirements

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

The coordinator's episodic memory SHALL support structured failure pattern recording with capability gap metadata, enabling systematic harness improvement.

#### Scenario: Structured failure recording
WHEN an agent encounters a task failure
THEN the failure SHALL be recorded in episodic memory with structured metadata: failure_type (enum: scope_violation, verification_failed, lock_unavailable, timeout, convergence_failed, context_exhaustion), capability_gap (free text describing what was missing), suggested_improvement (free text), affected_skill (skill name), and severity (low/medium/high/critical)

#### Scenario: Failure pattern analysis
WHEN the `/improve-harness` skill is invoked
THEN it SHALL query episodic memory for failure patterns within a configurable time window (default: 30 days)
AND group failures by capability_gap
AND rank by frequency and severity
AND generate a structured report with recommendations

#### Scenario: Report-to-feature pipeline
WHEN an improvement report identifies a high-priority capability gap
THEN the user SHALL be able to invoke a skill that takes the report finding and creates an OpenSpec change proposal from it
AND the skill SHALL pre-populate the proposal with context from the failure patterns, affected skills, and suggested improvements

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
THEN a triage pass SHALL run a configurable cheap model (default `claude-haiku-4-5`) over each session
AND produce a score covering: retry_count, tool_error_count, scope_violation_count, user_correction_count, and a single-shot struggle classification
AND persist the score under the session id alongside the normalized transcript

#### Scenario: Deep analysis runs on flagged sessions only
WHEN a session triage score exceeds the configured struggle threshold
THEN a deep-read analysis SHALL run a stronger model over the normalized transcript
AND emit findings using the failure-recording tag schema (`failure_type:*`, `capability_gap:*`, `affected_skill:*`, `severity:*`) from the Capability Gap Detection requirement
AND write the findings to episodic memory via the `remember` MCP tool with `source:transcript-mined` as an additional tag

#### Scenario: Mining is opt-in
WHEN the skill runs in a CI context or without an explicit `--enable` flag
THEN no LLM API calls SHALL be made and no episodic memory entries SHALL be written
AND the skill SHALL print a dry-run plan (per-adapter session counts, estimated triage cost, estimated deep-analysis cost given the configured threshold) and exit zero

#### Scenario: Improve-harness surfaces transcript-sourced findings
WHEN `/improve-harness` generates a report
AND episodic memory contains entries tagged `source:transcript-mined`
THEN the report SHALL include a "Source" column or annotation per finding distinguishing self-reported, coordinator-emitted, and transcript-mined signals
AND the report SHALL summarize the share of findings each source contributed
