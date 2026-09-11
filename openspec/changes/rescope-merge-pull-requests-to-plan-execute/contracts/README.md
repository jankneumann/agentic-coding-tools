# Contracts: rescope-merge-pull-requests-to-plan-execute

Contract sub-types evaluated for this change:

| Sub-type | Applicable? | Artifact |
|---|---|---|
| **OpenAPI** | No | No new HTTP endpoints. Coordinator merge-queue remains Phase 2 / out of scope. |
| **Database** | No | No new tables. File-tier `merge-plan.json` stays authoritative. |
| **Event** | No | No new event payloads. Living-plan amendment stays in-process `amend_plan()`. |
| **JSON Schema (data)** | **Yes** | `merge-plan.schema.json` — schema 1.1 of the durable merge plan. |
| **Type generation** | No | Python loaders already consume the JSON schema; no generated models in this change. |

## Coordination boundary

`merge-plan.schema.json` is the boundary between:

- `build_plan.py` / `classify_kind` (writers of definition fields)
- `execute_plan.py` (writer of live `outcome` / claims; reader of kind + remediation_skill)
- `next_node.py` (read-only ready-set)
- `render_plan.py` (Markdown projection)
- the SKILL.md conductor (operator discussion + iterate dispatch)

Implementation copies this schema onto
`skills/merge-pull-requests/contracts/merge-plan.schema.json`.
