# Contracts

Sub-types evaluated for this change:

| Sub-type | Applies? | Why |
|---|---|---|
| OpenAPI | No | No HTTP endpoint is added or changed. |
| Database | No | No schema or migration. |
| Events | No | No event payload is added or changed. |
| Type generation | No | No OpenAPI source to generate from. |

The one machine-readable interface this change touches is the trust posture
front-matter schema, `openspec/schemas/trust-posture.schema.json`. It is
already the canonical contract for that file, so it is extended in place
(`sync_windows`, task 2.3) rather than copied here.
