# Change Context: extend-handoff-document-with-supervisor-record

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-coordinator.1 | `specs/agent-coordinator/spec.md` — Supervisor Record Storage | Store one nullable supervisor record and expose a backward-compatible supervisor-only read across coordinator surfaces. | `openspec/contracts/agent-coordinator/openapi/handoffs.yaml`; `openspec/schemas/supervisor-record.schema.json` | D1, D7A | `agent-coordinator/database/migrations/034_handoff_supervisor_record.sql`; `agent-coordinator/src/handoffs.py`; `agent-coordinator/src/coordination_api.py`; `agent-coordinator/src/coordination_mcp.py`; `agent-coordinator/src/http_proxy.py` | `agent-coordinator/tests/test_handoff_supervisor_record.py`; `agent-coordinator/tests/test_handoffs.py`; `agent-coordinator/tests/e2e/postgres/test_handoffs_live.py` | Coordinator targeted 13 passed; declared package suite 105 passed; live PostgreSQL tests skipped because the service was unavailable. |
| agent-coordinator.2 | `specs/agent-coordinator/spec.md` — Session Continuity | Preserve current handoff behavior while round-tripping the optional supervisor record through all coordinator surfaces. | `openspec/contracts/agent-coordinator/openapi/handoffs.yaml` | D1 | `agent-coordinator/src/handoffs.py`; `agent-coordinator/src/coordination_api.py`; `agent-coordinator/src/coordination_cli.py`; `agent-coordinator/src/help_service.py` | `agent-coordinator/tests/test_handoff_supervisor_record.py`; `agent-coordinator/tests/test_coordination_api.py`; `agent-coordinator/tests/test_http_proxy.py` | Coordinator declared package suite 105 passed; Ruff passed; strict type checking of changed handoff code passed. |
| skill-workflow.1 | `specs/skill-workflow/spec.md` — Session Handoff Hooks | Pass the optional record through bridge and PhaseRecord payloads without changing ordinary handoffs or generic hooks. | `openspec/contracts/phase-record/schemas/handoff-local-fallback.schema.json` | D5, D6, D7A | `skills/coordination-bridge/scripts/coordination_bridge.py`; `skills/session-log/scripts/phase_record.py`; `openspec/contracts/phase-record/schemas/handoff-local-fallback.schema.json` | `skills/tests/coordination-bridge/test_handoff_supervisor_record.py`; `skills/tests/phase-record-compaction/test_phase_record_handoff.py`; `skills/tests/phase-record-compaction/test_schema_fixtures.py` | Host-plumbing targeted 29 passed; declared package suite 340 passed; generic hooks unchanged. |
| supervise.1 | `specs/supervise/spec.md` — Supervisor Rehydration Record | Deterministically derive active state, preserve durable state in a mirror, and wire `/supervise` rehydration and writes. | `openspec/schemas/supervisor-record.schema.json`; `openspec/schemas/supervisor-record-mirror.schema.json` | D2, D3, D4, D5, D7, D7A | `skills/supervise/scripts/cycle_state.py`; `skills/supervise/SKILL.md`; `skills/tests/supervise/fixtures/supervisor-record/` | `skills/tests/supervise/test_supervisor_record_schema.py`; `skills/tests/supervise/test_supervisor_record.py`; `skills/tests/supervise/test_cycle_state.py` | Schema suite 9 passed; builder targeted 11 passed; WorkflowContract 7 passed; full supervise suite 86 passed. |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Keep the cross-surface extension to one nullable key. | Coordinator model, database RPCs, HTTP, MCP, proxy, CLI, and contracts. | Preserves compatibility and avoids multiplying schema evolution across hand-written surfaces. |
| D2 | Split derivable active state from durable non-derivable state. | `active_changes` is rebuilt from repository state; the remaining sections are carried forward. | Keeps repository state authoritative without losing operator decisions. |
| D3 | Build the record deterministically in `cycle_state.py`. | Pure host-assisted builder and CLI subcommands with explicit `--now`. | Makes rehydration testable and independent of an LLM or network. |
| D4 | Use handoff as transport and a tracked mirror as durable truth. | Mirror read/write, newer-source selection, and fingerprint exclusion. | Allows offline recovery without creating volatile active-state churn. |
| D5 | Leave generic session hooks unchanged. | `/supervise` explicitly performs supervisor-only reads and record writes. | Avoids increasing SessionStart cost and keeps generic hooks generic. |
| D6 | Conditionally pass one key through host plumbing. | Bridge and PhaseRecord include `supervisor_record` only when supplied. | Existing payloads remain byte-for-byte compatible. |
| D7 | Freeze a versioned inner JSON Schema. | Full and mirror schemas plus fixtures and validation tests. | The inner record can evolve without adding coordinator columns. |
| D7A | Make retrieval reliable and mirror writes idempotent. | `supervisor_only`, newer-prior selection, unchanged-write no-op, bounded derivation. | Prevents ordinary handoffs from masking state and preserves cycle stability. |
| D8 | Sequence contracts, parallel implementation, docs, then integration. | Work-package DAG in `work-packages.yaml`. | Freezes interfaces before parallel workers consume them. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 4/4
- **Tests mapped**: 4 requirements have at least one planned test
- **Evidence collected**: 4/4 requirements have pass/fail evidence
- **Gaps identified**: live PostgreSQL round-trip awaits an environment with the local service available
- **Deferred items**: repository-wide skills collection collisions and missing optional mypy stubs are pre-existing infrastructure findings outside this change
