# Tasks: add-two-level-parallel-development

## Requirement Mapping

- R1 Skill Family Structure → 1.1, 1.2
- R2 Contract Artifacts → 2.1, 2.2
- R3 Work-Packages DAG Validation → 3.1, 3.2, 3.3
- R4 Coordinator get_task API → 3.4
- R5 Coordinator Cancellation Convention → 3.5
- R6 Coordinator Lock Key Policy → 3.6
- R7 Parallel Plan and Explore Skills → 4.1, 4.2
- R8 Review Skills → 5.1, 5.2
- R9 DAG Scheduler → 6.1
- R10 Package Execution Protocol → 6.2
- R11 Result Validation → 6.3
- R12 Escalation Handling → 6.4
- R13 Review + Integration Sequencing → 6.5
- R14 Circuit Breaking → 6.6
- R15 Feature Registry → 7.1, 7.2
- R16 Merge Queue → 8.1, 8.2
- R17 Parallel Validate Feature → 9.1
- R18 Formal Verification → FV.1, FV.2, FV.3

## 1. Skill Family Structure

- [x] 1.1 Rename existing skills to `linear-*` prefix with backward-compatible aliases. Update `CLAUDE.md`, `AGENTS.md`, and `docs/skills-workflow.md`.
  **Dependencies**: None
  **Files**: skills/linear-explore-feature/SKILL.md, skills/linear-plan-feature/SKILL.md, skills/linear-implement-feature/SKILL.md, skills/linear-validate-feature/SKILL.md, skills/linear-cleanup-feature/SKILL.md, skills/linear-iterate-on-plan/SKILL.md, skills/linear-iterate-on-implementation/SKILL.md, CLAUDE.md, AGENTS.md, docs/skills-workflow.md
  **Verify**: All existing skill invocations continue to work via aliases. `openspec validate add-two-level-parallel-development --strict` passes.

- [x] 1.2 Add `CAN_DISCOVER`, `CAN_POLICY`, `CAN_AUDIT` capability flags to coordinator capability detection in parallel skill stubs.
  **Dependencies**: 1.1
  **Files**: skills/parallel-implement-feature/SKILL.md, skills/parallel-plan-feature/SKILL.md
  **Verify**: Capability flags are declared in skill frontmatter and referenced in preflight checks.

## 2. Contract Artifacts

- [x] 2.1 Add `contracts` and `work-packages` artifact types to `openspec/schemas/feature-workflow/schema.yaml`. Add templates for OpenAPI spec stubs, Prism mock config, Schemathesis config, and Pact config.
  **Dependencies**: None
  **Files**: openspec/schemas/feature-workflow/schema.yaml, openspec/schemas/feature-workflow/templates/openapi-stub.yaml, openspec/schemas/feature-workflow/templates/prism-config.yaml, openspec/schemas/feature-workflow/templates/schemathesis-config.yaml, openspec/schemas/feature-workflow/templates/pact-config.yaml
  **Verify**: `openspec validate` recognizes the new artifact types without errors.

- [x] 2.2 Document lock key namespace conventions and canonicalization rules. Add reference page with prefix table, format, normalization rules, and examples.
  **Dependencies**: None
  **Files**: docs/lock-key-namespaces.md
  **Verify**: Documentation covers all 8 namespace prefixes with format and normalization rules.

## 3. Work-Packages DAG and Coordinator Deltas

- [x] 3.1 Install `work-packages.schema.json` validation pipeline: YAML-to-JSON parsing, JSON Schema validation, DAG cycle detection, lock key canonicalization checks.
  **Dependencies**: 2.1
  **Files**: scripts/validate_work_packages.py, scripts/tests/test_validate_work_packages.py
  **Traces**: R3
  **Verify**: `scripts/.venv/bin/python scripts/validate_work_packages.py --help` runs. Tests pass: `scripts/.venv/bin/python -m pytest scripts/tests/test_validate_work_packages.py -v`.

- [x] 3.2 Add `--validate-packages` mode to `scripts/parallel_zones.py` for scope non-overlap and lock non-overlap validation of parallel packages.
  **Dependencies**: 3.1
  **Files**: scripts/parallel_zones.py, scripts/tests/test_parallel_zones_packages.py
  **Traces**: R3
  **Verify**: `scripts/.venv/bin/python scripts/parallel_zones.py --validate-packages tests/fixtures/sample-work-packages.yaml` produces expected output.

- [x] 3.3 Install `work-queue-result.schema.json` validation as a library function callable by the orchestrator after `complete_work`.
  **Dependencies**: 3.1
  **Files**: scripts/validate_work_result.py, scripts/tests/test_validate_work_result.py
  **Traces**: R3
  **Verify**: `scripts/.venv/bin/python -m pytest scripts/tests/test_validate_work_result.py -v` passes.

- [x] 3.4 Expose existing `WorkQueueService.get_task(task_id)` as MCP tool and HTTP endpoint `GET /api/v1/tasks/{task_id}`.
  **Dependencies**: None
  **Files**: agent-coordinator/src/agent_coordinator/mcp_server.py, agent-coordinator/src/agent_coordinator/http_api.py, agent-coordinator/src/agent_coordinator/services/work_queue.py, agent-coordinator/tests/test_mcp_get_task.py, agent-coordinator/tests/test_http_get_task.py
  **Traces**: R4
  **Verify**: `cd agent-coordinator && uv run pytest tests/test_mcp_get_task.py tests/test_http_get_task.py -v` passes.

- [x] 3.5 Document cancellation convention: `complete_work(success=false)` with `error_code="cancelled_by_orchestrator"` in result. Add helper function `cancel_task_convention(task_id, reason)`.
  **Dependencies**: 3.4
  **Files**: agent-coordinator/src/agent_coordinator/services/work_queue.py, agent-coordinator/tests/test_cancel_convention.py
  **Traces**: R5
  **Verify**: `cd agent-coordinator && uv run pytest tests/test_cancel_convention.py -v` passes.

- [x] 3.6 Update lock key policy rules to permit `api:`, `db:`, `event:`, `flag:`, `env:`, `contract:`, `feature:` patterns in `acquire_lock`.
  **Dependencies**: None
  **Files**: agent-coordinator/src/agent_coordinator/services/lock_service.py, agent-coordinator/tests/test_lock_key_policy.py
  **Traces**: R6
  **Verify**: `cd agent-coordinator && uv run pytest tests/test_lock_key_policy.py -v` passes. Logical lock keys can be acquired and released.

## 4. Parallel Plan and Explore Skills

- [x] 4.1 Create `/parallel-explore-feature` skill that produces candidate shortlist with resource claim analysis for parallel feasibility.
  **Dependencies**: 1.1, 2.1
  **Files**: skills/parallel-explore-feature/SKILL.md
  **Traces**: R7
  **Verify**: Skill frontmatter is valid. Skill references contract artifacts and work-packages structure.

- [x] 4.2 Create `/parallel-plan-feature` skill that produces `contracts/` directory and `work-packages.yaml` conforming to `work-packages.schema.json`. Includes context slicing logic and capability-gated coordinator hooks.
  **Dependencies**: 1.2, 2.1, 3.1
  **Files**: skills/parallel-plan-feature/SKILL.md
  **Traces**: R7
  **Verify**: Skill frontmatter is valid. Output artifacts validate against schemas.

## 5. Review Skills

- [x] 5.1 Create `/parallel-review-plan` skill that receives plan artifacts as read-only input and produces findings per `review-findings.schema.json` with disposition classification.
  **Dependencies**: 1.1
  **Files**: skills/parallel-review-plan/SKILL.md
  **Traces**: R8
  **Verify**: Skill frontmatter is valid. Output validates against `review-findings.schema.json`.

- [x] 5.2 Create `/parallel-review-implementation` skill that receives a package diff as read-only input and produces findings per `review-findings.schema.json`. Supports vendor-diverse dispatch.
  **Dependencies**: 1.1
  **Files**: skills/parallel-review-implementation/SKILL.md
  **Traces**: R8
  **Verify**: Skill frontmatter is valid. Output validates against `review-findings.schema.json`.

## 6. Parallel Implement Feature with DAG Dispatch

- [x] 6.1 Implement DAG scheduler in `/parallel-implement-feature`: Phase A preflight (parse, validate, compute DAG, submit work queue tasks, begin monitoring).
  **Dependencies**: 3.1, 3.2, 3.4, 4.2
  **Files**: skills/parallel-implement-feature/SKILL.md, skills/parallel-implement-feature/scripts/dag_scheduler.py, skills/parallel-implement-feature/scripts/tests/test_dag_scheduler.py
  **Traces**: R9
  **Verify**: `agent-coordinator/.venv/bin/python -m pytest skills/parallel-implement-feature/scripts/tests/test_dag_scheduler.py -v` passes.

- [x] 6.2 Implement package execution protocol: Phase B (session registration, pause-lock checks B2/B9, deadlock-safe lock acquisition B3, scope enforcement B7, structured result B10).
  **Dependencies**: 6.1, 3.6
  **Files**: skills/parallel-implement-feature/scripts/package_executor.py, skills/parallel-implement-feature/scripts/scope_checker.py, skills/parallel-implement-feature/scripts/tests/test_package_executor.py, skills/parallel-implement-feature/scripts/tests/test_scope_checker.py
  **Traces**: R10
  **Verify**: `agent-coordinator/.venv/bin/python -m pytest skills/parallel-implement-feature/scripts/tests/ -v` passes.

- [x] 6.3 Implement result validation: Phase C1 (schema validation against `work-queue-result.schema.json`, revision matching, output key verification).
  **Dependencies**: 3.3, 6.1
  **Files**: skills/parallel-implement-feature/scripts/result_validator.py, skills/parallel-implement-feature/scripts/tests/test_result_validator.py
  **Traces**: R11
  **Verify**: `agent-coordinator/.venv/bin/python -m pytest skills/parallel-implement-feature/scripts/tests/test_result_validator.py -v` passes.

- [x] 6.4 Implement escalation handling: deterministic decision procedure per escalation type, pause-lock acquisition, contract revision bump procedure, plan revision bump procedure.
  **Dependencies**: 6.2, 3.5
  **Files**: skills/parallel-implement-feature/scripts/escalation_handler.py, skills/parallel-implement-feature/scripts/tests/test_escalation_handler.py
  **Traces**: R12
  **Verify**: `agent-coordinator/.venv/bin/python -m pytest skills/parallel-implement-feature/scripts/tests/test_escalation_handler.py -v` passes.

- [x] 6.5 Implement review + integration sequencing: Phase C3-C6 (per-package review dispatch, integration gate, `wp-integration` merge package, execution summary generation).
  **Dependencies**: 5.2, 6.3
  **Files**: skills/parallel-implement-feature/scripts/integration_orchestrator.py, skills/parallel-implement-feature/scripts/tests/test_integration_orchestrator.py
  **Traces**: R13
  **Verify**: `agent-coordinator/.venv/bin/python -m pytest skills/parallel-implement-feature/scripts/tests/test_integration_orchestrator.py -v` passes.

- [x] 6.6 Implement circuit breaking: heartbeat detection for stuck agents, retry budget enforcement, cancellation propagation to dependent packages.
  **Dependencies**: 6.1, 3.5
  **Files**: skills/parallel-implement-feature/scripts/circuit_breaker.py, skills/parallel-implement-feature/scripts/tests/test_circuit_breaker.py
  **Traces**: R14
  **Verify**: `agent-coordinator/.venv/bin/python -m pytest skills/parallel-implement-feature/scripts/tests/test_circuit_breaker.py -v` passes.

## 7. Feature Registry

- [x] 7.1 Implement `feature_registry.py` service with PostgreSQL migration for cross-feature resource claim management.
  **Dependencies**: 3.6
  **Files**: agent-coordinator/src/agent_coordinator/services/feature_registry.py, agent-coordinator/migrations/003_feature_registry.sql, agent-coordinator/tests/test_feature_registry.py
  **Traces**: R15
  **Verify**: `cd agent-coordinator && uv run pytest tests/test_feature_registry.py -v` passes.

- [x] 7.2 Implement conflict analysis and parallel feasibility assessment (`FULL`, `PARTIAL`, `SEQUENTIAL`) based on lock-key overlap detection.
  **Dependencies**: 7.1
  **Files**: agent-coordinator/src/agent_coordinator/services/feature_registry.py, agent-coordinator/tests/test_feasibility_assessment.py
  **Traces**: R15
  **Verify**: `cd agent-coordinator && uv run pytest tests/test_feasibility_assessment.py -v` passes.

## 8. Merge Queue and Cross-Feature Coordination

- [x] 8.1 Implement merge ordering and pre-merge check infrastructure in the coordinator.
  **Dependencies**: 7.2
  **Files**: agent-coordinator/src/agent_coordinator/services/merge_queue.py, agent-coordinator/tests/test_merge_queue.py
  **Traces**: R16
  **Verify**: `cd agent-coordinator && uv run pytest tests/test_merge_queue.py -v` passes.

- [x] 8.2 Create `/parallel-cleanup-feature` skill extending existing cleanup with cross-feature rebase coordination and merge queue integration.
  **Dependencies**: 8.1
  **Files**: skills/parallel-cleanup-feature/SKILL.md
  **Traces**: R16
  **Verify**: Skill frontmatter is valid. References merge queue coordinator primitives.

## 9. Parallel Validate Feature

- [x] 9.1 Create `/parallel-validate-feature` skill: slim integration-only validation, evidence completeness checking via `work-queue-result.schema.json` schema validation.
  **Dependencies**: 3.3
  **Files**: skills/parallel-validate-feature/SKILL.md
  **Traces**: R17
  **Verify**: Skill frontmatter is valid. Evidence completeness checks reference result schema.

## 10. Documentation and Workflow Integration

- [x] 10.1 Update `docs/skills-workflow.md` with parallel workflow documentation: dual skill family reference, work-packages lifecycle, DAG scheduling overview, escalation handling.
  **Dependencies**: 4.2, 6.1
  **Files**: docs/skills-workflow.md
  **Verify**: Documentation covers parallel workflow end-to-end.

- [x] 10.2 Update `docs/agent-coordinator.md` with new capabilities: `get_task` API, logical lock keys, feature registry, cancellation convention.
  **Dependencies**: 3.4, 3.5, 3.6, 7.1
  **Files**: docs/agent-coordinator.md
  **Verify**: Documentation covers all coordinator deltas.

## FV. Formal Verification

- [x] FV.1 Create TLA+ model for lock acquisition/release/expiry, task claim/complete, dependency gating, pause-lock coordination, orchestrator rescheduling. Run TLC model checker on bounded instances.
  **Dependencies**: 6.2
  **Files**: formal/parallel-coordination.tla, formal/parallel-coordination.cfg
  **Traces**: R18
  **Verify**: `tlc formal/parallel-coordination.tla` terminates without invariant violations.

- [x] FV.2 Create Lean safety proofs for DAG scheduler correctness: lock exclusivity, no double-claim, dependency safety, result immutability, cancellation propagation, pause-lock safety.
  **Dependencies**: FV.1
  **Files**: formal/lean/ParallelCoordination.lean, formal/lean/Proofs.lean
  **Traces**: R18
  **Verify**: `lake build` compiles without errors.

- [x] FV.3 Create property-based tests with randomized operation sequences against real coordinator, compared to abstract model. Integrate into CI.
  **Dependencies**: FV.1, 6.2
  **Files**: agent-coordinator/tests/test_property_based.py
  **Traces**: R18
  **Verify**: `cd agent-coordinator && uv run pytest tests/test_property_based.py -v` passes.
