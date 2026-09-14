# Contracts — harden-review-dispatch-parse-and-timeouts

This change introduces no HTTP API, no database schema, and no pub/sub events.
The contracted interfaces are on-disk JSON documents the dispatcher, converge
loop, and prompt helper must agree on.

## Contract sub-types evaluated

| Sub-type | Applies? | Notes |
|----------|----------|-------|
| OpenAPI | No | No HTTP endpoints. |
| Database | No | No schema changes. |
| Events | No | Coercion/repair/timeouts are Python logs and sidecar files, not bus events. |
| File format | **Yes** | Alias table, timeout budget, raw-output sidecar metadata. |

## Files

- [`finding-coercion.schema.json`](finding-coercion.schema.json) — alias table and
  severity↔criticality map applied before schema validation.
- [`dispatch-timeout-budget.schema.json`](dispatch-timeout-budget.schema.json) —
  per-vendor timeout seconds, override rules, empty-findings elapsed floor.
- [`vendor-raw-output.schema.json`](vendor-raw-output.schema.json) — sidecar
  metadata next to full stdout/stderr dumps.

The findings document itself remains `openspec/schemas/review-findings.schema.json`.
This change does not fork that schema.
