# Design: Side-Effects Validation for Gen-Eval Framework

**Change ID**: `add-side-effects-validation`

## Architecture Overview

This change extends the gen-eval framework's assertion and evaluation layers without modifying its execution model (sequential steps, transport routing, variable capture). The core architectural decision is: **enrich the data model, not the execution engine**.

```
┌─────────────────────────────────────────────────────┐
│                    Scenario YAML                     │
│  steps:                                              │
│    - expect: { body_contains, array_contains, ... }  │  ← Feature 1: Extended Assertions
│      side_effects: { verify: [...], prohibit: [...]} │  ← Feature 2: Side-Effect Declaration
│      semantic: { judge, criteria, confidence }       │  ← Feature 3: Semantic Evaluation
│  manifest: { visibility, source, determinism }       │  ← Feature 4: Scenario Packs
└─────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────┐
│                    Evaluator                          │
│                                                       │
│  1. Execute main step via transport client            │
│  2. Compare result against ExpectBlock (extended)     │
│  3. If pass → run side_effects.verify steps           │
│  4. Run side_effects.prohibit steps                   │
│  5. If semantic.judge → invoke LLM judgment           │
│  6. Compose StepVerdict with sub-verdicts             │
└─────────────────────────────────────────────────────┘
```

## Design Decisions

### D1: Extend ExpectBlock vs. Create New Assertion Model

**Decision**: Extend the existing `ExpectBlock` Pydantic model with new fields.

**Rationale**: The alternative — creating a separate `ExtendedExpectBlock` or `AssertionSet` model — would require changing all existing scenario YAML parsing and evaluator code to handle two models. Since ExpectBlock is already the assertion contract, adding fields is simpler and backward-compatible. All existing scenarios remain valid.

**Trade-off**: ExpectBlock grows from 7 to 13+ fields. Accepted because Pydantic validation keeps the model self-documenting, and fields are all optional with clear names.

### D2: Side-Effects as ActionStep Sub-Block vs. Separate Steps

**Decision**: Side-effect declarations live inside the ActionStep that produces them, not as standalone steps in the scenario.

**Rationale**: Scenario authors currently write manual DB verification steps after operations. The `side_effects` block makes the intent explicit: "this step SHOULD produce these effects and SHOULD NOT produce those." Keeping verification co-located with the producing step makes scenarios self-documenting and enables the evaluator to report side-effect verdicts as sub-verdicts of the producing step.

**Alternative rejected**: Standalone `verify_side_effects` steps scattered through the scenario. This is already possible today but loses the declarative "these are the expected side effects of this operation" semantics. Authors must mentally map verification steps back to the producing step.

### D3: Prohibit Semantics — Inverse Matching

**Decision**: `side_effects.prohibit` steps use standard ExpectBlock assertions but invert the verdict. If expectations MATCH, the prohibit step FAILS (the prohibited state exists).

**Implementation**: The evaluator runs the prohibit step normally through `_compare()`. If `diff` is None (expectations matched), the prohibit verdict is `fail` with reason "prohibited state detected". If `diff` is not None (expectations did NOT match), the prohibit verdict is `pass`.

This avoids introducing a separate "negative assertion" syntax — scenario authors use the same familiar assertion format but in a `prohibit` context.

### D4: Semantic Evaluation Independence

**Decision**: Semantic verdicts are additive — they enhance but never override structural verdicts.

**Rationale**: If `expect.status: 200` fails, the step fails regardless of semantic evaluation. If structural assertions pass but semantic evaluation fails, the step fails. If structural assertions pass and semantic evaluation is unavailable (LLM offline), the step passes with a `semantic_verdict: skip` warning.

This prevents LLM unavailability from causing false failures in CI while still providing semantic validation when available.

### D5: body_contains Deep Matching Algorithm

**Decision**: Recursive subset matching with the following rules:
- **Dict**: Expected dict matches actual dict if every key in expected exists in actual with a matching value (recursive).
- **List**: Expected list matches actual list if every item in expected has a matching item in actual (order-independent, recursive for nested structures).
- **Scalar**: Direct equality comparison.

**Implementation detail**: For list matching, each expected item must match a distinct actual item (no double-counting). This is O(n*m) but scenario lists are small (typically < 20 items).

### D6: Scenario Pack Manifest File Format

**Decision**: YAML manifest file co-located with scenario YAML files.

**Location**: `manifests/<category>.manifest.yaml` alongside `scenarios/<category>/` directories.

**Schema**:
```yaml
pack: lock-lifecycle
scenarios:
  - id: acquire-release
    visibility: public
    source: spec
    determinism: deterministic
    owner: gen-eval-testing
    promotion_status: approved
  - id: contention-holdout-1
    visibility: holdout
    source: manual
    determinism: deterministic
    owner: gen-eval-testing
    promotion_status: candidate
```

**Rationale**: YAML matches the scenario file format. Per-category manifests keep files focused. The alternative (single manifest.yaml for all scenarios) was rejected because it creates merge conflicts when multiple agents add scenarios in parallel.

### D7: Visibility Filtering Integration Point

**Decision**: Filtering happens in the generator, not the evaluator.

**Rationale**: The generator already filters by category, priority, and focus areas. Adding visibility as another filter dimension is natural. The evaluator remains agnostic to visibility — it evaluates whatever scenarios it receives. This preserves evaluator independence (a core spec requirement).

**Implementation**: The orchestrator passes `visibility_filter: "public"` or `visibility_filter: "all"` to the generator based on the execution context (implementation vs cleanup/validation).

## File Impact Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `models.py` | Modify | Add 6 fields to ExpectBlock, add `side_effects` and `semantic` blocks to ActionStep, add sub-verdict fields to StepVerdict |
| `evaluator.py` | Modify | Implement body_contains, body_excludes, status_one_of, rows_gte/lte, array_contains matching. Add side-effect execution loop. Add semantic judgment invocation. |
| `generator.py` | Modify | Add visibility-aware filtering from manifest |
| `descriptor.py` | Modify | Load scenario pack manifests |
| `reports.py` | Modify | Add visibility-grouped reporting, side-effect sub-verdicts, semantic confidence |
| `manifest.py` | New | Scenario pack manifest model and loader |
| `semantic_judge.py` | New | LLM-as-judge integration for semantic evaluation |
| `scenarios/` | New files | 5+ end-to-end user scenario templates |
| `manifests/` | New dir | Per-category manifest YAML files |
