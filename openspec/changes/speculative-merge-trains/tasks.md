# Tasks: Speculative Merge Trains

**Change ID**: `speculative-merge-trains`

## Phase 1: Contracts and Schema (wp-contracts)

- [ ] 1.1 Write tests for GitAdapter protocol — mock subprocess, verify branch create/delete/merge operations
  **Spec scenarios**: agent-coordinator.2 (speculative ref creation), agent-coordinator.2 (cleanup)
  **Contracts**: contracts/internal/git-adapter-api.yaml
  **Design decisions**: D3 (git adapter layer)
  **Dependencies**: None

- [ ] 1.2 Create `git_adapter.py` — GitAdapter protocol + SubprocessGitAdapter implementation
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for merge train state machine — state transitions, metadata storage, train composition
  **Spec scenarios**: agent-coordinator.3 (state machine), agent-coordinator.1 (train composition)
  **Contracts**: contracts/internal/merge-train-api.yaml
  **Design decisions**: D1 (metadata JSONB storage)
  **Dependencies**: None

- [ ] 1.4 Extend `MergeStatus` enum and `MergeQueueEntry` dataclass with train fields (train_id, partition_id, train_position, speculative_ref, decomposition)
  **Dependencies**: 1.3

- [ ] 1.5 Define `flags.yaml` JSON schema and create schema validation script
  **Spec scenarios**: (feature flag system, no spec scenario — schema-level)
  **Design decisions**: D7 (env var with YAML fallback)
  **Dependencies**: None

- [ ] 1.6 Extend `work-packages.schema.json` with `decomposition` field (enum: "stacked" | "branch", default: "branch")
  **Dependencies**: None

## Phase 2: Train Engine (wp-train-engine)

- [ ] 2.1 Write tests for partition detection — lock key prefix grouping, overlap computation, cross-partition identification
  **Spec scenarios**: agent-coordinator.1 (independent entries), agent-coordinator.1 (cross-partition)
  **Contracts**: contracts/internal/merge-train-api.yaml
  **Design decisions**: D2 (prefix-based partitioning)
  **Dependencies**: 1.4

- [ ] 2.2 Implement `compute_partitions(entries)` — group entries by lock key prefix, detect cross-partition entries
  **Dependencies**: 2.1

- [ ] 2.3 Write tests for `compose_train()` — train creation from queue, speculative position assignment, empty queue handling
  **Spec scenarios**: agent-coordinator.1 (all scenarios)
  **Contracts**: contracts/internal/merge-train-api.yaml
  **Design decisions**: D1 (metadata storage), D2 (partitioning)
  **Dependencies**: 2.2

- [ ] 2.4 Implement `compose_train()` — fetch queued entries, compute partitions, assign positions, create speculative refs via git adapter
  **Dependencies**: 2.3, 1.2

- [ ] 2.5 Write tests for `eject_from_train()` — priority decrement, independence check, re-speculation trigger
  **Spec scenarios**: agent-coordinator.4 (eject with independent successors), agent-coordinator.4 (eject with dependent successors)
  **Design decisions**: D4 (priority eject)
  **Dependencies**: 2.4

- [ ] 2.6 Implement `eject_from_train(feature_id)` — eject entry, decrement priority, check independence of successors, trigger re-speculation if needed
  **Dependencies**: 2.5

- [ ] 2.7 Write tests for partition-aware merge execution — parallel partition merge, cross-partition serialization
  **Spec scenarios**: agent-coordinator.5 (parallel partition merge), agent-coordinator.5 (cross-partition ordering)
  **Dependencies**: 2.6

- [ ] 2.8 Implement partition-aware merge executor — fast-forward main per partition, serialize cross-partition entries
  **Dependencies**: 2.7

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

- [ ] 3.5 Write tests for `affected_tests()` query — single file, no coverage, stale graph fallback
  **Spec scenarios**: codebase-analysis.3 (all scenarios)
  **Design decisions**: D5 (architecture graph extension)
  **Dependencies**: 3.4

- [ ] 3.6 Implement `affected_tests(changed_files)` — reverse traversal from changed files to test nodes, stale graph detection, fallback
  **Dependencies**: 3.5

- [ ] 3.7 Register `test_linker` in `compile_architecture_graph.py` pipeline as Stage 3.5 (between db_linker and flow_tracer)
  **Dependencies**: 3.6

## Phase 4: Feature Flags (wp-feature-flags)

- [ ] 4.1 Write tests for flag resolution — env var override, YAML fallback, default disabled
  **Design decisions**: D7 (resolution order), D6 (stacked diffs with flag gating)
  **Dependencies**: 1.5

- [ ] 4.2 Create `feature_flags.py` — Flag dataclass, load_flags(yaml_path), resolve_flag(name), create_flag(change_id), enable_flag(name), archive_flag(name)
  **Dependencies**: 4.1

- [ ] 4.3 Write tests for flag lifecycle — create on first stacked-diff, enable on feature completion, archive after release
  **Dependencies**: 4.2

- [ ] 4.4 Integrate flag creation into stacked-diff enqueue flow — auto-create flag when first stacked-diff package is enqueued
  **Dependencies**: 4.3, 1.4

- [ ] 4.5 Add `flag:` lock key registration for created flags
  **Dependencies**: 4.4

## Phase 5: Integration (wp-integration)

- [ ] 5.1 Write integration tests — full train lifecycle: enqueue → compose → speculate → pass CI → merge → cleanup
  **Spec scenarios**: All agent-coordinator scenarios
  **Dependencies**: 2.8, 3.7, 4.5

- [ ] 5.2 Extend MCP tools: add `compose_train`, `eject_from_train`, `get_train_status` to coordination_mcp.py
  **Dependencies**: 5.1

- [ ] 5.3 Extend HTTP API: add `/merge-train/compose`, `/merge-train/eject`, `/merge-train/status` endpoints to coordination_api.py
  **Dependencies**: 5.1

- [ ] 5.4 Add `affected_tests` as a new MCP tool and HTTP endpoint
  **Dependencies**: 3.7

- [ ] 5.5 Update `docs/parallel-agentic-development.md` with merge train architecture section
  **Dependencies**: 5.1

- [ ] 5.6 Update `docs/lessons-learned.md` with merge train patterns and conventions
  **Dependencies**: 5.1

- [ ] 5.7 Add database migration for any new indexes needed on feature_registry.metadata JSONB (GIN index on merge_queue.train_id)
  **Dependencies**: 5.1
