# Contracts — add-agy-grok-pi-harnesses

Contract sub-types evaluated for this change:

| Sub-type | Applicable | Reason |
|---|---|---|
| **Roster** | **yes** | `roster.md` — the canonical vendor strings, dispatch shapes, and runtime skill directories every work package writes against. This is the real coordination boundary for this change. |
| **Config schema** | **yes** | `provider-model-map.schema.json` — bumped to `schema_version: 2`, closing the provider key set via `propertyNames.enum` so a retired harness cannot be reintroduced by config alone. |
| OpenAPI | no | This change adds no endpoints and modifies no request/response shapes. `openapi/v1.yaml` exists as a schema-required stub with no paths; it is intentionally empty. |
| Database | no | No schema changes. Retiring a harness leaves its `agent_profiles` rows intact by design — seeding is additive (see the `agent-identity` spec delta). |
| Events | no | No new or modified events. |
| Type generation | no | No OpenAPI schemas to generate from. |

The interesting contract here is `roster.md`, not an API surface. This change is a
configuration and allow-list migration across 68 files; the thing parallel agents must agree on
is *which strings identify which vendor*, and that is precisely what drifted into ~13
inconsistent allow-lists in the first place.
