# Contracts: minimum-edge-dag-inference

No new contract sub-types apply to this change. Evaluated and rejected:

| Sub-type | Applies? | Why not |
|---|---|---|
| OpenAPI | No | No HTTP endpoints are introduced or modified. `plan-roadmap` is a local skill; the analyst LLM is invoked via the in-process Agent tool, not an HTTP interface this change controls. |
| Database | No | No persistent SQL schema. The LLM verdict cache is a filesystem artifact (`.cache/plan-roadmap/dep-inference/<hash>.json`) documented in `design.md` D4 — treated as a local scratch resource, not a contract. |
| Events | No | No event payloads are emitted. Existing `roadmap-orchestration` observability (item state transitions) is unchanged. |
| Type generation | No | No cross-language types to generate; all code is Python and changes are internal to `skills/plan-roadmap/` and `skills/roadmap-runtime/`. |

## Interface changes that ARE made (in-tree, not in `contracts/`)

1. **`openspec/schemas/roadmap.schema.json`** — extended with optional `scope` object on `RoadmapItem` and `DepEdge` object shape (legacy `list[str]` still accepted). This is the existing roadmap schema; the change is tracked as a spec delta (see `specs/roadmap-orchestration/spec.md`) rather than a new contract file.
2. **Analyst dispatch input/output shape** — internal to `decomposer._dispatch_tier_b`; not a cross-process contract.

If a future change adds a cross-agent or cross-service dep-inference API (e.g., coordinator-hosted verdict cache shared across agents), that change SHOULD add OpenAPI and/or event contracts here.
