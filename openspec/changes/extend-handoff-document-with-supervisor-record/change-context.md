# Change Context: extend-handoff-document-with-supervisor-record

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-coordinator.1 | `specs/agent-coordinator/spec.md` — Supervisor Record Storage | Store one nullable supervisor record and expose a backward-compatible supervisor-only read across coordinator surfaces. | --- | D1, D7A | --- | `agent-coordinator/tests/test_handoff_supervisor_record.py`; `agent-coordinator/tests/test_handoffs.py`; `agent-coordinator/tests/e2e/postgres/test_handoffs_live.py` | --- |
| agent-coordinator.2 | `specs/agent-coordinator/spec.md` — Session Continuity | Preserve current handoff behavior while round-tripping the optional supervisor record through all coordinator surfaces. | openspec/contracts/agent-coordinator/openapi/handoffs.yaml | D1 | --- | `agent-coordinator/tests/test_handoff_supervisor_record.py`; `agent-coordinator/tests/test_coordination_api.py`; `agent-coordinator/tests/test_http_proxy.py` | --- |
| skill-workflow.1 | `specs/skill-workflow/spec.md` — Session Handoff Hooks | Pass the optional record through bridge and PhaseRecord payloads without changing ordinary handoffs or generic hooks. | --- | D5, D6, D7A | --- | `skills/tests/coordination-bridge/test_handoff_supervisor_record.py`; `skills/tests/phase-record-compaction/test_phase_record_handoff.py`; `skills/tests/phase-record-compaction/test_schema_fixtures.py` | --- |
| supervise.1 | `specs/supervise/spec.md` — Supervisor Rehydration Record | Deterministically derive active state, preserve durable state in a mirror, and wire `/supervise` rehydration and writes. | --- | D2, D3, D4, D5, D7, D7A | --- | `skills/tests/supervise/test_supervisor_record_schema.py`; `skills/tests/supervise/test_supervisor_record.py`; `skills/tests/supervise/test_cycle_state.py` | --- |

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
- **Evidence collected**: 0/4 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
