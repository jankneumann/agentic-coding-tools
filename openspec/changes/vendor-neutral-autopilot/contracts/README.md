# Contracts

This change does not introduce HTTP endpoints, database schema, or event payloads. It introduces runtime contracts between lifecycle skills, dispatch adapters, and provider model mapping.

Evaluated contract sub-types:

- OpenAPI: not applicable.
- Database: not applicable.
- Events: not applicable.
- Runtime interface contracts: applicable; documented in this directory.

Contract artifacts:

- `phase-dispatch-contract.md` documents the provider-neutral dispatch payload and result shape.
- `provider-model-map.schema.json` documents the provider model mapping shape used by archetype resolution and dispatch.

