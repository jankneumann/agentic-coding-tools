# Change Context: add-supervisor-candidate-work-digest

Phase 1 traceability skeleton. Contract references are generated from traced contract
documents; implementation files and evidence remain unset until their respective phases.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| supervise.1 | `specs/supervise/spec.md` — Candidate-Work Digest | Maintain a bounded, deterministic, crash-recoverable candidate backlog with safe evidence loading, exact rubric coverage, stable ranking, lifecycle maintenance, and composable supervisor output. | --- | D1, D2, D3, D5, D6, D8 | --- | `test_digest_schemas.py`, `test_digest.py`, `test_digest_routing.py`, `test_digest_evidence.py`, `test_rubric_prompt.py`, `test_cycle_state.py`, `test_workflow_contract.py` | --- |
| supervise.2 | `specs/supervise/spec.md` — Approval Routing | Convert an approved digest stub into one validated roadmap request, require preview/SHA-guarded apply, preserve durable decision state, and never write roadmaps or dispatch implementation from digest code. | --- | D3, D4, D5 | --- | `test_supervisor_record_schema.py`, `test_supervisor_record.py`, `test_digest_routing.py`, `test_workflow_contract.py` | --- |

## Requirement-to-Package Assignment

| Req ID | Owning package(s) |
|--------|-------------------|
| supervise.1 | `wp-contracts`, `wp-digest-module`, `wp-rubric-prompt`, `wp-skill-docs`, `wp-integration` |
| supervise.2 | `wp-contracts`, `wp-digest-module`, `wp-skill-docs`, `wp-integration` |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Candidate payload and lifecycle have different ownership and update cadence. | Tracked, reversibly encoded per-stub files plus `back_edge.digested_stubs`; maintenance precedes SENSE. | Keeps validated input byte-stable while terminal and deferred state evolves safely. |
| D2 | Model judgment is useful for relevance/value but unsuitable for deterministic ordering. | Schema-bound five-factor scoring plus host-computed signals and a fixed total order. | Makes subjective evidence inspectable and ranking reproducible. |
| D3 | Existing cycle-state code owns rehydration, mirror persistence, and fingerprints. | A dedicated `digest.py` uses narrow `cycle_state.py` helpers. | Limits changes to proven state machinery and keeps the new CLI independently testable. |
| D4 | Roadmap mutation already has a preview and stale-base transaction owner. | `stub-to-request` emits one request; the host invokes refiner preview then guarded apply. | Avoids a second roadmap writer and preserves operator confirmation. |
| D5 | Decisions are durable supervisor facts that must survive rehydration. | `rank` and `decide` merge digest state through `write_mirror`; the next cycle prunes. | Preserves unrelated newer state and centralizes cleanup in the audited cycle. |
| D6 | Candidate output must compose with operational supervisor sections and survive cache reuse. | A candidate-focused stable digest distinguishes scoring time from lifecycle-update time. | Prevents candidate rendering from erasing gates, blockers, or sensor degradation. |
| D7 | The feature depends on existing supervisor and reference contracts but needs a stricter status view. | Build an all-status dependency index without using the ready-frontier as a status index. | Keeps completed, pending, blocked, archived, and unresolved states distinguishable. |
| D8 | Evidence and model output cross untrusted and failure-prone boundaries. | Bounded sanitized manifests, exact validation, and a fsynced roll-forward journal. | Prevents prompt injection, runaway context, partial publication, and retry suppression. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 2/2
- **Tests mapped**: 2/2 requirements have at least one planned test
- **Evidence collected**: 0/2 requirements have pass/fail evidence
- **Gaps identified**: implementation and validation evidence pending
- **Deferred items**: none
