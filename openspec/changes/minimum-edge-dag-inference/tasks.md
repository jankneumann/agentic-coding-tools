# Tasks: Minimum-Edge DAG Inference for `plan-roadmap`

Change-id: `minimum-edge-dag-inference`
Branch: `claude/optimize-dependency-graph-32iPY` (operator override)

## Phase 1: Schema and shared overlap primitive

- [ ] 1.1 Write tests for `scope_overlap` module — deterministic overlap primitives
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.deterministic-write-overlap, roadmap-orchestration.min-edge-dag.deterministic-lock-overlap, roadmap-orchestration.min-edge-dag.read-after-write
  **Contracts**: `openspec/changes/minimum-edge-dag-inference/contracts/README.md` (no contract artifacts; pure library change)
  **Design decisions**: D3 (extract scope-overlap), D6 (deterministic is crisp)
  **Dependencies**: None
  **Files**: `skills/tests/roadmap-runtime/test_scope_overlap.py` (new)

- [ ] 1.2 Extract `scope_overlap.py` from `validate_work_packages.py`
  **Design decisions**: D3
  **Dependencies**: 1.1
  **Files**: `skills/roadmap-runtime/scripts/scope_overlap.py` (new). Move `_glob_conflict`, `_lock_conflict` (and helpers) from `skills/validate-packages/scripts/validate_work_packages.py`; update the validator to import from the new module. Behavior must be byte-identical — guarded by existing `skills/tests/validate-packages/` tests.

- [ ] 1.3 Write tests for `roadmap.schema.json` scope acceptance and malformed-lock rejection
  **Spec scenarios**: roadmap-orchestration.roadmap-item-scope.accept-with-scope, .accept-without-scope, .reject-malformed-lock-keys
  **Dependencies**: None
  **Files**: `skills/tests/plan-roadmap/test_schema_scope.py` (new)

- [ ] 1.4 Extend `openspec/schemas/roadmap.schema.json` with optional `scope` object
  **Spec scenarios**: roadmap-orchestration.roadmap-item-scope.*
  **Design decisions**: D2 (optional), D7 (backward-compat loader)
  **Dependencies**: 1.3
  **Files**: `openspec/schemas/roadmap.schema.json`

## Phase 2: Edge record structure

- [ ] 2.1 Write tests for `DepEdge` dataclass + legacy-shape loader
  **Spec scenarios**: roadmap-orchestration.edge-rationale.records-source, .records-rationale, .llm-includes-confidence, .operator-explicit-preserved
  **Design decisions**: D7
  **Dependencies**: None
  **Files**: `skills/tests/roadmap-runtime/test_dep_edge.py` (new)

- [ ] 2.2 Introduce `DepEdge` dataclass in `roadmap-runtime/models.py` with legacy-shape loader
  **Spec scenarios**: roadmap-orchestration.edge-rationale.*
  **Design decisions**: D7
  **Dependencies**: 2.1
  **Files**: `skills/roadmap-runtime/scripts/models.py` (modify `RoadmapItem.depends_on` union type + normalizer)

## Phase 3: Tier A deterministic inference

- [ ] 3.1 Write tests for Tier A in `decomposer.build_dependency_dag`
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.deterministic-write-overlap, .deterministic-lock-overlap, .read-after-write, .no-deterministic-edge-when-no-overlap, .split-edges-remain-deterministic
  **Design decisions**: D1, D3, D6
  **Dependencies**: 1.2, 2.2
  **Files**: `skills/tests/plan-roadmap/test_decomposer.py` (add `TestTierADeterministic` class)

- [ ] 3.2 Rewrite `build_dependency_dag` to route through Tier A first
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.deterministic-*, .no-deterministic-edge-when-no-overlap
  **Design decisions**: D1, D3
  **Dependencies**: 3.1
  **Files**: `skills/plan-roadmap/scripts/decomposer.py` (replace `build_dependency_dag` body; delete old Rule 1 and Rule 2 after Tier B lands in Phase 5)

- [ ] 3.3 Write benchmark fixtures recording expected Tier A edge counts
  **Spec scenarios**: regression guard
  **Design decisions**: D1 (edge-count reduction is a success metric)
  **Dependencies**: 3.2
  **Files**: `skills/tests/plan-roadmap/fixtures/tier_a_bench_*.yaml` (3 fixtures: all-scoped, partial-scoped, no-scope), `skills/tests/plan-roadmap/test_tier_a_bench.py` (asserts edge counts)

## Phase 4: Tier B-0 cheap pruning

- [ ] 4.1 Write tests for pruning rules (transitive closure, disjoint sections, noun-phrase intersection)
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.cheap-pruning
  **Design decisions**: D5 (pruning is cost guard, not inference)
  **Dependencies**: None
  **Files**: `skills/tests/plan-roadmap/test_tier_b0_pruning.py` (new)

- [ ] 4.2 Implement `_tier_b0_can_prune(a, b, tier_a_edges)`
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.cheap-pruning
  **Design decisions**: D5
  **Dependencies**: 4.1
  **Files**: `skills/plan-roadmap/scripts/decomposer.py`

## Phase 5: Tier B LLM analyst dispatch

- [ ] 5.1 Write tests for Tier B with a mocked analyst (contract-level, not model-behavior)
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.llm-semantic-inference, .conservative-fallback-under-uncertainty
  **Design decisions**: D4 (analyst archetype), D6 (conservative policy)
  **Dependencies**: 3.2, 4.2
  **Files**: `skills/tests/plan-roadmap/test_tier_b_dispatch.py` (new). Mock patches `_dispatch_tier_b` to return canned verdicts; tests assert edges correctly reflect verdicts and conservative policy kicks in on `unclear`/`low`.

- [ ] 5.2 Implement `_dispatch_tier_b(pairs, proposal_sections) -> list[Verdict]`
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.llm-semantic-inference
  **Design decisions**: D4
  **Dependencies**: 5.1
  **Files**: `skills/plan-roadmap/scripts/decomposer.py` (new function); imports analyst archetype from `src.agents_config` with `resolve_model(analyst, {})`.

- [ ] 5.3 Implement `_apply_verdict(verdict)` with conservative policy
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.conservative-fallback-under-uncertainty
  **Design decisions**: D6
  **Dependencies**: 5.2
  **Files**: `skills/plan-roadmap/scripts/decomposer.py`

- [ ] 5.4 Write tests for Tier B caching + batching + ceiling
  **Spec scenarios**: roadmap-orchestration.llm-cost-controls.cached-by-hash, .batched-into-single-call, .hard-ceiling
  **Design decisions**: D4
  **Dependencies**: 5.2
  **Files**: `skills/tests/plan-roadmap/test_tier_b_cost_controls.py` (new)

- [ ] 5.5 Implement cache layer at `.cache/plan-roadmap/dep-inference/<hash>.json`
  **Spec scenarios**: roadmap-orchestration.llm-cost-controls.cached-by-hash
  **Design decisions**: D4
  **Dependencies**: 5.4
  **Files**: `skills/plan-roadmap/scripts/decomposer.py` + cache helper module if it grows (`skills/plan-roadmap/scripts/dep_cache.py`)

- [ ] 5.6 Implement batching (K=10 configurable) and hard ceiling (default 50 pairs)
  **Spec scenarios**: roadmap-orchestration.llm-cost-controls.batched-into-single-call, .hard-ceiling
  **Design decisions**: D4
  **Dependencies**: 5.5
  **Files**: `skills/plan-roadmap/scripts/decomposer.py`

## Phase 6: Cycle resolution and integration

- [ ] 6.1 Write tests for LLM-edge-preferring cycle breaker
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.dag-acyclicity-preserved
  **Design decisions**: D8
  **Dependencies**: 5.3
  **Files**: `skills/tests/plan-roadmap/test_cycle_breaker.py` (new or extend existing)

- [ ] 6.2 Update `_break_cycles` to prefer removing lowest-confidence LLM edges
  **Spec scenarios**: roadmap-orchestration.min-edge-dag.dag-acyclicity-preserved
  **Design decisions**: D8
  **Dependencies**: 6.1
  **Files**: `skills/plan-roadmap/scripts/decomposer.py`

- [ ] 6.3 Remove legacy Rule 1 (infra-first unconditional) and Rule 2 (keyword overlap) from `build_dependency_dag`
  **Design decisions**: D1 (replaced by Tier A + B), rationale captured in `docs/lessons-learned.md`
  **Dependencies**: 3.2, 5.3, 6.2
  **Files**: `skills/plan-roadmap/scripts/decomposer.py`. Delete `_infra_ids` inference block and keyword-overlap loop; Tier A + B fully subsume them. Rule 3 (split chains) is preserved per D9.

- [ ] 6.4 Update existing `TestBuildDependencyDag` tests
  **Dependencies**: 6.3
  **Files**: `skills/tests/plan-roadmap/test_decomposer.py`. Legacy tests assert "infra items become deps" and "keyword overlap creates edges" — rewrite to reflect Tier A/B contract, keeping regression coverage for cycle freedom and explicit-dep preservation.

## Phase 7: Documentation and lessons-learned

- [ ] 7.1 Update `skills/plan-roadmap/SKILL.md` with scope field + two-tier inference model
  **Dependencies**: 6.3
  **Files**: `skills/plan-roadmap/SKILL.md`

- [ ] 7.2 Append "deterministic-where-crisp / LLM-where-semantic" pattern to `docs/lessons-learned.md`
  **Dependencies**: 6.3
  **Files**: `docs/lessons-learned.md`

- [ ] 7.3 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to sync runtime copies
  **Dependencies**: 7.1, 7.2
  **Files**: regenerates `.claude/skills/plan-roadmap/`, `.agents/skills/plan-roadmap/`

## Phase 8: Full validation

- [ ] 8.1 `openspec validate minimum-edge-dag-inference --strict`
  **Dependencies**: all specs finalized

- [ ] 8.2 Run `skills/.venv/bin/python -m pytest skills/tests/plan-roadmap/ skills/tests/roadmap-runtime/ skills/tests/validate-packages/`
  **Dependencies**: all implementation tasks; validate-packages tests catch D3 extraction regressions

- [ ] 8.3 Run benchmark fixtures assertion (3.3) and confirm edge-count reduction on Tier A fixtures
  **Dependencies**: 3.3, 6.3

## Dependency graph summary

```
1.1 ── 1.2
1.3 ── 1.4
2.1 ── 2.2
1.2, 2.2 → 3.1 → 3.2 → 3.3
4.1 → 4.2
3.2, 4.2 → 5.1 → 5.2 → 5.3
5.2 → 5.4 → 5.5 → 5.6
5.3 → 6.1 → 6.2
3.2, 5.3, 6.2 → 6.3 → 6.4
6.3 → 7.1, 7.2 → 7.3
all → 8.1, 8.2, 8.3
```

Phases 1 and 2 are independent and can start in parallel. Phase 4 (Tier B-0 pruning) is independent of Phases 1/2 for tests but its implementation (4.2) must land before 5.x tests are meaningful end-to-end.
