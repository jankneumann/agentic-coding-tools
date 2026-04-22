# Design: Speculative Merge Trains with Stacked-Diff Decomposition and Build Graph Analysis

**Change ID**: `speculative-merge-trains`

## Architecture Overview

This feature extends the existing merge queue from a serial sync-point to a speculative merge train engine with partition-aware parallelism. It introduces three new subsystems:

```
                     ┌──────────────────────────────────────┐
                     │         Train Composer               │
                     │  (compose_train, partition, order)   │
                     └───────────────┬──────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                       ▼
  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
  │  Partition A       │  │  Partition B       │  │  Partition C       │
  │  (api:* keys)      │  │  (db:* keys)       │  │  (cross-partition) │
  │                    │  │                    │  │                    │
  │  ┌─Entry 1──────┐ │  │  ┌─Entry 3──────┐ │  │  ┌─Entry 5──────┐ │
  │  │spec: main+1  │ │  │  │spec: main+3  │ │  │  │spec: main+1+5│ │
  │  │CI: affected  │ │  │  │CI: affected  │ │  │  │CI: affected  │ │
  │  └──────────────┘ │  │  └──────────────┘ │  │  └──────────────┘ │
  │  ┌─Entry 2──────┐ │  │  ┌─Entry 4──────┐ │  │                    │
  │  │spec: main+1+2│ │  │  │spec: main+3+4│ │  │                    │
  │  │CI: affected  │ │  │  │CI: affected  │ │  │                    │
  │  └──────────────┘ │  │  └──────────────┘ │  │                    │
  └───────────────────┘  └───────────────────┘  └───────────────────┘
              │                      │                       │
              └──────────────────────┼───────────────────────┘
                                     ▼
                           ┌───────────────────┐
                           │   Merge Executor   │
                           │   (fast-forward    │
                           │    to main)        │
                           └───────────────────┘
```

## Design Decisions

### D1: Train state stored in feature_registry.metadata JSONB

**Decision**: Extend the existing `merge_queue` metadata key in `feature_registry.metadata` with train-specific fields rather than adding a new database table.

**Rationale**: The merge queue already stores its state in metadata JSONB (`merge_queue.status`, `merge_queue.pr_url`, etc.). Adding `train_id`, `train_position`, `speculative_ref`, and `partition_id` to this same metadata key keeps the data model unified and avoids a new migration for a join table. PostgreSQL JSONB indexing is sufficient for the query patterns (filter by train_id, order by position).

**Rejected alternative**: New `merge_trains` table with foreign key to `feature_registry`. This would give better query ergonomics but adds migration complexity and a join for every queue read.

### D2: Partition detection via lock key prefix grouping

**Decision**: Determine partitions by grouping entries' resource claims by lock key prefix (`api:`, `db:schema:`, `flag:`, file paths by top-level directory). Entries with non-overlapping prefix groups form independent partitions.

**Rationale**: Lock key namespaces (9 prefixes defined in `docs/lock-key-namespaces.md`) already encode the resource domain. Prefix-based grouping is O(N) and deterministic — no graph traversal needed. This reuses existing infrastructure without adding dependency on the build graph (which is Phase 2).

**Rejected alternative**: Build-graph-based partitioning. More accurate (detects semantic overlap) but requires the build graph to be current and adds a hard dependency on the architecture pipeline. Reserved for Phase 2 enhancement.

### D3: Git adapter layer for speculative branch creation

**Decision**: Introduce a `GitAdapter` protocol class that the merge train service calls for git operations (create speculative branch, merge commits, delete refs). The coordinator's merge queue calls the adapter; the adapter's implementation is injected at startup.

**Rationale**: The coordinator has been git-agnostic until now. Rather than coupling `merge_queue.py` directly to subprocess git calls, the adapter pattern:
- Keeps the service layer testable (mock adapter in tests)
- Allows future swap to libgit2 or GitHub API
- Isolates the blast radius of git failures

**Implementation**: `agent-coordinator/src/git_adapter.py` with a `GitAdapter` protocol and `SubprocessGitAdapter` implementation.

### D4: Priority eject with independence check

**Decision**: When a train entry fails CI, eject it and re-queue at `merge_priority - 10` (lower priority). Entries behind the ejected entry continue if their resource claims have zero overlap with the ejected entry's claims. Otherwise, they re-speculate against the reduced train.

**Rationale**: Priority eject is the fastest recovery strategy — independent entries are unaffected, and the ejected entry gets another chance after higher-priority entries merge. The independence check reuses `analyze_conflicts()` from the feature registry, which already computes claim overlap.

**Rejected alternative**: Full bisect-and-rebuild (GitLab model). More robust but CI cost is proportional to failure position — if entry 2 of 10 fails, entries 3-10 all re-speculate. At 50+ entries, this is prohibitively expensive.

**Cross-partition merge ordering algorithm** (used by `merge_partition()` in task 2.12):

```
def merge_train(train: Train) -> None:
    # 1. Build partition ready-graph:
    #    - nodes: partitions + cross-partition entries
    #    - edges: cross-partition entry X ∈ partitions {Pa, Pb} creates
    #      "Pa waits for X" and "Pb waits for X" — but X waits for all
    #      preceding entries in BOTH Pa and Pb.
    ready_graph = build_ready_graph(train)

    # 2. Topological sort; detect cycles (already done in compute_partitions,
    #    but re-verify here as a safety net).
    order = topo_sort(ready_graph)  # raises on cycle

    # 3. Advance in waves. Each wave merges everything currently runnable
    #    in parallel, then unblocks whatever the wave enabled.
    pending = set(order)
    with coordinator.transaction():          # ACID: all-or-nothing per wave
        while pending:
            wave = {n for n in pending
                    if all_passed(n) and no_unmet_deps(n, pending)}
            if not wave:
                # Deadlock — some node is waiting on something not in pending.
                # Should never happen if ready_graph is correct; log + abort.
                raise TrainDeadlockError(pending)

            # Parallel merges within the wave:
            #   - Regular partitions: fast-forward main → final speculative ref
            #   - Cross-partition entries: fast-forward main → entry's ref,
            #     then all partitions in entry.spans_partitions must rebase
            #     their remaining speculative refs onto the new main tip.
            parallel_map(merge_node, wave)

            pending -= wave

    # 4. Cleanup: delete speculative refs for the completed train.
    git_adapter.delete_speculative_refs(train.train_id)
```

**Key invariants**:
- A partition only merges when ALL its entries are SPEC_PASSED AND no cross-partition entry it depends on is still pending.
- A cross-partition entry merges only when ALL preceding entries in EVERY partition it spans have merged.
- The wave model allows non-overlapping partitions to merge truly in parallel (within a single wave) while still serializing through cross-partition entries.
- Rebasing after a cross-partition merge is cheap because the partitions' speculative refs already contain the cross-partition entry's changes (from the compose_train step).

### D5: Affected-test selection via architecture graph extension

**Decision**: Extend the architecture refresh pipeline with a new `test_linker.py` insight module (Layer 2) that creates `TEST_COVERS` edges from test nodes to source nodes. The affected-test query traverses reverse edges from changed files to find covering tests.

**Rationale**: The architecture graph already has import edges, call edges, and a `transitive_dependents()` traversal. Adding test nodes and `TEST_COVERS` edges lets the existing traversal machinery answer "which tests are affected by this file change?" without a new algorithm. The incremental approach (Phase 1: import-level, Phase 2: transitive, Phase 3: fixture-aware) ships value early.

**Rejected alternative**: Standalone affected-test tool (e.g., pytest-testmon, coverage-based). These require runtime coverage data and don't integrate with the existing architecture graph. They also can't be queried by the merge train service without a separate data store.

### D6: Stacked diffs with feature flag gating

**Decision**: Work packages in stacked-diff mode (`decomposition: stacked` in work-packages.yaml) each become an independent PR targeting main. Incomplete features are gated behind flags declared in `flags.yaml` at repo root.

**Rationale**: Full stacked diffs maximize merge train throughput by reducing the merge unit from "entire feature" to "single work package". Feature flags ensure partially-landed features don't affect production behavior. The `flags.yaml` registry is version-controlled, so flag state is auditable and reviewable.

**Rejected alternative**: Branch-based stacking (stacked within feature branch). Simpler but doesn't reduce branch lifetime or conflict surface for the merge train — the feature branch still needs to merge to main as one unit.

### D7: Feature flag implementation — environment variable with YAML fallback

**Decision**: Flag resolution order: `FF_<FLAG_NAME>` environment variable → `flags.yaml` file → default (disabled). Flag names derive from the feature's change-id, normalized to uppercase with underscores.

**Rationale**: Environment variables allow per-environment override (staging enables a flag, production doesn't) without code changes. `flags.yaml` provides the default state and serves as documentation. This is deliberately minimal — no runtime flag service, no A/B testing, no percentage rollouts. Those can be added later if needed.

**Failure modes** (defensive defaults so flag system never blocks the coordinator):
- `flags.yaml` missing: treat as empty registry, log one-time warning, all flags default to disabled. This supports bootstrapping a new repo that doesn't yet have any flags.
- `flags.yaml` malformed (YAML parse error, schema violation): raise `FlagsConfigError` at startup. This is a deployment bug — fail loud, don't silently run with "everything disabled".
- Flag referenced in code but not declared in `flags.yaml`: `resolve_flag()` returns `False` with a warning log. This keeps flag *removal* safe — orphaned `is_enabled("OLD_FLAG")` calls degrade to disabled, not crash.
- `FF_*` env var for an undeclared flag: rejected (ignored with warning) per the fail-closed rule in Security Considerations.

## Data Flow

### Train Composition Flow

**Triggers**: `compose_train()` runs in two modes: (a) on-demand immediately after each `enqueue` call, and (b) via a periodic background sweep every `MERGE_TRAIN_SWEEP_INTERVAL_SECONDS` (default 60s). The periodic sweep catches work that gets enqueued during a composition (when the on-enqueue trigger races) and recovers from transient failures (e.g., if a prior compose_train raised and the entry is still QUEUED).

```
1. Agent calls enqueue_merge(feature_id, pr_url)
2. MergeQueueService stores QUEUED status in metadata
3. compose_train() is called (immediately after enqueue AND by the periodic sweep):
   a. Fetch all QUEUED entries, sorted by merge_priority
   b. Group entries by lock key prefix → compute partitions
   c. Within each partition, assign speculative positions
   d. For each position, create speculative ref:
      - Position 1: git merge-base main + entry-1
      - Position 2: git merge-base main + entry-1 + entry-2
      - etc.
   e. Store train_id, position, partition_id, speculative_ref in metadata
   f. Set status to SPECULATING
4. External CI system runs tests for each speculative ref:
   - Query build graph for affected tests
   - Run only affected tests against speculative ref
5. On CI completion:
   - SUCCESS: Set status to SPEC_PASSED
   - FAILURE: Call eject_from_train(feature_id)
6. When all entries in a partition reach SPEC_PASSED:
   - Fast-forward main to the last speculative ref
   - Set status to MERGED for all entries
   - Deregister from feature registry
```

### Affected-Test Query Flow

```
1. Train entry has speculative ref with changed files
2. Query: affected_tests(changed_files) →
   a. Find nodes in architecture.graph.json matching changed files
   b. Compute transitive dependents of those nodes
   c. Filter to nodes with kind="test_function" or kind="test_class"
   d. Return unique test file paths
3. CI runs only those test files
4. Fallback: if graph is stale (>24h), run full test suite
```

## Migration Strategy

### Phase 1: Foundation (this change)

- Merge train state machine in coordinator
- Git adapter layer
- Partition detection
- Test linker module (import-level)
- `flags.yaml` schema and resolution
- `decomposition` field in work-packages.yaml schema

### Phase 2: Integration

- Wire train composition into existing `/cleanup-feature` and `/merge-pull-requests` skills
- Add transitive closure to affected-test analysis
- Speculative branch cleanup cron job
- CI integration (GitHub Actions `merge_group` trigger for train entries)

### Phase 3: Scale

- Fixture-aware test analysis
- Train metrics (throughput, eject rate, CI time savings)
- Adaptive partition sizing based on historical conflict data
- Event bus notifications for train state changes (LISTEN/NOTIFY)

### D8: Post-speculation claim validation

**Decision**: After each speculative ref is created, compute the actual `git diff` of changed files and map them to lock key namespaces via a heuristic `file_path_to_namespaces(path)` function (defined in `merge_train_types.py`, see tasks 1.4a/1.4b). If the actual changes span namespaces not declared in the entry's `resource_claims`, transition the entry to BLOCKED with a claim mismatch error.

**Rationale**: Partition detection trusts agent-provided resource claims (D2). But agents can be wrong — they declare claims at enqueue time based on expected changes, not actual changes. Post-speculation validation catches mismatches before CI runs, preventing unsafe partition assignment. This is a defense-in-depth layer: the pre-merge check (existing) validates claim overlap with other features, and post-speculation validation ensures claims are truthful.

**File-path-to-namespace mapping** (the reverse of the 9 namespaces defined in `docs/lock-key-namespaces.md`):

```python
# Declared at module level in merge_train_types.py — unit-testable
PATH_TO_NAMESPACE_RULES: list[tuple[str, str]] = [
    ("contracts/**",                      "contract:"),
    ("**/migrations/**",                  "db:migration-slot"),
    ("database/migrations/**",            "db:migration-slot"),
    ("**/schema*.py",                     "db:schema:"),
    ("**/models/**",                      "db:schema:"),
    ("**/models.py",                      "db:schema:"),
    ("src/api/**",                        "api:"),
    ("**/routes/**",                      "api:"),
    ("**/endpoints/**",                   "api:"),
    ("src/events/**",                     "event:"),
    ("**/event_handlers/**",              "event:"),
    ("flags.yaml",                        "flag:"),
]

def file_path_to_namespaces(path: str) -> set[str]:
    """Return the set of logical namespaces a path COULD belong to.
    Returns empty set if no rule matches — claim validation treats
    empty-set paths as 'out-of-scope for logical checking' (file-level
    locks still apply)."""
    return {ns for pattern, ns in PATH_TO_NAMESPACE_RULES if fnmatch(path, pattern)}
```

**Key invariant**: This mapping is HEURISTIC, not authoritative. An empty result does not fail validation — it means "this file is locked at path-level, not namespace-level". A non-empty result is compared against the declared `resource_claims` prefixes. Only a provable mismatch (actual namespace X not in declared set) triggers BLOCKED.

**Rejected alternative**: Coordinator computes claims from git diff at enqueue time (removing agent responsibility). This couples the coordinator to understanding code-to-lock-key mapping for WRITING claims, which is a planning-time concern. The heuristic mapping used here is only for VERIFYING claims post-hoc, which is a narrower, safer coupling.

### D9: BLOCKED entry recovery lifecycle

**Decision**: BLOCKED entries can be recovered two ways: (1) manual re-enqueue by the entry owner with updated claims/branch, or (2) automatic re-evaluation during compose_train if the entry has been BLOCKED for more than 1 hour (conflict may have been resolved by other merges).

**Rationale**: Without a recovery path, BLOCKED entries accumulate and require manual intervention. Auto-re-evaluation handles the common case where a conflict was caused by a preceding entry that has since merged (resolving the conflict). The 1-hour delay prevents rapid re-evaluation loops.

**Rejected alternative**: Immediate automatic re-evaluation on every compose_train. This wastes git operations for entries BLOCKED due to genuine conflicts that won't resolve without code changes.

### D10: Affected-test traversal bounds

**Decision**: Reverse BFS in `affected_tests()` is bounded to 10,000 node visits per query. Traversal stops at test nodes (does not continue through test-to-test edges). If the bound is exceeded, the function returns `None` (run all tests).

**Rationale**: On a monorepo with 10K+ files, an unbounded BFS from a highly-connected node (e.g., `config.py` with 85 dependents) could visit thousands of nodes. The bound ensures predictable latency (<100ms target). The fallback to "run all tests" is safe — it's what happens today without the build graph.

### D11: Train operation authorization model

**Decision**: Train operations use the existing agent profiles trust level system. `compose_train` and `get_train_status` require trust level >= 3 (operator). `eject_from_train` requires either feature ownership (registered_by matches agent_id) or trust level >= 3. `report_spec_result` requires trust level >= 2 (standard agent).

**Rationale**: The coordinator already has an authorization model (profiles + policy engine). Train operations fit naturally into this model. The key constraint is that arbitrary agents should not be able to eject other agents' entries or manipulate train composition.

### D12: Max-eject threshold and ABANDONED terminal state

**Decision**: Each train entry tracks `eject_count: int` in its metadata, incremented on every `eject_from_train` call. When `eject_count` reaches `MAX_EJECT_COUNT` (default 3), the entry transitions to a new terminal state `ABANDONED` instead of being re-queued. ABANDONED entries are removed from train composition until the owner manually re-enqueues them (which resets `eject_count` to 0). The entry owner is notified via the audit trail.

**Rationale**: Without a threshold, an entry that persistently fails CI can be ejected indefinitely, consuming speculative CI cycles and pushing `merge_priority` into arbitrarily negative territory. At 50-1000 agent scale, a single broken entry could absorb significant CI budget. The threshold bounds the failure cost: at most `MAX_EJECT_COUNT` CI runs are wasted on a persistently-broken entry before it is set aside for human investigation.

**Configurable**: `MAX_EJECT_COUNT` is a constant in `merge_train_types.py`, not a per-request parameter. It's tunable per deployment but not per-entry (to prevent gaming).

**Interaction with priority decrement**: The `-10` decrement still applies up to the threshold. So an entry with initial priority 5 will be ejected at priorities 5, -5, -15, then transition to ABANDONED (not re-queued at -25).

**Recovery**: Manual re-enqueue of an ABANDONED entry resets `eject_count = 0` AND restores `merge_priority` to the originally-registered value. This gives the owner a clean slate after fixing the underlying issue.

**Rejected alternative**: Time-based eject cooldown (e.g., "can only re-eject after 1 hour"). This slows the bleed but doesn't bound total CI cost. A count-based threshold is simpler and has a provable upper bound.

## Security Considerations

- **Speculative branches are ephemeral**: Created under `refs/speculative/train-<id>/pos-<n>`, automatically deleted after train completes or entry is ejected. Never pushed to remote (local only).
- **Speculative ref naming is validated**: Ref names must match `^refs/speculative/train-[a-f0-9]{8,32}/pos-\d{1,4}$`. Agent-provided branch names must match `^[a-zA-Z0-9/_.-]{1,200}$`. Validation prevents command injection via branch names.
- **Git adapter uses shell=False exclusively**: All subprocess calls use explicit argument lists, never shell interpretation. This prevents injection even if validation is bypassed.
- **Crash recovery**: Coordinator startup enumerates `refs/speculative/` and deletes orphaned refs with no active train entries. Watchdog sweeps refs older than 6 hours.
- **Post-speculation claim validation**: After speculative refs are created, actual file changes are validated against declared resource claims. Mismatches cause BLOCKED transition, preventing unsafe partition assignment.
- **Train operations require authorization**: compose_train requires operator trust (level 3+). eject_from_train requires ownership or operator trust. This prevents unauthorized train manipulation.
- **Feature flags are defense-in-depth, not security gates**: Flags gate incomplete functionality, not access control. Security-critical features should not rely on flags alone. Flagged code MUST pass type checking and linting — flags gate runtime behavior, not static analysis.
- **Feature flag env var resolution is fail-closed**: Any `FF_*` environment variable not declared in `flags.yaml` is rejected (ignored with warning), preventing injection of undeclared flags.
- **Audit trail extended**: All train operations (compose, eject, merge, claim validation, flag create/enable/archive) logged via existing audit service.
