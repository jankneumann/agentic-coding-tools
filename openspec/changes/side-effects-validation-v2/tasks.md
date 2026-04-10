# Tasks: Side-Effects Validation for Gen-Eval Framework (v2)

**Change ID**: `side-effects-validation-v2`

## Phase 1: Extended Assertions and Side-Effect Verification (PR 1)

### Model Foundation

- [ ] 1.1 Write tests for extended assertion types (body_contains, body_excludes, status_one_of, rows_gte, rows_lte, array_contains) and mutual exclusion validation
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_extended_assertions.py`
  **Spec scenarios**: gen-eval-framework (Extended Assertion Types): body_contains matches partial structure, body_excludes detects unwanted content, status_one_of accepts any listed code, status and status_one_of are mutually exclusive, rows_gte validates minimum row count, rows_lte validates maximum row count, array_contains matches element in array
  **Design decisions**: D1 (extend ExpectBlock), D5 (deep matching algorithm)
  **Dependencies**: None

- [ ] 1.2 Add body_contains, body_excludes, status_one_of, rows_gte, rows_lte, array_contains to ExpectBlock model with mutual exclusion validator
  **Files**: `agent-coordinator/evaluation/gen_eval/models.py`
  **Spec scenarios**: gen-eval-framework (Extended Assertion Types): all scenarios
  **Design decisions**: D1
  **Dependencies**: 1.1

- [ ] 1.3 Add SideEffectStep, SideEffectsBlock, SideEffectVerdict, SemanticBlock, SemanticVerdict models. Add side_effects and semantic fields to ActionStep. Add side_effect_verdicts and semantic_verdict to StepVerdict.
  **Files**: `agent-coordinator/evaluation/gen_eval/models.py`
  **Spec scenarios**: gen-eval-framework (Side-Effect Declaration): all model scenarios. gen-eval-framework (Semantic Evaluation): all model scenarios.
  **Design decisions**: D2 (sub-block design), D4 (semantic model)
  **Dependencies**: 1.2

- [ ] 1.4 Consolidate ManifestEntry/ScenarioPackManifest -- remove from models.py, ensure manifest.py is the sole definition. Update all imports: `__init__.py` (re-exports), `test_manifest.py` (test imports), and any other files importing these from models.
  **Files**: `agent-coordinator/evaluation/gen_eval/models.py`, `agent-coordinator/evaluation/gen_eval/manifest.py`, `agent-coordinator/evaluation/gen_eval/__init__.py`, `agent-coordinator/tests/test_evaluation/test_gen_eval/test_manifest.py`
  **Design decisions**: D8
  **Dependencies**: 1.3

### Evaluator Extensions

- [ ] 1.5 Write tests for side-effect verify execution, prohibit inverse matching, skip-on-failure behavior, and step_start_time injection
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_side_effects.py`
  **Spec scenarios**: gen-eval-framework (Side-Effect Declaration): Verify side effects after successful operation, Prohibit detects unintended mutation, Side effects skipped on main step failure, Step start time auto-captured
  **Design decisions**: D2, D3
  **Dependencies**: 1.3

- [ ] 1.6 Implement extended assertion matching in evaluator _compare() method: body_contains (with _deep_contains helper), body_excludes, status_one_of, rows_gte, rows_lte, array_contains (with _compare_array_contains helper)
  **Files**: `agent-coordinator/evaluation/gen_eval/evaluator.py`
  **Spec scenarios**: gen-eval-framework (Extended Assertion Types): all scenarios
  **Design decisions**: D1, D5
  **Dependencies**: 1.1, 1.2

- [ ] 1.7 Implement side-effect execution loop: _execute_side_effects() and _run_side_effect_step() methods with verify/prohibit semantics and step_start_time injection. Integrate into _execute_step().
  **Files**: `agent-coordinator/evaluation/gen_eval/evaluator.py`
  **Spec scenarios**: gen-eval-framework (Side-Effect Declaration): Verify side effects after successful operation, Prohibit detects unintended mutation, Side effects skipped on main step failure, Step start time auto-captured
  **Design decisions**: D2, D3
  **Dependencies**: 1.5, 1.6

### Validation

- [ ] 1.8 Run ruff lint, mypy strict, and pytest on all modified/new files. Fix any issues.
  **Dependencies**: 1.7

## Phase 2: Semantic Evaluation + Scenario Pack Restructuring (PR 2)

### Semantic Evaluation

- [ ] 2.1 Write tests for semantic evaluation: LLM invocation, confidence thresholds, LLM unavailability handling, skip when judge=false, structural override behavior
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_semantic_eval.py`
  **Spec scenarios**: gen-eval-framework (Semantic Evaluation): Semantic evaluation judges search relevance, Low confidence produces semantic failure, Unavailable LLM produces skip not failure
  **Design decisions**: D4
  **Dependencies**: 1.3 (SemanticBlock/SemanticVerdict models from Phase 1)

- [ ] 2.2 Implement semantic_judge.py -- LLM-as-judge using the framework's existing CLIBackend/AdaptiveBackend (not hardcoded subprocess). Accept backend as dependency. Parse structured JSON response. Handle unavailability gracefully (skip verdict). Honor existing timeout, rate-limit detection, and budget tracking.
  **Files**: `agent-coordinator/evaluation/gen_eval/semantic_judge.py`
  **Spec scenarios**: gen-eval-framework (Semantic Evaluation): all scenarios
  **Design decisions**: D4, D9 (use existing LLM backend)
  **Dependencies**: 2.1

- [ ] 2.3 Integrate semantic evaluation into evaluator _execute_step(): add _evaluate_semantic() method, invoke after structural + side-effect evaluation, compose semantic_verdict into StepVerdict
  **Files**: `agent-coordinator/evaluation/gen_eval/evaluator.py`
  **Spec scenarios**: gen-eval-framework (Semantic Evaluation): all scenarios
  **Design decisions**: D4
  **Dependencies**: 2.1, 2.2

### Scenario Pack Restructuring

- [ ] 2.4 Split manifests/manifest.yaml into 12 per-category manifest files. Verify that all 97 entries are preserved and correctly categorized.
  **Files**: `agent-coordinator/evaluation/gen_eval/manifests/*.manifest.yaml` (12 new files), remove `manifests/manifest.yaml`
  **Spec scenarios**: gen-eval-framework (Scenario Pack Manifest): per-category manifest organization
  **Design decisions**: D6
  **Dependencies**: 1.4 (model consolidation)

- [ ] 2.5 Update manifest.py loader to glob for `*.manifest.yaml` in the manifests directory. Wire manifest loading into the generator (visibility-aware filtering) and orchestrator (pass visibility context). Update TemplateGenerator to support recursive scenario discovery (load YAML from subdirectories, not just top-level). Update test_manifest.py for new file structure.
  **Files**: `agent-coordinator/evaluation/gen_eval/manifest.py`, `agent-coordinator/evaluation/gen_eval/generator.py`, `agent-coordinator/evaluation/gen_eval/orchestrator.py`, `agent-coordinator/tests/test_evaluation/test_gen_eval/test_manifest.py`
  **Design decisions**: D6, D7
  **Dependencies**: 2.4

### Report and Feedback Extensions

- [ ] 2.6 Write tests for extended reports (side-effect sub-verdicts, semantic confidence) and extended feedback (side-effect failure focus areas, semantic gap suggestions)
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_reports_extended.py`, `agent-coordinator/tests/test_evaluation/test_gen_eval/test_feedback_extended.py`
  **Spec scenarios**: gen-eval-framework (Feedback Loop MODIFIED): side-effect failure patterns, semantic gaps
  **Dependencies**: 1.3

- [ ] 2.7 Update reports.py: add side-effect sub-verdict counts per step, semantic confidence scores, semantic skip-reason aggregation (count and reasons for skipped semantic evaluations), verify/prohibit verdict totals, ensure visibility-grouped reporting (per_visibility) is populated from per-category manifests
  **Files**: `agent-coordinator/evaluation/gen_eval/reports.py`
  **Dependencies**: 2.6, 2.5

- [ ] 2.8 Update feedback.py: surface side-effect failures as distinct focus area category, surface semantic evaluation gaps (steps where semantic was skipped due to LLM unavailability)
  **Files**: `agent-coordinator/evaluation/gen_eval/feedback.py`
  **Dependencies**: 2.6

### Validation

- [ ] 2.9 Run ruff lint, mypy strict, and pytest on all modified/new files. Fix any issues.
  **Dependencies**: 2.8

## Phase 3: E2E Scenario Templates + Integration (PR 3)

### Templates

- [ ] 3.1 Write tests validating E2E scenario template YAML structure, Pydantic model compliance, and feature usage (each template uses at least one extended assertion and one side-effect block)
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_e2e_templates.py`
  **Spec scenarios**: gen-eval-framework (End-to-End User Scenario Templates): all scenarios
  **Design decisions**: D2, D5
  **Dependencies**: 1.7 (evaluator supports extended assertions + side-effects)

- [ ] 3.2 Create memory lifecycle E2E scenario template using body_contains for search verification, side_effects.verify for audit trail, and side_effects.prohibit for no-unintended-writes
  **Files**: `agent-coordinator/evaluation/gen_eval/scenarios/memory-crud/memory-lifecycle-e2e.yaml`
  **Spec scenarios**: gen-eval-framework (E2E Templates): Memory lifecycle template validates search correctness
  **Dependencies**: 3.1

- [ ] 3.3 Create lock-task workflow E2E scenario template with side_effects.verify after each state-changing step
  **Files**: `agent-coordinator/evaluation/gen_eval/scenarios/work-queue/lock-task-workflow-e2e.yaml`
  **Spec scenarios**: gen-eval-framework (E2E Templates): Lock-task template verifies intermediate state transitions
  **Dependencies**: 3.1

- [ ] 3.4 Create policy enforcement E2E scenario template with side_effects.prohibit on denied operations
  **Files**: `agent-coordinator/evaluation/gen_eval/scenarios/auth-boundary/policy-enforcement-e2e.yaml`
  **Spec scenarios**: gen-eval-framework (E2E Templates): Policy enforcement template confirms no side effects on denial
  **Dependencies**: 3.1

- [ ] 3.5 Create handoff integrity and cross-interface consistency E2E scenario templates
  **Files**: `agent-coordinator/evaluation/gen_eval/scenarios/handoffs/handoff-integrity-e2e.yaml`, `agent-coordinator/evaluation/gen_eval/scenarios/cross-interface/full-consistency-e2e.yaml`
  **Dependencies**: 3.1

- [ ] 3.6 Add manifest entries for new E2E scenarios in the appropriate per-category manifest files
  **Files**: `agent-coordinator/evaluation/gen_eval/manifests/*.manifest.yaml`
  **Dependencies**: 3.2, 3.3, 3.4, 3.5, 2.4

### Integration

- [ ] 3.7 Write integration test exercising extended assertions + side effects + semantic eval + manifest loading in a combined scenario
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_integration_extended.py`
  **Dependencies**: 3.6

### Validation

- [ ] 3.8 Run ruff lint, mypy strict, and pytest on all modified/new files. Verify all existing tests still pass.
  **Dependencies**: 3.7
