# Change Context: extend-handoff-document-with-supervisor-record

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-coordinator.1 | `specs/agent-coordinator/spec.md` — Supervisor Record Storage | Store one nullable supervisor record and expose a backward-compatible supervisor-only read across coordinator surfaces. | `openspec/contracts/agent-coordinator/openapi/handoffs.yaml`; `openspec/schemas/supervisor-record.schema.json` | D1, D7A, D9 | `agent-coordinator/database/migrations/034_handoff_supervisor_record.sql`; `agent-coordinator/src/handoffs.py`; `agent-coordinator/src/coordination_api.py`; `agent-coordinator/src/coordination_mcp.py`; `agent-coordinator/src/http_proxy.py` | `agent-coordinator/tests/test_handoff_supervisor_record.py`; `agent-coordinator/tests/test_handoffs.py`; `agent-coordinator/tests/e2e/postgres/test_handoffs_live.py` | Migration 034 applied with `ON_ERROR_STOP` after 000–033 in an isolated database; RPC signatures were unique and the live PostgreSQL suite passed 4/4. |
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
| D9 | Gate on changed surfaces and live migration evidence; report broad suites diagnostically. | Integration verification in `work-packages.yaml`, task 5.1, and validation report. | Keeps feature regressions blocking without expanding scope into pre-existing repository harness failures. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| II-001 | wp-coordinator | compatibility | medium | fixed | Restored the pre-extension positional `HandoffDocument` constructor ABI and added a regression test. |
| II-002 | wp-coordinator | correctness | medium | fixed | Replaced the schema-invalid help example with a complete v1 record and pinned its required keys. |
| II-003 | wp-contracts | contract_mismatch | low | fixed | Aligned both OpenAPI copies with structural JSON equality. |
| II-004 | wp-contracts | compatibility | high | fixed | Moved runtime schema consumers to canonical paths that survive change archival. |
| II-005 | wp-supervisor-builder | resilience | medium | fixed | Reported degraded handoff state for cold-start and newer-mirror recovery. |
| II-006 | wp-supervisor-builder | correctness | medium | fixed | Sanitized before validation, validated final documents, and rejected future versions. |
| II-007 | wp-supervisor-builder | security | medium | fixed | Rejected symlinked mirror destinations and used atomic replacement. |
| VAL-SPEC-001 | wp-skill-docs | correctness | critical | fixed | Ran the repository installer and proved canonical `supervise` files exactly match both generated runtime trees. |
| VAL-SPEC-002 | wp-coordinator | contract_mismatch | high | fixed | Corrected stale delta-spec wording to the established, tested `rpc_failed:` diagnostic contract without changing public behavior. |
| VAL-EVID-003 | wp-coordinator | correctness | high | fixed | Applied migrations 000–033 then 034 to a real PostgreSQL database and passed all four live handoff tests. |
| VAL-ACCEPT-004 | wp-integration | correctness | high | fixed | Replaced the overbroad conjunctive gate with explicit changed-surface required gates; broad-suite failures remain visible diagnostics. |

## Coverage Summary

- **Requirements traced**: 4/4
- **Tests mapped**: 4 requirements have at least one planned test
- **Evidence collected**: 4/4 requirements have pass/fail evidence
- **Implementation iteration evidence**: 30 focused coordinator tests and 121 feature-adjacent skills tests passed; changed coordinator files passed strict mypy and all changed Python surfaces passed Ruff.
- **Validation-fix evidence**: runtime mirrors exact; migration 034 staged after 033; live PostgreSQL handoff suite 4/4; strict OpenSpec valid.
- **Gaps identified**: none on the changed surface
- **Deferred items**: repository-wide skills collection collisions and missing optional mypy stubs are pre-existing infrastructure findings outside this change
