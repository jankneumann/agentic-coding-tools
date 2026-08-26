# Contracts — fix-architecture-freshness-evidence

## Sub-types evaluated

| Sub-type | Applicable | Rationale |
|---|---|---|
| JSON Schema | **Yes** | `architecture-provenance.schema.json` is the published contract for `docs/architecture-analysis/architecture.provenance.json`. This change bumps it to `schema_version: 2` and adds a required `tier` enum to every artifact entry. |
| OpenAPI | No | No HTTP endpoint is introduced or modified. The RPC facade is a subprocess/stdio interface, not an HTTP surface, and its method names and response fields are unchanged — only the *values* of already-published fields become populated. |
| Database | No | No schema, migration, or query changes. |
| Events | No | No event payloads are introduced or modified. |
| Type generation | No | The published schema has no generated Python or TypeScript binding in this repository; its only programmatic consumer is `skills/tests/refresh-architecture-contracts/test_architecture_provenance_contract.py`, which validates against the JSON directly. |

## `architecture-provenance.schema.json`

The v2 shape. Two deltas against the published v1
(`openspec/schemas/architecture-provenance.schema.json`):

1. `properties.schema_version.const`: `1` → `2`
2. `properties.artifacts.items` gains a required `tier` of `committed | local-cache`

Artifact items are `additionalProperties: false`, so `tier` cannot be introduced
additively — every reader of the published schema must move in step. That is why the
version constant moves with it rather than accepting both shapes (design D2).

Task 1.5 promotes this file to `openspec/schemas/`; the copy here is the reviewable
contract as-proposed.
