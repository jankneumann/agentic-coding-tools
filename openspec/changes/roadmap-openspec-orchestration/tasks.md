# Tasks: Roadmap-Oriented OpenSpec Planning and Execution

**Change ID**: roadmap-openspec-orchestration
**Status**: Draft

## Phase 1: Shared Roadmap Runtime (wp-runtime)

- [ ] 1.1 Write unit tests for roadmap schema validation and parser failure modes
  **Spec scenarios**: roadmap-orchestration.1 (decompose markdown), roadmap-orchestration.4 (artifact corruption)
  **Contracts**: openspec/changes/roadmap-openspec-orchestration/contracts/README.md
  **Dependencies**: None

- [ ] 1.2 Implement roadmap artifact schema + parser (`roadmap.yaml`, `checkpoint.json`, `learning-log.md`)
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for checkpoint resume semantics (idempotent resume, dependency-block handling)
  **Spec scenarios**: roadmap-orchestration.2 (resume), roadmap-orchestration.2 (dependency blocked)
  **Dependencies**: None

- [ ] 1.4 Implement checkpoint manager shared by roadmap skills
  **Dependencies**: 1.3

## Phase 2: `plan-roadmap` Decomposition Skill (wp-plan-roadmap)

- [ ] 2.1 Write decomposition tests with representative long proposals (well-formed, insufficient-input, ambiguous)
  **Spec scenarios**: roadmap-orchestration.1 (decompose), roadmap-orchestration.1 (reject insufficient input)
  **Dependencies**: None

- [ ] 2.2 Implement decomposition engine and `plan-roadmap` skill workflow
  **Dependencies**: 2.1, 1.2

- [ ] 2.3 Implement OpenSpec scaffold generation for approved roadmap candidates
  **Spec scenarios**: roadmap-orchestration.1 (seed scaffolds)
  **Dependencies**: 2.2

## Phase 3: `autopilot-roadmap` Execution Skill (wp-autopilot-roadmap)

- [ ] 3.1 Write scheduler policy tests (`wait_if_budget_exceeded`, `switch_if_time_saved`, no-eligible-vendor)
  **Spec scenarios**: roadmap-orchestration.3 (wait), roadmap-orchestration.3 (switch), roadmap-orchestration.3 (fail closed)
  **Dependencies**: None

- [ ] 3.2 Implement usage-limit-aware policy engine and vendor selector
  **Dependencies**: 3.1

- [ ] 3.3 Implement roadmap execution orchestrator in `autopilot-roadmap` skill using existing implement/review skills
  **Dependencies**: 3.2, 1.4

- [ ] 3.4 Implement learning-log writer + pre-run learning ingestion and item reprioritization
  **Spec scenarios**: roadmap-orchestration.2 (learning feedback)
  **Dependencies**: 3.3

## Phase 4: Integration and Documentation (wp-integration)

- [ ] 4.1 Write integration tests for full lifecycle (plan roadmap → execute item A → adapt item B)
  **Spec scenarios**: roadmap-orchestration.1, roadmap-orchestration.2, roadmap-orchestration.4
  **Dependencies**: 2.3, 3.4

- [ ] 4.2 Update docs and usage guidance for roadmap workflows and scheduling policy configuration
  **Dependencies**: 4.1

- [ ] 4.3 Run strict OpenSpec validation and targeted test suites
  **Dependencies**: 4.2
