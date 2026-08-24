# agent-coordinator Specification (delta)

## ADDED Requirements

### Requirement: Model Routing API Surface

The coordinator SHALL expose the model-routing operations over both transports — HTTP
(`POST /routing/select_model`, `GET /routing/catalog`, `GET /routing/decisions/{id}`,
`GET /routing/usage`, `POST /routing/feedback`) and MCP tools for local agents — with Bearer
authentication consistent with existing endpoints. Selection requests SHALL identify `agent_id`
and `dispatch_kind`; responses SHALL return the selected candidate (including optional thinking),
ranked adaptive alternatives, ordered static `capacity_fallbacks`, and decision provenance.

#### Scenario: Cloud agent selects a model over HTTP

- **WHEN** a cloud agent POSTs task signals, `agent_id`, and `dispatch_kind` to
  `/routing/select_model` with a valid Bearer token
- **THEN** the response SHALL contain the selected candidate, ranked alternatives, ordered static
  `capacity_fallbacks`, and a decision ID

#### Scenario: Local agent uses the MCP tool

- **WHEN** a local agent invokes the `select_model_for_task` MCP tool
- **THEN** the same resolver and request/response semantics SHALL serve the request as the HTTP path

### Requirement: Model Routing Storage Migrations

The coordinator database SHALL gain additive-only migrations for `model_catalog`,
`model_posteriors`, `routing_decisions`, and `routing_spend_ledger`; applying and rolling back the
feature flag MUST NOT require destructive schema changes.

#### Scenario: Migrations are additive

- **WHEN** the model-routing migrations are applied to an existing database
- **THEN** no existing table SHALL be altered destructively
- **AND** disabling adaptive routing SHALL require no schema rollback

### Requirement: Routing Watchdog Jobs

The coordinator watchdog SHALL schedule the catalog refresher, local-endpoint health probes, ToS
monitor, model canary, and feedback aggregation jobs on configurable intervals, and job failures
SHALL be recorded as signals without crashing the watchdog loop.

#### Scenario: Job failure is contained

- **WHEN** the catalog refresher raises an exception
- **THEN** the watchdog SHALL record a failure signal and continue scheduling other jobs
