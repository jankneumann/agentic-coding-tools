# harness-engineering — delta for judge-transcript-struggle-triage-in-collect-transcripts

Closes drift between the "Session Transcript Mining" requirement's existing
model-resolved triage language and the pre-this-change pure-arithmetic
implementation: triage now asks a calibrated judgment for struggle
classification, deep-analysis flagging, user-redirection, and out-of-scope
work, falling back to the original deterministic rule when the judgment is
unavailable. The four counters themselves are untouched.

## MODIFIED Requirements

### Requirement: Session Transcript Mining

The system SHALL ingest raw session transcripts from supported coding-agent harnesses via vendor-specific adapters, normalize them to a common event schema, triage them with a calibrated judgment over a deterministic fallback, and write structured findings to episodic memory for consumption by `/improve-harness`.

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
THEN a triage pass SHALL compute the deterministic counters (retry_count, tool_error_count, scope_violation_count, user_correction_count) via unchanged pure functions
AND SHALL compact the session's normalized events to user/assistant/tool-result text (excluding tool_use payloads) and ask a single calibrated judgment call for struggle_level (a bounded choice among none/low/medium/high), whether the session warrants deep analysis, whether the user redirected the agent, and whether the agent did out-of-scope work
AND WHEN the judgment is unavailable (the decision helper cannot be reached, or returns no usable answer) THEN struggle_level and the deep-analysis flag SHALL fall back to the prior weighted-sum-over-counters rule with its 5/10 bucket thresholds, unchanged bit for bit, and the redirection/out-of-scope judged fields SHALL be absent rather than guessed
AND SHALL persist the score (counters, struggle_level, flagged_for_deep_analysis, and the judged fields when available) under the session id alongside the normalized transcript

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
