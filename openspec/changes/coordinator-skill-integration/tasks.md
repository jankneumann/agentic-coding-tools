# Tasks: coordinator-skill-integration

## 1. Foundation (sequential - other tasks depend on these)

- [ ] 1.1 Create coordination bridge Python module
  **Dependencies**: None
  **Files**: `scripts/coordination_bridge.py`, `scripts/tests/test_coordination_bridge.py`
  **Requirement**: Coordination Bridge Script
  **Description**: Create transport-aware HTTP helpers for coordination operations: `detect_coordination(http_url=None, api_key=None) -> dict`, `try_lock`, `try_unlock`, `try_submit_work`, `try_get_work`, `try_complete_work`, `try_handoff_write`, `try_handoff_read`, `try_remember`, `try_recall`, `try_check_guardrails`. Return normalized no-op responses with `status="skipped"` when unavailable.

- [ ] 1.2 Define coordination detection preamble template
  **Dependencies**: None
  **Files**: `docs/coordination-detection-template.md`
  **Requirement**: Coordination Detection
  **Description**: Provide reusable preamble logic that sets `COORDINATOR_AVAILABLE`, `COORDINATION_TRANSPORT` (`mcp|http|none`), and capability flags (`CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`) for CLI and Web/Cloud contexts.

- [ ] 1.3 Document canonical skill distribution workflow
  **Dependencies**: None
  **Files**: `docs/skills-workflow.md`
  **Requirement**: Canonical Skill Distribution
  **Description**: Document that `skills/` is source-of-truth and runtime skill trees are synced via `skills/install.sh --mode rsync --agents claude,codex,gemini`.

## 2. Canonical Skill Enhancements (parallelizable - separate files under `skills/`)

- [ ] 2.1 Add coordination hooks to canonical `/implement-feature`
  **Dependencies**: 1.2
  **Files**: `skills/implement-feature/SKILL.md`
  **Requirements**: Coordination Detection, File Locking in Implement Feature, Work Queue Integration in Implement Feature, Session Handoff Hooks, Guardrail Pre-checks
  **Description**: Add transport-aware preamble and capability-gated hooks: locking (`CAN_LOCK`), queue (`CAN_QUEUE_WORK`), guardrails (`CAN_GUARDRAILS`), handoffs (`CAN_HANDOFF`), with fallback behavior unchanged.

- [ ] 2.2 Add coordination hooks to canonical `/plan-feature`
  **Dependencies**: 1.2
  **Files**: `skills/plan-feature/SKILL.md`
  **Requirements**: Coordination Detection, Session Handoff Hooks, Memory Hooks
  **Description**: Add preamble, handoff read/write (`CAN_HANDOFF`), and memory recall (`CAN_MEMORY`) while preserving standalone behavior.

- [ ] 2.3 Add coordination hooks to canonical `/iterate-on-plan`
  **Dependencies**: 1.2
  **Files**: `skills/iterate-on-plan/SKILL.md`
  **Requirements**: Coordination Detection, Session Handoff Hooks, Memory Hooks
  **Description**: Add preamble, handoff read/write (`CAN_HANDOFF`), memory recall at start (`CAN_MEMORY`), and remember on iteration completion (`CAN_MEMORY`).

- [ ] 2.4 Add coordination hooks to canonical `/iterate-on-implementation`
  **Dependencies**: 1.2
  **Files**: `skills/iterate-on-implementation/SKILL.md`
  **Requirements**: Coordination Detection, Session Handoff Hooks, Memory Hooks
  **Description**: Add preamble, handoff read/write (`CAN_HANDOFF`), memory recall at start (`CAN_MEMORY`), and remember on iteration completion (`CAN_MEMORY`).

- [ ] 2.5 Add coordination hooks to canonical `/validate-feature`
  **Dependencies**: 1.2
  **Files**: `skills/validate-feature/SKILL.md`
  **Requirements**: Coordination Detection, Memory Hooks
  **Description**: Add preamble, memory recall at start (`CAN_MEMORY`), and remember on completion (`CAN_MEMORY`).

- [ ] 2.6 Add coordination hooks to canonical `/cleanup-feature`
  **Dependencies**: 1.2
  **Files**: `skills/cleanup-feature/SKILL.md`
  **Requirements**: Coordination Detection, Session Handoff Hooks, File Locking in Implement Feature
  **Description**: Add preamble, handoff read/write (`CAN_HANDOFF`), and lock cleanup behavior when lock capability exists (`CAN_LOCK`).

- [ ] 2.7 Add coordination hooks to canonical `/security-review`
  **Dependencies**: 1.2
  **Files**: `skills/security-review/SKILL.md`
  **Requirements**: Coordination Detection, Guardrail Pre-checks
  **Description**: Add preamble and guardrail pre-check reporting (`CAN_GUARDRAILS`) before scan execution.

- [ ] 2.8 Add coordination hooks to canonical `/explore-feature`
  **Dependencies**: 1.2
  **Files**: `skills/explore-feature/SKILL.md`
  **Requirements**: Coordination Detection, Memory Hooks
  **Description**: Add preamble and memory recall at start (`CAN_MEMORY`) for improved continuity.

## 3. New Canonical Skill

- [ ] 3.1 Create canonical `/setup-coordinator` skill
  **Dependencies**: 1.2
  **Files**: `skills/setup-coordinator/SKILL.md`
  **Requirement**: Setup Coordinator Skill
  **Description**: Add onboarding covering CLI MCP setup/verification and Web/Cloud HTTP setup/verification, plus capability summary and fallback guidance.

## 4. Runtime Mirror Sync (sequential after canonical changes)

- [ ] 4.1 Sync canonical skills into runtime mirrors
  **Dependencies**: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1
  **Files**: `.claude/skills/*`, `.codex/skills/*`, `.gemini/skills/*` (generated updates)
  **Requirement**: Canonical Skill Distribution
  **Description**: Run `skills/install.sh --mode rsync --agents claude,codex,gemini --deps none --python-tools none` to propagate canonical changes.

- [ ] 4.2 Verify mirror consistency after sync
  **Dependencies**: 4.1
  **Files**: (validation only)
  **Requirement**: Canonical Skill Distribution
  **Description**: Verify no unexpected runtime drift remains after sync (all integrated skills in runtime trees match canonical `skills/` content for this change).

## 5. Documentation (parallelizable with groups 2-3, before validation)

- [ ] 5.1 Add coordinator integration section to skills-workflow docs
  **Dependencies**: None
  **Files**: `docs/skills-workflow.md`
  **Requirement**: Skill Integration Usage Patterns (agent-coordinator spec)
  **Description**: Document transport model (MCP vs HTTP), capability flags, canonical `skills/` authoring, sync command, and graceful fallback behavior.

- [ ] 5.2 Add skill integration patterns to agent-coordinator docs
  **Dependencies**: None
  **Files**: `docs/agent-coordinator.md`
  **Requirement**: Skill Integration Usage Patterns (agent-coordinator spec)
  **Description**: Document skill-to-capability mapping for CLI and Web/Cloud, setup guidance, and fallback semantics. Include explicit linkage note that Neon standardization is handled in a separate coordinator infrastructure proposal, while this change remains backend-agnostic.

## 6. Validation (sequential - explicit 3 providers x 2 transports matrix)

- [ ] 6.1 MCP matrix: local CLI path across three providers
  **Dependencies**: 4.2, 5.1, 5.2
  **Files**: (read-only validation)
  **Requirements**: Coordination Detection, Canonical Skill Distribution
  **Description**: Validate representative integrated skills in each CLI runtime:
  - Claude Codex CLI + MCP
  - Codex CLI + MCP
  - Gemini CLI + MCP
  For each runtime, explicitly verify:
  - detection sets `COORDINATION_TRANSPORT=mcp`
  - capability flags are populated correctly for exposed MCP tools
  - `/implement-feature` executes lock/queue/guardrail hooks only when the corresponding `CAN_*` flag is true
  - `/plan-feature` or `/iterate-on-plan` reads/writes handoffs only when `CAN_HANDOFF=true`
  - `/validate-feature` and `/iterate-on-*` memory hooks run only when `CAN_MEMORY=true`

- [ ] 6.2 HTTP matrix: Web/Cloud path across three providers
  **Dependencies**: 6.1
  **Files**: (read-only validation)
  **Requirements**: Coordination Detection, Coordination Bridge Script
  **Description**: Validate representative integrated flows in each Web/Cloud runtime:
  - Claude Web + HTTP API
  - Codex Cloud + HTTP API
  - Gemini Web/Cloud + HTTP API
  For each runtime, explicitly verify:
  - detection sets `COORDINATION_TRANSPORT=http`
  - bridge-based capability detection reflects reachable HTTP endpoints
  - capability-gated hooks match HTTP capability availability (including partial-capability cases)
  - guardrail violations are reported informationally (phase 1) without hard blocking

- [ ] 6.3 Degraded fallback matrix (both transports)
  **Dependencies**: 6.2
  **Files**: (read-only validation)
  **Requirements**: Coordination Detection, Coordination Bridge Script
  **Description**: Simulate coordinator unavailability for MCP and HTTP paths. Verify for each provider/runtime:
  - detection falls back to `COORDINATION_TRANSPORT=none` and/or `COORDINATOR_AVAILABLE=false` as appropriate
  - skills continue with standalone behavior (no coordinator-induced hard failure)
  - bridge/tool calls degrade to informational skip behavior (`status="skipped"` where applicable)
  - lock release/cleanup paths do not fail if coordinator is unreachable mid-run

- [ ] 6.4 Run OpenSpec validation
  **Dependencies**: 6.3
  **Files**: (validation only)
  **Requirements**: All
  **Description**: Run `openspec validate coordinator-skill-integration --strict` and resolve all validation errors.

## Parallel Execution Map

```
Group 1 (foundation):   [1.1] [1.2] [1.3]
Group 2 (canonical):    [2.1] [2.2] [2.3] [2.4] [2.5] [2.6] [2.7] [2.8]  (parallel, depend on 1.2)
Group 3 (new skill):    [3.1]                                              (depends on 1.2, parallel with group 2)
Group 4 (sync):         [4.1] -> [4.2]                                     (after groups 2-3)
Group 5 (docs):         [5.1] [5.2]                                        (parallel with groups 2-3)
Group 6 (validate):     [6.1] -> [6.2] -> [6.3] -> [6.4]                  (after 4.2 and docs)
```

Maximum parallel width: 10 tasks (groups 2 + 3 + 5 combined)
