# usage-accounting Specification (delta)

## ADDED Requirements

### Requirement: Normalized Usage Record

The system SHALL represent model usage as one record per vendor API call (one assistant message in a
transcript), never as a per-session aggregate, so that rollups by phase, agent, model, or day are
queries rather than re-ingestion. Each record SHALL carry: `ts`, `vendor`, `model` (the vendor's
own identifier as observed, never the archetype tier), `effort` (the harness-reported reasoning
level when present, else null), `input_tokens`, `output_tokens`, `cache_creation_tokens`,
`cache_read_tokens`, `thinking_tokens` (null when the vendor does not report it), `session_id`,
`agent_id` (the sub-agent id for sidechain transcripts, null for the parent session),
`parent_session_id`, `project`, `principal`, `host`, `git_branch`, `vendor_cost_usd` (a cost figure
the vendor itself reported, else null), and `record_hash`.

`record_hash` SHALL be the SHA-256 of the canonical JSON of `(vendor, session_id, agent_id,
message_id_or_uuid, usage)`, and `(vendor, session_id, record_hash)` SHALL be unique so that
re-ingesting an unchanged transcript inserts zero rows.

#### Scenario: One row per assistant message

- **WHEN** a Claude Code transcript contains 58 assistant records with `message.usage`
- **THEN** ingesting it SHALL produce exactly 58 usage records
- **AND** each record's `model` SHALL equal that message's `message.model`
- **AND** each record's `effort` SHALL equal that line's top-level `effort`

#### Scenario: Re-ingestion is idempotent

- **GIVEN** a transcript already ingested
- **WHEN** the collector runs again with no new lines
- **THEN** zero rows SHALL be inserted
- **AND** the ingest state cursor SHALL be unchanged

#### Scenario: Thinking tokens captured when reported

- **WHEN** an assistant message carries `usage.output_tokens_details.thinking_tokens = 662`
- **THEN** the usage record's `thinking_tokens` SHALL be 662
- **AND** a message without that field SHALL yield `thinking_tokens = null`, not 0

### Requirement: Dispatch Record

The system SHALL record one dispatch record per autopilot phase dispatch, written by the
orchestrator at dispatch time, carrying: `dispatch_id`, `change_id`, `phase`, `archetype`,
`intended_model` (provider-specific identifier as passed to the adapter), `intended_tier`,
`intended_thinking`, `provider`, `signals` (JSON), `override_source` (`null`, `env`, or `config`),
`session_id` (the orchestrator's session), `agent_id` (the dispatched sub-agent id, patched in when
the dispatch returns), `transcript_path` (when known), `dispatched_at`, and `completed_at`.

An override run SHALL still produce a dispatch record, with `override_source` set and
`archetype` carrying the archetype that would have been resolved, so that override runs are visible
to the mismatch report instead of disappearing.

#### Scenario: Dispatch record written before the sub-agent starts

- **WHEN** autopilot builds dispatch kwargs for phase `IMPLEMENT`
- **THEN** a dispatch record SHALL be POSTed to the coordinator before the adapter is invoked
- **AND** the record SHALL contain `intended_model`, `intended_thinking`, `archetype`, and `change_id`

#### Scenario: Agent id patched on return

- **WHEN** the dispatch adapter returns a sub-agent id `ad4118f0bd29192ec`
- **THEN** the dispatch record SHALL be updated with `agent_id = "ad4118f0bd29192ec"`
- **AND** `transcript_path` SHALL be set to the sidechain transcript path when it exists

#### Scenario: Override run still recorded

- **GIVEN** `AUTOPILOT_PHASE_MODEL_OVERRIDE=PLAN=gpt-5.4`
- **WHEN** autopilot dispatches `PLAN`
- **THEN** a dispatch record SHALL exist with `intended_model = "gpt-5.4"` and `override_source = "env"`
- **AND** `archetype` SHALL be `"architect"`

### Requirement: Sub-agent Transcript Discovery

The Claude Code transcript adapter SHALL discover sidechain transcripts at
`<projects-dir>/<project-hash>/<session-id>/subagents/agent-<agent-id>.jsonl` in addition to the
parent `<session-id>.jsonl`, and SHALL stamp `agent_id` and `parent_session_id` on every event from
a sidechain file.

#### Scenario: Sidechain transcripts enumerated with the parent

- **GIVEN** a session directory containing the parent transcript and three `subagents/agent-*.jsonl` files
- **WHEN** the adapter discovers sessions
- **THEN** it SHALL return four session summaries
- **AND** the three sidechain summaries SHALL have `parent_session_id` equal to the parent session id
- **AND** `agent_id` SHALL equal the `agent-<id>` filename stem without the prefix

### Requirement: Hook-Driven Ingestion With Offline Spool

The system SHALL run a usage collector from the Claude Code `Stop`, `SubagentStop`, and
`SessionEnd` hooks that reads transcript lines beyond a per-file cursor, normalizes them via the
`collect-transcripts` adapters, sanitizes them, and POSTs usage records and sanitized transcript
events to the coordinator. The collector SHALL be gated by `USAGE_LEDGER_ENABLED` (default `true`
when a coordinator URL is configured, otherwise `false`). It SHALL always exit 0, SHALL complete
within 5 seconds at p95 for 500 new lines, SHALL be killed by the hook timeout at 30 seconds, and
SHALL advance cursors only after the coordinator acknowledges the batch.

When the coordinator is unreachable the collector SHALL append the batch to a local spool under
`~/.claude/state/usage-spool/` and SHALL replay spooled batches at the start of its next run before
processing new lines.

#### Scenario: Stop hook ships new usage within the latency target

- **GIVEN** a running session with 12 new assistant messages since the last hook run
- **WHEN** the `Stop` hook fires
- **THEN** 12 usage records SHALL be visible via `GET /usage/summary` within 60 seconds
- **AND** the hook process SHALL exit 0

#### Scenario: Coordinator unreachable spools and exits zero

- **GIVEN** the coordinator returns connection refused
- **WHEN** the collector runs
- **THEN** it SHALL write the batch to the spool directory
- **AND** exit 0 without advancing the cursor
- **AND** on the next run with the coordinator reachable it SHALL replay the spool first and then delete the replayed file

#### Scenario: Collector disabled leaves behaviour unchanged

- **GIVEN** `USAGE_LEDGER_ENABLED=false`
- **WHEN** any hook fires
- **THEN** the collector SHALL exit 0 immediately without reading transcripts or contacting the coordinator

#### Scenario: Cloud session parity

- **GIVEN** a Claude Code web session in an ephemeral container with `COORDINATION_API_URL` set
- **WHEN** the session's `Stop` and `SubagentStop` hooks fire
- **THEN** usage records and transcript events for the parent and every sub-agent SHALL reach the coordinator without any `claude --teleport` step
- **AND** the records SHALL carry `host` identifying the container and `principal` from the API key identity

### Requirement: Versioned Pricing Table

The coordinator SHALL load a pricing table from `agent-coordinator/pricing.yaml` carrying
`schema_version` (integer, validated against an enum), a monotonic `version` string, and per
`(vendor, model)` rates in USD per million tokens for `input`, `output`, `cache_read`,
`cache_write`, and optionally `thinking`. Model keys MAY be exact identifiers or prefix patterns;
exact matches SHALL win over prefixes. The loader SHALL validate the file with a JSON schema and
fail loud at startup on a malformed file or an unknown vendor. Rates SHALL be edited by hand; no
automatic refresh is part of this capability.

#### Scenario: Loader rejects malformed pricing file

- **WHEN** `pricing.yaml` omits `version` or lists a vendor not in `agents.yaml`
- **THEN** coordinator startup SHALL fail with an error naming the offending key

#### Scenario: Exact model key wins over prefix

- **GIVEN** rates for `claude-opus-5` and prefix `claude-opus-`
- **WHEN** cost is estimated for model `claude-opus-5`
- **THEN** the exact entry SHALL be used

### Requirement: Cost Estimation Provenance

Every cost figure the system stores or reports SHALL carry `pricing_version` and
`estimated = true`. When no rate exists for a record's `(vendor, model)`, `cost_usd` SHALL be
null with `cost_reason = "no_price"`; the system SHALL never store zero as a stand-in for unknown.
When the vendor reported its own cost, `vendor_cost_usd` SHALL be stored alongside the estimate
and reports SHALL prefer it, labelled as vendor-reported.

#### Scenario: Unknown model yields null cost with reason

- **WHEN** a usage record has `model = "experimental-x"` with no pricing entry
- **THEN** `cost_usd` SHALL be null and `cost_reason` SHALL be `"no_price"`
- **AND** the summary route SHALL count the record under `unpriced_records`

#### Scenario: Estimate stamped with pricing version

- **WHEN** a usage record is priced under pricing version `2026.09.1`
- **THEN** the record SHALL carry `pricing_version = "2026.09.1"` and `estimated = true`

### Requirement: Sanitized Transcript Event Store With Retention

The coordinator SHALL store normalized, sanitized transcript events per session and agent in a
`transcript_events` table for central deep analysis, and SHALL purge events older than 90 days via a
nightly `WatchdogService` job. Usage records and dispatch records SHALL never be purged by that
job. Events SHALL pass the `collect-transcripts` sanitizer before leaving the session host; the
coordinator SHALL reject an ingest batch whose `sanitized` flag is false.

#### Scenario: Events older than retention are purged

- **GIVEN** transcript events dated 91 days ago and usage records of the same age
- **WHEN** the nightly retention job runs
- **THEN** the 91-day-old transcript events SHALL be deleted
- **AND** the usage record count SHALL be unchanged

#### Scenario: Unsanitized batch rejected

- **WHEN** `POST /usage/ingest` receives an events batch with `sanitized: false`
- **THEN** the coordinator SHALL return 422 and store nothing from that batch

### Requirement: Usage Query Routes

The coordinator SHALL expose `POST /usage/ingest` and `POST /usage/dispatch` (API key required)
and `GET /usage/summary`, `GET /usage/by-phase`, `GET /usage/by-model`, `GET /usage/mismatches`,
and `GET /usage/events` (unauthenticated GET, matching existing convention). All GET routes SHALL
accept `since`, `until`, `change_id`, `vendor`, and `model` filters and SHALL return totals for the
four token counters, thinking tokens, estimated cost, vendor cost, and `unpriced_records`.

#### Scenario: Summary reflects ingested records

- **GIVEN** 20 usage records for vendor `claude_code` across two models
- **WHEN** `GET /usage/summary?vendor=claude_code` is called
- **THEN** the response SHALL include per-model totals for the two models and a grand total

#### Scenario: Ingest requires API key

- **WHEN** `POST /usage/ingest` is called without an API key
- **THEN** the response SHALL be 401

### Requirement: Intended-Versus-Actual Mismatch Reporting

The coordinator SHALL join dispatch records to usage records on `(session_id, agent_id)` and SHALL
report, per `(change_id, phase, dispatch_id)`: intended model, intended thinking, the set of actual
models observed, the set of actual effort values observed, token totals, and estimated cost. A
dispatch SHALL be flagged `model_mismatch` when any observed model is not the intended model, and
`thinking_mismatch` when the intended thinking is non-null and any observed effort differs from it.
A dispatch with no joined usage records SHALL be flagged `unattributed`.

#### Scenario: Sub-agent ran a different model than intended

- **GIVEN** a dispatch record for `PLAN_REVIEW` with `intended_model = "claude-fable-5-1"`
- **AND** the joined sidechain transcript shows `message.model = "claude-opus-5"`
- **WHEN** `GET /usage/by-phase?change_id=<id>` is called
- **THEN** that row SHALL have `model_mismatch = true` and `actual_models = ["claude-opus-5"]`

#### Scenario: Thinking mismatch detected

- **GIVEN** a dispatch record with `intended_thinking = "xhigh"` and observed `effort = "high"`
- **WHEN** the by-phase report is generated
- **THEN** the row SHALL have `thinking_mismatch = true`

#### Scenario: Unattributed dispatch surfaced

- **GIVEN** a dispatch record whose `agent_id` matches no usage record
- **WHEN** `GET /usage/mismatches` is called
- **THEN** the dispatch SHALL appear with `unattributed = true`
