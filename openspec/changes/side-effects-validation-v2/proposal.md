# Proposal: Side-Effects Validation for Gen-Eval Framework (v2)

**Change ID**: `side-effects-validation-v2`
**Status**: Draft
**Created**: 2026-04-10
**Predecessor**: `add-side-effects-validation` (PR #72, abandoned due to merge conflicts)

## Why

The gen-eval framework currently validates HTTP status codes, CLI exit codes, response body fields (via JSONPath), database row counts/values, cross-interface consistency, and error message substrings. This covers basic correctness validation but falls short of simulating real user scenarios for three reasons:

1. **The assertion model is incomplete.** Scenario YAMLs already use `body_contains`, `body_excludes`, and `status_one_of` assertions informally, but these are not formalized in the `ExpectBlock` Pydantic model. They are not validated, documented, or uniformly supported by the evaluator.

2. **No declarative side-effect validation pattern exists.** Verifying that an operation produced the correct side effects (audit trail entries, state transitions, downstream writes) requires ad-hoc multi-step DB queries. There is no reusable pattern for declaring "this operation MUST produce these side effects and MUST NOT produce those others."

3. **No semantic evaluation exists.** Fuzzy operations like search, summarization, and recommendation cannot be validated beyond structural checks. An LLM-as-judge capability would enable validating functional correctness for these operations.

Additionally, the monolithic `manifests/manifest.yaml` (97 entries, 584 lines) creates merge conflicts when multiple agents add scenarios. Splitting into per-category manifests and consolidating the `ManifestEntry`/`ScenarioPackManifest` models (currently duplicated in both `models.py` and `manifest.py`) improves maintainability.

This is a clean re-plan of PR #72 (`add-side-effects-validation`), which accumulated irreconcilable conflicts with main after significant codebase evolution. All design decisions (D1-D7) from the original proposal remain valid; the implementation is rebased onto the current codebase and split into 3 independently mergeable PRs to reduce conflict risk.

## What Changes

### Feature 1: Formalize Extended Assertion Types

Add `body_contains`, `body_excludes`, `status_one_of`, `rows_gte`, `rows_lte`, and `array_contains` to the `ExpectBlock` Pydantic model and implement them in the evaluator's `_compare()` method.

- `body_contains`: Deep recursive subset matching on response body
- `body_excludes`: Negative assertion -- body must NOT contain these fields/values
- `status_one_of`: Accept multiple valid status codes (e.g., `[200, 201]`), mutually exclusive with `status`
- `rows_gte` / `rows_lte`: Range assertions for DB row counts
- `array_contains`: Assert a response array has an element matching specified field criteria

### Feature 2: Side-Effect Declaration and Verification

Introduce a declarative `side_effects` block on `ActionStep` with `verify` (must succeed) and `prohibit` (must not match) sub-steps. The evaluator automatically executes verification steps after the main step.

- `verify` steps confirm expected mutations occurred
- `prohibit` steps use inverse matching (D3): if expectations MATCH, the prohibit step FAILS
- Both skip if the main step failed
- `step_start_time` auto-injected for time-range DB queries

### Feature 3: Semantic Evaluation with LLM-as-Judge

Add `SemanticBlock` on `ActionStep` and `semantic_judge.py` module. Semantic verdicts are additive (D4): they enhance but never override structural verdicts. When LLM is unavailable, produces `skip` not `failure`.

### Feature 4: Scenario Pack Restructuring

- Split monolithic `manifests/manifest.yaml` into per-category manifest files
- Consolidate `ManifestEntry`/`ScenarioPackManifest` into `manifest.py` only (remove from `models.py`)

### Feature 5: End-to-End User Scenario Templates

Create 5 E2E scenario templates demonstrating all new assertion and side-effect capabilities:
- Memory lifecycle (store -> search -> verify correctness -> verify audit -> verify no unintended writes)
- Lock-task workflow (acquire -> submit -> claim -> complete -> verify state transitions)
- Policy enforcement (denied -> verify no side effects -> escalate -> verify correct side effects)
- Handoff integrity (write -> read from different agent -> verify audit)
- Cross-interface consistency (HTTP -> MCP -> CLI -> DB state verification)

### Feature 6: Report and Feedback Integration

Extend reports with side-effect sub-verdicts and semantic confidence scores. Extend feedback synthesis to surface side-effect failures and semantic evaluation gaps as suggested focus areas.

## Impact

Affected capability spec: **`gen-eval-framework`** (delta at `openspec/changes/side-effects-validation-v2/specs/gen-eval-framework/spec.md`)

Expected repository impact:
- `models.py`: +6 fields on ExpectBlock, +4 new model classes (SideEffectStep, SideEffectsBlock, SemanticBlock, SideEffectVerdict, SemanticVerdict), model consolidation
- `evaluator.py`: +5 new methods (~350 lines) for assertion matching, side-effect execution, semantic evaluation
- `semantic_judge.py`: New module (~110 lines) for LLM-as-judge via CLI
- `manifest.py`: Minor updates for consolidated model imports
- `reports.py`, `feedback.py`, `generator.py`: Extended for new signals
- `manifests/`: 12 per-category files replacing 1 monolithic file
- `scenarios/`: 5 new E2E scenario templates
- 8 new test files (~1,900 lines)

## Approaches Considered

### Approach A: Assertion-First -- Extend ExpectBlock + Evaluator (Recommended)

**Description**: Enrich the assertion layer within the existing step-based execution model. Add extended assertions to ExpectBlock, `side_effects`/`semantic` blocks to ActionStep, and compose verdicts with sub-verdicts.

**Pros**:
- Builds on existing evaluator architecture -- no new execution model
- Scenario authors use the same YAML format they already know
- Side-effect verification becomes first-class with its own reporting
- Backward compatible -- all existing scenarios remain valid

**Cons**:
- ExpectBlock grows from 8 to 14 fields
- ActionStep gains two new optional blocks (side_effects, semantic)

**Effort**: L

### Approach B: Plugin Architecture -- Pluggable Validators

**Description**: Introduce a plugin system where validators are registered by type (structural, semantic, side-effect). Each plugin receives step results and returns sub-verdicts.

**Pros**:
- Clean separation of concerns per validation type
- Easy to add new validation types without modifying core models

**Cons**:
- Over-engineers for current scale (1 project using gen-eval)
- Plugin discovery and configuration add complexity
- Scenario YAML needs different syntax to reference plugins

**Effort**: L

### Approach C: Pre/Post Hooks Instead of Inline Side-Effects

**Description**: Add scenario-level `preconditions`/`postconditions` blocks instead of per-step side-effect declarations.

**Pros**:
- Cleaner separation between user actions and verification

**Cons**:
- Cannot verify side effects of individual steps -- only final state
- Loses intermediate state transition verification (dealbreaker for multi-step scenarios)
- Doesn't address assertion gaps or semantic validation

**Effort**: M

### Selected Approach

**Approach A: Assertion-First** -- selected because the gen-eval framework already has the right execution model. The gap is in the assertion layer, not the execution architecture. Enriching ExpectBlock and adding `side_effects`/`semantic` blocks keeps the model familiar while making side-effect validation declarative and first-class.

Approach B deferred to a future change if the validator set grows beyond 3-4 types.
Approach C rejected -- inability to verify intermediate state transitions is a dealbreaker.

## Delivery Strategy

Split into 3 independently mergeable PRs to reduce conflict risk:

1. **PR 1 (wp-assertions-sideeffects)**: Extended assertions + side-effect verification + model consolidation
2. **PR 2 (wp-semantic-packs)**: Semantic evaluation + scenario pack restructuring + report/feedback extensions
3. **PR 3 (wp-e2e-templates)**: E2E scenario templates + integration tests

Each PR is self-contained and testable independently. PR 2 depends on PR 1; PR 3 depends on PR 2.

## Dependencies

- Existing `gen-eval-framework` implementation (models, evaluator, orchestrator, clients)
- Existing `use_llm_judgment` flag and CLI integration
- `claude --print` CLI for semantic evaluation (graceful degradation when unavailable)

## Risks

- **Semantic evaluation non-determinism**: Mitigated by confidence thresholds, optional blocks, and deterministic fallback when LLM unavailable.
- **Side-effect verification overhead**: Mitigated by optional blocks and skip-on-failure behavior.
- **Model complexity growth**: Mitigated by Pydantic validation and logical field grouping.
- **Repeat merge conflicts**: Mitigated by 3-PR split strategy -- each PR has a small, focused diff.
