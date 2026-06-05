# Usage API

## ADDED Requirements

### Requirement: Usage Query Endpoints

The coordinator API SHALL expose read endpoints for aggregated usage behind the
existing Bearer-token authentication. It MUST provide `/usage/summary`,
`/usage/daily`, `/usage/by-model`, and `/usage/by-vendor`, each accepting
optional `vendor`, `model`, `principal`, and date-range filters.

#### Scenario: Summary returns fleet totals

- **WHEN** an authenticated client requests `GET /usage/summary`
- **THEN** the response SHALL include total input/output/cache tokens and total
  estimated cost across all records matching the (optional) filters

#### Scenario: Daily rollup is bucketed by UTC day

- **WHEN** an authenticated client requests `GET /usage/daily`
- **THEN** the response SHALL contain one bucket per UTC day, each with
  per-vendor token and cost subtotals

#### Scenario: Unauthenticated request is rejected

- **WHEN** a client requests any `/usage/*` endpoint without a valid Bearer key
- **THEN** the API SHALL respond `401` and SHALL NOT return usage data

#### Scenario: Filters narrow the result set

- **WHEN** a client requests `GET /usage/by-model?vendor=claude`
- **THEN** the response SHALL include only records whose vendor is `claude`,
  grouped by model

### Requirement: Usage Ingestion Endpoint

The API SHALL accept batched `UsageRecord` writes from the collector and apply
them idempotently using the `(vendor, session_id, record_hash)` key.

#### Scenario: Duplicate batch is a no-op

- **WHEN** the collector POSTs a batch whose records were already persisted
- **THEN** the API SHALL acknowledge success and insert zero new rows

### Requirement: Live Usage Event Stream

The API SHALL expose `GET /events/usage` as a dedicated Server-Sent Events
stream — separate from `/events/work` (which is keyed on a non-empty work-id
and therefore unsuitable for a global usage feed). The endpoint SHALL accept
the same Bearer auth as the rest of the usage API and an optional `vendor`
query filter. When new records are persisted the API SHALL publish a
`usage.recorded` event to this stream whose `data:` payload is a JSON object
containing `{ "vendors": [...], "record_count": int, "ts": "<RFC3339>" }`.
Polling MUST remain available as a fallback.

#### Scenario: New records push an SSE event

- **WHEN** a batch of new records is persisted
- **THEN** subscribers connected to `GET /events/usage` SHALL receive a
  `usage.recorded` event whose payload lists the affected vendors and the
  count of new records

#### Scenario: Vendor filter narrows the stream

- **GIVEN** a subscriber connects to `GET /events/usage?vendor=claude`
- **WHEN** a batch lands that contains only `openai` records
- **THEN** the API SHALL NOT push a `usage.recorded` event to that subscriber

### Requirement: Pricing Seeded From Agent Registry

Cost estimates SHALL be computed from a pricing table whose model identifiers
are seeded from `agent-coordinator/agents.yaml` (`model` + `model_fallbacks`),
so the API's known-model set cannot drift from the configured vendor models.
Estimated costs MUST be labelled as estimates.

#### Scenario: Configured model has a price entry

- **WHEN** a model is listed in `agents.yaml`
- **THEN** the pricing table SHALL contain an entry (rate or explicit "unknown")
  for that model identifier
