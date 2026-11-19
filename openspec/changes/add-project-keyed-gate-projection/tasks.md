# Tasks: add-project-keyed-gate-projection

## 1. Coordinator storage and configuration

- [x] 1.1 Write failing tests for the migration text and the config
  - File: `agent-coordinator/tests/test_gate_projection_migration.py`, `agent-coordinator/tests/test_gate_projection_service.py` (config cases)
  - Spec scenarios: No enrolment means an empty listing
  - Design: D2, D3
  - Size: S
- [x] 1.2 Add `047_gate_projection.sql` and `GateProjectionConfig`
  - File: `agent-coordinator/database/migrations/047_gate_projection.sql`, `agent-coordinator/src/config.py`
  - Depends on: 1.1
  - Size: S

## 2. Coordinator service

- [x] 2.1 Write failing service tests against a fake database and a fake approval service
  - File: `agent-coordinator/tests/test_gate_projection_service.py`
  - Spec scenarios: all of Gate Projection Snapshot, Cross-Project Pending Gate Listing, Gate Decision Through the Approval Service
  - Design: D2, D4, D5, D7, D8
  - Size: M
- [x] 2.2 Implement `agent-coordinator/src/gate_projection.py`
  - Depends on: 1.2, 2.1
  - Size: M

Checkpoint: `uv run --project agent-coordinator pytest agent-coordinator/tests/test_gate_projection_service.py agent-coordinator/tests/test_gate_projection_migration.py -q` passes.

## 3. Coordinator routes and contract

- [x] 3.1 Write `openspec/contracts/agent-coordinator/openapi/gates.yaml`
  - Design: D8
  - Size: S
- [x] 3.2 Write failing route tests
  - File: `agent-coordinator/tests/test_gate_projection_api.py`
  - Spec scenarios: A project that is not enrolled is refused; An oversized snapshot is refused; A repository-routed gate is refused with its answer hint; An unknown gate is not found; An invalid decision is rejected
  - Size: S
- [x] 3.3 Implement `agent-coordinator/src/gate_projection_routes.py` and install it
  - File: `agent-coordinator/src/gate_projection_routes.py`, `agent-coordinator/src/coordination_api.py`
  - Depends on: 2.2, 3.1, 3.2
  - Size: S

Checkpoint: coordinator `ruff check`, `mypy --strict src/` and `pytest -m "not e2e and not integration"` pass, including the OpenAPI contract test with no new baseline entry.

## 4. Repository collector

- [x] 4.1 Write failing collector tests on temporary checkouts
  - File: `skills/tests/supervise/test_gate_projection.py`
  - Spec scenarios: all of Gate Projection Collector
  - Design: D5, D6, D9, D10
  - Size: M
- [x] 4.2 Implement `skills/supervise/scripts/gate_projection.py` and sync runtime copies
  - Depends on: 4.1
  - Size: M
- [x] 4.3 Document the collector and the two environment variables
  - File: `skills/supervise/SKILL.md`, `agent-coordinator/.env.example` if present
  - Size: S

Checkpoint: `skills/.venv/bin/python -m pytest skills/tests/supervise -q` passes; `openspec validate add-project-keyed-gate-projection --strict` is valid.

## 5. Deployment (operator)

- [ ] 5.1 Apply migration 047 on the deployed coordinator, set `GATE_PROJECTION_PROJECTS`, push from two repositories and read the listing
  - Cannot be done where this change is built: no container runtime, and the deployed coordinator's database is not reachable. The acceptance outcomes are verified by unit tests until this is done.
  - Size: S
