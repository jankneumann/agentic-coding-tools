# Durable context refresh record contracts

This directory defines the v1 coordination boundary for
`project-context-runtime`.

| Contract | Purpose |
|---|---|
| `context-refresh-types.schema.json` | Shared producer, artifact, validation, remediation, fallback, revision, and semantic-index definitions |
| `context-refresh-operation.schema.json` | Mutable clone-local operation ledger stored outside Git-tracked content |
| `context-refresh-manifest.schema.json` | Deterministic repository manifest projection suitable for staging |

No OpenAPI, database, or event contract applies to this change. The runtime is
a local Python library; the work-package schema's `contracts.openapi` field
points to this README as the primary contract index.

## Compatibility

- All schemas use JSON Schema Draft 2020-12.
- `schema_version` is exactly `1`.
- Unknown versions fail closed and are never rewritten as v1.
- `$ref` resolution is local to this directory and must not access the network.
- The mutable operation and deterministic manifest are intentionally different
  documents; consumers must not commit `operation.json`.

## Canonical examples

The implementation test suite must validate at least:

- a pending operation with no producer results;
- a degraded completed operation with exact-search fallback;
- a successful manifest with deterministic repository artifacts;
- a manifest whose semantic index is pending with an explicit fallback;
- rejection examples for unknown versions, unsafe paths, duplicate producer
  IDs, missing remediation, and mismatched semantic revisions.
