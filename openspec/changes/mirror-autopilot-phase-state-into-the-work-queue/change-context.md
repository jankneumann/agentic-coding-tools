# Change Context: mirror-autopilot-phase-state-into-the-work-queue

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md | Coordinated Autopilot Phase Projection | openspec/contracts/agent-coordinator/openapi/work-queue.yaml | D1-D11 | skills/autopilot/scripts/queue_projection.py; skills/autopilot/scripts/runner.py; skills/autopilot/scripts/autopilot.py; skills/coordination-bridge/scripts/coordination_bridge.py; agent-coordinator/database/migrations/037_autopilot_phase_projection_visibility.sql; agent-coordinator/database/migrations/038_atomic_projection_labels.sql; agent-coordinator/src/coordination_api.py; agent-coordinator/src/event_stream.py; agent-coordinator/src/issue_service.py; agent-coordinator/src/work_queue.py; openspec/contracts/agent-coordinator/openapi/work-queue.yaml | skills/tests/autopilot/test_queue_projection.py; skills/tests/autopilot/test_phase_projection_runner.py; skills/tests/coordination-bridge/test_projection_issue_helpers.py; agent-coordinator/tests/test_autopilot_projection_visibility.py; agent-coordinator/tests/integration/postgres/test_autopilot_projection_acceptance_postgres.py; agent-coordinator/tests/integration/postgres/test_work_queue_postgres.py; agent-coordinator/tests/integration/postgres/test_fresh_database_migration.py; agent-coordinator/tests/e2e/postgres/test_work_queue_live.py | PASS: 432 Autopilot; 96 bridge; 127 coordinator unit/API; 30 live PostgreSQL/E2E; 224 Kanban (6 skipped); build, Ruff, dependency direction, mirrors, and 90 strict OpenSpec artifacts |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1, D6, D7, D9, D11 | Derive one bounded canonical issue projection and repair only adapter-owned labels. | queue_projection.py, coordinator-only bridge helpers, and migration 038 per-change transaction | Keeps queue state non-authoritative, makes concurrent generations serializable, and keeps repair idempotent. |
| D2, D3, D4, D8, D10 | Register projection only at explicit coordinated boundaries after durable writes. | runner.py canonical writers, project-state, run-loop injection, and SKILL protocol | Preserves save-before-project and coordinator-free isolation. |
| D5 | Reuse the existing board data path. | migration 037 projection event, migration 038 atomic labels, cancelled-row filtering, and event_stream snapshot refresh | Avoids frontend changes while bounding visibility latency and preventing cancelled projections from entering normal board reads. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| R4-1,3,4,5,7,10 | wp-projection-adapter | correctness | high | fixed | Canonical ESCALATE persistence/projection and transactionally serialized label repair (`e7558c4e`, `83a2dad8`). |
| R4-2,6,9 | wp-live-integration | verification | high | fixed | Added real PostgreSQL, EventBus, label-query, crash-resume, concurrency, and full HTTP-stack acceptance evidence. |
| R4-8 | wp-projection-adapter | contract | medium | fixed | OpenAPI request constraints and optional exact projection labels match runtime. |
| R4-11-20 | both | advisory/positive | low | accepted | Recorded in round-4 dispositions; no blocking behavior remained after fixes. |

## Coverage Summary

- **Requirements traced**: 1/1
- **Tests mapped**: 1 requirement has at least one test
- **Evidence collected**: 1/1 requirements have pass evidence
- **Gaps identified**: none
- **Deferred items**: none

The canonical curated skills invocation is `cd skills && .venv/bin/python -m pytest -q`. An explicit monolithic `pytest tests` invocation is not a project gate because it bypasses the curated `testpaths` ordering and causes known flat-module import collisions (`models`, `runner`) during collection.
