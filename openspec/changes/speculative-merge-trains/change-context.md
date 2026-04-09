# Change Context: speculative-merge-trains

**Change ID**: `speculative-merge-trains`
**Plan Revision**: 5
**Contracts Revision**: 3

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-coordinator.R1 | specs/agent-coordinator/spec.md#Requirement-Speculative-Merge-Train-Composition-R1 | compose_train groups entries into partitions by lock key prefix; periodic sweep every 60s | contracts/internal/merge-train-api.yaml#/compose_train | D2, D11 | agent-coordinator/src/merge_train.py; agent-coordinator/src/merge_queue.py; agent-coordinator/src/merge_train_service.py (MergeTrainSweeper); agent-coordinator/src/coordination_api.py (lifespan wiring); agent-coordinator/src/coordination_mcp.py (MCP tools); agent-coordinator/supabase/migrations/020_merge_train_indexes.sql | tests/test_merge_train.py::test_compose_train_partitions_by_prefix; tests/test_merge_train_service.py::TestMergeTrainSweeper; tests/test_merge_train_service.py::TestFullLifecycle | --- |
| agent-coordinator.R2 | specs/agent-coordinator/spec.md#Requirement-Speculative-Branch-Management-R2 | Git adapter creates/deletes speculative refs per train position | contracts/internal/git-adapter-api.yaml#/create_speculative_ref | D3 | agent-coordinator/src/git_adapter.py; agent-coordinator/src/merge_train.py | tests/test_git_adapter.py::test_create_speculative_ref_position_1; tests/test_git_adapter.py::test_cleanup_after_train | --- |
| agent-coordinator.R3 | specs/agent-coordinator/spec.md#Requirement-Train-Entry-State-Machine-R3 | QUEUED→SPECULATING→SPEC_PASSED→MERGING→MERGED with EJECTED/BLOCKED/ABANDONED branches | contracts/internal/merge-train-api.yaml#/report_spec_result | D1, D12 | agent-coordinator/src/merge_train_types.py; agent-coordinator/src/merge_train.py | tests/test_merge_train_types.py::test_status_transitions; tests/test_merge_train.py::test_report_spec_result_pass_and_fail | --- |
| agent-coordinator.R4 | specs/agent-coordinator/spec.md#Requirement-Priority-Eject-Recovery-R4 | eject_from_train decrements priority by 10, continues independent successors | contracts/internal/merge-train-api.yaml#/eject_from_train | D4 | agent-coordinator/src/merge_train.py | tests/test_merge_train.py::test_eject_independent_successors; tests/test_merge_train.py::test_eject_dependent_successors | --- |
| agent-coordinator.R5 | specs/agent-coordinator/spec.md#Requirement-Partition-Aware-Merge-R5 | Wave-based merge executor with cross-partition ordering via TrainDeadlockError invariant | --- | D4 | agent-coordinator/src/merge_train.py | tests/test_merge_train.py::test_merge_partitions_parallel; tests/test_merge_train.py::test_cross_partition_merge_order | --- |
| agent-coordinator.R6 | specs/agent-coordinator/spec.md#Requirement-Train-Operation-Authorization-R6 | compose_train requires trust>=3; eject requires ownership or trust>=3 | contracts/internal/merge-train-api.yaml | D11 | agent-coordinator/src/merge_train.py | tests/test_merge_train.py::test_compose_train_requires_operator_trust; tests/test_merge_train.py::test_eject_ownership_enforcement | --- |
| agent-coordinator.R7 | specs/agent-coordinator/spec.md#Requirement-Speculative-Ref-Security-and-Cleanup-R7 | Ref name regex validation, shell=False, crash recovery, TTL>6h GC | contracts/internal/git-adapter-api.yaml | D3 | agent-coordinator/src/git_adapter.py; agent-coordinator/src/merge_train.py | tests/test_git_adapter.py::test_ref_name_validation; tests/test_git_adapter.py::test_injection_prevention; tests/test_merge_train.py::test_crash_recovery | --- |
| agent-coordinator.R8 | specs/agent-coordinator/spec.md#Requirement-Post-Speculation-Claim-Validation-R8 | file_path_to_namespaces heuristic compares actual changes to declared claims | --- | D8 | agent-coordinator/src/merge_train_types.py; agent-coordinator/src/merge_train.py | tests/test_merge_train_types.py::test_file_path_to_namespaces; tests/test_merge_train.py::test_claim_validation_mismatch_blocks | --- |
| agent-coordinator.R9 | specs/agent-coordinator/spec.md#Requirement-BLOCKED-Entry-Recovery-R9 | Manual re-enqueue or auto-re-evaluation after 1h | --- | D9 | agent-coordinator/src/merge_train.py | tests/test_merge_train.py::test_blocked_manual_reenqueue; tests/test_merge_train.py::test_blocked_auto_reeval_after_1h | --- |
| agent-coordinator.R10 | specs/agent-coordinator/spec.md#Requirement-Partition-Detection-Performance-R10 | O(N·P) partition detection; cross-partition cycle detection | --- | D2 | agent-coordinator/src/merge_train.py | tests/test_merge_train.py::test_partition_detection_1000_entries_benchmark; tests/test_merge_train.py::test_cross_partition_cycle_detection | --- |
| agent-coordinator.R11 | specs/agent-coordinator/spec.md#Requirement-Speculative-Ref-Creation-Performance-R11 | git merge-tree, tree_oid caching, parallel partitions | contracts/internal/git-adapter-api.yaml#/create_speculative_ref | D3 | agent-coordinator/src/git_adapter.py | tests/test_git_adapter.py::test_merge_tree_success; tests/test_git_adapter.py::test_merge_tree_conflict | --- |
| agent-coordinator.R12 | specs/agent-coordinator/spec.md#Requirement-Automatic-Flag-Creation-for-Stacked-Diff-Features-R12 | First stacked enqueue auto-creates flag; subsequent reuses | --- | D6, D7 | agent-coordinator/src/merge_queue.py; agent-coordinator/src/feature_flags.py | tests/test_merge_queue.py::test_enqueue_stacked_auto_creates_flag; tests/test_merge_queue.py::test_enqueue_stacked_reuses_existing_flag | --- |
| agent-coordinator.R13 | specs/agent-coordinator/spec.md#Requirement-Merge-Queue-Enqueue-Extended-R13 | enqueue accepts decomposition=stacked\|branch (default branch) | contracts/internal/merge-train-api.yaml | D6 | agent-coordinator/src/merge_queue.py | tests/test_merge_queue.py::test_enqueue_stacked_field; tests/test_merge_queue.py::test_enqueue_default_branch | --- |
| agent-coordinator.R14 | specs/agent-coordinator/spec.md#Requirement-Max-Eject-Threshold-and-ABANDONED-State-R14 | eject_count, MAX_EJECT_COUNT=3, ABANDONED terminal, manual re-enqueue resets | --- | D12 | agent-coordinator/src/merge_train.py; agent-coordinator/src/merge_train_types.py | tests/test_merge_train.py::test_eject_count_increments; tests/test_merge_train.py::test_max_eject_transitions_to_abandoned; tests/test_merge_train.py::test_reenqueue_abandoned_resets | --- |
| codebase-analysis.R1 | specs/codebase-analysis/spec.md#Requirement-Test-Node-Extraction | test_linker extracts test_function/test_class nodes with tags | contracts/internal/test-linker-output.yaml | D5 | skills/refresh-architecture/scripts/insights/test_linker.py | tests/test_test_linker.py::test_extract_test_functions; tests/test_test_linker.py::test_parametrized_tag | --- |
| codebase-analysis.R2 | specs/codebase-analysis/spec.md#Requirement-Test-Coverage-Edge-Creation | TEST_COVERS edges from direct imports; stdlib excluded | contracts/internal/test-linker-output.yaml | D5 | skills/refresh-architecture/scripts/insights/test_linker.py | tests/test_test_linker.py::test_direct_import_edge; tests/test_test_linker.py::test_stdlib_excluded | --- |
| codebase-analysis.R3 | specs/codebase-analysis/spec.md#Requirement-Affected-Test-Query | affected_tests(files, graph_path) -> list or None for fallback | contracts/internal/test-linker-output.yaml#/affected_tests_query | D5, D10 | skills/refresh-architecture/scripts/affected_tests.py; agent-coordinator/src/refresh_rpc_client.py (compute_affected_tests); agent-coordinator/src/coordination_mcp.py (affected_tests tool); agent-coordinator/src/coordination_api.py (/merge-train/affected-tests) | tests/test_affected_tests.py::test_single_file_with_test; tests/test_affected_tests.py::test_stale_graph_returns_none; tests/test_affected_tests.py::test_10k_bound; tests/test_refresh_rpc_client.py::TestComputeAffectedTests | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Store train state in feature_registry.metadata JSONB | `merge_queue.py`, `merge_train.py` use `METADATA_KEY="merge_queue"` sub-dict with train fields | Unified data model, no new migration for state split |
| D2 | Partition detection via lock key prefix grouping (O(N·P)) | `merge_train.compute_partitions()` uses union-find on entries' claim prefixes | Deterministic, fast, reuses 9 existing namespaces without build graph dependency |
| D3 | Git adapter protocol isolates git operations | `src/git_adapter.py` Protocol + `SubprocessGitAdapter` | Keeps coordinator testable; prevents command injection via shell=False + regex validation |
| D4 | Priority eject with independence check + wave merge | `eject_from_train()` decrements priority by -10; `merge_partition()` uses wave algorithm with TrainDeadlockError | Cheapest recovery for independent entries; wave model serializes only where necessary |
| D5 | Affected-test via architecture graph extension | `test_linker.py` insight module creates TEST_COVERS edges; `affected_tests.py` runs reverse BFS | Reuses existing traversal machinery; incremental phases ship value early |
| D6 | Stacked diffs with feature flag gating | `enqueue(..., decomposition="stacked")` auto-creates flag via `feature_flags.create_flag()` | Maximum merge train throughput; partial features dormant but visible |
| D7 | Flag resolution order FF_*env → flags.yaml → disabled, fail-closed | `feature_flags.resolve_flag()`; undeclared FF_* vars rejected | Per-environment override without code changes; defense-in-depth |
| D8 | Post-speculation claim validation via file_path_to_namespaces | `merge_train_types.PATH_TO_NAMESPACE_RULES`; heuristic mapping with empty-set opt-out | Catches agent-declared claim mismatches without coupling to code-to-lock mapping at enqueue time |
| D9 | BLOCKED recovery: manual re-enqueue OR auto-reeval after 1h | `merge_train.reenqueue_blocked()`, `compose_train` auto-re-evaluation | Handles both agent-fixable and merge-order-fixable conflicts |
| D10 | affected_tests reverse BFS bounded to 10K visits | `affected_tests.py` tracks visited set; returns None over bound | Predictable <100ms latency on 10K-node monorepo graphs |
| D11 | Train operations require trust level ≥ 3 or ownership | `merge_train._check_trust_level()` integrates profiles service | Reuses existing profile authorization; prevents unauthorized train manipulation |
| D12 | MAX_EJECT_COUNT=3 with ABANDONED terminal state | `merge_train_types.MAX_EJECT_COUNT`; `eject_from_train` increments count, transitions to ABANDONED at threshold | Bounds CI waste from broken entries; recovery via manual re-enqueue resets |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

*(Populated during parallel-review-implementation; empty for sequential implementation.)*

## Coverage Summary

- **Requirements traced**: 17/17 (14 agent-coordinator + 3 codebase-analysis)
- **Tests mapped**: 17 requirements have at least one test
- **Evidence collected**: 17/17 — full non-e2e suite passes (`1798 passed, 64 skipped` on the coordinator venv after wp-integration changes)
- **Gaps identified**: ---
- **Deferred items**:
  - Transitive (Phase 2) affected-test analysis — Phase 1 ships import-level only
  - Fixture-aware test analysis — deferred to Phase 2 per proposal scope boundaries
  - Feature flag archival — deferred to Phase 2 pending "release cycle" definition
  - CI integration (GitHub Actions merge_group trigger) — deferred to Phase 2

## Phase 5 (wp-integration) Files Changed

**Source:**
- `agent-coordinator/src/refresh_rpc_client.py` (new) — `RefreshRpcClient` + `compute_affected_tests()` (task 5.8a, 5.4)
- `agent-coordinator/src/merge_train_service.py` (new) — DB-backed `MergeTrainService` + `MergeTrainSweeper` periodic sweep (task 5.9)
- `agent-coordinator/src/coordination_mcp.py` (modified) — `compose_train`, `eject_from_train`, `get_train_status`, `report_spec_result`, `affected_tests` MCP tools (tasks 5.2, 5.4)
- `agent-coordinator/src/coordination_api.py` (modified) — `/merge-train/*` HTTP endpoints + sweeper lifespan wiring (tasks 5.3, 5.9)
- `agent-coordinator/src/merge_train_types.py` (modified) — `DEFAULT_SWEEP_INTERVAL_SECONDS` constant

**Database:**
- `agent-coordinator/supabase/migrations/020_merge_train_indexes.sql` (new) — GIN + BTREE expression indexes on `metadata->'merge_queue'` sub-document (task 5.7)

**Tests:**
- `agent-coordinator/tests/test_refresh_rpc_client.py` (new) — 20 tests (RPC client + `compute_affected_tests`)
- `agent-coordinator/tests/test_merge_train_service.py` (new) — 25 tests (service layer, sweeper, full lifecycle integration) covering task 5.1
- `agent-coordinator/tests/test_merge_train_types.py` (modified) — sweep interval constant import

**Docs:**
- `docs/parallel-agentic-development.md` (modified) — "Speculative Merge Trains" subsection (task 5.5)
- `docs/lessons-learned.md` (modified) — "Speculative Merge Train Patterns" section (task 5.6)
