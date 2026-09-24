# agent-coordinator Specification (dg-00 delta)

## ADDED Requirements

### Requirement: Model Routing API Surface

The coordinator SHALL serve all five operations from the merged routing OpenAPI contract:
`POST /routing/select_model`, `GET /routing/catalog`, `GET /routing/decisions/{id}`,
`GET /routing/usage`, and `POST /routing/feedback`. The coordinator SHALL expose the same
selection operation as the `select_model_for_task` MCP tool, and both transports SHALL use the
same routing service.

#### Scenario: POST selection operation is served

- **WHEN** a cloud agent POSTs task signals to `/routing/select_model` with valid authentication
- **THEN** the response SHALL contain the selected candidate, ranked alternatives, and a decision ID

#### Scenario: GET catalog operation is served

- **WHEN** an authenticated caller GETs `/routing/catalog`
- **THEN** the response SHALL contain stored catalog entries without an external refresh

#### Scenario: GET decision operation is served

- **WHEN** an authenticated caller GETs `/routing/decisions/{id}` for a persisted decision ID
- **THEN** the response SHALL contain that persisted selection record

#### Scenario: GET usage operation is served

- **WHEN** an authenticated caller GETs `/routing/usage` with a valid usage window
- **THEN** the response SHALL contain the ledger aggregate for that requested window

#### Scenario: POST feedback operation is served

- **WHEN** an authenticated caller POSTs a valid event to `/routing/feedback`
- **THEN** the coordinator SHALL accept the event through the shared routing service

#### Scenario: Local agent uses the MCP tool

- **WHEN** a local agent invokes the `select_model_for_task` MCP tool
- **THEN** the same resolver SHALL serve the request as the HTTP path

### Requirement: Model Routing Storage Migrations

The coordinator database SHALL gain additive-only migrations for `model_catalog`,
`model_posteriors`, `routing_decisions`, and `routing_spend_ledger`. Applying the migration more
than once MUST preserve the schema and existing data.

#### Scenario: Migrations are additive and idempotent

- **WHEN** the model-routing migrations are applied and the migration runner is invoked again
- **THEN** no existing table SHALL be altered destructively
- **AND** the second run SHALL require no schema rollback

### Requirement: dg-00 Routing Watchdog Jobs

The coordinator watchdog SHALL schedule the OpenRouter catalog refresher, local-endpoint health
probe, and spend-ledger rollup independently. A failure in one routing job SHALL be recorded
without preventing the other jobs or the watchdog loop from continuing.

#### Scenario: Routing job failure is contained

- **WHEN** the catalog refresher raises an exception
- **THEN** the watchdog SHALL record a routing-job failure signal
- **AND** the local probe and ledger rollup SHALL remain independently schedulable

#### Scenario: Ledger rollup uses an independent schedule

- **WHEN** the ledger-rollup interval is due while the refresher or local probe is not due or fails
- **THEN** the watchdog SHALL still run the ledger rollup on its own schedule
