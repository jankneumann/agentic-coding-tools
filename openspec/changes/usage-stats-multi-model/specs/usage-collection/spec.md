# Usage Collection

## ADDED Requirements

### Requirement: Normalized Usage Record

The collector SHALL normalize every vendor's native usage data into a single
`UsageRecord` shape before persistence, so that downstream storage, pricing,
and presentation never special-case a vendor. A `UsageRecord` MUST contain:
`ts` (UTC timestamp), `vendor`, `model`, `input_tokens`, `output_tokens`,
`cache_creation_tokens`, `cache_read_tokens`, `cost_usd` (nullable),
`session_id`, `project`, `principal`, `agent_id`, `host`, and `record_hash`.

#### Scenario: Claude transcript record normalized

- **WHEN** the Claude adapter parses an assistant message in
  `~/.claude/projects/<p>/<session>.jsonl` containing a `usage` object and a
  `model` field
- **THEN** it SHALL emit one `UsageRecord` with `vendor="claude"`, the four
  token counts mapped from `input_tokens` / `output_tokens` /
  `cache_creation_input_tokens` / `cache_read_input_tokens`, and `model` set to
  the record's model name

#### Scenario: Codex token_count event normalized

- **WHEN** the Codex adapter parses a `token_count` event in
  `~/.codex/sessions/**/rollout-*.jsonl`
- **THEN** it SHALL emit one `UsageRecord` with `vendor="codex"` and token
  counts mapped from the event's per-model breakdown, including cached tokens
  where present

#### Scenario: Unknown model produces a record with null cost

- **WHEN** an adapter emits a `UsageRecord` whose `model` is not present in the
  pricing table
- **THEN** the record SHALL still be persisted with `cost_usd = null` rather
  than being dropped, so token totals remain accurate even when cost is unknown

### Requirement: Vendor Adapter Isolation

Each vendor SHALL be supported by exactly one adapter module implementing a
common interface (`discover_files()` and `iter_records()`). Adding or removing a
vendor MUST NOT require changes to the schema, storage, pricing, or API layers.

#### Scenario: Adding a vendor touches only its adapter

- **WHEN** a new vendor adapter file is added under `collector/adapters/`
- **THEN** the collector SHALL pick it up via the adapter registry without edits
  to `schema.py`, `store.py`, `pricing.py`, or the API routes

#### Scenario: Antigravity adapter is an explicit unsupported stub

- **WHEN** the Antigravity adapter is invoked
- **THEN** it SHALL raise a clearly-typed "not yet supported" signal that the
  collector records as a skipped-vendor warning, and SHALL NOT abort ingestion
  of other vendors

### Requirement: Incremental Idempotent Ingestion

The collector SHALL ingest only new data on each run and SHALL be safe to run
repeatedly without creating duplicate records. It MUST track a per-file
watermark (path, modification time, byte offset) in `usage_ingest_state` and
MUST deduplicate records on `(vendor, session_id, record_hash)`.

#### Scenario: Re-running the collector adds no duplicates

- **WHEN** the collector runs twice over an unchanged set of log files
- **THEN** the second run SHALL insert zero new rows into `usage_records`

#### Scenario: Only appended data is re-read

- **WHEN** a log file grows since the last run
- **THEN** the collector SHALL resume from the stored byte offset / mtime
  watermark rather than re-parsing the whole file

### Requirement: Fleet Attribution

Every persisted record SHALL carry fleet-attribution dimensions (`principal`,
`agent_id`, `host`) so usage can be aggregated across machines and agents.

#### Scenario: Records attributed to the ingesting principal and host

- **WHEN** the collector pushes records from a given machine
- **THEN** each record SHALL be tagged with the resolved `principal`,
  `agent_id` (when available), and `host` of that machine

### Requirement: Session-End Ingestion with Offline Spool

Ingestion SHALL be triggered automatically at session end via the existing
session lifecycle hooks. When the coordinator is unreachable, the collector
SHALL spool records locally and retry on a later run rather than losing data.

#### Scenario: Session end triggers ingestion

- **WHEN** a Claude/Codex/Gemini session ends and the session-end hook fires
- **THEN** the collector SHALL scan that vendor's logs and push new records to
  the coordinator

#### Scenario: Coordinator unreachable spools locally

- **WHEN** the collector cannot reach the coordinator API
- **THEN** it SHALL persist pending records to a local spool and exit
  non-fatally, and a subsequent successful run SHALL flush the spool
