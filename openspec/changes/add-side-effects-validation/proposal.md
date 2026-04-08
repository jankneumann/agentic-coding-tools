# Proposal: Side-Effects Validation for Gen-Eval Framework

**Change ID**: `add-side-effects-validation`
**Status**: Draft
**Created**: 2026-04-08

## Why

The gen-eval framework currently validates HTTP status codes, CLI exit codes, response body fields (via JSONPath), database row counts/values, cross-interface consistency (overlapping field names), and error message substrings. This covers a significant portion of correctness validation, but falls short of simulating real user scenarios for three reasons:

1. **The assertion model is incomplete**. Scenario YAMLs already use `body_contains`, `body_excludes`, and `status_one_of` assertions that are not formalized in the `ExpectBlock` Pydantic model. These assertions work informally in some scenarios but are not validated, documented, or uniformly supported by the evaluator.

2. **No collection or semantic assertions exist**. A memory search returning 3 results cannot be validated for correctness beyond "not empty" or exact field match. There is no way to assert "the response array contains an item matching these criteria" or "the returned content is semantically relevant to the query." Full user scenario simulation requires both structural collection assertions and optional LLM-as-judge semantic evaluation.

3. **No declarative side-effect validation pattern exists**. Verifying that an operation produced the correct side effects (audit trail entries, state transitions, downstream writes) requires ad-hoc multi-step DB queries. There is no reusable pattern for declaring "this operation MUST produce these side effects and MUST NOT produce these others" — the scenario author must manually build the verification steps every time.

4. **Scenario pack management and multi-source bootstrapping are not yet implemented**. The `add-software-factory-tooling` proposal (Draft, 0/13 tasks completed) identified scenario pack manifests, visibility-aware filtering (public vs holdout), and multi-source scenario bootstrapping as needed capabilities. These are absorbed into this proposal since they directly enable richer side-effect validation workflows.

## What Changes

### Feature 1: Formalize Extended Assertion Types

Add `body_contains`, `body_excludes`, `status_one_of`, `rows_gte`, `rows_lte`, and `array_contains` to the `ExpectBlock` Pydantic model and implement them in the evaluator's `_compare()` method.

- `body_contains`: Deep partial matching — assert that expected structure exists within response body (supports nested dicts and arrays)
- `body_excludes`: Negative assertion — assert that a structure does NOT appear in the response
- `status_one_of`: Accept multiple valid status codes (e.g., `[200, 201]`)
- `rows_gte` / `rows_lte`: Range assertions for DB row counts (e.g., "at least 3 results")
- `array_contains`: Assert that a response array contains at least one item matching specified field criteria

### Feature 2: Side-Effect Declaration and Verification

Introduce a declarative `side_effects` block on `ActionStep` that specifies expected and prohibited side effects after a step executes. The evaluator automatically generates verification queries/requests.

```yaml
steps:
  - id: search_memories
    transport: http
    method: POST
    endpoint: /memory/query
    body:
      tags: ["project-deadlines"]
      limit: 10
    expect:
      status: 200
      not_empty: true
      array_contains:
        path: "$.memories"
        match:
          tags: ["project-deadlines"]
    side_effects:
      verify:
        - transport: db
          sql: "SELECT COUNT(*) as cnt FROM audit_log WHERE operation = 'memory_query' AND agent_id = '{{ agent_id }}'"
          expect:
            row:
              cnt: 1
      prohibit:
        - transport: db
          sql: "SELECT COUNT(*) as cnt FROM memory_episodic WHERE created_at > '{{ step_start_time }}'"
          expect:
            rows: 0
```

The `side_effects.verify` steps confirm expected mutations occurred. The `side_effects.prohibit` steps confirm that no unintended mutations happened. Both are auto-executed after the main step and reported as sub-verdicts.

### Feature 3: Semantic Evaluation with LLM-as-Judge

Extend the existing `use_llm_judgment` flag to support structured semantic assertions:

```yaml
steps:
  - id: search_memories
    transport: http
    method: POST
    endpoint: /memory/query
    body:
      query: "What were the project deadline decisions?"
    expect:
      status: 200
      not_empty: true
    semantic:
      judge: true
      criteria: "The returned memories should be relevant to project deadline decisions"
      min_confidence: 0.7
      fields:
        - "$.memories[*].summary"
```

The `semantic` block invokes the existing LLM judgment pathway (`claude --print`) with structured criteria and confidence thresholds. This enables validating functional correctness for fuzzy operations like search, summarization, and recommendation.

### Feature 4: Scenario Pack Management (absorbed from add-software-factory-tooling)

Introduce scenario-pack manifests with visibility metadata (`public` vs `holdout`), provenance tracking (`spec`, `contract`, `incident`, `archive`, `manual`), and visibility-aware filtering in gen-eval execution.

- Manifest model with validation for visibility, source, determinism, ownership
- Visibility-aware scenario filtering: implementation runs see `public` only, cleanup/validation gates see both
- Visibility-grouped reporting (pass/fail counts per visibility bucket)
- Multi-source scenario bootstrap from spec deltas, contracts, incidents, and archived exemplars

### Feature 5: End-to-End User Scenario Templates

Create reusable scenario templates for common multi-step user journeys:

- **Memory lifecycle**: Store memories with tags -> search by various criteria -> verify returned results match (structural + semantic) -> verify audit trail -> verify no unintended writes
- **Lock-task workflow**: Acquire lock -> submit task -> claim task -> complete task -> verify state transitions at each step -> verify audit trail consistency -> cleanup
- **Policy enforcement**: Attempt operation with insufficient permissions -> verify denial -> verify no side effects occurred -> escalate permissions -> retry -> verify success + correct side effects
- **Handoff integrity**: Write handoff document -> read from different agent -> verify content matches -> verify audit trail records both operations
- **Cross-interface consistency**: Perform operation via HTTP -> verify same state via MCP -> verify same state via CLI -> verify same state via DB

## Impact

Affected capability specs and planned delta files:

- **`gen-eval-framework`**: `openspec/changes/add-side-effects-validation/specs/gen-eval-framework/spec.md`

Expected repository impact:

- Extended `ExpectBlock` model with 6+ new assertion types
- New `side_effects` block on `ActionStep` for declarative verification
- New `semantic` block for LLM-as-judge evaluation
- Scenario pack manifest model and visibility-aware execution
- 5+ new end-to-end scenario templates demonstrating full user journeys
- Updated evaluator with collection matching, semantic judgment, and side-effect verification
- Updated reports with side-effect verdicts and semantic confidence scores

## Approaches Considered

### Approach A: Assertion-First — Extend ExpectBlock + Evaluator (Recommended)

**Description**: Focus on making the assertion layer rich enough to express any side-effect validation declaratively within the existing step-based model. Add `body_contains`, `body_excludes`, `status_one_of`, `array_contains`, `rows_gte/lte` to ExpectBlock. Add `side_effects` as a new block on ActionStep. Add `semantic` for LLM judgment. Absorb scenario pack management from add-software-factory-tooling. Create end-to-end scenario templates using the new assertions.

**Pros**:
- Builds on the existing evaluator architecture — no new execution model needed
- Scenario authors express side-effect expectations in the same YAML format they already know
- Formalization of informal assertions (body_contains etc.) fixes existing technical debt
- Side-effect verification becomes a first-class concept with its own reporting
- Scenario pack management enables structured test organization

**Cons**:
- The `side_effects` block adds complexity to the ActionStep model
- Semantic evaluation introduces LLM cost and non-determinism into the evaluation pipeline
- Absorbing software-factory-tooling features increases scope

**Effort**: L

### Approach B: Plugin Architecture — Pluggable Validators

**Description**: Instead of extending the core assertion model, introduce a plugin system where validators are registered by type (structural, semantic, side-effect, collection). Each plugin receives the step result and returns sub-verdicts. The evaluator orchestrates plugin execution.

**Pros**:
- Clean separation of concerns — each validation type is an independent module
- Easy to add new validation types without modifying core models
- Third-party projects could contribute custom validators

**Cons**:
- Over-engineers the problem for the current scale (1 project using gen-eval)
- Plugin discovery, registration, and configuration add complexity
- Scenario YAML would need a different syntax to reference plugins
- Harder for scenario authors to understand what validation is available

**Effort**: L

### Approach C: Scenario Composition — Pre/Post Hooks Instead of Inline Side-Effects

**Description**: Rather than adding side-effect declarations to individual steps, add scenario-level `preconditions` and `postconditions` blocks that run before/after the main step sequence. Preconditions establish known state, postconditions verify all side effects. Keep the step model unchanged.

**Pros**:
- Cleaner separation between "what the user does" (steps) and "what we verify" (postconditions)
- Precondition block could support write operations (INSERT test data) — something the current DB client can't do
- Simpler mental model: steps = user actions, postconditions = system verification

**Cons**:
- Cannot verify side effects of individual steps — only the final state after all steps complete
- Loses the ability to verify intermediate state transitions (e.g., "after claiming a task but before completing it, the status should be 'in_progress'")
- Precondition writes would require lifting the read-only DB client restriction
- Doesn't address the assertion gap (body_contains etc.) or semantic validation

**Effort**: M

### Selected Approach

**Approach A: Assertion-First** — selected because the gen-eval framework already has the right execution model (sequential steps with transport routing and variable capture). The gap is in the assertion layer, not the execution architecture. Enriching ExpectBlock and adding `side_effects`/`semantic` blocks to ActionStep keeps the model familiar to scenario authors while making side-effect validation declarative and first-class. The plugin approach (B) over-engineers for current scale, and the pre/post hook approach (C) loses intermediate state verification.

Approach B (Plugin Architecture) deferred to a future change if the validator set grows beyond 3-4 types.
Approach C (Pre/Post Hooks) rejected — inability to verify intermediate state transitions is a dealbreaker for multi-step user scenario simulation.

## Dependencies

- Existing `gen-eval-framework` implementation (models, evaluator, orchestrator, clients)
- Existing `use_llm_judgment` flag and CLI integration for semantic evaluation
- `add-software-factory-tooling` change (absorbed — its gen-eval-framework spec delta and scenario pack features are incorporated here)

## Risks

- **Semantic evaluation non-determinism**: LLM-as-judge produces non-deterministic results. Mitigation: confidence thresholds, optional `semantic` blocks (never required), and deterministic fallback when LLM unavailable.
- **Side-effect verification overhead**: Additional DB queries per step could slow evaluation. Mitigation: side_effects blocks are optional, parallel execution within a step's verification phase.
- **Model complexity growth**: ExpectBlock and ActionStep are getting larger. Mitigation: group new fields logically (assertion extensions vs side-effect declarations), validate with Pydantic to catch misuse early.
- **Scope creep from absorbed change**: Software-factory-tooling had 5 features across 13 tasks. Mitigation: only absorb Features 1 (scenario packs) and relevant parts of Feature 3 (validation-driven rework). DTU scaffold, archive intelligence, and dogfood features remain in the original proposal.
