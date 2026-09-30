# harness-engineering Specification (delta)

## MODIFIED Requirements

### Requirement: Agent Throughput Dashboard

The system SHALL provide an `/agent-metrics` skill that generates throughput, quality, and model-usage reports from audit data, telemetry, and the usage ledger.

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

#### Scenario: Model usage and mismatch report
WHEN `/agent-metrics --usage` is invoked, optionally with `--change <change-id>`
THEN it SHALL query `GET /usage/by-phase`, `GET /usage/by-model`, and `GET /usage/mismatches`
AND render a per-change, per-phase table with columns: phase, archetype, intended model, actual model(s), intended thinking, actual effort(s), thinking tokens, input/output/cache tokens, estimated cost, pricing version, and a mismatch marker
AND render per-vendor and per-model totals with `unpriced_records` called out
AND label every cost figure as an estimate carrying its pricing version, or as vendor-reported when `vendor_cost_usd` is present
AND degrade with a warning and an empty section when the coordinator is unreachable

### Requirement: Session Transcript Mining

The system SHALL ingest raw session transcripts from supported coding-agent harnesses via vendor-specific adapters, normalize them to a common event schema that preserves model and token-usage attribution, triage them with a cheap model, and write structured findings to episodic memory for consumption by `/improve-harness`.

#### Scenario: Adapter discovers and normalizes transcripts
WHEN the `/collect-transcripts` skill is invoked with a harness adapter selected
THEN the adapter SHALL enumerate available sessions from its source (filesystem path or harness API)
AND emit a sequence of normalized events per session conforming to `skills/collect-transcripts/references/event-schema.md`
AND write the normalized event stream to `docs/transcripts/<date>/<session-id>.jsonl`

#### Scenario: Adapter preserves model and usage attribution
WHEN an adapter normalizes an assistant event whose raw record carries a model identifier and token usage
THEN the normalized event SHALL carry `model` equal to the vendor's identifier, `effort` when the harness reports it, and a `usage` block with `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, and `thinking_tokens` (null when not reported)
AND the Claude Code CLI adapter SHALL read `message.model`, the top-level `effort`, and `usage.output_tokens_details.thinking_tokens`
AND the Grok and Pi adapters SHALL map cache-read and cache-write counters when present
AND the Grok adapter SHALL carry the vendor-reported `total_cost_usd` into `vendor_cost_usd`

#### Scenario: Adapter discovers sub-agent transcripts
WHEN the Claude Code CLI adapter enumerates a session that has a `subagents/` directory
THEN it SHALL emit one additional session summary per `agent-*.jsonl` file with `agent_id` and `parent_session_id` populated
AND events from those files SHALL carry the same `agent_id` and `parent_session_id`

#### Scenario: Adapter fails soft on source unavailability
WHEN a transcript source is unavailable (path missing, API endpoint absent, authentication missing, harness not installed)
THEN the adapter SHALL log a structured warning identifying the harness and the reason
AND exit with a non-fatal status that does not block other adapters or the downstream analysis pipeline

#### Scenario: Sanitization precedes any LLM analysis
WHEN normalized events are produced
THEN the sanitizer SHALL redact secrets, high-entropy strings, and environment-specific paths from event payloads (including tool-call arguments and tool-result outputs) BEFORE the events are passed to triage or deep-analysis models or shipped to the coordinator
AND the sanitizer SHALL be the one used by the `session-log` skill, extended as needed for transcript-specific structures
AND the sanitizer SHALL NOT alter `model`, `effort`, or `usage` fields

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

#### Scenario: Central transcript events available for deep analysis
WHEN `/collect-transcripts` is invoked with `--source coordinator --since <date>`
THEN it SHALL read sanitized events from `GET /usage/events` instead of local files
AND the downstream triage and deep-analysis steps SHALL run unchanged over those events
