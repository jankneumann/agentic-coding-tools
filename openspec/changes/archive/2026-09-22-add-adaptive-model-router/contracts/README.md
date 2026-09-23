# Contracts: add-adaptive-model-router

Sub-types evaluated per plan-feature Step 7:

- **OpenAPI** — `openapi/v1.yaml`: the five `/routing/*` endpoints (MCP tool
  `select_model_for_task` mirrors `POST /routing/select_model`).
- **Database** — `db/schema.sql`: four additive tables (`model_catalog`, `model_posteriors`,
  `routing_decisions`, `routing_spend_ledger`). Seed data intentionally omitted: catalog rows are
  produced by the refresher; test fixtures live with the integration tests (task 2.1).
- **Events** — `events/routing-signal.schema.json`: routing signal payloads riding `audit_log` +
  OTel.
- **Generated models** — `contracts/generated/models.py` is the task 1.3 Pydantic projection
  of the OpenAPI schemas; focused parity tests guard fields, requiredness, and key scalar types.

These contracts are the coordination boundary for the canonical dg-00 packages:
`wp-db-catalog`, `wp-resolver`, `wp-dispatch`, and `wp-integration`. Feedback producers
and the usage dashboard remain deferred consumers recorded in `../deferred-tasks.md`.
