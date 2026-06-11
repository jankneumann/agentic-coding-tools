# Contracts — add-timestamped-priorities-tree

## Sub-types evaluated

| Sub-type | Applies? | Notes |
|---|---|---|
| OpenAPI (REST endpoints) | **No** | This change does not introduce or modify HTTP endpoints. |
| Database (schema migrations) | **No** | No schema changes; the coordinator is not involved in writing priorities artifacts. |
| Event (event payload schemas) | **No** | No events are emitted to the EventBus or coordinator. |
| Type generation stubs | **No** | No cross-language type bindings are generated. |

## Status

This change is a single-skill, filesystem-only change. The only structured interface introduced is the **mandatory artifact header schema** on `report.json`, which is documented in `design.md` (D4) and made normative in `specs/skill-workflow/spec.md` ("Mandatory Artifact Header on Report JSON" requirement). The header schema is small enough that an inline JSON-shape description in the spec is sufficient; a separate `contracts/schemas/header.json` would be over-formalization for ~6 fields.

If the codeviz roadmap's `skills/shared/artifact_header.py` lands, that helper will become the de-facto contract for header construction. This change does not block on it.
