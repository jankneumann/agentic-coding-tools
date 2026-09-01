# Contracts — extend-handoff-document-with-supervisor-record

Evaluated sub-types:

- **OpenAPI** — `openapi/handoffs.yaml`: the proposed revision of
  `openspec/contracts/agent-coordinator/openapi/handoffs.yaml`. `writeHandoff` gains
  the optional `supervisor_record` property; `readHandoff`'s response documents the
  key. Integration copies this file over the canonical one (task 5.2).
- **Database** — `db/034_handoff_supervisor_record.sql`: the migration verbatim
  (column, `DROP FUNCTION` of the eight-arg overload, recreated `write_handoff` with
  the defaulted ninth parameter, `read_handoff` selecting the column). Task 1.2
  copies it to `agent-coordinator/database/migrations/`.
- **Events** — none. The record is carried inside the existing handoff payload; no
  new bus event.
- **Type generation** — none. `HandoffDocument` and `PhaseRecord` are hand-written
  dataclasses; the inner record is a `dict[str, Any]` validated by
  `schemas/supervisor-record.schema.json`; the dedicated `schemas/supervisor-record-mirror.schema.json` validates the tracked non-derivable subset. Both are promoted to `openspec/schemas/` in task 5.2 so runtime validation survives archival.

Compatibility boundary: migration 034 preserves migration 002 defaults, invoker-security mode, empty-summary semantics, and aggregate ordering.

Coordination boundary: `wp-coordinator` and `wp-host-plumbing` both add one key named
here and are otherwise disjoint; `wp-supervisor-builder` produces documents that must
validate against `schemas/supervisor-record.schema.json`.
