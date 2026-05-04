# Contracts — add-prototyping-stage

This change introduces a new skill (`/prototype-feature`) and extends `/iterate-on-plan`. No HTTP API endpoints, database schemas, or event payloads are introduced.

## Contract sub-types evaluated

| Sub-type | Applicable? | Rationale |
|---|---|---|
| OpenAPI | No | No HTTP endpoints introduced. Skills communicate via file artifacts and CLI arguments. |
| Database schema | No | No persistent state changes. Prototype outcomes live in `openspec/changes/<id>/prototype-findings.md`. |
| Event payload | No | No cross-service events. Parallel variant dispatch uses in-process `Task()` orchestration. |
| **Internal data schema** | **Yes** | `VariantDescriptor` is a structured artifact shared between `/prototype-feature` (producer) and `/iterate-on-plan` (consumer). Schema enforces compatibility. |
| Internal data schema | Yes | `SynthesisPlan` is the output of `synthesize_variants()` consumed by iterate-on-plan's prototype-context loader. |

## Files

- `schemas/variant-descriptor.schema.json` — JSON Schema for `VariantDescriptor` objects recorded in `prototype-findings.md`. Producer: `/prototype-feature`. Consumer: `/iterate-on-plan --prototype-context`.
- `schemas/synthesis-plan.schema.json` — JSON Schema for the output of `synthesize_variants(descriptors) -> synthesis_plan`. Producer: `skills/parallel-infrastructure/scripts/variant_descriptor.py`. Consumer: `/iterate-on-plan` prototype-context loader.

## Stability

Both schemas are **v1** (draft). Additive changes only within v1 (new optional fields). Breaking changes require a new major version file (`variant-descriptor-v2.schema.json`) and a migration note in iterate-on-plan's skill doc.
