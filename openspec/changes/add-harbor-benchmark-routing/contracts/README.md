# Contracts — add-harbor-benchmark-routing

Sub-types evaluated:

- **Database** — applies. `db/schema.sql` is the contract for migration
  `035_model_routing.sql` (`model_catalog`, `model_posteriors` only; see design.md
  D3 for what stays with `add-adaptive-model-router`).
- **Event/data schemas** — applies. `schemas/combo.schema.json`,
  `schemas/trial-record.schema.json`, and `schemas/corpus-manifest.schema.json` are
  the coordination boundary between the converter, sweep runner, importer, and
  scorecard work packages.
- **OpenAPI** — not applicable as a new surface. `resolve_for_phase` keeps its
  existing response shape; adaptive mode only adds entries to the existing
  `reasons[]` array (model-routing.4 scenarios pin this).
- **Type generation** — deferred to implementation: Pydantic models for the three
  JSON schemas are generated inside `packages/harbor-bench` (task 1.1 validates the
  schemas themselves).
