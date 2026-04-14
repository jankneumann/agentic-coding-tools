# Proposal: Minimum-Edge DAG Inference for `plan-roadmap`

## Why

The `plan-roadmap` skill's `build_dependency_dag()` (`skills/plan-roadmap/scripts/decomposer.py:387-443`) over-linearizes roadmaps because its infrastructure-first heuristic (Rule 1, lines 413-417) adds an edge from **every** non-infra item to **every** infra item unconditionally. For a roadmap with M infra items and N feature items, this produces M×N edges before any keyword overlap is considered, collapsing the DAG into a near-linear staircase.

Observed in practice: when decomposing a proposal, the user had to override the heuristic with minimal explicit `depends_on` lists because the auto-inferred DAG serialized work that was genuinely parallelizable. This is a **capability gap**, not just a papercut — the downstream consumer (`autopilot-roadmap`) picks ready items by "all deps completed", so each spurious edge reduces concurrency available to any current or future parallel executor.

### Design principle driving this change

> **Use determinism where input→output is crisp. Use LLM inference where ambiguity or semantic reasoning is required. Do not invent more elaborate rules to paper over a fundamentally semantic question.**

Applied here:
- **Deterministic signal**: declared scope overlap (`write_allow` glob intersect, shared lock keys on canonicalized namespaces) — crisp, testable, reusable from `skills/validate-packages/scripts/validate_work_packages.py:199-292`.
- **Semantic signal**: "does item B's work actually depend on item A's work?" — requires reading descriptions, understanding technical coupling, and reasoning about architecture. This is what analyst-archetype LLM agents are for (`src/agents_config.py::resolve_model(analyst, {})`).

The previous rule-based heuristics (infra-first unconditional, keyword overlap on titles) are the wrong tool for the wrong question — they try to approximate semantic reasoning with textual pattern matching.

## What Changes

### 1. Schema: Optional scope on `RoadmapItem`
- Extend `openspec/schemas/roadmap.schema.json` with optional `scope` object:
  - `scope.write_allow: string[]` — glob patterns the item may modify
  - `scope.read_allow: string[]` — glob patterns the item may read
  - `scope.lock_keys: string[]` — canonicalized logical keys (e.g., `db:schema:users`, `api:GET /v1/users`) per `docs/lock-key-namespaces.md`
- All fields optional; absence does not forbid an item, it simply skips the deterministic tier for that item.

### 2. Two-tier dependency inference in `decomposer.py`

Replace `build_dependency_dag()` with a pipeline that uses the **strongest available signal** per item-pair:

- **Tier A (deterministic scope overlap)**: When *both* items in a pair declare `scope`, add an edge iff:
  - `write_allow` glob intersection exists (reuse `fnmatch` logic from `validate_work_packages.py`), OR
  - shared `lock_keys` (set intersection on canonicalized keys), OR
  - one item's `write_allow` intersects the other's `read_allow` (read-after-write).
  - **No edge otherwise.** This is how we achieve minimum-edge DAGs when the data is there.

- **Tier B (LLM analyst inference)**: When either item lacks scope *and* the pair cannot be ruled out by cheap guards (see Tier B-0 below), dispatch an analyst-archetype Task(Explore) agent with:
  - Both items' titles + descriptions
  - The proposal section each item was decomposed from
  - A short schema: `{depends_on: "yes"|"no"|"unclear", rationale: str, confidence: "low"|"medium"|"high"}`
  - The conservative policy: **when `confidence == "low"` OR `depends_on == "unclear"`, add the edge** (false-negative-worse-than-false-positive preference from discovery).
  - Results cached by `(item_a_id, item_b_id)` hash so re-runs are idempotent.

- **Tier B-0 (cheap pruning, before dispatching LLMs)**: Skip Tier B entirely when pair-independence is trivially true, to control cost:
  - Items in unrelated capability sets (non-overlapping parent-proposal sections AND no shared noun phrases)
  - Items already connected transitively via Tier A
  - Items at the same priority with no textual co-reference
  - This is the **only** remaining "deterministic rule" — and only to avoid O(N²) LLM calls, not to infer deps.

- **Rule 3 (unchanged)**: Split chains remain linear; part 2 depends on part 1. This is deterministic by construction — the split *created* the dependency.

### 3. Edge rationale for transparency
Every inferred edge carries a `rationale: str` and `source: "deterministic" | "llm" | "explicit" | "split"` stored alongside `depends_on`. Exposed in `roadmap.yaml` so humans can audit and prune. Required by the "plans read plausibly to humans" success criterion.

Example:
```yaml
depends_on:
  - id: infra-db-schema
    rationale: "write_allow overlap on src/db/**"
    source: deterministic
  - id: feat-auth-refactor
    rationale: "auth-refactor introduces the User.role field that this item queries"
    source: llm
    confidence: medium
```

### 4. Conservative uncertainty policy
Under ambiguity, the algorithm keeps the edge:
- Tier A missing data → run Tier B
- Tier B low confidence or "unclear" → keep edge
- Consistent with the discovery answer that false negatives are worse.

### 5. LLM dispatch and cost controls
- Use the existing analyst archetype (`src/agents_config.py`) so the vendor/model is configurable per deployment.
- Batch pairs into a single analyst call when possible (one agent analyzes up to K pairs in one prompt) to amortize context cost.
- Cache results keyed on `(item_a_content_hash, item_b_content_hash)` in `.cache/plan-roadmap/dep-inference/`.
- Hard ceiling: max-pairs-per-roadmap (configurable, default 50); above that, emit a warning and fall back to Tier A only, requiring users to declare scope.

### 6. Tests and benchmark roadmaps
- Unit tests in `skills/tests/plan-roadmap/test_decomposer.py` for:
  - Tier A scope-overlap positive/negative cases (pure determinism, no LLM)
  - Tier B-0 cheap pruning (pure determinism)
  - Tier B with a mocked analyst (integration-style; pins the contract, not the model behavior)
  - Conservative policy: unclear/low-confidence → edge retained
- Benchmark roadmap fixtures under `skills/tests/plan-roadmap/fixtures/` with recorded expected edge counts (for Tier A only, since LLM outputs are non-deterministic) to prevent regression on the deterministic path.

### 7. Documentation updates
- `skills/plan-roadmap/SKILL.md` — document the `scope` field, the two-tier inference model, and when to declare scope for precise minimum-edge DAGs.
- `docs/lessons-learned.md` — capture the **deterministic-where-crisp / LLM-where-semantic** principle as a reusable pattern for other skills.

### Out of Scope
- Making `autopilot-roadmap` itself parallel (separate proposal).
- Auto-inferring `scope` from proposal text via LLM. Scope remains explicit user/skill-author declaration — it's the *deterministic* input that anchors Tier A.
- Coordinating with `speculative-merge-trains` or `harness-engineering-features` drafts — will align semantics once those land.

## Approaches Considered

### Approach 1: Deterministic-first with LLM semantic fallback *(Recommended)*

**Description**: Tier A (declared scope → deterministic overlap) + Tier B (LLM analyst for ambiguous pairs) + Tier B-0 (cheap pruning to control LLM cost).

**Pros**:
- Respects the design principle: determinism where clear, LLM where semantic
- Tier A reuses existing, tested overlap code from `validate_work_packages.py`
- Tier B replaces fragile text heuristics with actual reasoning over item descriptions + proposal context
- Edge rationale + source field make output auditable
- Cost-controlled via batching and caching; degrades gracefully (ceiling → Tier A only with warning)

**Cons**:
- Introduces LLM latency and cost into `plan-roadmap` (mitigated by batching, caching, ceiling)
- Tier B results are non-deterministic across runs (mitigated by caching; tests pin contract not output)
- Two inference paths to maintain

**Effort**: M

### Approach 2: Pure LLM semantic inference (no scope fields)

**Description**: Skip the schema change. For every non-trivial pair, dispatch an analyst agent to infer the dependency from descriptions. No deterministic tier except Tier B-0 pruning and split-chain linearity.

**Pros**:
- Smallest schema impact (no roadmap.schema.json change)
- Uniform inference model — no "which tier ran?" complexity
- Fully aligned with "use LLMs for semantic questions"

**Cons**:
- Misses the deterministic floor: when scope *is* known (glob overlap is unambiguous conflict), asking an LLM is wasteful and introduces flakiness
- Higher LLM cost (no cheap deterministic path)
- Non-deterministic across runs even when inputs permit a crisp answer
- Harder to test — no deterministic oracle for the deterministic cases

**Effort**: S–M

### Approach 3: Pure scope-based (reject items without scope)

**Description**: Require every `RoadmapItem` to declare `scope`. Dependency inference is purely deterministic overlap + lock keys + split chains. Reject `roadmap.yaml` generation if any item lacks scope.

**Pros**:
- Maximally deterministic and testable
- No LLM cost or non-determinism
- Forces users to think about scope upfront (possibly beneficial)

**Cons**:
- **Violates the design principle** by requiring crisp data for an inherently semantic question — not every item has a clean, glob-expressible scope at decomposition time
- High adoption friction — users have to learn the scope vocabulary (globs, lock namespaces) before they get any plan
- Punts the hard cases back to the user instead of using the tools (LLMs) available to solve them
- Existing archived roadmaps have no scope field — backward-incompat without a migration step

**Effort**: M

## Selected Approach

> **Decision (Gate 1)**: Approach 1 approved by operator.

**Approach 1: Deterministic-first with LLM semantic fallback** is selected and directly applies the user's stated principle:
- Deterministic signal (Tier A) for the crisp case: *declared scope → glob/lock overlap*
- LLM semantic inference (Tier B) for the ambiguous case: *undeclared scope → analyst reasons over descriptions + proposal context*
- Deterministic Tier B-0 used only for **cost control**, not inference — cheap guards to prune obviously-independent pairs before LLM dispatch

This aligns with all four discovery answers:
- Neutralizes **Rule 1 (infra-first unconditional)** — the primary offender — by replacing it with either Tier A overlap (if scoped) or an LLM question "does this feature actually depend on this infra?"
- Implements **scope fields** as the deterministic anchor (user's scope-model preference)
- Preserves conservative behavior under uncertainty via "unclear/low-confidence ⇒ keep edge" policy (**false-negatives-worse-than-false-positives**)
- Serves the **composite success metric**: edge-count reduction (Tier A determinism), parallel-scheduler readiness (precise + semantically-aware DAG), human-plausible plans (rationale + source on every edge)

### Alternatives (demoted)

- *Approach 2 (pure LLM)* — wastes the crisp deterministic signal when scope *is* declared and introduces unnecessary flakiness there. Kept as a possible simplification if Tier A adoption is low.
- *Approach 3 (pure scope-required)* — rejected. Violates the design principle: forces a crisp-data requirement on a question that is inherently semantic when scope is unknown, and pushes work back to users that LLMs can do.
