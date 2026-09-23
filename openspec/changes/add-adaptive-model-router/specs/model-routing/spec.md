# model-routing Specification (dg-00 delta)

## Purpose

Wire the already-merged routing computation core to durable catalog storage, coordinator
transports, local/OpenRouter endpoints, watchdog scheduling, and a bounded static-tier fallback.
The preserved full proposal is in `deferred-specs/`; it is not a dg-00 delivery claim.

## ADDED Requirements

### Requirement: Model Catalog

The system SHALL maintain a durable catalog keyed by `(vendor, model, endpoint_kind)`, where
`endpoint_kind` is one of `vendor-cli`, `vendor-sdk`, `openrouter`, or `local`. Catalog reads
MUST be served from coordinator storage without calling an external API on the read path, and
rows older than the configured threshold SHALL be reported as stale.

#### Scenario: Catalog row served without external calls

- **WHEN** a routing request loads candidates
- **THEN** candidate rows SHALL be returned from coordinator storage
- **AND** no OpenRouter or vendor API call SHALL occur on the read path

#### Scenario: Catalog row is stale by age

- **WHEN** a stored row's refresh timestamp is older than the configured stale threshold
- **THEN** the read SHALL return that stored row with `stale: true`
- **AND** the read SHALL NOT trigger an external refresh

### Requirement: OpenRouter Catalog Refresher

The system SHALL refresh OpenRouter model pricing and availability on a schedule using a
standing key. A failed refresh MUST leave previously stored rows available to readers.

#### Scenario: Scheduled refresh updates pricing

- **WHEN** OpenRouter reports a changed price
- **THEN** the stored row SHALL receive the new price and refresh timestamp

#### Scenario: Refresh failure preserves rows

- **WHEN** the OpenRouter API is unavailable
- **THEN** existing catalog rows SHALL remain served and become stale by age

### Requirement: Local Endpoint Registration

The system SHALL register local OpenAI-compatible endpoints declared with `endpoint_kind` and
`base_url`, health-probe them, and exclude unavailable rows from resolver candidates.

#### Scenario: Unhealthy local endpoint is excluded

- **WHEN** a local endpoint fails its health probe
- **THEN** its catalog row SHALL be marked unavailable
- **AND** the resolver SHALL exclude it until a probe succeeds

### Requirement: Adaptive Selection Resolver Surface

The coordinator SHALL expose the merged resolver through `select_model_for_task`, returning a
selected candidate, ranked alternatives, exclusions, and a durable decision ID.

#### Scenario: Selection is persisted

- **WHEN** the resolver selects a feasible candidate
- **THEN** the response SHALL include a decision ID
- **AND** querying that decision ID SHALL return the persisted selection record

### Requirement: Metered-Counterfactual Cost Ledger

The system SHALL record actual and counterfactual spend rows and SHALL label estimated-token
rows. The watchdog SHALL schedule a current-month ledger rollup independently of refresh/probe
jobs.

#### Scenario: Ledger distinguishes estimates

- **WHEN** usage is recorded from estimated token counts
- **THEN** the ledger row SHALL retain `tokens_estimated: true`

#### Scenario: Ledger records actual and counterfactual spend

- **WHEN** a completed routing decision reports usage and baseline pricing
- **THEN** one ledger row SHALL record both `actual_usd` and `counterfactual_usd`
- **AND** usage summaries SHALL compute savings from those recorded values

### Requirement: Static-Tier Fallback and Kill Switch

Adaptive resolution SHALL be default-off. When `ROUTING_ADAPTIVE` is off, the exact static
resolution object SHALL be returned. When enabled, resolver error or timeout MUST return that
same static object within the configured bound.

#### Scenario: Flag off preserves the exact result

- **WHEN** `ROUTING_ADAPTIVE` is absent or off
- **THEN** phase resolution SHALL return the exact pre-change static result

#### Scenario: Resolver timeout is bounded

- **WHEN** the adaptive resolver does not respond within its configured timeout
- **THEN** the caller SHALL receive the exact static result within the bounded fallback window

#### Scenario: Resolver unavailability or error is bounded

- **WHEN** adaptive routing is enabled and the resolver is unavailable or raises an error
- **THEN** the caller SHALL receive the exact static result within the configured fallback bound
