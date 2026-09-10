# Change Context: add-cross-roadmap-readiness-resolver

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|-------------|-------------|--------------|-----------------|---------------|---------|----------|
| roadmap-orchestration.1 | Canonical Cross-Roadmap Readiness Resolution | Expose one globally ranked resolver and one runtime-owned `_get_ready_items` definition imported by autopilot and the resolver. | `contracts/readiness-result.schema.json` | D1, D4 | `skills/roadmap-runtime/scripts/readiness.py`; `resolve_readiness.py`; `skills/autopilot-roadmap/scripts/orchestrator.py` | `TestSharedAdmissionRule`; global ranking tests; existing plan-roadmap cross-roadmap tests | pass `f4eec841` |
| roadmap-orchestration.2 | Checkpoint-Authoritative Cross-Roadmap Edges | Use valid checkpoint terminal sets as authority, definition state only when absent, and fail closed on hard-invalid state. | `contracts/readiness-result.schema.json` | D2, D5 | `skills/roadmap-runtime/scripts/resolve_readiness.py`; `skills/supervise/scripts/cycle_state.py` | checkpoint completion/failure/divergence/invalid/duplicate tests; supervisor ready-set tests | pass `f4eec841` |
| roadmap-orchestration.3 | Deterministic Readiness Projection | Emit a stable source fingerprint, consistency diagnostics, and byte-identical JSON without time, mtime, or advisory inputs. | `contracts/readiness-result.schema.json` | D3, D5 | `skills/roadmap-runtime/scripts/resolve_readiness.py` | fingerprint normalization, advisory isolation, schema, and CLI boundary tests | pass `f4eec841` |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Admission must have one authority. | Runtime-owned helper plus direct imports in autopilot and resolver. | Prevents drift while preserving the old function contract. |
| D2 | Checkpoint terminal sets are canonical execution truth. | Two-pass effective completion and hard/soft consistency diagnostics. | Prevents stale roadmap fields or advisory projections from unblocking work. |
| D3 | Staleness must be content-derived. | Canonical normalized projection hashed with SHA-256; stable JSON serialization. | Makes repeat runs and future materialized projections reproducible. |
| D4 | Callers need one ranking while supervise needs compatibility. | Flat global sort with a grouped supervisor wrapper. | Adds canonical ordering without breaking the existing supervisor CLI shape. |
| D5 | Readiness observation must not mutate state. | Read-only CLI with bounded diagnostics and hard-error exit 2. | Keeps resolver output a projection rather than a new authority. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| plan-C1 | wp-readiness-runtime | correctness | high | fixed | Separated hard-invalid checkpoints from soft status divergence. |
| plan-C2 | wp-readiness-runtime | contract mismatch | high | fixed | Added bounded invalid-roadmap and duplicate-roadmap-id codes. |
| plan-C3 | wp-readiness-runtime | spec gap | medium | fixed | Fully specified fingerprint normalization. |
| impl-C1 | wp-readiness-runtime | resilience | medium | fixed | Added linear duplicate-item detection and RED regression. |
| impl-C2 | wp-readiness-runtime | correctness | low | fixed | Added actual CLI stdout/status regression. |

## Coverage Summary

- **Requirements traced**: 3/3
- **Scenarios verified**: 11/11
- **Tests mapped**: 3/3 requirements have behavioral tests
- **Evidence collected**: 3/3 requirements have passing evidence
- **Review fix findings resolved**: 5/5
- **Gaps identified**: none
- **Deferred items**: none
