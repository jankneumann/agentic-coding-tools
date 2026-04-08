# Tasks: Side-Effects Validation for Gen-Eval Framework

**Change ID**: `add-side-effects-validation`

## Phase 1: Formalize Extended Assertion Types

- [ ] 1.1 Write tests for body_contains, body_excludes, status_one_of, rows_gte, rows_lte, and array_contains assertions
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_extended_assertions.py`
  **Spec scenarios**: gen-eval-framework (Extended Assertion Types): body_contains matches partial structure, body_excludes detects unwanted content, status_one_of accepts any listed code, status and status_one_of are mutually exclusive, rows_gte validates minimum row count, array_contains matches element in array
  **Design decisions**: D1 (extend ExpectBlock), D5 (deep matching algorithm)
  **Dependencies**: None

- [ ] 1.2 Add body_contains, body_excludes, status_one_of, rows_gte, rows_lte, array_contains to ExpectBlock model
  **Files**: `agent-coordinator/evaluation/gen_eval/models.py`
  **Spec scenarios**: gen-eval-framework (Extended Assertion Types): all scenarios
  **Design decisions**: D1
  **Dependencies**: 1.1

- [ ] 1.3 Implement extended assertion matching in evaluator _compare() method
  **Files**: `agent-coordinator/evaluation/gen_eval/evaluator.py`
  **Spec scenarios**: gen-eval-framework (Extended Assertion Types): body_contains matches partial structure, body_excludes detects unwanted content, status_one_of accepts any listed code, rows_gte validates minimum row count, array_contains matches element in array
  **Design decisions**: D1, D5
  **Dependencies**: 1.1, 1.2

- [ ] 1.4 Add mutual exclusion validation for status vs status_one_of
  **Files**: `agent-coordinator/evaluation/gen_eval/models.py`
  **Spec scenarios**: gen-eval-framework (Extended Assertion Types): status and status_one_of are mutually exclusive
  **Design decisions**: D1
  **Dependencies**: 1.2

## Phase 2: Side-Effect Declaration and Verification

- [ ] 2.1 Write tests for side_effects.verify execution, side_effects.prohibit inverse matching, skip-on-failure behavior, and step_start_time injection
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_side_effects.py`
  **Spec scenarios**: gen-eval-framework (Side-Effect Declaration): Verify side effects after successful operation, Prohibit detects unintended mutation, Side effects skipped on main step failure, Step start time auto-captured
  **Design decisions**: D2 (sub-block design), D3 (prohibit semantics)
  **Dependencies**: 1.1

- [ ] 2.2 Add SideEffectsBlock and side_effects field to ActionStep model, add side_effect_verdicts to StepVerdict
  **Files**: `agent-coordinator/evaluation/gen_eval/models.py`
  **Spec scenarios**: gen-eval-framework (Side-Effect Declaration): all scenarios
  **Design decisions**: D2
  **Dependencies**: 2.1

- [ ] 2.3 Implement side-effect execution loop in evaluator _execute_step()
  **Files**: `agent-coordinator/evaluation/gen_eval/evaluator.py`
  **Spec scenarios**: gen-eval-framework (Side-Effect Declaration): Verify side effects after successful operation, Side effects skipped on main step failure, Step start time auto-captured
  **Design decisions**: D2, D3
  **Dependencies**: 2.1, 2.2, 1.3

- [ ] 2.4 Implement prohibit inverse matching logic
  **Files**: `agent-coordinator/evaluation/gen_eval/evaluator.py`
  **Spec scenarios**: gen-eval-framework (Side-Effect Declaration): Prohibit detects unintended mutation
  **Design decisions**: D3
  **Dependencies**: 2.3

## Phase 3: Semantic Evaluation with LLM-as-Judge

- [ ] 3.1 Write tests for semantic evaluation invocation, confidence thresholds, LLM unavailability handling, and semantic verdict reporting
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_semantic_eval.py`
  **Spec scenarios**: gen-eval-framework (Semantic Evaluation): Semantic evaluation judges search relevance, Low confidence produces semantic failure, Unavailable LLM produces skip not failure
  **Design decisions**: D4 (semantic independence)
  **Dependencies**: None

- [ ] 3.2 Add SemanticBlock and semantic field to ActionStep model, add semantic_verdict to StepVerdict
  **Files**: `agent-coordinator/evaluation/gen_eval/models.py`
  **Spec scenarios**: gen-eval-framework (Semantic Evaluation): all scenarios
  **Design decisions**: D4
  **Dependencies**: 3.1

- [ ] 3.3 Implement semantic_judge.py — LLM-as-judge integration via CLI pathway
  **Files**: `agent-coordinator/evaluation/gen_eval/semantic_judge.py`
  **Spec scenarios**: gen-eval-framework (Semantic Evaluation): Semantic evaluation judges search relevance, Low confidence produces semantic failure, Unavailable LLM produces skip not failure
  **Design decisions**: D4
  **Dependencies**: 3.1, 3.2

- [ ] 3.4 Integrate semantic evaluation into evaluator _execute_step()
  **Files**: `agent-coordinator/evaluation/gen_eval/evaluator.py`
  **Spec scenarios**: gen-eval-framework (Semantic Evaluation): all scenarios
  **Design decisions**: D4
  **Dependencies**: 3.3, 2.3

## Phase 4: Scenario Pack Management

- [ ] 4.1 Write tests for manifest model validation, visibility filtering, provenance tracking, and visibility-grouped reporting
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_manifest.py`, `agent-coordinator/tests/test_evaluation/test_gen_eval/test_visibility_filter.py`
  **Spec scenarios**: gen-eval-framework (Scenario Pack Manifest): Manifest validates public vs holdout, Manifest preserves provenance, Invalid visibility rejected. gen-eval-framework (Visibility-Aware Execution): Implementation run excludes holdout, Cleanup gate includes holdout, Report includes visibility coverage
  **Design decisions**: D6 (manifest format), D7 (filter integration point)
  **Dependencies**: None

- [ ] 4.2 Implement manifest.py — scenario pack manifest model and loader
  **Files**: `agent-coordinator/evaluation/gen_eval/manifest.py`
  **Spec scenarios**: gen-eval-framework (Scenario Pack Manifest): all scenarios
  **Design decisions**: D6
  **Dependencies**: 4.1

- [ ] 4.3 Add visibility-aware filtering to generator and descriptor
  **Files**: `agent-coordinator/evaluation/gen_eval/generator.py`, `agent-coordinator/evaluation/gen_eval/descriptor.py`
  **Spec scenarios**: gen-eval-framework (Visibility-Aware Execution): Implementation run excludes holdout, Cleanup gate includes holdout
  **Design decisions**: D7
  **Dependencies**: 4.1, 4.2

- [ ] 4.4 Add visibility-grouped sections to report generation
  **Files**: `agent-coordinator/evaluation/gen_eval/reports.py`
  **Spec scenarios**: gen-eval-framework (Visibility-Aware Execution): Report includes visibility coverage
  **Design decisions**: D7
  **Dependencies**: 4.3

- [ ] 4.5 Implement multi-source scenario bootstrap in gen-eval-scenario skill
  **Files**: `skills/gen-eval-scenario/SKILL.md`, `skills/gen-eval-scenario/scripts/bootstrap.py`
  **Spec scenarios**: gen-eval-framework (Multi-Source Scenario Bootstrap): Bootstrap from spec deltas, Bootstrap from contract artifact, Bootstrap from empty spec delta produces no scenarios
  **Design decisions**: D6
  **Dependencies**: 4.2

## Phase 5: End-to-End User Scenario Templates

- [ ] 5.1 Write tests validating scenario template YAML structure and Pydantic model compliance
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_e2e_templates.py`
  **Spec scenarios**: gen-eval-framework (End-to-End User Scenario Templates): all scenarios
  **Design decisions**: D2, D5
  **Dependencies**: 1.3, 2.3

- [ ] 5.2 Create memory lifecycle scenario template (store → search → verify correctness → verify audit → verify no unintended writes)
  **Files**: `agent-coordinator/evaluation/gen_eval/scenarios/memory-crud/memory-lifecycle-e2e.yaml`
  **Spec scenarios**: gen-eval-framework (End-to-End Templates): Memory lifecycle template validates search correctness
  **Design decisions**: D2, D5
  **Dependencies**: 5.1

- [ ] 5.3 Create lock-task workflow scenario template (acquire → submit → claim → complete → verify state transitions → verify audit)
  **Files**: `agent-coordinator/evaluation/gen_eval/scenarios/work-queue/lock-task-workflow-e2e.yaml`
  **Spec scenarios**: gen-eval-framework (End-to-End Templates): Lock-task template verifies intermediate state transitions
  **Design decisions**: D2
  **Dependencies**: 5.1

- [ ] 5.4 Create policy enforcement scenario template (denied → verify no side effects → escalate → verify correct side effects)
  **Files**: `agent-coordinator/evaluation/gen_eval/scenarios/auth-boundary/policy-enforcement-e2e.yaml`
  **Spec scenarios**: gen-eval-framework (End-to-End Templates): Policy enforcement template confirms no side effects on denial
  **Design decisions**: D2, D3
  **Dependencies**: 5.1

- [ ] 5.5 Create handoff integrity and cross-interface consistency scenario templates
  **Files**: `agent-coordinator/evaluation/gen_eval/scenarios/handoffs/handoff-integrity-e2e.yaml`, `agent-coordinator/evaluation/gen_eval/scenarios/cross-interface/full-consistency-e2e.yaml`
  **Spec scenarios**: gen-eval-framework (End-to-End Templates): all template scenarios
  **Design decisions**: D2
  **Dependencies**: 5.1

- [ ] 5.6 Create initial scenario pack manifests for existing and new scenario categories
  **Files**: `agent-coordinator/evaluation/gen_eval/manifests/lock-lifecycle.manifest.yaml`, `agent-coordinator/evaluation/gen_eval/manifests/memory-crud.manifest.yaml`, `agent-coordinator/evaluation/gen_eval/manifests/work-queue.manifest.yaml`, `agent-coordinator/evaluation/gen_eval/manifests/auth-boundary.manifest.yaml`, `agent-coordinator/evaluation/gen_eval/manifests/handoffs.manifest.yaml`, `agent-coordinator/evaluation/gen_eval/manifests/cross-interface.manifest.yaml`
  **Spec scenarios**: gen-eval-framework (Scenario Pack Manifest): Manifest validates public vs holdout
  **Design decisions**: D6
  **Dependencies**: 4.2, 5.2, 5.3, 5.4, 5.5

## Phase 6: Report and Feedback Integration

- [ ] 6.1 Write tests for side-effect sub-verdict reporting, semantic confidence in reports, and updated feedback synthesis
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_reports_extended.py`, `agent-coordinator/tests/test_evaluation/test_gen_eval/test_feedback_extended.py`
  **Spec scenarios**: Cross-phase integration coverage
  **Dependencies**: 2.2, 3.2

- [ ] 6.2 Update reports.py to include side-effect verdicts, semantic confidence scores, and visibility groups
  **Files**: `agent-coordinator/evaluation/gen_eval/reports.py`
  **Spec scenarios**: Cross-phase integration coverage
  **Dependencies**: 6.1, 4.4

- [ ] 6.3 Update feedback.py to incorporate side-effect failures and semantic evaluation gaps into suggested focus areas
  **Files**: `agent-coordinator/evaluation/gen_eval/feedback.py`
  **Spec scenarios**: Cross-phase integration coverage
  **Dependencies**: 6.1

## Phase 7: Integration and Validation

- [ ] 7.1 Run full integration test: extended assertions + side effects + semantic eval + manifests against live services
  **Files**: `agent-coordinator/tests/test_evaluation/test_gen_eval/test_integration_extended.py`
  **Spec scenarios**: Cross-phase end-to-end validation
  **Dependencies**: 1.3, 2.4, 3.4, 4.4, 5.6, 6.2, 6.3
