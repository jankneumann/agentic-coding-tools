# Contracts — pack-and-parallelize-vendor-review

No HTTP API, database schema, or pub/sub events. Contracts are the review
packet on disk and the verify-then-wire structured-output table.

## Contract sub-types evaluated

| Sub-type | Applies? | Notes |
|----------|----------|-------|
| OpenAPI | No | No HTTP endpoints. |
| Database | No | No schema changes. |
| Events | No | Concurrency is in-process. |
| File format | **Yes** | Review packet. |
| Empirical table | **Yes** | Structured-output probe results. |

## Files

- [`review-packet.schema.json`](review-packet.schema.json) — packet metadata
  written next to the markdown body.
- [`vendor-structured-output.md`](vendor-structured-output.md) — probe table.
  Only `verified` rows may change `agents.yaml`.

Async `task_id_pattern` / `success_pattern` regexes are **out of scope**
(dg-02). This change must not add new ones.
