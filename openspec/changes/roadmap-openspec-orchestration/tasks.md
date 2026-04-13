# Tasks: Roadmap-Oriented OpenSpec Planning and Execution

**Change ID**: roadmap-openspec-orchestration
**Status**: Draft

## Phase 1: Roadmap Artifacts and Contracts

- [ ] 1.1 Write tests for roadmap artifact schema and parser
  **Spec scenarios**: roadmap-orchestration.1 (decompose markdown), roadmap-orchestration.4 (progressive context reload)
  **Contracts**: contracts/roadmap/README.md
  **Dependencies**: None

- [ ] 1.2 Define roadmap artifact schema and persistence helpers (`roadmap.yaml`, `checkpoint.json`, `learning-log.md`)
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for checkpoint resume semantics (idempotent resume, skip completed phases)
  **Spec scenarios**: roadmap-orchestration.2 (resume from checkpoint)
  **Dependencies**: None

- [ ] 1.4 Implement checkpoint manager used by both roadmap skills
  **Dependencies**: 1.3

## Phase 2: `plan-roadmap` Skill

- [ ] 2.1 Write decomposition tests using representative long proposal inputs (single-phase, multi-phase, ambiguous scope)
  **Spec scenarios**: roadmap-orchestration.1 (decompose markdown), roadmap-orchestration.1 (seed change folders)
  **Dependencies**: None

- [ ] 2.2 Create `skills/plan-roadmap/SKILL.md` and decomposition scripts reusing explore/plan workflow components
  **Dependencies**: 2.1, 1.2

- [ ] 2.3 Add draft OpenSpec change scaffold generation from approved roadmap candidates
  **Dependencies**: 2.2

## Phase 3: `autopilot-roadmap` Skill

- [ ] 3.1 Write scheduler tests for usage-limit-aware policy decisions (`wait_if_budget_exceeded`, `switch_if_time_saved`)
  **Spec scenarios**: roadmap-orchestration.3 (wait policy), roadmap-orchestration.3 (alternate vendor)
  **Dependencies**: None

- [ ] 3.2 Implement roadmap scheduler and policy engine with vendor capability metadata
  **Dependencies**: 3.1

- [ ] 3.3 Create `skills/autopilot-roadmap/SKILL.md` orchestration flow integrating existing autopilot and review skills
  **Dependencies**: 3.2, 1.4

- [ ] 3.4 Implement learning artifact generation and pre-run ingestion hooks between roadmap items
  **Spec scenarios**: roadmap-orchestration.2 (learning feedback)
  **Dependencies**: 3.3

## Phase 4: Integration, Validation, and Documentation

- [ ] 4.1 Add integration tests covering end-to-end roadmap lifecycle (plan → execute item1 → adapt item2)
  **Dependencies**: 2.3, 3.4

- [ ] 4.2 Update docs for roadmap workflow and policy configuration
  **Dependencies**: 4.1

- [ ] 4.3 Run validation (`openspec validate roadmap-openspec-orchestration --strict`) and fix issues
  **Dependencies**: 4.2
