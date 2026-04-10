# Design: Side-Effects Validation for Gen-Eval Framework (v2)

**Change ID**: `side-effects-validation-v2`

## Architecture Overview

This change extends the gen-eval framework's assertion and evaluation layers without modifying its execution model (sequential steps, transport routing, variable capture). The core architectural decision is: **enrich the data model, not the execution engine**.

```
+-----------------------------------------------------+
|                    Scenario YAML                     |
|  steps:                                              |
|    - expect: { body_contains, array_contains, ... }  |  <- Feature 1: Extended Assertions
|      side_effects: { verify: [...], prohibit: [...]} |  <- Feature 2: Side-Effect Declaration
|      semantic: { judge, criteria, confidence }       |  <- Feature 3: Semantic Evaluation
|  manifest: { visibility, source, determinism }       |  <- Feature 4: Scenario Packs
+---------------------------+--------------------------+
                            |
                            v
+-----------------------------------------------------+
|                    Evaluator                          |
|                                                       |
|  1. Capture step_start_time                           |
|  2. Execute main step via transport client            |
|  3. Compare result against ExpectBlock (extended)     |
|  4. If pass -> run side_effects.verify steps          |
|  5. Run side_effects.prohibit steps                   |
|  6. If semantic.judge -> invoke LLM judgment          |
|  7. Compose StepVerdict with sub-verdicts             |
+-----------------------------------------------------+
```

## Design Decisions

### D1: Extend ExpectBlock vs. Create New Assertion Model

**Decision**: Extend the existing `ExpectBlock` Pydantic model with new optional fields.

**Rationale**: Creating a separate `ExtendedExpectBlock` model would require changing all existing scenario YAML parsing and evaluator code. Since ExpectBlock is already the assertion contract, adding fields is simpler and backward-compatible. All existing scenarios remain valid.

**Trade-off**: ExpectBlock grows from 8 to 14 fields. Accepted because Pydantic validation keeps the model self-documenting, and all new fields are optional with clear names.

### D2: Side-Effects as ActionStep Sub-Block vs. Separate Steps

**Decision**: Side-effect declarations live inside the ActionStep that produces them, not as standalone steps.

**Rationale**: Co-location makes scenarios self-documenting ("this step SHOULD produce these effects and SHOULD NOT produce those") and enables the evaluator to report side-effect verdicts as sub-verdicts of the producing step.

**Alternative rejected**: Standalone `verify_side_effects` steps scattered through the scenario. Loses the declarative semantics and requires readers to mentally map verification steps back to producing steps.

### D3: Prohibit Semantics -- Inverse Matching

**Decision**: `side_effects.prohibit` steps use standard ExpectBlock assertions but invert the verdict. If expectations MATCH (the prohibited state exists), the prohibit step FAILS.

**Implementation**: The evaluator runs the prohibit step normally through `_compare()`. If `diff` is None (expectations matched), verdict is `fail` with "prohibited state detected". If `diff` is not None (expectations did NOT match), verdict is `pass`.

This avoids introducing a separate negative assertion syntax.

### D4: Semantic Evaluation Independence

**Decision**: Semantic verdicts are additive -- they enhance but never override structural verdicts.

**Rules**:
- If structural assertions fail -> semantic evaluation is skipped
- If structural assertions pass + semantic fails -> step fails
- If structural assertions pass + LLM unavailable -> semantic verdict is `skip`, step passes
- Semantic evaluation runs AFTER side-effect evaluation

This prevents LLM unavailability from causing false failures in CI.

### D5: body_contains Deep Matching Algorithm

**Decision**: Recursive subset matching:
- **Dict**: Every key in expected must exist in actual with a matching value (recursive)
- **List**: Every expected item must have a matching distinct actual item (order-independent, recursive for nested structures)
- **Scalar**: Direct equality

For list matching, each expected item must match a distinct actual item (no double-counting). O(n*m) but scenario lists are small (<20 items).

### D6: Per-Category Manifest Files

**Decision**: Split the monolithic `manifests/manifest.yaml` into per-category files (e.g., `manifests/lock-lifecycle.manifest.yaml`).

**Rationale**: Per-category manifests reduce merge conflicts when multiple agents add scenarios. The alternative (single manifest.yaml) was the source of conflicts in PR #72.

**Implementation**: The manifest loader (`load_manifests_from_dirs`) already supports loading from multiple files. The split requires updating the single-file loader path and creating individual files from the existing data.

### D7: Visibility Filtering Integration Point

**Decision**: Filtering happens in the generator, not the evaluator.

**Rationale**: The generator already filters by category, priority, and focus areas. Adding visibility as another filter dimension is natural. The evaluator remains agnostic to visibility -- it evaluates whatever scenarios it receives. This preserves evaluator independence (a core spec requirement).

### D8: Model Consolidation -- ManifestEntry in manifest.py Only

**Decision**: Remove `ManifestEntry` and `ScenarioPackManifest` from `models.py`, keep them only in `manifest.py`.

**Rationale**: These models are currently duplicated in both files. The manifest module is the logical home since it contains all manifest loading/filtering logic. Other modules that need these types will import from `manifest.py`.

**Impact**: Any code currently importing from `models.py` will need import path updates. Grep and fix all references.

## File Impact Summary

### PR 1: wp-assertions-sideeffects
| File | Change Type | Description |
|------|-------------|-------------|
| `models.py` | Modify | +6 ExpectBlock fields, +SideEffectStep, +SideEffectsBlock, +SideEffectVerdict, +SemanticBlock, +SemanticVerdict, remove ManifestEntry/ScenarioPackManifest |
| `evaluator.py` | Modify | +_deep_contains, +_compare_array_contains, +_execute_side_effects, +_run_side_effect_step. Extend _compare() for new assertions. |
| `manifest.py` | Modify | Ensure ManifestEntry/ScenarioPackManifest are the sole definitions |
| `test_extended_assertions.py` | New | Tests for all 6 extended assertion types |
| `test_side_effects.py` | New | Tests for verify, prohibit, skip-on-failure, step_start_time |

### PR 2: wp-semantic-packs
| File | Change Type | Description |
|------|-------------|-------------|
| `semantic_judge.py` | New | LLM-as-judge via CLI pathway |
| `evaluator.py` | Modify | +_evaluate_semantic, integrate into _execute_step() |
| `reports.py` | Modify | +side-effect sub-verdicts, +semantic confidence, +visibility groups |
| `feedback.py` | Modify | +side-effect failure focus areas, +semantic gap suggestions |
| `generator.py` | Modify | +visibility-aware filtering parameter |
| `manifests/` | Restructure | Split manifest.yaml into 12 per-category files |
| `test_semantic_eval.py` | New | Tests for semantic evaluation |
| `test_reports_extended.py` | New | Tests for extended reporting |
| `test_feedback_extended.py` | New | Tests for extended feedback |
| `test_manifest.py` | Modify | Update for per-category manifest loading |

### PR 3: wp-e2e-templates
| File | Change Type | Description |
|------|-------------|-------------|
| `scenarios/memory-crud/memory-lifecycle-e2e.yaml` | New | Memory lifecycle E2E template |
| `scenarios/work-queue/lock-task-workflow-e2e.yaml` | New | Lock-task workflow E2E template |
| `scenarios/auth-boundary/policy-enforcement-e2e.yaml` | New | Policy enforcement E2E template |
| `scenarios/handoffs/handoff-integrity-e2e.yaml` | New | Handoff integrity E2E template |
| `scenarios/cross-interface/full-consistency-e2e.yaml` | New | Cross-interface consistency E2E template |
| `manifests/*.manifest.yaml` | Modify | Add entries for new E2E scenarios |
| `test_e2e_templates.py` | New | Validate YAML structure and Pydantic compliance |
| `test_integration_extended.py` | New | Full integration test with all features |
