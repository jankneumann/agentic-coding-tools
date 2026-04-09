# Tasks: Speculative Merge Trains

**Change ID**: `speculative-merge-trains`

## Phase 1: Contracts and Schema (wp-contracts)

- [x] 1.1 Write tests for GitAdapter protocol — mock subprocess, verify branch create/delete/merge operations, **injection prevention tests** (semicolons, backticks, $(), newlines in branch names)
  **Spec scenarios**: agent-coordinator.2 (speculative ref creation), agent-coordinator.2 (cleanup), agent-coordinator.7 (ref naming validation)
  **Contracts**: contracts/internal/git-adapter-api.yaml
  **Design decisions**: D3 (git adapter layer)
  **Dependencies**: None

- [x] 1.2 Create `git_adapter.py` — GitAdapter protocol + SubprocessGitAdapter implementation. MUST use `subprocess.run(args_list, shell=False)` exclusively. Validate ref names match `^refs/speculative/train-[a-f0-9]{8,32}/pos-\d{1,4}$`, branch names match `^[a-zA-Z0-9/_.-]{1,200}$`.
  **Dependencies**: 1.1

- [x] 1.3 Write tests for merge train data types — MergeTrainStatus enum, TrainEntry dataclass, TrainComposition dataclass
  **Spec scenarios**: agent-coordinator.3 (state machine)
  **Contracts**: contracts/internal/merge-train-api.yaml
  **Design decisions**: D1 (metadata JSONB storage)
  **Dependencies**: None

- [x] 1.4 Create `merge_train_types.py` — data types for train entries, partitions, and compositions. Extend `MergeStatus` enum with SPECULATING, SPEC_PASSED, EJECTED, ABANDONED states (ABANDONED = terminal state after max eject threshold; see D12). Add `eject_count: int` and `last_eject_reason: str | None` fields to TrainEntry metadata. This file is the shared type definition — `merge_queue.py` and `merge_train.py` both import from it.
  **Dependencies**: 1.3

- [x] 1.4a Write tests for `file_path_to_namespaces(path: str) -> set[str]` — the inverse mapping from a repo-relative file path to the set of lock-key namespaces that path could belong to. Tests MUST cover: `src/api/**` → `{"api:"}`, `src/db/schema/**` and `**/models/**` → `{"db:schema:"}`, `**/migrations/**` → `{"db:migration-slot"}`, `src/events/**` → `{"event:"}`, `contracts/**` → `{"contract:"}`, unrelated paths (e.g., `README.md`, `docs/**`) → `set()` (empty). Tests MUST include a "path maps to no namespace" case that the caller handles as "claim validation cannot verify, log info".
  **Spec scenarios**: agent-coordinator.8 (claim matches), agent-coordinator.8 (claim mismatch)
  **Design decisions**: D8 (post-speculation validation)
  **Dependencies**: 1.3

- [x] 1.4b Implement `file_path_to_namespaces(path: str) -> set[str]` in `merge_train_types.py`. The mapping is heuristic: it returns the set of namespaces the path is LIKELY related to, not a guarantee. The algorithm applies rules in priority order (first match wins unless multiple rules overlap — then union):
  - `contracts/**` → `{"contract:"}`
  - `**/migrations/**` or `supabase/migrations/**` → `{"db:migration-slot"}`
  - `**/schema*.py`, `**/models/**`, `**/models.py` → `{"db:schema:"}`
  - `src/api/**`, `**/routes/**`, `**/endpoints/**` → `{"api:"}`
  - `src/events/**`, `**/event_handlers/**` → `{"event:"}`
  - `flags.yaml` → `{"flag:"}`
  - All other paths → `set()` (claim validation skips these — they are file-level locks, not logical locks)
  The rules MUST be declared as a list of `(glob_pattern, namespace)` tuples at module level so they are unit-testable and extensible. Reference `docs/lock-key-namespaces.md` in the module docstring. Document that this is a HEURISTIC — unmapped paths do not fail claim validation, they are simply out-of-scope for logical-namespace checking (file-path locks still apply).
  **Dependencies**: 1.4a, 1.4

- [x] 1.5 Define `flags.yaml` JSON schema (`openspec/schemas/flags.schema.json`) and create schema validation script. Schema MUST include: flag name (max 64 chars), owner (change-id), status (disabled/enabled/archived), description (max 500 chars), created_at, archived_at.
  **Spec scenarios**: (feature flag system, no spec scenario — schema-level)
  **Design decisions**: D7 (env var with YAML fallback)
  **Dependencies**: None

- [x] 1.6 Extend `work-packages.schema.json` with `decomposition` field (enum: "stacked" | "branch", default: "branch")
  **Dependencies**: None

## Phase 2: Train Engine (wp-train-engine)

- [x] 2.1 Write tests for partition detection — lock key prefix grouping, overlap computation, cross-partition identification, **cross-partition cycle detection**, **1000-entry performance benchmark** (must complete in <5s)
  **Spec scenarios**: agent-coordinator.1 (independent entries), agent-coordinator.1 (cross-partition), agent-coordinator.9 (performance bound), agent-coordinator.9 (cycle detection)
  **Contracts**: contracts/internal/merge-train-api.yaml
  **Design decisions**: D2 (prefix-based partitioning)
  **Dependencies**: 1.4

- [x] 2.2 Implement `compute_partitions(entries)` — group entries by lock key prefix using union-find or multiset intersection (O(N·P) where P = prefixes per entry). Detect cross-partition entries. Detect cycles in cross-partition dependency graph.
  **Dependencies**: 2.1

- [x] 2.3 Write tests for `compose_train()` — train creation from queue, speculative position assignment, empty queue handling, **authorization checks** (trust level 3+ required), **1-entry train**, **100-entry train**
  **Spec scenarios**: agent-coordinator.1 (all scenarios), agent-coordinator.6 (authorization)
  **Contracts**: contracts/internal/merge-train-api.yaml
  **Design decisions**: D1 (metadata storage), D2 (partitioning), D11 (authorization)
  **Dependencies**: 2.2

- [x] 2.4 Implement `compose_train()` — fetch queued entries, verify caller trust level >= 3, compute partitions, assign positions, create speculative refs via git adapter using `git merge-tree --write-tree --messages <base> <branch>` (requires git 2.38+, no working directory IO).
  **Conflict detection contract**: The git adapter MUST detect conflicts via BOTH (a) non-zero exit code from `git merge-tree` AND (b) parsing `--messages` output for conflict markers. On conflict, return the `create_speculative_ref` output as `{success: False, tree_oid: None, commit_sha: None, conflict_files: [...], error: None}`; on success, return `{success: True, tree_oid: "<oid>", commit_sha: "<sha>", conflict_files: [], error: None}`; on non-conflict errors (git missing, network, disk), return `{success: False, tree_oid: None, commit_sha: None, conflict_files: [], error: "<message>"}`. Field names MUST match `contracts/internal/git-adapter-api.yaml`.
  **Tree caching**: Cache `(base_tree_oid, branch_tree_oid) -> result_tree_oid` per train_id to avoid redundant merge-tree computation across positions N and N+1 when the base doesn't change. The `tree_oid` field in the contract exists specifically to enable this caching.
  **Git version check**: On adapter startup, verify `git --version` is >= 2.38; fail fast with a clear error if not.
  **Dependencies**: 2.3, 1.2

- [x] 2.5 Write tests for post-speculation claim validation — claim matches actual changes, claim mismatch triggers BLOCKED, partition reassignment scenarios
  **Spec scenarios**: agent-coordinator.8 (claim matches), agent-coordinator.8 (claim mismatch)
  **Design decisions**: D8 (post-speculation validation)
  **Dependencies**: 2.4

- [x] 2.6 Implement post-speculation claim validation — call git adapter `get_changed_files(speculative_ref)`, then for each changed file compute `file_path_to_namespaces(path)` (from 1.4b). Union the results into `actual_namespaces`. Extract declared namespaces from `resource_claims` (take prefix before first `:`, e.g., `api:GET /v1/users` → `api:`). If `actual_namespaces - declared_namespaces` is non-empty, transition the entry to BLOCKED with reason `claim mismatch: actual changes span namespaces {extra} not declared in resource_claims`. Files with empty namespace set (heuristic says "unknown") are skipped from validation, not treated as mismatches.
  **Dependencies**: 2.5, 1.4b

- [x] 2.7 Write tests for `eject_from_train()` — priority decrement, independence check, re-speculation trigger, **authorization** (owner or trust level 3+), **ejection of last entry in partition**, **eject_count increment**, **ABANDONED transition at MAX_EJECT_COUNT**, **re-enqueue of ABANDONED entry resets eject_count and restores priority**
  **Spec scenarios**: agent-coordinator.R4 (eject with independent successors), agent-coordinator.R4 (eject with dependent successors), agent-coordinator.R4 (below max threshold), agent-coordinator.R4 (reaches max threshold → ABANDONED), agent-coordinator.R4 (manual re-enqueue of ABANDONED), agent-coordinator.R6 (eject authorization)
  **Design decisions**: D4 (priority eject), D11 (authorization), D12 (max eject threshold + ABANDONED)
  **Dependencies**: 2.6

- [x] 2.8 Implement `eject_from_train(feature_id)` — verify caller authorization, increment `eject_count`, check if `eject_count == MAX_EJECT_COUNT` (default 3): if so, transition to ABANDONED, notify owner via audit trail with reason "max_eject_exceeded", do NOT re-queue. Otherwise: transition to EJECTED, decrement priority by 10, check independence of successors via lock key overlap, trigger re-speculation for dependent successors. Also extend the existing `enqueue` path (task 2.16) to reset `eject_count = 0` and restore original `merge_priority` when an ABANDONED entry is manually re-enqueued.
  **Design decisions**: D4, D12
  **Dependencies**: 2.7

- [x] 2.9 Write tests for BLOCKED entry recovery — manual re-enqueue, automatic re-evaluation after 1 hour, permanent BLOCKED (conflict not resolved)
  **Spec scenarios**: agent-coordinator.10 (manual re-enqueue), agent-coordinator.10 (automatic re-evaluation)
  **Design decisions**: D9 (BLOCKED recovery lifecycle)
  **Dependencies**: 2.8

- [x] 2.10 Implement BLOCKED entry recovery — re-enqueue method for owners, auto-re-evaluation in compose_train for entries BLOCKED > 1 hour
  **Dependencies**: 2.9

- [x] 2.11 Write tests for partition-aware merge execution — parallel partition merge, cross-partition serialization, **speculative ref cleanup after merge**
  **Spec scenarios**: agent-coordinator.5 (parallel partition merge), agent-coordinator.5 (cross-partition ordering), agent-coordinator.7 (cleanup)
  **Dependencies**: 2.10

- [x] 2.12 Implement partition-aware merge executor per the wave algorithm in design.md D4 (build ready-graph → topo-sort with cycle detection → merge in waves within a coordinator transaction → cleanup speculative refs). Regular partitions fast-forward main to their final speculative ref; cross-partition entries fast-forward main to the entry's ref and rebase remaining partition speculative refs onto the new main tip. Must raise `TrainDeadlockError` if a wave is empty while entries remain pending. All speculative refs for the completed train MUST be deleted in the cleanup step.
  **Design decisions**: D4 (cross-partition merge ordering pseudo-code)
  **Dependencies**: 2.11

- [x] 2.13 Write tests for crash recovery — orphaned speculative refs from dead trains, startup cleanup routine
  **Spec scenarios**: agent-coordinator.7 (cleanup on crash), agent-coordinator.7 (TTL garbage collection)
  **Dependencies**: 2.12

- [x] 2.14 Implement crash recovery — startup routine to enumerate refs/speculative/ and delete orphans, watchdog integration for TTL-based GC of refs older than 6 hours
  **Dependencies**: 2.13

- [x] 2.15 Write tests for extended `enqueue` — accepts `decomposition` field (default "branch"), rejects invalid values, auto-creates feature flag via `feature_flags.create_flag()` on first stacked-diff enqueue for a feature, reuses existing flag on subsequent stacked-diff enqueues, registers `flag:` lock key via the existing lock service
  **Spec scenarios**: agent-coordinator.R13 (all 3 scenarios), agent-coordinator.R12 (auto-create), agent-coordinator.R12 (reuse existing flag)
  **Contracts**: contracts/internal/merge-train-api.yaml (if enqueue contract extended)
  **Design decisions**: D6 (stacked diffs with flag gating), D7 (flag resolution)
  **Dependencies**: 2.14, 4.2

- [x] 2.16 Extend `enqueue` method in `merge_queue.py` — accept optional `decomposition: Literal["stacked", "branch"] = "branch"` and `stack_position: int | None = None` parameters. Validate decomposition value (reject unknowns). On first stacked-diff enqueue for a feature, call `feature_flags.create_flag(change_id)` to auto-create the flag (idempotent — no-op if already exists). Register `flag:<name>` lock key via existing lock service. Store `decomposition` and `stack_position` in entry metadata.
  **Dependencies**: 2.15

## Phase 3: Build Graph Extension (wp-build-graph)

- [x] 3.1 Write tests for test node extraction — naming convention discovery, parametrized test handling, node metadata
  **Spec scenarios**: codebase-analysis.1 (test function discovery), codebase-analysis.1 (parametrized tests)
  **Contracts**: contracts/internal/test-linker-output.yaml
  **Design decisions**: D5 (architecture graph extension)
  **Dependencies**: None

- [x] 3.2 Create `test_linker.py` insight module — extract test nodes from Python test files, add to architecture graph
  **Dependencies**: 3.1

- [x] 3.3 Write tests for TEST_COVERS edge creation — direct import mapping, standard library exclusion
  **Spec scenarios**: codebase-analysis.2 (direct import edge), codebase-analysis.2 (no standard library edge)
  **Contracts**: contracts/internal/test-linker-output.yaml
  **Dependencies**: 3.2

- [x] 3.4 Implement TEST_COVERS edge creation in `test_linker.py` — trace imports from test files to source modules, create edges with confidence/evidence
  **Dependencies**: 3.3

- [x] 3.5 Write tests for `affected_tests()` query — single file, no coverage, stale graph fallback, **traversal bound (10K nodes)**, **cycle detection**, **performance benchmark (<100ms for 10K-node graph)**
  **Spec scenarios**: codebase-analysis.3 (all scenarios including traversal bound)
  **Design decisions**: D5 (architecture graph extension), D10 (traversal bounds)
  **Dependencies**: 3.4

- [x] 3.6 Implement `affected_tests(changed_files)` — reverse BFS from changed files to test nodes, stop at test nodes, visited-set cycle detection, 10K node bound with fallback to None, stale graph detection (>24h)
  **Dependencies**: 3.5

- [x] 3.7 Register `test_linker` in `compile_architecture_graph.py` pipeline. This is NOT a drop-in insert — the existing pipeline runs stages 1-3 sequentially (graph mutations) then stages 4-6 concurrently on an in-memory read-only copy. Adding test_linker requires:
  - (a) Insert `test_linker.run(input_dir, output_path=graph_path)` as a new Stage 3b between `db_linker` (Stage 3) and the in-memory graph load for Stages 4-6 (~10 lines added to orchestration)
  - (b) Update the module docstring (lines 1-30) to document the new stage
  - (c) Extend existing pipeline integration test in `refresh-architecture/tests/test_compile_architecture_graph.py` to verify TEST_COVERS edges appear in the output graph
  - (d) Verify the concurrent stages (flow_tracer, impact_ranker, parallel_zones) correctly read the new test nodes/edges — they should be transparent since the graph is JSON-shaped
  - (e) Estimated diff: ~50 LOC in compile_architecture_graph.py + insights/__init__.py (export test_linker)
  **Dependencies**: 3.6

- [x] 3.8 Implement the server side of the refresh-architecture RPC per `contracts/internal/refresh-architecture-rpc.yaml`. Expose `is_graph_stale`, `trigger_refresh`, and `get_refresh_status` as a callable surface that the coordinator can reach. Create new module `skills/refresh-architecture/scripts/rpc_server.py`:
  - `is_graph_stale` reads `architecture.graph.json` mtime and node count
  - `trigger_refresh` spawns `refresh_architecture.sh` as a detached subprocess, stores the refresh_id → subprocess mapping in an in-memory dict (for now — no persistence needed), returns idempotently if one is already running
  - `get_refresh_status` checks the subprocess state
  - Transport: callable via `python -m rpc_server <method> <json-args>` for subprocess-style invocation from the coordinator (avoids needing a long-running service). Document this in the module docstring.
  **Contracts**: contracts/internal/refresh-architecture-rpc.yaml
  **Dependencies**: 3.7

## Phase 4: Feature Flags (wp-feature-flags)

- [x] 4.1 Write tests for flag resolution — env var override, YAML fallback, default disabled, **fail-closed for undeclared FF_* vars**, **flag with type check/lint verification**
  **Design decisions**: D7 (resolution order), D6 (stacked diffs with flag gating)
  **Dependencies**: 1.5

- [x] 4.2 Create `feature_flags.py` — Flag dataclass, load_flags(yaml_path), resolve_flag(name), create_flag(change_id), enable_flag(name), archive_flag(name). Fail-closed behaviors:
  - Reject any `FF_*` env var not declared in flags.yaml (log warning, use YAML/default value).
  - If `flags.yaml` is missing entirely: treat as empty registry (all flags default to disabled), log a one-time startup warning. Do NOT raise — the coordinator must boot without flags.yaml to support bootstrapping a new repo.
  - If `flags.yaml` exists but is malformed (YAML parse error, schema violation): raise `FlagsConfigError` at startup — this is a deployment bug, fail loud.
  - If a flag referenced in code is not in `flags.yaml`: `resolve_flag()` returns `False` (disabled) and logs a warning. This makes flag removal safe — orphaned `is_enabled("OLD_FLAG")` calls degrade to disabled, not crash.
  **Dependencies**: 4.1

- [x] 4.3 Write tests for flag lifecycle — `create_flag(change_id)` is idempotent (returns existing flag if already present), `enable_flag(name)` transitions disabled→enabled, archival is deferred to Phase 2 (see proposal Scope Boundaries)
  **Dependencies**: 4.2

- [x] 4.4 Expose `create_flag(change_id)` as a public module function in `feature_flags.py` — used by `merge_queue.enqueue` (task 2.16) to auto-create flags on first stacked-diff enqueue. Must be idempotent: returns the existing Flag object if one already exists for the change_id. Writes to `flags.yaml` atomically (write to temp file, fsync, rename).
  **Dependencies**: 4.2

- [x] 4.5 Integrate `flag:` lock key registration into `create_flag` — when a new flag is created, also register `flag:<name>` as a lock key via the existing lock service. Note: the actual enqueue-time invocation lives in task 2.16 (wp-train-engine); this task only ensures `create_flag` emits the lock registration call.
  **Dependencies**: 4.4

- [x] 4.6 Write tests verifying flagged code passes static analysis — type checking (mypy) and linting (ruff) must pass regardless of flag state
  **Design decisions**: D6 (flagged code must pass static analysis)
  **Dependencies**: 4.2

## Phase 5: Integration (wp-integration)

- [x] 5.1 Write integration tests — full train lifecycle: enqueue → compose → speculate → claim validate → pass CI → merge → cleanup. Include crash recovery scenario, BLOCKED recovery scenario, and ejection with re-speculation.
  **Spec scenarios**: All agent-coordinator scenarios
  **Dependencies**: 2.14, 3.7, 4.6

- [x] 5.2 Extend MCP tools: add `compose_train`, `eject_from_train`, `get_train_status`, `report_spec_result` to coordination_mcp.py. All tools MUST enforce trust level checks per D11.
  **Dependencies**: 5.1

- [x] 5.3 Extend HTTP API: add `/merge-train/compose`, `/merge-train/eject`, `/merge-train/status`, `/merge-train/report-result` endpoints to coordination_api.py. All endpoints MUST require `X-API-Key` auth and enforce trust levels per D11.
  **Dependencies**: 5.1

- [x] 5.4 Add `affected_tests` as a new MCP tool and HTTP endpoint
  **Dependencies**: 3.7

- [x] 5.5 Update `docs/parallel-agentic-development.md` with merge train architecture section
  **Dependencies**: 5.1

- [x] 5.6 Update `docs/lessons-learned.md` with merge train patterns and conventions
  **Dependencies**: 5.1

- [x] 5.7 Add database migration: GIN index on `metadata->'merge_queue'->'train_id'`, BTREE index on `metadata->'merge_queue'->'partition_id'`, BTREE index on `metadata->'merge_queue'->'train_position'`. Include EXPLAIN ANALYZE verification.
  **Dependencies**: 5.1

- [x] 5.8a Implement the client side of the refresh-architecture RPC in the coordinator (`agent-coordinator/src/refresh_rpc_client.py`). Wraps the three methods defined in `contracts/internal/refresh-architecture-rpc.yaml` (`is_graph_stale`, `trigger_refresh`, `get_refresh_status`). Must honor the failure-mode contract: if the RPC subsystem is unreachable, log a warning and return `RefreshClientUnavailable` sentinels rather than raising. Include connection timeout (5s) and method timeout (30s for is_graph_stale, 10s for trigger_refresh, 5s for get_refresh_status).
  **Contracts**: contracts/internal/refresh-architecture-rpc.yaml
  **Dependencies**: 5.1, 3.8

- [x] 5.8 Integrate the `refresh-architecture` trigger into compose_train flow using the 5.8a client — before composing a train, call `is_graph_stale(max_age_hours=6)`. If stale and no refresh is in flight, call `trigger_refresh` and either (a) wait up to 60s (polling `get_refresh_status` every 5s) for completion or (b) proceed with a "full test suite needed" flag on all entries (configurable per deployment). If the client returns `RefreshClientUnavailable`, log a warning and proceed with the full-suite fallback (no exception raised — must not block train composition on an unavailable subsystem).
  **Dependencies**: 5.1, 3.7, 5.8a

- [x] 5.9 Implement the periodic compose_train sweep. compose_train is triggered two ways: (1) on-demand via the MCP/HTTP endpoints from 5.2/5.3 (called on each enqueue), and (2) by a periodic sweep that runs every `MERGE_TRAIN_SWEEP_INTERVAL_SECONDS` (default 60s, configurable via env var). The sweep owner is a new background task registered in the coordinator startup (`agent-coordinator/src/coordination_service.py` or equivalent lifecycle hook), using `asyncio.create_task` with cancellation on shutdown. The sweep task MUST:
  - Be idempotent (no-op if no QUEUED entries)
  - Honor the existing authorization model (sweep runs as the coordinator service identity, trust level 3)
  - Log start/end/duration of each sweep at INFO level
  - Catch and log exceptions without crashing the task (it must keep running across errors)
  - Be testable via a "single-pass" mode that runs once and returns (for integration tests)
  **Spec scenarios**: new scenario under R1 covering periodic invocation
  **Dependencies**: 5.2, 5.3
