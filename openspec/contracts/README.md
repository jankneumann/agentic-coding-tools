# Stable contract schemas

This directory is the **canonical, stable home for machine-readable contract
artifacts** (JSON Schema, OpenAPI) — parallel to `openspec/specs/` and organized
by capability:

```
openspec/contracts/<capability>/schemas/*.schema.json
openspec/contracts/<capability>/openapi/*.yaml
```

## Why this exists

Contracts were originally authored inside a change directory
(`openspec/changes/<change-id>/contracts/...`). That is the right place while
the change is *in flight*, but a contract **outlives its change**: skill and
service code is validated against it indefinitely. When the change is archived,
`openspec/changes/<id>/` moves to `openspec/changes/archive/<date>-<id>/`, and
every test or tool that loaded the contract by its change-local path breaks with
`FileNotFoundError` — silent archive-drift that only surfaces when the full test
suite runs against a clean tree.

Moving the canonical copy here gives it a path that does not move on archival.
The copy left behind in `openspec/changes/archive/<date>-<id>/contracts/` stays
as the historical snapshot of what the change shipped; the copy here is the one
live code references.

## Workflow

- **New contract, still in flight**: author it under the change dir as usual.
- **Contract that must be referenced after the change archives**: promote it here
  (same schema, capability-scoped path) and point tests/tools at
  `openspec/contracts/<capability>/...`. Do this *before* archiving the change so
  no window of drift opens.

## Current contents

| Capability | Artifact | Promoted from |
|---|---|---|
| `prototyping` | `variant-descriptor.schema.json`, `synthesis-plan.schema.json` | `add-prototyping-stage` (archived 2026-05-04) |
| `phase-record` | `phase-record.schema.json`, `handoff-local-fallback.schema.json` | `phase-record-compaction` (archived 2026-04-25) |
| `project-context-refresh` | `context-refresh-manifest.schema.json`, `context-refresh-operation.schema.json`, `context-refresh-types.schema.json` | `add-durable-context-refresh-records` (archived 2026-07-25) |
| `project-context-refresh` | `context-checkpoint.schema.json` | `add-branch-local-context-checkpoints` (ri-09) |
| `project-context-refresh` | `context-drift-gate.schema.json` | `add-deterministic-context-drift-gates` (ri-10) |
| `project-context-refresh` | `context-convergence-record.schema.json` | `integrate-main-context-convergence` (ri-11) |

## Contracts a skill also ships as install assets

A shared-library skill may need its schemas at runtime in repositories that have
no `openspec/contracts/` at all. `project-context-refresh` is the current
example: `skills/project-context-runtime/` loads its schemas from
`install_assets/openspec/schemas/`, and `install.sh` copies that tree into each
consumer repo.

For those capabilities the promoted copy here is **not** what the runtime loads —
it is the stable reference for tooling, review, and downstream repositories. The
two copies must stay byte-identical, so change them in the same commit;
`skills/tests/project-context-runtime/test_promoted_contracts.py` fails if they
drift, and also fails if a new install-asset schema is never promoted.
