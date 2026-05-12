# Contracts: Phase-Record Compaction

This change introduces internal data-model contracts but does not modify any external interfaces. Contract sub-types were evaluated as follows:

| Sub-type | Applies? | Rationale |
|---|---|---|
| **Type schemas** | Yes | `PhaseRecord` is a new data model consumed by multiple skills (session-log, autopilot, all six phase-boundary skills) and the coordinator handoff API. The schema documents the contract these consumers must agree on. The handoff local-file fallback gets a sibling schema documenting the on-disk format. |
| **OpenAPI** | No | No new HTTP endpoints introduced or modified. The coordinator's existing `/handoffs/write` and `/handoffs/read` endpoints are reused unchanged. |
| **Database** | No | The `handoff_documents` table schema (`agent-coordinator/database/migrations/002_handoff_documents.sql`) is unchanged. Existing JSONB columns (`completed_work`, `decisions`, `next_steps`, `relevant_files`, `in_progress`) accommodate `PhaseRecord` payloads without migration. |
| **Events** | No | No new events introduced. Token-counting telemetry uses the existing audit-log mechanism, which is not an event-bus contract. |
| **Generated types** | No | The `PhaseRecord` dataclass lives in `skills/session-log/scripts/phase_record.py` as the single source of truth. No cross-language type generation needed (no TypeScript / OpenAPI codegen pipeline involves it). |

## Contracts in this directory

- `schemas/phase-record.schema.json` — JSON Schema for the unified `PhaseRecord` data model. Validates both the in-memory dataclass (after serialization) and the on-disk handoff fallback `payload` field. Round-trip through `render_markdown()`/`parse_markdown()` and `to_handoff_payload()`/`from_handoff_payload()` SHALL preserve all fields validated by this schema.

- `schemas/handoff-local-fallback.schema.json` — JSON Schema for the `openspec/changes/<change-id>/handoffs/<phase-slug>-<N>.json` files written when `PhaseRecord.write_both()` cannot reach the coordinator. Wraps the `PhaseRecord` payload with envelope metadata (timestamp, error type) so post-hoc analysis can distinguish local fallbacks from primary coordinator writes.

## Validation

Both schemas are validated against fixtures in task 1.3 (`skills/tests/phase-record-compaction/test_schema_fixtures.py`). The `PhaseRecord` Python dataclass MUST produce JSON that validates against `phase-record.schema.json` after `to_handoff_payload()`. The local-fallback writer in `phase_record.py:write_both()` MUST produce JSON that validates against `handoff-local-fallback.schema.json`.
