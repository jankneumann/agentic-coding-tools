# Tasks: Speculative Merge Trains

**Change ID**: `speculative-merge-trains`

## Phase 1: Contracts and Schema (wp-contracts)

- [ ] 1.1 Write tests for GitAdapter protocol — mock subprocess, verify branch create/delete/merge operations, **injection prevention tests** (semicolons, backticks, $(), newlines in branch names)
  **Spec scenarios**: agent-coordinator.2 (speculative ref creation), agent-coordinator.2 (cleanup), agent-coordinator.7 (ref naming validation)
  **Contracts**: contracts/internal/git-adapter-api.yaml
  **Design decisions**: D3 (git adapter layer)
  **Dependencies**: None

- [ ] 1.2 Create `git_adapter.py` — GitAdapter protocol + SubprocessGitAdapter implementation. MUST use `subprocess.run(args_list, shell=False)` exclusively. Validate ref names match `^refs/speculative/train-[a-f0-9]{8,32}/pos-\d{1,4}$`, branch names match `^[a-zA-Z0-9/_.-]{1,200}$`.
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for merge train data types — MergeTrainStatus enum, TrainEntry dataclass, TrainComposition dataclass
  **Spec scenarios**: agent-coordinator.3 (state machine)
  **Contracts**: contracts/internal/merge-train-api.yaml
  **Design decisions**: D1 (metadata JSONB storage)
  **Dependencies**: None

- [ ] 1.4 Create `merge_train_types.py` — data types for train entries, partitions, and compositions. Extend `MergeStatus` enum with SPECULATING, SPEC_PASSED, EJECTED states. This file is the shared type definition — `merge_queue.py` and `merge_train.py` both import from it.
  **Dependencies**: 1.3

- [ ] 1.5 Define `flags.yaml` JSON schema (`openspec/schemas/flags.schema.json`) and create schema validation script. Schema MUST include: flag name (max 64 chars), owner (change-id), status (disabled/enabled/archived), description (max 500 chars), created_at, archived_at.
  **Spec scenarios**: (feature flag system, no spec scenario — schema-level)
  **Design decisions**: D7 (env var with YAML fallback)
  **Dependencies**: None

- [ ] 1.6 Extend `work-packages.schema.json` with `decomposition` field (enum: "stacked" | "branch", default: "branch")
  **Dependencies**: None

## Phase 2: Train Engine (wp-train-engine)

- [ ] 2.1 Write tests for partition detection — lock key prefix grouping, overlap computation, cross-partition identification, **cross-partition cycle detection**, **1000-entry performance benchmark** (must complete in <5s)
  **Spec scenarios**: agent-coordinator.1 (independent entries), agent-coordinator.1 (cross-partition), agent-coordinator.9 (performance bound), agent-coordinator.9 (cycle detection)
  **Contracts**: contracts/internal/merge-train-api.yaml
  **Design decisions**: D2 (prefix-based partitioning)
  **Dependencies**: 1.4

- [ ] 2.2 Implement `compute_partitions(entries)` — group entries by lock key prefix using union-find or multiset intersection (O(N·P) where P = prefixes per entry). Detect cross-partition entries. Detect cycles in cross-partition dependency graph.
  **Dependencies**: 2.1

- [ ] 2.3 Write tests for `compose_train()` — train creation from queue, speculative position assignment, empty queue handling, **authorization checks** (trust level 3+ required), **1-entry train**, **100-entry train**
  **Spec scenarios**: agent-coordinator.1 (all scenarios), agent-coordinator.6 (authorization)
  **Contracts**: contracts/internal/merge-train-api.yaml
  **Design decisions**: D1 (metadata storage), D2 (partitioning), D11 (authorization)
  **Dependencies**: 2.2

- [ ] 2.4 Implement `compose_train()` — fetch queued entries, verify caller trust level >= 3, compute partitions, assign positions, create speculative refs via git adapter using `git merge-tree` (no working directory IO). Cache tree objects per train_id.
  **Dependencies**: 2.3, 1.2

- [ ] 2.5 Write tests for post-speculation claim validation — claim matches actual changes, claim mismatch triggers BLOCKED, partition reassignment scenarios
  **Spec scenarios**: agent-coordinator.8 (claim matches), agent-coordinator.8 (claim mismatch)
  **Design decisions**: D8 (post-speculation validation)
  **Dependencies**: 2.4

- [ ] 2.6 Implement post-speculation claim validation — compute actual changed files from speculative ref diff, map to lock key namespaces, compare against declared claims. BLOCKED on mismatch.
  **Dependencies**: 2.5

- [ ] 2.7 Write tests for `eject_from_train()` — priority decrement, independence check, re-speculation trigger, **authorization** (owner or trust level 3+), **ejection of last entry in partition**
  **Spec scenarios**: agent-coordinator.4 (eject with independent successors), agent-coordinator.4 (eject with dependent successors), agent-coordinator.6 (eject authorization)
  **Design decisions**: D4 (priority eject), D11 (authorization)
  **Dependencies**: 2.6

- [ ] 2.8 Implement `eject_from_train(feature_id)` — verify caller authorization, eject entry, decrement priority by 10, check independence of successors via lock key overlap, trigger re-speculation for dependent successors.
  **Dependencies**: 2.7

- [ ] 2.9 Write tests for BLOCKED entry recovery — manual re-enqueue, automatic re-evaluation after 1 hour, permanent BLOCKED (conflict not resolved)
  **Spec scenarios**: agent-coordinator.10 (manual re-enqueue), agent-coordinator.10 (automatic re-evaluation)
  **Design decisions**: D9 (BLOCKED recovery lifecycle)
  **Dependencies**: 2.8

- [ ] 2.10 Implement BLOCKED entry recovery — re-enqueue method for owners, auto-re-evaluation in compose_train for entries BLOCKED > 1 hour
  **Dependencies**: 2.9

- [ ] 2.11 Write tests for partition-aware merge execution — parallel partition merge, cross-partition serialization, **speculative ref cleanup after merge**
  **Spec scenarios**: agent-coordinator.5 (parallel partition merge), agent-coordinator.5 (cross-partition ordering), agent-coordinator.7 (cleanup)
  **Dependencies**: 2.10

- [ ] 2.12 Implement partition-aware merge executor — fast-forward main per partition, serialize cross-partition entries, delete speculative refs after train completion
  **Dependencies**: 2.11

- [ ] 2.13 Write tests for crash recovery — orphaned speculative refs from dead trains, startup cleanup routine
  **Spec scenarios**: agent-coordinator.7 (cleanup on crash), agent-coordinator.7 (TTL garbage collection)
  **Dependencies**: 2.12

- [ ] 2.14 Implement crash recovery — startup routine to enumerate refs/speculative/ and delete orphans, watchdog integration for TTL-based GC of refs older than 6 hours
  **Dependencies**: 2.13

## Phase 3: Build Graph Extension (wp-build-graph)

- [ ] 3.1 Write tests for test node extraction — naming convention discovery, parametrized test handling, node metadata
  **Spec scenarios**: codebase-analysis.1 (test function discovery), codebase-analysis.1 (parametrized tests)
  **Contracts**: contracts/internal/test-linker-output.yaml
  **Design decisions**: D5 (architecture graph extension)
  **Dependencies**: None

- [ ] 3.2 Create `test_linker.py` insight module — extract test nodes from Python test files, add to architecture graph
  **Dependencies**: 3.1

- [ ] 3.3 Write tests for TEST_COVERS edge creation — direct import mapping, standard library exclusion
  **Spec scenarios**: codebase-analysis.2 (direct import edge), codebase-analysis.2 (no standard library edge)
  **Contracts**: contracts/internal/test-linker-output.yaml
  **Dependencies**: 3.2

- [ ] 3.4 Implement TEST_COVERS edge creation in `test_linker.py` — trace imports from test files to source modules, create edges with confidence/evidence
  **Dependencies**: 3.3

- [ ] 3.5 Write tests for `affected_tests()` query — single file, no coverage, stale graph fallback, **traversal bound (10K nodes)**, **cycle detection**, **performance benchmark (<100ms for 10K-node graph)**
  **Spec scenarios**: codebase-analysis.3 (all scenarios including traversal bound)
  **Design decisions**: D5 (architecture graph extension), D10 (traversal bounds)
  **Dependencies**: 3.4

- [ ] 3.6 Implement `affected_tests(changed_files)` — reverse BFS from changed files to test nodes, stop at test nodes, visited-set cycle detection, 10K node bound with fallback to None, stale graph detection (>24h)
  **Dependencies**: 3.5

- [ ] 3.7 Register `test_linker` in `compile_architecture_graph.py` pipeline as Stage 3.5 (between db_linker and flow_tracer)
  **Dependencies**: 3.6

## Phase 4: Feature Flags (wp-feature-flags)

- [ ] 4.1 Write tests for flag resolution — env var override, YAML fallback, default disabled, **fail-closed for undeclared FF_* vars**, **flag with type check/lint verification**
  **Design decisions**: D7 (resolution order), D6 (stacked diffs with flag gating)
  **Dependencies**: 1.5

- [ ] 4.2 Create `feature_flags.py` — Flag dataclass, load_flags(yaml_path), resolve_flag(name), create_flag(change_id), enable_flag(name), archive_flag(name). Fail-closed: reject any `FF_*` env var not declared in flags.yaml (log warning, use YAML/default value).
  **Dependencies**: 4.1

- [ ] 4.3 Write tests for flag lifecycle — create on first stacked-diff, enable on feature completion, archive after release, **archived flags moved to flags.archive.yaml after 1 release cycle**
  **Dependencies**: 4.2

- [ ] 4.4 Integrate flag creation into stacked-diff enqueue flow — auto-create flag when first stacked-diff package is enqueued
  **Dependencies**: 4.3, 1.4

- [ ] 4.5 Add `flag:` lock key registration for created flags
  **Dependencies**: 4.4

- [ ] 4.6 Write tests verifying flagged code passes static analysis — type checking (mypy) and linting (ruff) must pass regardless of flag state
  **Design decisions**: D6 (flagged code must pass static analysis)
  **Dependencies**: 4.2

## Phase 5: Integration (wp-integration)

- [ ] 5.1 Write integration tests — full train lifecycle: enqueue → compose → speculate → claim validate → pass CI → merge → cleanup. Include crash recovery scenario, BLOCKED recovery scenario, and ejection with re-speculation.
  **Spec scenarios**: All agent-coordinator scenarios
  **Dependencies**: 2.14, 3.7, 4.6

- [ ] 5.2 Extend MCP tools: add `compose_train`, `eject_from_train`, `get_train_status`, `report_spec_result` to coordination_mcp.py. All tools MUST enforce trust level checks per D11.
  **Dependencies**: 5.1

- [ ] 5.3 Extend HTTP API: add `/merge-train/compose`, `/merge-train/eject`, `/merge-train/status`, `/merge-train/report-result` endpoints to coordination_api.py. All endpoints MUST require `X-API-Key` auth and enforce trust levels per D11.
  **Dependencies**: 5.1

- [ ] 5.4 Add `affected_tests` as a new MCP tool and HTTP endpoint
  **Dependencies**: 3.7

- [ ] 5.5 Update `docs/parallel-agentic-development.md` with merge train architecture section
  **Dependencies**: 5.1

- [ ] 5.6 Update `docs/lessons-learned.md` with merge train patterns and conventions
  **Dependencies**: 5.1

- [ ] 5.7 Add database migration: GIN index on `metadata->'merge_queue'->'train_id'`, BTREE index on `metadata->'merge_queue'->'partition_id'`, BTREE index on `metadata->'merge_queue'->'train_position'`. Include EXPLAIN ANALYZE verification.
  **Dependencies**: 5.1

- [ ] 5.8 Integrate `refresh-architecture` trigger into compose_train flow — if architecture graph is stale (>6h), trigger refresh before train composition. If refresh unavailable, compose_train proceeds but flags all entries as "full test suite needed".
  **Dependencies**: 5.1, 3.7
