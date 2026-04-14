# Session Log: minimum-edge-dag-inference

---

## Phase: Plan (2026-04-14)

**Agent**: claude_code | **Session**: N/A (coordinator transport disabled)

### Decisions

1. **Two-tier inference (deterministic-first + LLM-fallback)** — Apply the operator's principle "determinism where input→output is crisp, LLM where ambiguity demands semantic reasoning" at the algorithm boundary. Tier A uses `fnmatch`-based glob/lock overlap when both items declare `scope`; Tier B dispatches an analyst-archetype LLM per ambiguous pair.

2. **Optional scope fields on `RoadmapItem`** — Extend `roadmap.schema.json` with `scope.{write_allow, read_allow, lock_keys}` as optional. Absence routes the item through Tier B, not a validation error. Preserves backward compatibility with archived roadmaps.

3. **Rule 1 (infra-first unconditional) is the primary offender** — Confirmed via Explore agent survey of `decomposer.py:413-417`. The M×N edge blowup dominates text-heuristic over-linearization. Rule 2 (keyword overlap) is secondary; Rule 3 (split chains) is retained as deterministic-by-construction.

4. **Extract scope-overlap into `roadmap-runtime/scope_overlap.py`** — Reuse the tested primitives from `skills/validate-packages/scripts/validate_work_packages.py` rather than duplicate. One conflict-model mental model across roadmap and work-package layers.

5. **Edge records carry `source` + `rationale` + optional `confidence`** — `depends_on` transitions from `list[str]` to `list[DepEdge]` with backward-compat loader. Human-auditable output is a stated success-metric component.

6. **Conservative under LLM uncertainty** — "unclear" or low-confidence verdicts keep the edge, per operator's discovery-question answer that false negatives are worse than false positives.

7. **Sequential tier** — Coordinator unavailable (transport=none) and the feature is narrowly scoped to the `plan-roadmap` skill. Single `wp-main` package. Local-parallel decomposition not justified for this blast radius.

8. **Operator branch override honored** — The cloud harness pre-checked out `claude/optimize-dependency-graph-32iPY`. Worktree setup re-use attempted but the branch was already occupying the main checkout; planning proceeded directly in the main checkout without a separate worktree. Commits will push to the override branch.

### Alternatives Considered

- **Approach 2 (tighten heuristics only)**: rejected — layering stoplists and word-count thresholds approximates a semantic question with text patterns. Kept as a fallback contingency if Tier A schema change is controversial.
- **Approach 3 (require scope on every item)**: rejected — violates the design principle by demanding crisp data for an inherently semantic question when scope is unknown. Pushes work back to users that LLMs can do.

### Trade-offs

- Accepted **LLM latency + non-determinism on the Tier B path** over **continued rule-based flakiness**. Mitigations: batching (K=10), content-hash caching, hard ceiling (default 50 pairs) with conservative-fallback warning.
- Accepted **schema evolution to `DepEdge`** over **stay-with-list[str]**. Loader accepts both forms, so archived roadmaps remain valid.
- Accepted **Tier A being authoritative when both items are scoped** over **always also running Tier B**. Rationale: the deterministic answer is the crisp answer; asking the LLM to second-guess glob intersection wastes calls and introduces flakiness.

### Open Questions

- [ ] Should `.cache/plan-roadmap/dep-inference/` be checked into repo for roadmap reproducibility, or left as local scratch? Default is local-only; revisit if CI needs identical edge sets.
- [ ] Should the analyst batch size (K=10) be per-run configurable via `plan_roadmap.tier_b_batch_size` in `openspec/config.yaml`, or hardcoded? Default is config-driven in the implementation.
- [ ] Coordination with `speculative-merge-trains` — that draft also reasons about DAG/dependency semantics for merges. Alignment deferred until one lands.

### Context

Operator invoked `/plan-feature` with a capability-gap signal: `plan-roadmap`'s default dependency heuristic produced linear chains where real parallelism existed, forcing manual `depends_on` overrides. Mid-planning, operator added a design principle: prefer LLM semantic inference over more-elaborate rules when the question is ambiguous. Proposal was rewritten to use Tier A (deterministic scope overlap) for crisp conflicts and Tier B (analyst LLM) for semantic pair inference, with deterministic cheap pruning (Tier B-0) only as a cost guard. Result: five artifacts (proposal, spec delta, design, tasks, work-packages) with the work-packages YAML validating cleanly against the repo's schema and overlap checker.
