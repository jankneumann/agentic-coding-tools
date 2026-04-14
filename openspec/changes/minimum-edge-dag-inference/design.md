# Design: Minimum-Edge DAG Inference for `plan-roadmap`

## Context

`plan-roadmap` currently over-linearizes roadmaps via three text-based rules in `skills/plan-roadmap/scripts/decomposer.py::build_dependency_dag()`:

- **Rule 1 (lines 413-417)**: Unconditional infra→feature edges. Every non-infra item gets an edge to every infra item regardless of whether the feature actually touches that infra. Primary cause of edge-count blowup.
- **Rule 2 (lines 420-436)**: Keyword overlap on titles (≥2 unique non-common words + higher priority). Fragile for generic domain nouns.
- **Rule 3 (lines 377-379)**: Split chains. Part N depends on part N-1. Correct by construction.

Downstream consumer `autopilot-roadmap` selects ready items via `_get_ready_items()` (all deps completed), so every spurious edge reduces concurrency visibility.

## Design Principle

> Use determinism where input→output is crisp. Use LLM inference where ambiguity or semantic reasoning is required. Do not invent more elaborate rules to approximate a semantic question.

Applied to dependency inference:
- **Crisp**: declared scope overlap — globs intersect, lock-key sets intersect. Pure set/fnmatch logic, already proven in `skills/validate-packages/scripts/validate_work_packages.py::validate_scope_overlap` and `validate_lock_overlap`.
- **Semantic**: "does item B's work technically depend on item A's work?" — requires reading descriptions, understanding architecture, inferring coupling. This is analyst-archetype LLM territory.

## Architecture

### D1. Two-tier pipeline with deterministic cost guard

```
build_dependency_dag(items, proposal_context)
│
├─ preserve_explicit_edges(items)                      # source: "explicit"
├─ preserve_split_chains(items)                        # source: "split"
│
├─ FOR each pair (a, b):
│   │
│   ├─ IF pair ∈ explicit_or_split: continue
│   │
│   ├─ IF a.scope AND b.scope:                         # Tier A
│   │     overlap = deterministic_overlap(a, b)
│   │     IF overlap: add_edge(source="deterministic", rationale=overlap.desc)
│   │     # No Tier B — Tier A is authoritative when both scoped
│   │     continue
│   │
│   ├─ IF tier_b0_can_prune(a, b, existing_edges):     # Tier B-0 cost guard
│   │     continue
│   │
│   └─ queue_for_tier_b(a, b)                          # Tier B batch
│
├─ batched_llm_verdicts = analyst_dispatch(queue)      # Batched, cached
│
└─ FOR each verdict:
    apply_conservative_policy(verdict)                 # unclear|low → keep edge
```

### D2. Scope declaration on `RoadmapItem`

Schema additions to `openspec/schemas/roadmap.schema.json`:

```json
{
  "scope": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "write_allow": { "type": "array", "items": { "type": "string" } },
      "read_allow":  { "type": "array", "items": { "type": "string" } },
      "lock_keys":   {
        "type": "array",
        "items": {
          "type": "string",
          "pattern": "^(api|db|event|flag|env|contract|feature):.+$"
        }
      }
    }
  }
}
```

All three subfields optional. Absence of `scope` routes the item through Tier B on all its pairs.

### D3. Deterministic overlap primitives (Tier A)

Reuse from `skills/validate-packages/scripts/validate_work_packages.py`:

- `_glob_conflict(globs_a, globs_b) -> list[tuple]` — `fnmatch`-based pairwise intersection
- `_lock_conflict(keys_a, keys_b) -> set` — canonicalized set intersection

Wrap these in a `roadmap-runtime` module `skills/roadmap-runtime/scripts/scope_overlap.py` so both `validate_work_packages.py` and `decomposer.py` share a single implementation. Extract-don't-copy — the existing logic is the contract.

### D4. Analyst dispatch (Tier B)

Single entry point `decomposer._dispatch_tier_b(pairs, proposal_sections)`:

- Resolves analyst archetype via `src.agents_config.resolve_model(analyst, {})` (same pattern as `plan-feature` step 2)
- Prompts with JSON-schema-constrained output (`depends_on`, `rationale`, `confidence`)
- Batches up to K=10 pairs per dispatch (configurable via `plan_roadmap.tier_b_batch_size`)
- Caches verdicts under `.cache/plan-roadmap/dep-inference/<hash>.json`

**Cache key**: `sha256(sorted([content_hash(a), content_hash(b)]))` where `content_hash(item)` is `sha256(item.title + "\n" + item.description)`. Pair is order-independent; content change invalidates cache.

### D5. Tier B-0 cheap pruning rules

Pruning does NOT add edges; it only skips LLM dispatch. Rules:

1. **Transitive closure**: if `(a → … → b)` already exists in Tier A edges, skip.
2. **Disjoint parent sections**: if `a.parent_section != b.parent_section` AND title-noun-phrase intersection is empty, skip.
3. **Explicit no-dep**: if either item has `scope` declared AND no overlap was found in Tier A, skip (Tier A is authoritative for fully-scoped pairs — handled upstream, listed here for completeness).

Noun-phrase extraction: simple regex `\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b` + lowercase noun tokens of length ≥4. Deterministic — no NLP model needed for this pruning step.

### D6. Conservative policy under uncertainty

Explicitly encoded in `_apply_verdict()`:

```python
if verdict.depends_on == "yes":        add_edge
elif verdict.depends_on == "no"   and verdict.confidence in ("medium","high"): skip
else:                                  add_edge(rationale=f"conservative-fallback: {verdict.depends_on}/{verdict.confidence}")
```

The "no + low-confidence" case keeps the edge. This directly implements the Gate-1 discovery answer.

### D7. Edge record structure

`RoadmapItem.depends_on` transitions from `list[str]` to `list[DepEdge]` where:

```python
@dataclass
class DepEdge:
    id: str                                      # target item_id
    source: Literal["deterministic","llm","split","explicit"]
    rationale: str
    confidence: Literal["low","medium","high"] | None = None  # LLM only
```

Backward compat: `roadmap.yaml` loader accepts both the legacy `depends_on: [<id>, ...]` and the new `depends_on: [{id, source, rationale, ...}, ...]`. Legacy shape is auto-normalized to `source: "explicit", rationale: "legacy"`.

### D8. Cycle-breaking update

`_break_cycles()` prefers removing lowest-confidence LLM edges first (they're the ones most likely to be wrong). Fallback to existing DFS back-edge removal when all remaining edges are deterministic or explicit.

### D9. Non-goals

- **No auto-inference of `scope`**. Users/skill authors declare it. An LLM-inferred `scope` would re-introduce the flakiness we're removing.
- **Not changing `autopilot-roadmap`'s execution model**. The DAG becomes more accurate; the executor still picks one ready item at a time.
- **Not changing the proposal→roadmap decomposition algorithm** (`decompose()` at `decomposer.py`), only the dependency-edge subroutine called at the end.

## Key Decisions

- **D1**: Two-tier over single-tier. Ship both because each covers the other's blind spot — pure determinism fails on undeclared scope; pure LLM wastes calls when scope IS declared. Directly reflects the design principle.
- **D2**: Optional `scope` rather than required. Required would make the skill unusable on unscoped proposals; optional keeps current ergonomics while rewarding users who invest in scope for precise DAGs.
- **D3**: Extract scope-overlap into `roadmap-runtime/scope_overlap.py` rather than duplicate. One conflict-model mental model across roadmap and work-package layers.
- **D5**: Pruning is deterministic and minimal. It's a *cost* guard, not an *inference* rule — explicitly called out to avoid drift back into "clever rules" territory.
- **D6**: Conservative-on-uncertainty applies to LLM verdicts only. Deterministic non-overlap is crisp and trusted.
- **D7**: Breaking change to `DepEdge` shape is acceptable because loader accepts both forms. Archived roadmaps stay readable.
- **D8**: LLM edges are preferentially broken during cycle resolution because they're the softer signal. Deterministic edges reflect actual file conflicts and should rarely be removed.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| LLM cost at scale (N² pairs on large roadmaps) | Tier B-0 pruning + batching (K=10) + caching + hard ceiling (default 50 pairs) with warning |
| Non-deterministic edge sets across runs | Cache keyed on content hash; identical inputs produce identical edges |
| Schema migration breaks archived roadmaps | `scope` optional; `depends_on` loader accepts legacy `list[str]` form |
| Analyst returns malformed JSON | Validate against schema; on parse failure treat as `{depends_on:"unclear", confidence:"low"}` (conservative fallback keeps edge) |
| `roadmap-runtime` module extraction breaks `validate_work_packages.py` | Covered by existing `skills/tests/` — CI fails loudly if the extraction changes behavior |
