# Contracts: Specialized Workflow Agents

## Evaluated Contract Sub-Types

### OpenAPI Contracts
**Not applicable.** This feature does not introduce or modify HTTP API endpoints.
The `agent_requirements` parameter added to `/work/submit` and `/work/claim`
extends existing endpoints with an optional JSONB field — this is covered by
the existing OpenAPI contract for the coordination API, not a new one.

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
