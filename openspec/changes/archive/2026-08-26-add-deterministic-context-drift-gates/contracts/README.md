# Contracts — add-deterministic-context-drift-gates

## Primary contract

`context-drift-gate.schema.json` — the structured report the composed drift gate emits.

This change has no HTTP surface, so the report schema occupies the primary contract slot,
following the convention ri-08 and ri-09 used for the same reason. See
`openspec/contracts/README.md` for the promotion rule: this file must be copied to
`openspec/contracts/project-context-refresh/schemas/` **before** the change is archived,
and kept byte-identical with the installed copy under
`skills/project-context-refresh/install_assets/openspec/schemas/`.

The schema's job is to make four things distinguishable that the existing terminal refresh
outcome collapses into one `degraded` value:

| Group | Blocks? | Meaning |
|---|---|---|
| `blocking_drift` | yes (exit 2) | committed managed output is stale |
| `informational_drift` | no | an active change carries an unmerged spec delta |
| `not_configured` | no | an optional owner is absent — external degradation |
| `failed` | yes (exit 1) | a producer raised, or provenance is unverifiable |

## Sub-types evaluated

| Sub-type | Applicable | Why |
|---|---|---|
| OpenAPI | no | The gate is a CLI entry point and a CI job. It introduces no endpoint, and it does not extend the coordinator's HTTP surface. |
| Database | no | The gate records nothing durable — it constructs no `OperationStore` and writes no manifest, by requirement. |
| Events | no | Nothing subscribes to gate outcomes; the CI exit code is the signal. |
| Type generation | no | The report is consumed by the gate's own renderer and by humans reading CI logs, not across a language boundary. |

## Contracts consumed, not defined here

- `context-refresh-types.schema.json` — `GitRevision`, `RepositoryPath`, and `Remediation`
  are referenced by `$ref` rather than restated.
- `context-checkpoint.schema.json` — ri-09's per-package report. This change adds it to the
  promoted-contract byte-compare test, which currently omits it; the schema itself is
  unchanged.
- `architecture-provenance.schema.json` — the committed provenance baseline this change
  begins tracking. Its shape is unchanged; only its version-control status changes.
