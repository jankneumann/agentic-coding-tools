# Change Context: mirror-autopilot-phase-state-into-the-work-queue

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md | Coordinated Autopilot Phase Projection | openspec/contracts/agent-coordinator/openapi/work-queue.yaml | D1-D11 | skills/autopilot/scripts/queue_projection.py; skills/autopilot/scripts/runner.py; skills/autopilot/scripts/autopilot.py; skills/coordination-bridge/scripts/coordination_bridge.py; agent-coordinator/database/migrations/037_autopilot_phase_projection_visibility.sql; agent-coordinator/src/event_stream.py; openspec/contracts/agent-coordinator/openapi/work-queue.yaml | skills/tests/autopilot/test_queue_projection.py; skills/tests/autopilot/test_phase_projection_runner.py; skills/tests/coordination-bridge/test_projection_issue_helpers.py; agent-coordinator/tests/test_autopilot_projection_visibility.py | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1, D6, D7, D9, D11 | Derive one bounded canonical issue projection and repair only adapter-owned labels. | queue_projection.py and coordinator-only bridge helpers | Keeps queue state non-authoritative and repair idempotent. |
| D2, D3, D4, D8, D10 | Register projection only at explicit coordinated boundaries after durable writes. | runner.py canonical writers, project-state, run-loop injection, and SKILL protocol | Preserves save-before-project and coordinator-free isolation. |
| D5 | Reuse the existing board data path. | migration 037 projection event and event_stream snapshot refresh | Avoids frontend changes while bounding visibility latency. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 1/1
- **Tests mapped**: 1 requirement has at least one test
- **Evidence collected**: 0/1 requirements have pass/fail evidence
- **Gaps identified**: live PostgreSQL/coordinator proof deferred to validation
- **Deferred items**: live-service assertions require validation environment
