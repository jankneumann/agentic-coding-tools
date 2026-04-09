# Proposal: Speculative Merge Trains with Stacked-Diff Decomposition and Build Graph Analysis

**Change ID**: `speculative-merge-trains`
**Status**: Draft
**Created**: 2026-04-09

## Why

The current merge queue processes features **one at a time** (sync-point pattern). At the current scale of 1–5 concurrent agents, this works. But as the system scales to 50–1000 agents, the serial merge queue becomes the primary bottleneck:

1. **O(N) merge time**: N concurrent features means N sequential pre-merge-check → merge → rebase cycles. With 50 agents producing features concurrently, the merge queue becomes a multi-hour bottleneck.
2. **Feature branches amplify conflict surface**: Work packages currently merge into a feature branch, then the feature branch merges to main. This two-hop merge doubles the conflict surface and delays integration feedback.
3. **No affected-test selection**: Pre-merge checks validate resource claims only — they don't run builds or tests. When speculative merges introduce actual CI validation, running the full test suite for every merge candidate is prohibitively expensive.
4. **Conservative parallelism**: `SEQUENTIAL_THRESHOLD=0.5` forces serialization when >50% of resource claims overlap, but finer-grained analysis (build graph, import graph) could reveal that the actual *semantic* overlap is much smaller.

Companies operating monorepos at scale (Google, Meta, Shopify, GitLab) solve this with three complementary techniques:

- **Stacked diffs**: Work packages land on main independently (not via feature branches), reducing branch lifetime and conflict surface
- **Speculative merge trains**: Multiple merge candidates are tested in parallel against speculative base states (main + preceding candidates)
- **Build graph analysis**: Only affected tests run per merge candidate, making speculative CI feasible at scale

This proposal brings all three to the agentic coordination system.

## What Changes

### Feature 1: Speculative Merge Train Engine (Coordinator Extension)

Extend `merge_queue.py` and `feature_registry.py` with a speculative merge train that tests multiple merge candidates in parallel:

- **Train composition**: Group queued entries into a train ordered by priority. Each entry is speculatively rebased onto `main + all preceding entries`.
- **Parallel CI**: Each train position runs CI against its speculative base. Positions are independent — CI for position 3 doesn't wait for position 1 to finish.
- **Priority eject on failure**: When a train entry fails, it's ejected from the train and re-queued at lower priority. Entries behind it continue if conflict analysis confirms no dependency (no overlapping lock keys or affected files). If dependency exists, those entries re-speculate against the new train (without the ejected entry).
- **Partition-aware trains**: Train entries with non-overlapping lock key namespaces (e.g., `api:` vs `db:schema:`) form independent sub-trains that merge in true parallel — no speculation needed within a partition.
- **State machine extension**: QUEUED → SPECULATING → SPEC_PASSED → MERGING → MERGED, with EJECTED for failed entries.

### Feature 2: Stacked-Diff Work Package Decomposition

Transform the work package workflow so packages land directly on main instead of collecting on feature branches:

- **Package-as-PR**: Each work package in `work-packages.yaml` becomes an independent PR targeting main. The DAG `depends_on` ordering determines merge train position.
- **Feature flag gating**: Incomplete features are gated behind lightweight feature flags (environment-variable-based with a `flags.yaml` registry). Packages land on main but their functionality is dormant until the flag is enabled.
- **Stack ordering**: Work packages within a feature form a stack: `wp-contracts` → `wp-backend-users` → `wp-backend-billing` → `wp-integration`. Each lands on main independently, in DAG order.
- **Backward compatibility**: Features can opt into stacked-diff mode (`decomposition: stacked`) or use traditional feature branches (`decomposition: branch`). Merge train supports both.

### Feature 3: Build Graph Analysis for Affected-Test Selection

Extend the architecture refresh pipeline (`skills/refresh-architecture/`) with test-aware analysis that powers affected-test selection for merge train CI:

- **Phase 1 — Import-level mapping**: Extract test nodes from `test_*.py` / `*_test.py` files. Create `TEST_COVERS` edges by tracing imports from test files to source modules. "If `billing.py` changes, run `test_billing.py`."
- **Phase 2 — Transitive closure**: Extend affected-test analysis through the call graph. If `billing.py` changes and `utils.py` calls `billing.py`, also flag `test_utils.py`. Uses existing `transitive_dependents()` traversal.
- **Phase 3 — Fixture-aware analysis**: Parse pytest conftest hierarchy, fixture definitions, and parametrize expansion. Build fixture dependency graph as new edges in `architecture.graph.json`.
- **Merge train integration**: When a train entry runs CI, the build graph determines which tests to run based on the changed files in that entry. This makes speculative CI proportional to change size, not repo size.

### Feature 4: Lightweight Feature Flag System

Add a minimal feature flag mechanism for safe stacked-diff-to-main workflow:

- **`flags.yaml` registry**: Declares flags with name, owner (change-id), status (disabled/enabled/archived), and description
- **Runtime resolution**: Environment variable override (`FF_<FLAG_NAME>=1`) with fallback to `flags.yaml`
- **Lifecycle**: Flag created when first stacked-diff package lands. Flag enabled when all packages in the feature land and pass integration tests. Flag archived after one release cycle.
- **Lock key integration**: Flags register as `flag:<name>` lock keys so the coordinator tracks ownership.

## Approaches Considered

### Approach 1: Full Train in Coordinator (Recommended)

**Description**: Extend `merge_queue.py` with train composition, speculative state tracking, and partition analysis. Speculative branches are created by a new coordinator service method that delegates to git operations. Build graph analysis lives in the refresh-architecture pipeline, queried by the coordinator during train composition.

**Pros**:
- Single source of truth for merge ordering (PostgreSQL-backed, auditable)
- Reuses existing feature registry resource claims for partition detection
- Integrates naturally with existing MCP tools (`enqueue_merge`, `run_pre_merge_checks`)
- Transactional guarantees for train state transitions (ACID)
- Existing audit trail captures all train decisions

**Cons**:
- Coordinator must perform git operations (speculative branch creation) — currently it's git-agnostic
- Increases coordinator complexity (~500-800 new lines in merge queue service)
- Coordinator becomes a bottleneck if git operations are slow

**Effort**: L

### Approach 2: Skill-Orchestrated Train with Coordinator State

**Description**: Train composition logic lives in a new `skills/merge-train/` skill. The skill reads the merge queue from the coordinator, computes the train, creates speculative branches locally, triggers CI, and reports results back. Coordinator only stores state and ordering.

**Pros**:
- Keeps coordinator git-agnostic (clean separation of concerns)
- Skill can use existing worktree infrastructure for speculative branches
- Easier to iterate on train logic without coordinator redeployment
- Can run locally without coordinator (graceful degradation)

**Cons**:
- State split between coordinator (queue) and skill (train execution)
- No transactional guarantee across train composition and state update
- Skill must poll coordinator for state changes (no push notification)
- Harder to audit — decisions split across two systems

**Effort**: L

### Approach 3: Minimal Train — Partition-Only Parallelism

**Description**: Skip speculative merge trains entirely. Instead, extend the merge queue to detect non-overlapping partitions (using build graph analysis) and merge entries from different partitions in true parallel. Within a partition, merges remain serial.

**Pros**:
- Much simpler (no speculative branches, no train composition)
- No git operations in coordinator
- Build graph analysis still delivers value (affected-test selection)
- Works with both feature branches and stacked diffs

**Cons**:
- Limited parallelism gain — if most changes touch shared code, still serial
- Doesn't address the "waiting for CI" bottleneck within a partition
- Leaves the most impactful optimization (speculative testing) on the table

**Effort**: M

### Selected Approach

**Approach 1: Full Train in Coordinator** — selected by user. The rationale: with the system scaling to 50–1000 agents, the full speculative merge train delivers the highest throughput. The coordinator already manages the merge queue state machine and resource claims; extending it with train logic keeps the source of truth unified. The git operation concern is mitigated by delegating actual branch creation to a thin git adapter layer that the coordinator calls.

## Success Criteria

1. **Merge throughput**: N independent features merge in O(N/K) time where K is the number of independent partitions, down from O(N) serial
2. **Affected-test selection**: Merge train CI runs only tests affected by each entry's changed files, validated by comparing selected tests vs full suite results
3. **Stacked-diff workflow**: Work packages can land on main independently, gated by feature flags, with no regression in integration safety
4. **Train resilience**: A failing entry is ejected and the train continues for independent entries, with no manual intervention required
5. **Backward compatibility**: Traditional feature-branch workflow continues to work alongside stacked-diff mode

## Impact

- **Merge throughput**: Independent features merge in O(N/K) time where K = number of independent partitions, down from O(N) serial. Validated by success criterion #1.
- **CI efficiency**: Affected-test selection reduces per-entry CI time by 30–70% for small changes (fewer files → fewer tests). Validated by success criterion #2 (compare affected tests vs full suite).
- **Branch lifetime**: Stacked-diff workflow reduces branch lifetime from days (feature branch) to hours (single work package), reducing conflict surface quadratically. Validated by success criterion #3.
- **Safety**: No regression — feature flags + pre-merge checks + post-speculation claim validation maintain existing safeguards.
- **Affected capabilities**: `agent-coordinator` (merge queue, feature registry), `codebase-analysis` (architecture graph, test analysis)

## Scope Boundaries

**In scope (this change — Phase 1)**:
- Speculative merge train engine with partition-aware parallelism
- Stacked-diff enqueue mode with `decomposition: stacked` field
- Import-level and transitive-call-level affected-test analysis
- Lightweight feature flag system (flags.yaml + env var)
- Post-speculation claim validation
- Crash recovery and TTL garbage collection for speculative refs

**Deferred (Phase 2 — separate change)**:
- Fixture-aware test analysis (conftest hierarchy, pytest fixtures)
- DAG scheduling integration (wire work-packages.yaml `depends_on` into compose_train ordering). Phase 1 assumes manual ordering via `merge_priority`; coordinators must ensure priorities respect DAG order.
- Build-graph-based partition detection (replace prefix-based with semantic overlap analysis)
- Train metrics and adaptive partition sizing
- CI integration (GitHub Actions `merge_group` trigger for train entries)

## Dependencies

- Existing merge queue service (`agent-coordinator/src/merge_queue.py`)
- Existing feature registry (`agent-coordinator/src/feature_registry.py`)
- Existing architecture refresh pipeline (`skills/refresh-architecture/`)
- Existing DAG scheduler (`skills/parallel-infrastructure/scripts/dag_scheduler.py`)
- Existing work packages schema (`openspec/schemas/work-packages.schema.json`)

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Speculative branches create git garbage | Medium | Auto-cleanup: delete speculative refs after train completes or entry is ejected |
| Train recomputation on eject is expensive | Medium | Partition isolation: entries in other partitions are unaffected by eject |
| Build graph staleness causes wrong test selection | High | Integrate `refresh-architecture --validate` into train entry submission; stale graph → full test suite fallback |
| Feature flag leakage (incomplete feature exposed) | Medium | Flags default to disabled; `flags.yaml` is version-controlled; CI checks for orphaned flags |
| Stacked diffs break bisect (partial features on main) | Low | Feature flags ensure partial features are dormant; flag-gated code paths excluded from bisect analysis |
