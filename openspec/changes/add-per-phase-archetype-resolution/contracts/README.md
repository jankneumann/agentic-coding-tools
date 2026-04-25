# Contracts

Machine-readable interface definitions for this change. The implementation MUST conform to these contracts.

## Files

| File | Purpose |
|---|---|
| `openapi/v1.yaml` | OpenAPI 3.1 contract for `POST /archetypes/resolve_for_phase`. Tests in Phase 3 validate request/response/error against this. |
| `schemas/archetypes-config-v2.schema.json` | JSON Schema for the extended `archetypes.yaml` (schema_version 1 → 2 with `phase_mapping`). Tests in Phase 2 validate the loaded config against this. |
| `schemas/loop-state-v3.schema.json` | JSON Schema for `LoopState` schema_version 3 (with `phase_archetype` field). Tests in Phase 4 validate JSON round-trip. |

## Sub-types Evaluated

- **OpenAPI** — Yes, this change adds a new HTTP endpoint (`POST /archetypes/resolve_for_phase`).
- **Database schema** — No new tables; `phase_archetype` is a new column on the existing agent-status persistence (handled in coordinator implementation, not contract layer since the column type is straightforward TEXT).
- **Event** — No new events; existing `phase_token_pre`/`phase_token_post` audit events are unchanged.
- **Type generation** — Deferred. The skills client uses untyped dicts; if type strictness becomes a need later, generate from `openapi/v1.yaml` at that point.

## Contract Revision Semantics

Per `skill-workflow` Requirement: Contract Revision Semantics — these contracts may be revised during implementation if a discovered requirement makes them inaccurate. Revisions during Phase 2/3 must be reflected in the spec deltas before Phase 9 documentation lands.
