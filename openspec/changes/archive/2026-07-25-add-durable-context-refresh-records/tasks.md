# Tasks: Add durable context refresh records

> Change ID: `add-durable-context-refresh-records`
> Selected approach: Git-common-dir ledger plus deterministic committed manifest
> TDD rule: every implementation task depends on the test task that proves it.

## 1. Contract models and installed schemas

- [x] 1.1 Write schema contract tests. **Size: S**
  - Cover valid examples, malformed records, unknown versions, duplicate producer IDs, conditional remediation, semantic fallback references, repository-relative artifact paths, and offline install-asset reference resolution.
  - **Spec scenarios**: project-context-refresh-records.1, .3, .8, .9, .10, .14, .16, .17, .18
  - **Contracts**: `contracts/context-refresh-types.schema.json`, `contracts/context-refresh-operation.schema.json`, `contracts/context-refresh-manifest.schema.json`
  - **Design decisions**: D1, D4, D5, D6
  - **Dependencies**: None
- [x] 1.2 Install the versioned schema assets. **Size: S**
  - Copy the three reviewed contracts into `skills/project-context-runtime/install_assets/openspec/schemas/` without changing their IDs or relative references.
  - **Dependencies**: 1.1
- [x] 1.3 Add strict project-context-runtime models. **Size: M**
  - Implement strict dataclasses/enums and `from_dict`/`to_dict` conversion without permissive defaults for freshness-bearing fields.
  - Reject unknown schema versions and duplicate producer IDs at the model boundary.
  - **Dependencies**: 1.1, 1.2
- [x] 1.4 Write atomic persistence tests. **Size: S**
  - Cover same-directory temporary files, file fsync, atomic replacement, parent-directory fsync, unchanged-byte detection, and cleanup after write failure.
  - **Spec scenarios**: project-context-refresh-records.5, project-context-refresh-records.6, project-context-refresh-records.12, project-context-refresh-records.15
  - **Contracts**: `contracts/context-refresh-operation.schema.json`, `contracts/context-refresh-manifest.schema.json`
  - **Design decisions**: D3, D4
  - **Dependencies**: 1.2
- [x] 1.5 Implement the shared atomic persistence primitive. **Size: S**
  - Add `scripts/atomic.py` as runtime-core infrastructure used by both the operation store and manifest writer.
  - Return whether canonical bytes changed so same-revision manifest writes remain observable no-ops.
  - **Dependencies**: 1.4
- [x] Checkpoint: run tests, review diff, verify scope.

## 2. Durable operation store

- [x] 2.1 Write operation-store tests. **Size: M**
  - Cover deterministic identity, idempotent create-or-load, different revision separation, cross-process reload, concurrent creation, interrupted atomic writes, retry transitions, and malformed-record refusal.
  - **Spec scenarios**: project-context-refresh-records.1, .2, .3, .4, .5, .6, .7, .18
  - **Contracts**: `contracts/context-refresh-operation.schema.json`
  - **Design decisions**: D2, D3, D5
  - **Dependencies**: 1.3
- [x] 2.2 Implement the Git-common-dir operation store. **Size: M**
  - Use deterministic IDs, per-operation advisory locks, the shared atomic persistence primitive, and validated monotonic transitions.
  - Expose `create_or_load`, `load`, `begin_attempt`, `record_producer_result`, `record_semantic_index`, and `finalize`.
  - Resolve the common directory through Git; never derive the store from a worktree-local `.git` file path.
  - **Dependencies**: 1.5, 2.1
- [x] Checkpoint: run tests, review diff, verify scope.

## 3. Deterministic manifest writer

- [x] 3.1 Write deterministic manifest tests. **Size: M**
  - Cover canonical byte output, stable ordering, changed-artifact inventory, validation summaries, degraded fallback reporting, external semantic references, same-revision reruns, and atomic replacement.
  - **Spec scenarios**: project-context-refresh-records.8, .9, .10, .11, .12, .13, .14, .15, .17
  - **Contracts**: `contracts/context-refresh-types.schema.json`, `contracts/context-refresh-manifest.schema.json`
  - **Design decisions**: D4, D5, D6
  - **Dependencies**: 1.3
- [x] 3.2 Implement canonical manifest projection. **Size: M**
  - Write the validated repository artifact through the shared atomic replacement primitive.
  - Sort producer results, artifact paths, validations, remediation entries, and fallbacks before serialization.
  - Exclude attempt timestamps, lock metadata, absolute paths, and other volatile operation fields.
  - Validate the complete projection before replacing the target manifest.
  - **Dependencies**: 1.5, 3.1
- [x] Checkpoint: run tests, review diff, verify scope.

## 4. Runtime integration and documentation

- [x] 4.1 Write the cross-process integration test. **Size: M**
  - Exercise the supported runtime facade to create an operation in one process, resume it in a second process, emit a manifest in a managed worktree, and prove a duplicate request reuses the original operation ID.
  - **Spec scenarios**: project-context-refresh-records.2, .4, .5, .6, .12, .15, .18
  - **Contracts**: all files under `contracts/`
  - **Design decisions**: D1, D2, D3, D4, D5
  - **Dependencies**: 2.2, 3.2
- [x] 4.2 Expose the supported runtime facade. **Size: S**
  - Export only the reviewed model, store, and manifest entry points from `scripts/__init__.py`; keep atomic helpers private.
  - **Spec scenarios**: project-context-refresh-records.2, .4, .12, .15
  - **Contracts**: all files under `contracts/`
  - **Design decisions**: D1, D4, D5
  - **Dependencies**: 4.1
- [x] 4.3 Document project-context refresh records. **Size: S**
  - Cover operation lifecycle, storage boundary, manifest fields, consumer responsibilities, cleanup behavior, and fail-closed recovery in `docs/project-context-refresh.md`.
  - **Spec scenarios**: project-context-refresh-records.7, .9, .10, .14, .16, .17
  - **Contracts**: all files under `contracts/`
  - **Design decisions**: D1-D7
  - **Dependencies**: 4.2
- [x] 4.4 Run final validation. **Size: S**
  - Run strict OpenSpec validation, schema example validation, project-context-runtime tests, install-asset tests, ruff, and mypy for touched Python modules.
  - **Dependencies**: 4.2, 4.3
- [x] Checkpoint: run tests, review diff, verify scope.

## Completion criteria

- Every SHALL/MUST scenario is covered by at least one test task.
- No implementation task is larger than M; no task is XL.
- `openspec validate add-durable-context-refresh-records --strict` passes.
- JSON Schema examples validate with Draft 2020-12; unknown versions fail.
- Repeated execution for one repository and revision is byte-idempotent for the manifest and identity-idempotent for the operation record.
