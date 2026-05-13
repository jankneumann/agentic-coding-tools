# Contracts

This change is a skill-content + convention change. No HTTP API, database schema, event payload, or shared client/server contract is introduced or modified.

## Sub-type evaluation

| Sub-type | Applicable? | Rationale |
|---|---|---|
| OpenAPI (HTTP API) | No | No new endpoints. Existing endpoints unchanged. |
| Database schema | No | No table/column changes. No migrations. |
| Event payloads (JSON Schema) | No | No new events emitted. |
| Type generation stubs (`pydantic`, TS interfaces) | No | No shared cross-language types introduced. |

## What does change that resembles a contract

One internal schema is extended:

- **`review-findings.schema.json`** (under `skills/parallel-infrastructure/schemas/` — exact path confirmed during implementation in task 2.2.2) gains two required fields: `axis` (5-value enum) and `severity` (5-value enum). This is an internal coordination schema between the `parallel-review-*` skills and the consensus synthesizer; it is not a public-facing contract and does not warrant a `contracts/` directory of its own.

The schema change is captured in the spec deltas under "Review Findings Schema Extension" and tested in task 2.2.1.

## Why a stub README rather than an empty `contracts/openapi/v1.yaml`

By convention in this repo, skill-content-only changes that introduce no functional endpoints place a README here rather than authoring an empty OpenAPI file. See `openspec/changes/add-prototyping-stage/contracts/README.md` and `openspec/changes/specialized-workflow-agents/contracts/README.md` for prior precedent.

`work-packages.yaml` references this README as the `contracts.openapi.primary` entry point.
