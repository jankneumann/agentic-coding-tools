# Contracts — rescope-context-drift-enforcement

## Sub-types evaluated

| Sub-type | Applicable | Rationale |
|---|---|---|
| JSON Schema | **Yes** | `context-drift-gate.schema.json` is the published contract for the gate report. This change adds the resolved base revision to `tree` and an attribution axis to `ProducerFinding`. |
| OpenAPI | No | No HTTP surface. The gate is a CLI producing a JSON document on stdout. |
| Database | No | No schema, migration, or query changes. |
| Events | No | The `context_gate` record appended to `docs/merge-logs/metrics.jsonl` reuses the existing `MergeEvent` dataclass (`merge_events.py:28-45`), whose `event_type` is an open string. No new payload schema. |
| Type generation | No | No generated bindings; the schema is validated directly in tests. |

## `context-drift-gate.schema.json`

Two additive deltas against the published schema:

1. `properties.tree` gains `base_resolved_revision` and `base_resolved_from`.
2. `$defs.ProducerFinding` gains `attribution` and `attributed_owner`.

**`schema_version` stays at `1`.** Its own description says it is "incremented only on a
breaking change," and neither addition is breaking: both are absent from the relevant
`required` lists, so every report written before this change still validates.

The coupling that does exist runs the other way. `tree` and `ProducerFinding` are both
`additionalProperties: false`, so a report carrying the new fields does **not** validate
against the old schema. The schema must therefore land in the same change as the code that
emits them — it cannot trail it.

`base_resolved_from` is an enum of `remote | local | null` rather than a free string,
because the whole point of recording it is that a reader can tell the two apart without
re-deriving them. `attribution` is a three-value enum including `indeterminate`, so an
undecidable case is stated rather than silently coerced — it is *treated* as inherited for
the verdict, but the report does not claim to know something it does not.

Task 1.7 and task 2.7 promote this file to `openspec/schemas/` and the mirrored copy under
`openspec/contracts/project-context-refresh/schemas/`; the copy here is the reviewable
contract as-proposed.
