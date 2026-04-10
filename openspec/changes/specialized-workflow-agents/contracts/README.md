# Contracts: Specialized Workflow Agents

## Evaluated Contract Sub-Types

### OpenAPI Contracts
**Applicable — additive parameter extension.** Phase 3 adds an optional
`agent_requirements` parameter to existing `/work/submit` and `/work/claim`
endpoints. This is a backward-compatible extension (new optional field on
existing request bodies). No new endpoints are introduced, but the request
schemas for these two endpoints change. The existing coordination API OpenAPI
spec should be updated to include the new field when task 3.3.2 is implemented.

### Database Contracts
**Applicable — minimal.** Phase 3 adds an `agent_requirements` JSONB column to
the `work_queue` table. This is an additive, nullable column that does not break
existing queries. The migration is defined in task 3.5.1.

### Event Contracts
**Not applicable.** No new events are introduced.

### Type Generation Stubs
**Not applicable.** The `ArchetypeConfig` dataclass is defined directly in
`agents_config.py` — no code generation from contracts needed.

## Schema Files

### archetypes.schema.json (Phase 2)
JSON Schema for `archetypes.yaml` validation, created in task 2.3.1.
Location: `openspec/schemas/archetypes.schema.json`

### work-packages.schema.json modification (Phase 3)
The optional `archetype` field added to package definitions in task 3.2.1
extends the existing schema — not a new contract file.
