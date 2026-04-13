# Tasks: Roadmap-Oriented OpenSpec Planning and Execution

**Change ID**: roadmap-openspec-orchestration
**Status**: Draft

## Phase 1: Shared Roadmap Runtime (wp-runtime)

- [ ] 1.1 Write unit tests for roadmap artifact models and schema validation
  **Spec scenarios**: Decompose markdown proposal, Artifact corruption detected during load
  **Contracts**: contracts/roadmap.schema.json, contracts/checkpoint.schema.json, contracts/learning-log.schema.json
  **Dependencies**: None
  **Files**: skills/roadmap-runtime/scripts/tests/test_models.py

- [ ] 1.2 Implement artifact models with JSON Schema validation (`skills/roadmap-runtime/scripts/models.py`)
  **Dependencies**: 1.1
  **Files**: skills/roadmap-runtime/scripts/models.py

- [ ] 1.3 Write tests for checkpoint resume semantics (idempotent resume, dependency-block, item failure propagation)
  **Spec scenarios**: Resume from persisted checkpoint, Abort item execution when dependency incomplete, Handle individual item failure
  **Dependencies**: None
  **Files**: skills/roadmap-runtime/scripts/tests/test_checkpoint.py

- [ ] 1.4 Implement checkpoint manager (`skills/roadmap-runtime/scripts/checkpoint.py`)
  **Dependencies**: 1.3

- [ ] 1.5 Write tests for learning-log progressive disclosure (root index, per-item entries, bounded loading, compaction)
  **Spec scenarios**: Learning feedback updates remaining items, Learning log compaction for long roadmaps, Progressive context reload per phase
  **Dependencies**: None
  **Files**: skills/roadmap-runtime/scripts/tests/test_learning.py, skills/roadmap-runtime/scripts/tests/test_context.py

- [ ] 1.6 Implement learning-log helpers, sanitizer, and bounded context assembly
  **Spec scenarios**: Redact sensitive content from learning entries, Validate sanitization on checkpoint writes
  **Dependencies**: 1.5, 1.2
  **Files**: skills/roadmap-runtime/scripts/learning.py, skills/roadmap-runtime/scripts/sanitizer.py, skills/roadmap-runtime/scripts/context.py

## Phase 2: `plan-roadmap` Decomposition Skill (wp-plan-roadmap)

- [ ] 2.1 Write decomposition tests (well-formed, insufficient-input, ambiguous, undersized-merge, oversized-split)
  **Spec scenarios**: Decompose markdown proposal, Reject insufficient input, Merge undersized items, Split oversized items
  **Dependencies**: None
  **Files**: skills/plan-roadmap/scripts/tests/test_decomposer.py

- [ ] 2.2 Implement decomposition engine and `plan-roadmap` skill workflow
  **Dependencies**: 2.1, 1.2
  **Files**: skills/plan-roadmap/scripts/decomposer.py, skills/plan-roadmap/SKILL.md

- [ ] 2.3 Implement OpenSpec scaffold generation with parent_roadmap linking
  **Spec scenarios**: Seed OpenSpec change scaffolds from approved candidates
  **Dependencies**: 2.2
  **Files**: skills/plan-roadmap/scripts/scaffolder.py

## Phase 3: `autopilot-roadmap` Execution Skill (wp-autopilot-roadmap)

- [ ] 3.1 Write policy engine tests (wait, switch, cascading failure, fail-closed, max switch attempts)
  **Spec scenarios**: Wait policy, Switch policy, Cascading vendor failures, Fail closed
  **Dependencies**: None
  **Files**: skills/autopilot-roadmap/scripts/tests/test_policy.py

- [ ] 3.2 Implement usage-limit-aware policy engine with cascading vendor failover
  **Dependencies**: 3.1
  **Files**: skills/autopilot-roadmap/scripts/policy.py

- [ ] 3.3 Implement roadmap execution orchestrator with item failure handling and observability
  **Spec scenarios**: Handle individual item failure, Structured logging for item state transitions, Structured logging for policy decisions, Structured logging for checkpoint operations
  **Dependencies**: 3.2, 1.4
  **Files**: skills/autopilot-roadmap/scripts/orchestrator.py, skills/autopilot-roadmap/SKILL.md

- [ ] 3.4 Implement learning-log writer + pre-run learning ingestion and adaptive replanner
  **Spec scenarios**: Learning feedback updates remaining items
  **Dependencies**: 3.3, 1.6
  **Files**: skills/autopilot-roadmap/scripts/replanner.py

## Phase 4: Integration and Documentation (wp-integration)

- [ ] 4.1 Write integration tests for full lifecycle (plan roadmap → execute item A → adapt item B → handle failure)
  **Spec scenarios**: Decompose markdown proposal, Learning feedback updates remaining items, Handle individual item failure, Artifact corruption detected during load
  **Dependencies**: 2.3, 3.4
  **Files**: skills/roadmap-runtime/scripts/tests/integration/, skills/plan-roadmap/scripts/tests/integration/, skills/autopilot-roadmap/scripts/tests/integration/

- [ ] 4.2 Update docs for roadmap workflows and scheduling policy configuration
  **Dependencies**: 4.1
  **Files**: docs/skills-workflow.md, docs/parallel-agentic-development.md

- [ ] 4.3 Update CLAUDE.md workflow table with roadmap skill entry points
  **Dependencies**: 4.2
  **Files**: CLAUDE.md
  **Notes**: Add `/plan-roadmap` and `/autopilot-roadmap` to the workflow table while maintaining the existing progressive disclosure structure. AGENTS.md is a symlink to CLAUDE.md so it updates automatically.

- [ ] 4.4 Run strict OpenSpec validation and full test suites
  **Dependencies**: 4.3
