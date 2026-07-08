# Contracts: add-adaptive-model-router

Sub-types evaluated per plan-feature Step 7:

- **OpenAPI** — `openapi/v1.yaml`: the five `/routing/*` endpoints (MCP tool
  `select_model_for_task` mirrors `POST /routing/select_model`).
- **Database** — `db/schema.sql`: four additive tables (`model_catalog`, `model_posteriors`,
  `routing_decisions`, `routing_spend_ledger`). Seed data intentionally omitted: catalog rows are
  produced by the refresher; test fixtures live with the integration tests (task 2.1).
- **Events** — `events/routing-signal.schema.json`: routing signal payloads riding `audit_log` +
  OTel.
- **Type generation** — deferred to implementation task 1.4 (`contracts/generated/models.py`
  from the OpenAPI schemas); no hand-written stubs to avoid drift.

These contracts are the coordination boundary: wp-resolver, wp-dispatch, wp-feedback, and
wp-dashboard all program against them rather than each other's internals.
