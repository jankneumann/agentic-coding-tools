# Tasks: coordinator-skill-integration

## 1. Foundation (sequential — other tasks depend on these)

- [ ] 1.1 Create coordination bridge Python module
  **Dependencies**: None
  **Files**: `scripts/coordination_bridge.py`, `scripts/tests/test_coordination_bridge.py`
  **Requirement**: Coordination Bridge Script
  **Description**: Create a shared bridge with transport-aware HTTP helpers for coordination operations. Include `detect_coordination(http_url=None, api_key=None) -> dict` returning availability, transport, and capabilities; plus `try_lock`, `try_unlock`, `try_submit_work`, `try_get_work`, `try_complete_work`, `try_handoff_write`, `try_handoff_read`, `try_remember`, `try_recall`, and `try_check_guardrails`. All helpers return normalized success-like results with `status="skipped"` when unavailable.

- [ ] 1.2 Define the coordination detection preamble template
  **Dependencies**: None
  **Files**: `docs/coordination-detection-template.md`
  **Requirement**: Coordination Detection
  **Description**: Write a reusable snippet for all integrated skills that determines `COORDINATOR_AVAILABLE`, `COORDINATION_TRANSPORT` (`mcp|http|none`), and capability flags (`CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`) using MCP tool discovery for CLI and HTTP bridge checks for Web/Cloud.

- [ ] 1.3 Add runtime parity validator
  **Dependencies**: None
  **Files**: `scripts/validate_skill_runtime_parity.py`, `scripts/tests/test_validate_skill_runtime_parity.py`, `docs/skills-runtime-parity.md`
  **Requirement**: Cross-Surface Skill Parity
  **Description**: Add a parity checker that verifies coordinator-integrated skills are synchronized across `.claude/skills/`, `.codex/skills/`, `.gemini/skills/`, and `skills/`. Document intentional-difference exceptions (if any) and fail validation on unapproved drift.

## 2. Skill Enhancements (parallelizable by skill family; no overlapping files between items)

- [ ] 2.1 Add coordination hooks to `/implement-feature` across all runtimes
  **Dependencies**: 1.2
  **Files**: `.claude/skills/implement-feature/SKILL.md`, `.codex/skills/implement-feature/SKILL.md`, `.gemini/skills/implement-feature/SKILL.md`, `skills/implement-feature/SKILL.md`
  **Requirements**: Coordination Detection, File Locking in Implement Feature, Work Queue Integration in Implement Feature, Session Handoff Hooks, Guardrail Pre-checks, Cross-Surface Skill Parity
  **Description**: Add transport-aware preamble and capability-gated hooks: lock/unlock (`CAN_LOCK`), work queue (`CAN_QUEUE_WORK`), guardrail checks (`CAN_GUARDRAILS`), and handoff read/write (`CAN_HANDOFF`). Keep local `Task()` fallback when queue capability is unavailable.

- [ ] 2.2 Add coordination hooks to `/plan-feature` across all runtimes
  **Dependencies**: 1.2
  **Files**: `.claude/skills/plan-feature/SKILL.md`, `.codex/skills/plan-feature/SKILL.md`, `.gemini/skills/plan-feature/SKILL.md`, `skills/plan-feature/SKILL.md`
  **Requirements**: Coordination Detection, Session Handoff Hooks, Memory Hooks, Cross-Surface Skill Parity
  **Description**: Add transport-aware preamble, handoff read/write (`CAN_HANDOFF`), and memory recall (`CAN_MEMORY`) while preserving current behavior when capabilities are unavailable.

- [ ] 2.3 Add coordination hooks to `/iterate-on-plan` across all runtimes
  **Dependencies**: 1.2
  **Files**: `.claude/skills/iterate-on-plan/SKILL.md`, `.codex/skills/iterate-on-plan/SKILL.md`, `.gemini/skills/iterate-on-plan/SKILL.md`, `skills/iterate-on-plan/SKILL.md`
  **Requirements**: Coordination Detection, Session Handoff Hooks, Memory Hooks, Cross-Surface Skill Parity
  **Description**: Add transport-aware preamble, handoff read/write (`CAN_HANDOFF`), memory recall at start (`CAN_MEMORY`), and iteration memory write on completion (`CAN_MEMORY`).

- [ ] 2.4 Add coordination hooks to `/iterate-on-implementation` across all runtimes
  **Dependencies**: 1.2
  **Files**: `.claude/skills/iterate-on-implementation/SKILL.md`, `.codex/skills/iterate-on-implementation/SKILL.md`, `.gemini/skills/iterate-on-implementation/SKILL.md`, `skills/iterate-on-implementation/SKILL.md`
  **Requirements**: Coordination Detection, Session Handoff Hooks, Memory Hooks, Cross-Surface Skill Parity
  **Description**: Add transport-aware preamble, handoff read/write (`CAN_HANDOFF`), memory recall at start (`CAN_MEMORY`), and iteration memory write on completion (`CAN_MEMORY`).

- [ ] 2.5 Add coordination hooks to `/validate-feature` across all runtimes
  **Dependencies**: 1.2
  **Files**: `.claude/skills/validate-feature/SKILL.md`, `.codex/skills/validate-feature/SKILL.md`, `.gemini/skills/validate-feature/SKILL.md`, `skills/validate-feature/SKILL.md`
  **Requirements**: Coordination Detection, Memory Hooks, Cross-Surface Skill Parity
  **Description**: Add transport-aware preamble, memory recall at start (`CAN_MEMORY`), and validation outcome memory write on completion (`CAN_MEMORY`).

- [ ] 2.6 Add coordination hooks to `/cleanup-feature` across all runtimes
  **Dependencies**: 1.2
  **Files**: `.claude/skills/cleanup-feature/SKILL.md`, `.codex/skills/cleanup-feature/SKILL.md`, `.gemini/skills/cleanup-feature/SKILL.md`, `skills/cleanup-feature/SKILL.md`
  **Requirements**: Coordination Detection, Session Handoff Hooks, File Locking in Implement Feature, Cross-Surface Skill Parity
  **Description**: Add transport-aware preamble, handoff read/write (`CAN_HANDOFF`), and lock cleanup logic when lock capability exists (`CAN_LOCK`), without introducing failures in standalone mode.

- [ ] 2.7 Add coordination hooks to `/security-review` across all runtimes
  **Dependencies**: 1.2
  **Files**: `.claude/skills/security-review/SKILL.md`, `.codex/skills/security-review/SKILL.md`, `.gemini/skills/security-review/SKILL.md`, `skills/security-review/SKILL.md`
  **Requirements**: Coordination Detection, Guardrail Pre-checks, Cross-Surface Skill Parity
  **Description**: Add transport-aware preamble and guardrail pre-check reporting (`CAN_GUARDRAILS`) before scan execution.

- [ ] 2.8 Add coordination hooks to `/explore-feature` across all runtimes
  **Dependencies**: 1.2
  **Files**: `.claude/skills/explore-feature/SKILL.md`, `.codex/skills/explore-feature/SKILL.md`, `.gemini/skills/explore-feature/SKILL.md`, `skills/explore-feature/SKILL.md`
  **Requirements**: Coordination Detection, Memory Hooks, Cross-Surface Skill Parity
  **Description**: Add transport-aware preamble and memory recall on start (`CAN_MEMORY`) to bring prior exploration/validation context into new explorations.

## 3. New Skill (parallelizable with group 2)

- [ ] 3.1 Create `/setup-coordinator` skill across all runtimes
  **Dependencies**: 1.2
  **Files**: `.claude/skills/setup-coordinator/SKILL.md`, `.codex/skills/setup-coordinator/SKILL.md`, `.gemini/skills/setup-coordinator/SKILL.md`, `skills/setup-coordinator/SKILL.md`
  **Requirement**: Setup Coordinator Skill
  **Description**: Create onboarding skill that handles (1) CLI MCP setup and verification, (2) Web/Cloud HTTP API setup and verification, (3) capability summary, (4) troubleshooting and graceful fallback messaging, and (5) runtime-specific config guidance.

## 4. Documentation (parallelizable with groups 2-3)

- [ ] 4.1 Add coordinator integration section to skills-workflow docs
  **Dependencies**: None
  **Files**: `docs/skills-workflow.md`
  **Requirement**: Skill Integration Usage Patterns (agent-coordinator spec)
  **Description**: Document transport model (MCP vs HTTP), capability flags, runtime parity policy, per-skill integration points, fallback behavior, and `/setup-coordinator` workflow.

- [ ] 4.2 Add skill integration patterns to agent-coordinator docs
  **Dependencies**: None
  **Files**: `docs/agent-coordinator.md`
  **Requirement**: Skill Integration Usage Patterns (agent-coordinator spec)
  **Description**: Document which skills consume which coordinator capabilities across CLI and Web/Cloud agents, including setup paths, authentication expectations, and fallback behavior.

## 5. Validation (sequential — depends on implementation)

- [ ] 5.1 Validate CLI transport path across Claude Codex, Codex, and Gemini runtimes
  **Dependencies**: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1
  **Files**: (read-only validation, no file modifications)
  **Requirements**: Coordination Detection, Cross-Surface Skill Parity
  **Description**: Run representative skills in each CLI runtime with MCP configured and verify detection sets `COORDINATION_TRANSPORT=mcp`, capability flags are accurate, and hooks execute only when relevant capabilities exist.

- [ ] 5.2 Validate Web/Cloud HTTP path and degraded fallback
  **Dependencies**: 5.1
  **Files**: (read-only validation, no file modifications)
  **Requirements**: Coordination Detection, Coordination Bridge Script
  **Description**: Validate HTTP transport behavior with coordinator reachable and unreachable. Verify `COORDINATION_TRANSPORT=http` when reachable, `none` when unreachable, and `status="skipped"` no-op fallbacks instead of hard failures.

- [ ] 5.3 Run runtime parity validator
  **Dependencies**: 5.2, 1.3
  **Files**: (validation only)
  **Requirements**: Cross-Surface Skill Parity
  **Description**: Run `scripts/validate_skill_runtime_parity.py` and resolve all unsanctioned differences across `.claude`, `.codex`, `.gemini`, and `skills` trees.

- [ ] 5.4 Run OpenSpec validation
  **Dependencies**: 5.3
  **Files**: (validation only)
  **Requirements**: All
  **Description**: Run `openspec validate coordinator-skill-integration --strict` and resolve all validation errors. Confirm every requirement maps to at least one task.

## Parallel Execution Map

```
Group 1 (foundation):   [1.1] [1.2] [1.3]
                         |     |     |
Group 2 (skills):      [2.1] [2.2] [2.3] [2.4] [2.5] [2.6] [2.7] [2.8]  (all parallel, depend on 1.2)
Group 3 (new skill):   [3.1]                                              (parallel with group 2, depends on 1.2)
Group 4 (docs):        [4.1] [4.2]                                        (parallel with groups 2-3)
Group 5 (validate):    [5.1] → [5.2] → [5.3] → [5.4]                     (sequential, after groups 2-4)
```

Maximum parallel width: 11 tasks (groups 2 + 3 + 4 combined)
