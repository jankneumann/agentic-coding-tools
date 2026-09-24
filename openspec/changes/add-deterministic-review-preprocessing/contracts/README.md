# Contracts — add-deterministic-review-preprocessing

No HTTP API, database schema, or pub/sub events. Contracts are on-disk file
formats consumed by the packet builder, the dispatcher, the convergence loop,
and the OCR adapter.

## Contract sub-types evaluated

| Sub-type | Applies? | Notes |
|----------|----------|-------|
| OpenAPI | No | No HTTP endpoints. |
| Database | No | No schema changes. |
| Events | No | All in-process. |
| File format | **Yes** | Packet metadata v2, rule sidecar, coverage block, fact-check decisions. |
| Enum mapping | **Yes** | OCR category and severity to review-findings vocabulary. |

## Files

- [`review-packet.schema.json`](review-packet.schema.json) — packet metadata,
  `schema_version: 2`. Supersedes the v1 contract archived under
  `2026-09-13-pack-and-parallelize-vendor-review`; adds `selection`,
  `rule_groups`, and `truncated`.
- [`review-rules.schema.json`](review-rules.schema.json) — shape of the
  embedded `review-rules.json` sidecar and of a project's `.review-rules.json`.
- [`vendor-coverage.schema.json`](vendor-coverage.schema.json) — the optional
  `coverage` block on a findings payload, plus the finding-level
  `existing_code` and `line_resolution` fields this change adds to the
  canonical review-findings schema.
- [`fact-check-decisions.schema.json`](fact-check-decisions.schema.json) — the
  per-vendor decision file written to the round directory.
- [`ocr-adapter.md`](ocr-adapter.md) — OCR command line, output rewrite, and
  the enum mapping table added to `finding-coercion.json`.

Every JSON contract is Draft 2020-12 and is validated by a test that locates
this directory through `openspec_paths.change_dir`, so archival does not break
it.
