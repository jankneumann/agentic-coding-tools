# agent-coordinator Specification (delta)

## ADDED Requirements

### Requirement: Usage Ledger Persistence

The coordinator SHALL persist model usage in four additive tables created by migration
`037_model_usage_ledger.sql`: `usage_records`, `dispatch_records`, `transcript_events`, and
`usage_ingest_state`, following the existing migration conventions (`IF NOT EXISTS`, single
transaction, checksum-tracked, never edited after apply). The migration SHALL also replace the
`agent_sessions.phase_archetype` CHECK constraint with one accepting every archetype in
`archetypes.yaml`. Cost columns SHALL enforce provenance: `pricing_version` and `estimated` are
NOT NULL whenever `cost_usd` is non-null.

#### Scenario: Migration applies additively

- **GIVEN** a coordinator database at migration 034
- **WHEN** the coordinator starts
- **THEN** migration 037 SHALL apply within one transaction
- **AND** all pre-existing tables SHALL be unchanged except the widened CHECK constraint

#### Scenario: Cost without provenance rejected

- **WHEN** an insert sets `cost_usd = 0.12` with `pricing_version = NULL`
- **THEN** the database SHALL reject the row with a constraint violation

### Requirement: Usage Ledger HTTP Coverage

The coordination HTTP API SHALL expose the usage ledger routes: `POST /usage/ingest` and
`POST /usage/dispatch`, `GET /usage/summary`, `GET /usage/by-phase`, `GET /usage/by-model`,
`GET /usage/mismatches`, and `GET /usage/events` — **all** requiring the API key, and all reads
scoped to the caller's own principal unless its profile grants cross-principal visibility.

The reads are not exempt. An earlier draft called them "unauthenticated, matching the existing
read/write convention"; the convention says the opposite for comparable data — `GET /audit` and
`GET /profiles/me` both carry `Depends(verify_api_key)`, and only genuinely low-sensitivity
routes such as `/locks/status/{path}` are open. These routes expose per-principal token spend and
cost, and `/usage/events` returns sanitized transcript content. `POST /usage/dispatch` SHALL accept an upsert keyed by
`dispatch_id` so the orchestrator can patch `agent_id` after the sub-agent returns. Routes SHALL be
listed in the API coverage enumeration and reachable through the HTTP proxy tool.

#### Scenario: Usage routes available (HTTP-USAGE-1)

- **WHEN** the HTTP API is running
- **THEN** POST /usage/ingest SHALL accept a batch of usage records and sanitized events (requires API key)
- **AND** POST /usage/dispatch SHALL upsert a dispatch record (requires API key)
- **AND** GET /usage/summary, /usage/by-phase, /usage/by-model, /usage/mismatches, and /usage/events SHALL return filtered results

#### Scenario: Ingest rejects unauthorized access (HTTP-USAGE-1a)

- **WHEN** a POST request is made to /usage/ingest without an API key header
- **THEN** the endpoint SHALL return 401 Unauthorized

#### Scenario: Dispatch upsert patches agent id (HTTP-USAGE-2)

- **GIVEN** a dispatch record `d1` with `agent_id = null`
- **WHEN** POST /usage/dispatch is called with `{"dispatch_id": "d1", "agent_id": "abc123"}`
- **THEN** the stored record SHALL have `agent_id = "abc123"` and all other fields unchanged

### Requirement: Transcript Event Retention Job

The `WatchdogService` SHALL run a nightly job that deletes `transcript_events` older than the
configured retention (`USAGE_EVENT_RETENTION_DAYS`, default 90) and SHALL record the deleted count in
the audit log under operation `usage_retention_purge`. The job SHALL NOT touch `usage_records` or
`dispatch_records`.

#### Scenario: Nightly purge audited

- **GIVEN** 40 transcript events older than 90 days
- **WHEN** the retention job runs
- **THEN** 40 rows SHALL be deleted
- **AND** an audit entry with `operation = "usage_retention_purge"` and `result.deleted = 40` SHALL exist
