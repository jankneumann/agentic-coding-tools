# Change Context: mirror-autopilot-phase-state-into-the-work-queue

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md | Coordinated Autopilot Phase Projection | openspec/contracts/agent-coordinator/openapi/work-queue.yaml | D1-D11 | skills/autopilot/scripts/queue_projection.py; skills/autopilot/scripts/runner.py; skills/autopilot/scripts/autopilot.py; skills/coordination-bridge/scripts/coordination_bridge.py; agent-coordinator/database/migrations/037_autopilot_phase_projection_visibility.sql; agent-coordinator/database/migrations/038_atomic_projection_labels.sql; agent-coordinator/database/migrations/039_projection_integrity_and_insert_events.sql; agent-coordinator/src/coordination_api.py; agent-coordinator/src/event_stream.py; agent-coordinator/src/issue_service.py; agent-coordinator/src/work_queue.py; openspec/contracts/agent-coordinator/openapi/work-queue.yaml | skills/tests/autopilot/test_queue_projection.py; skills/tests/autopilot/test_phase_projection_runner.py; skills/tests/coordination-bridge/test_projection_issue_helpers.py; agent-coordinator/tests/test_autopilot_projection_visibility.py; agent-coordinator/tests/integration/postgres/test_autopilot_projection_acceptance_postgres.py; agent-coordinator/tests/integration/postgres/test_work_queue_postgres.py; agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py; agent-coordinator/tests/e2e/postgres/test_work_queue_live.py | PASS: 436 Autopilot; 96 bridge; 143 coordinator unit/API; 18 focused live PostgreSQL/E2E; 29 installer; mirror parity and focused Ruff passed |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1, D6, D7, D9, D11 | Derive one bounded canonical issue projection and repair only adapter-owned labels. | queue_projection.py, coordinator-only bridge helpers, and migrations 038-039 per-change transaction | Keeps queue state non-authoritative, makes concurrent generations serializable, and keeps repair idempotent. |
| D2, D3, D4, D8, D10 | Register projection only at explicit coordinated boundaries after durable writes. | runner.py canonical writers, project-state, run-loop injection, and SKILL protocol | Preserves save-before-project and coordinator-free isolation. |
| D5 | Reuse the existing board data path. | migration 037 update events, migration 039 insert events/integrity repair, cancelled-row filtering, and event_stream snapshots | Avoids frontend changes while bounding visibility latency and preventing cancelled projections from entering normal board reads. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| R4-1,3,4,5,7,10 | wp-projection-adapter | correctness | high | fixed | Canonical ESCALATE persistence/projection and transactionally serialized label repair (`e7558c4e`, `83a2dad8`). |
| R4-2,6,9 | wp-live-integration | verification | high | fixed | Added real PostgreSQL, EventBus, label-query, crash-resume, concurrency, and full HTTP-stack acceptance evidence. |
| R4-8 | wp-projection-adapter | contract | medium | fixed | OpenAPI request constraints and optional exact projection labels match runtime. |
| R4-11-20 | both | advisory/positive | low | accepted | Recorded in round-4 dispositions; no blocking behavior remained after fixes. |
| R5-1-11 | both | correctness/contract/compatibility | high-medium | fixed | First-insert refresh, replay/collision/terminal integrity, executable idempotent ESCALATE recovery, auto-resume persistence, exact API bounds, and real mirror validation. |
| R5-12-18 | both | advisory/positive | low | accepted | Positive verification and bounded observations are recorded in round-5 dispositions. |

## Coverage Summary

- **Requirements traced**: 1/1
- **Tests mapped**: 1 requirement has at least one test
- **Evidence collected**: 1/1 requirements have pass evidence
- **Gaps identified**: none
- **Deferred items**: none

The canonical curated skills invocation is `cd skills && .venv/bin/python -m pytest -q`. An explicit monolithic `pytest tests` invocation is not a project gate because it bypasses the curated `testpaths` ordering and causes known flat-module import collisions (`models`, `runner`) during collection.
