# Spec Delta: roadmap-orchestration / minimum-edge-dag-inference

## ADDED Requirements

### Requirement: Minimum-Edge Dependency Inference

The `plan-roadmap` workflow SHALL infer dependency edges between roadmap items using the strongest available signal per item-pair, preferring deterministic conflict detection when inputs permit a crisp answer and delegating semantic analysis to an LLM analyst agent otherwise. The resulting DAG SHALL NOT add edges beyond those justified by the selected tier, except for conservative fallback edges described below.

#### Scenario: Deterministic edge from declared write-write scope overlap

WHEN two roadmap items both declare a `scope.write_allow` field
AND their `write_allow` glob sets have a non-empty intersection under `fnmatch` semantics
THEN `plan-roadmap` SHALL add a dependency edge between them
AND the edge SHALL carry `source: "deterministic"` and a `rationale` string naming the overlapping glob(s).

#### Scenario: Deterministic edge from shared lock keys

WHEN two roadmap items both declare `scope.lock_keys`
AND their `lock_keys` sets share at least one canonicalized key (per `docs/lock-key-namespaces.md`)
THEN `plan-roadmap` SHALL add a dependency edge between them
AND the edge SHALL carry `source: "deterministic"` and a `rationale` string naming the shared key(s).

#### Scenario: Deterministic edge from read-after-write scope relationship

WHEN item A declares `scope.write_allow` that intersects item B's `scope.read_allow`
AND no edge already exists between them
THEN `plan-roadmap` SHALL add an edge such that B depends on A
AND the edge SHALL carry `source: "deterministic"` and `rationale: "read-after-write on <glob>"`.

#### Scenario: No deterministic edge when both items declare scope and no overlap exists

WHEN two roadmap items both declare `scope` (at least `write_allow`)
AND their `write_allow`, `read_allow`, and `lock_keys` sets have no intersections
THEN `plan-roadmap` SHALL NOT add a deterministic edge between them
AND the pair SHALL be excluded from LLM inference (Tier A is authoritative when both sides are fully scoped).

#### Scenario: LLM semantic inference when scope is missing on either side

WHEN at least one of the two roadmap items does NOT declare `scope`
AND the pair is not eliminated by cheap pruning (Tier B-0)
THEN `plan-roadmap` SHALL dispatch an analyst-archetype agent with the items' titles, descriptions, and parent-proposal section text
AND the agent SHALL return a structured verdict `{depends_on: "yes"|"no"|"unclear", rationale: str, confidence: "low"|"medium"|"high"}`
AND the edge decision SHALL be recorded with `source: "llm"` and the returned `confidence` and `rationale`.

#### Scenario: Conservative fallback preserves edges under LLM uncertainty

WHEN the LLM analyst returns `depends_on: "unclear"` OR `confidence: "low"`
THEN `plan-roadmap` SHALL add the edge rather than omitting it
AND the edge SHALL carry `source: "llm"` with `rationale` including the string `"conservative-fallback"`.

#### Scenario: Cheap pruning before LLM dispatch

WHEN a pair of items is a candidate for Tier B LLM inference
AND the pair is already transitively connected via Tier A edges
OR the pair has disjoint parent-proposal sections AND no shared noun phrases in titles
THEN `plan-roadmap` SHALL skip LLM dispatch for that pair
AND no edge SHALL be added on the basis of pruning alone.

#### Scenario: Split-induced edges remain deterministic

WHEN a roadmap item is split into multiple parts because its effort exceeds single-change scope
THEN `plan-roadmap` SHALL add a linear chain of dependencies between consecutive parts
AND each such edge SHALL carry `source: "split"` and `rationale: "part N depends on part N-1"`.

#### Scenario: DAG acyclicity preserved across all tiers

WHEN dependency inference completes across Tier A, Tier B, and split chains
THEN the resulting graph SHALL be acyclic as verified by `Roadmap.has_cycle()`
AND any cycle SHALL be broken by removing the lowest-confidence LLM-sourced edge first, then by DFS back-edge removal as a last resort.

### Requirement: Roadmap Item Scope Declaration

The `roadmap.yaml` artifact SHALL support an optional `scope` object on each item so that `plan-roadmap` can perform deterministic overlap-based dependency inference. Absence of `scope` SHALL NOT cause validation failure; it simply routes the item's pairs through LLM inference (Tier B).

#### Scenario: Accept roadmap item with scope declaration

WHEN a roadmap item declares `scope.write_allow`, `scope.read_allow`, or `scope.lock_keys`
THEN `roadmap.yaml` validation SHALL accept it per `contracts/roadmap.schema.json`
AND the declared fields SHALL be consumed by Tier A inference.

#### Scenario: Accept roadmap item without scope declaration

WHEN a roadmap item omits the `scope` field entirely
THEN `roadmap.yaml` validation SHALL accept it
AND the item's pairs SHALL be eligible for Tier B LLM inference.

#### Scenario: Reject roadmap item with malformed lock keys

WHEN a roadmap item declares `scope.lock_keys` containing values that do not match the canonicalization regex `^(api|db|event|flag|env|contract|feature):.+$`
THEN `roadmap.yaml` validation SHALL fail with an error naming the offending key
AND the error message SHALL reference `docs/lock-key-namespaces.md` for format guidance.

### Requirement: Edge Rationale and Source Attribution

Every dependency edge emitted into `roadmap.yaml` SHALL carry a `source` classification and a human-readable `rationale` string so that operators can audit and prune the inferred DAG.

#### Scenario: Edge records source classification

WHEN `plan-roadmap` adds any edge (deterministic, LLM, split, or explicit)
THEN the edge entry SHALL include a `source` field with one of the values: `"deterministic"`, `"llm"`, `"split"`, `"explicit"`.

#### Scenario: Edge records rationale string

WHEN `plan-roadmap` adds any edge
THEN the edge entry SHALL include a non-empty `rationale` field describing why the edge exists
AND for `source: "llm"` edges the `rationale` SHALL include the analyst's returned reasoning verbatim.

#### Scenario: LLM edges include confidence

WHEN `plan-roadmap` adds an edge with `source: "llm"`
THEN the edge entry SHALL include a `confidence` field with one of the values: `"low"`, `"medium"`, `"high"`.

#### Scenario: Operator-added explicit edges preserved

WHEN `plan-roadmap` regenerates a roadmap and an item already contains an entry in `depends_on` with `source: "explicit"`
THEN the existing edge SHALL be preserved as-is
AND the inference tiers SHALL NOT add a duplicate edge between the same pair.

### Requirement: LLM Inference Cost Controls

Because Tier B dispatches LLM calls, `plan-roadmap` SHALL bound cost and latency through pruning, batching, caching, and a hard ceiling.

#### Scenario: Pair results cached by content hash

WHEN Tier B computes a verdict for an item pair
THEN the verdict SHALL be cached under `.cache/plan-roadmap/dep-inference/` keyed on the SHA-256 of the sorted pair of item content hashes
AND subsequent `plan-roadmap` runs with identical inputs SHALL reuse the cached verdict without re-dispatching.

#### Scenario: Pairs batched into a single analyst call when possible

WHEN Tier B has multiple pair verdicts pending
THEN `plan-roadmap` SHALL batch up to `K` pairs (default K=10, configurable) into a single analyst dispatch
AND the analyst prompt SHALL return verdicts for all batched pairs in one structured response.

#### Scenario: Hard ceiling on LLM pairs per run

WHEN the number of Tier B candidate pairs exceeds the configured ceiling (default 50)
THEN `plan-roadmap` SHALL emit a warning naming the number of suppressed pairs
AND those pairs SHALL be skipped with `source: "llm"` replaced by `source: "ceiling-skipped"` and a conservative edge added (consistent with false-negative-worse-than-false-positive policy)
AND the warning SHALL advise the user to declare `scope` on items to route pairs through the cheaper Tier A path.
