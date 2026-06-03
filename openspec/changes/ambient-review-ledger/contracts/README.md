# Contracts: ambient-review-ledger

Contract sub-types evaluated for this change:

| Sub-type | Applicable? | Artifact |
|---|---|---|
| **OpenAPI** | No | No new HTTP REST endpoints. Coordinator sync reuses existing `memory`/`audit` services; GitHub issue filing uses existing GitHub MCP tools. |
| **Database** | No | No new tables. Coordinator sync rides on existing `memory`/`audit` storage; the ledger's source of truth is the local `.review-ledger/` file. |
| **Event** | **Yes** | `events/ledger.changed.schema.json` — SSE payload for the kanban-viz review-ledger swimlane (Phase 5). |
| **JSON Schema (data)** | **Yes** | `review-ledger.schema.json` — the local-first ledger file format (Phase 2). |
| **Type generation** | Deferred | Models generated from `review-ledger.schema.json` during implementation (Python ledger-entry model; TS interface for the swimlane). Not pre-generated here. |

## Reused (not re-specified) contracts

- `openspec/schemas/review-findings.schema.json` — the wrapped finding shape.
  This change adds an `ambient` value to its `review_type` enum (additive).
- `openspec/schemas/consensus-report.schema.json` and the
  `consensus_synthesizer` matching logic — reused by `compact` for dedup (D5).

## Coordination boundary

`review-ledger.schema.json` is the boundary between the ledger library (Phase 2),
the ambient runner (Phase 1), issue sync (Phase 4), and the swimlane (Phase 5).
`events/ledger.changed.schema.json` is the boundary between the ledger/SSE
producer and the kanban-viz consumer.
