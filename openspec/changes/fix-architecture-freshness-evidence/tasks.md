# Tasks — fix-architecture-freshness-evidence

Sizes follow the plan-feature sizing reference. No task is L or XL.

## 1. Provenance artifact tiers

- [x] 1.1 Write contract tests for the v2 provenance schema — **S**
  **Spec scenarios**: architecture-refresh.16
  **Design decisions**: D1 (tier required), D2 (const 2, not enum)
  **Contracts**: `openspec/schemas/architecture-provenance.schema.json`
  **Files**: `skills/tests/refresh-architecture-contracts/test_architecture_provenance_contract.py`
  **Dependencies**: None
  Assert `schema_version` is `const: 2`; assert an artifact entry without `tier` is
  rejected; assert a `tier` outside `{committed, local-cache}` is rejected.

- [x] 1.2 Write freshness tests for an absent local-cache artifact — **S**
  **Spec scenarios**: architecture-refresh.17
  **Files**: `skills/refresh-architecture/scripts/tests/test_provenance.py`
  **Dependencies**: None

- [x] 1.3 Write freshness tests for a present-but-modified local-cache artifact — **XS**
  **Spec scenarios**: architecture-refresh.18
  **Files**: `skills/refresh-architecture/scripts/tests/test_provenance.py`
  **Dependencies**: None

- [x] 1.4 Write a freshness test for the legacy schema-version reason code — **XS**
  **Spec scenarios**: architecture-refresh.19
  **Design decisions**: D3 (distinct reason code)
  **Files**: `skills/refresh-architecture/scripts/tests/test_provenance.py`
  **Dependencies**: None

- [ ] Checkpoint: run the provenance suite, confirm the four new tests fail for the right reason

- [x] 1.5 Publish the v2 provenance schema — **S**
  **Spec scenarios**: architecture-refresh.16
  **Design decisions**: D1, D2
  **Files**: `openspec/schemas/architecture-provenance.schema.json`
  **Dependencies**: 1.1

- [x] 1.6 Add the `PROVENANCE_SCHEMA_VERSION_MISMATCH` reason code — **XS**
  **Spec scenarios**: architecture-refresh.19
  **Design decisions**: D3
  **Files**: `skills/refresh-architecture/scripts/arch_utils/provenance.py`
  **Dependencies**: 1.4

- [ ] Checkpoint: run `pytest skills/refresh-architecture/scripts/tests skills/tests/refresh-architecture-contracts`, review the diff, confirm scope

- [x] 1.7 Extend `_OWNED_TOP_LEVEL` entries to carry a tier — **S**
  **Design decisions**: D1, D7 (which artifacts move)
  **Files**: `skills/refresh-architecture/scripts/arch_utils/provenance.py`
  **Dependencies**: 1.5
  `(name, required)` pairs become `(name, required, tier)` triples. Assign
  `local-cache` to `treesitter_enrichment.json`, `python_analysis.json`,
  `parallel_zones.json`; `committed` to every other entry.

- [x] 1.8 Record the tier in `build_provenance` — **S**
  **Spec scenarios**: architecture-refresh.16
  **Files**: `skills/refresh-architecture/scripts/arch_utils/provenance.py`
  **Dependencies**: 1.7

- [x] 1.9 Make `check_freshness` tier-aware — **M**
  **Spec scenarios**: architecture-refresh.17, architecture-refresh.18
  **Design decisions**: D1
  **Files**: `skills/refresh-architecture/scripts/arch_utils/provenance.py`
  **Dependencies**: 1.2, 1.3, 1.7
  The artifact loop at `provenance.py:747-765` currently reports `ARTIFACT_MISSING`
  for any absent recorded artifact regardless of the `required` flag. Absence becomes
  drift only for `tier == committed`; the digest check stays unconditional on presence.

- [x] 1.10 Reject provenance from an earlier schema version — **S**
  **Spec scenarios**: architecture-refresh.19
  **Design decisions**: D3
  **Files**: `skills/refresh-architecture/scripts/arch_utils/provenance.py`
  **Dependencies**: 1.6, 1.9

- [ ] Checkpoint: run the provenance suite, review the diff, confirm no file outside `arch_utils/` changed

- [x] 1.11 Bump `PROVENANCE_SCHEMA_VERSION` to 2 — **XS**
  **Design decisions**: D6
  **Files**: `skills/refresh-architecture/scripts/arch_utils/provenance.py`
  **Dependencies**: 1.8, 1.10

- [x] 1.12 Bump `PRODUCER_VERSION` to 1.3.0 — **XS**
  **Design decisions**: D6
  **Files**: `skills/refresh-architecture/scripts/arch_utils/provenance.py`
  **Dependencies**: 1.11

## 2. RPC entry point grounding

- [x] 2.1 Write a test that the default entry point is provenance-backed — **S**
  **Spec scenarios**: architecture-refresh.20
  **Design decisions**: D4 (resolution order), D5 (reset seam)
  **Files**: `skills/refresh-architecture/scripts/tests/test_rpc_server.py`
  **Dependencies**: None
  Assert `reason != "mtime"` and that `source_revision`, `producer_version`,
  `input_fingerprint`, `provenance_path` are non-null when reached via `get_server()`.

- [x] 2.2 Write a test that elapsed time alone never flips the verdict — **S**
  **Spec scenarios**: architecture-refresh.21
  **Files**: `skills/refresh-architecture/scripts/tests/test_rpc_server.py`
  **Dependencies**: None
  Backdate the graph mtime well beyond the age threshold with inputs unchanged.

- [x] 2.3 Write a test that the verdict is independent of the working directory — **S**
  **Spec scenarios**: architecture-refresh.22
  **Files**: `skills/refresh-architecture/scripts/tests/test_rpc_server.py`
  **Dependencies**: None

- [x] 2.4 Add a `reset_server()` seam — **XS**
  **Design decisions**: D5
  **Files**: `skills/refresh-architecture/scripts/rpc_server.py`
  **Dependencies**: 2.1

- [ ] Checkpoint: run `pytest skills/refresh-architecture/scripts/tests/test_rpc_server.py`, confirm the three new tests fail for the right reason

- [x] 2.5 Resolve `repo_root` inside `get_server()` — **S**
  **Spec scenarios**: architecture-refresh.20, architecture-refresh.21
  **Design decisions**: D4
  **Files**: `skills/refresh-architecture/scripts/rpc_server.py`
  **Dependencies**: 2.1, 2.2, 2.4
  Order: `REFRESH_RPC_REPO_ROOT`, then `git rev-parse --show-toplevel` from the graph
  path's directory, then `None`. Legacy mode stays reachable only when no repository
  resolves.

- [x] 2.6 Resolve the default graph path against the repository — **S**
  **Spec scenarios**: architecture-refresh.22
  **Design decisions**: D4
  **Files**: `skills/refresh-architecture/scripts/rpc_server.py`
  **Dependencies**: 2.3, 2.5

- [x] 2.7 Confirm the merge-train probe reports a real drift reason — **XS**
  **Spec scenarios**: architecture-refresh.20
  **Files**: `agent-coordinator/tests/test_refresh_rpc_client.py`
  **Dependencies**: 2.5, 2.6
  Read-only verification that `merge_train_service.py:220`'s caller now receives
  populated provenance fields. No production change expected in this task.

- [ ] Checkpoint: run the rpc_server suite plus `agent-coordinator` refresh-client tests, review the diff

## 3. Merge hygiene for generated JSON

- [x] 3.1 Write a test asserting the heavy artifacts are declared unmergeable — **XS**
  **Files**: `skills/tests/refresh-architecture-contracts/test_generated_artifact_merge_policy.py`
  **Dependencies**: None
  Assert `git check-attr merge` reports `binary` for the four heavy JSON paths.

- [x] 3.2 Declare the heavy artifacts `merge=binary` — **XS**
  **Files**: `.gitattributes`
  **Dependencies**: 3.1
  Cover `architecture.graph.json`, `architecture.diagnostics.json`,
  `treesitter_enrichment.json`, `parallel_zones.json`, following the `uv.lock` precedent.

- [ ] Checkpoint: run `git check-attr merge` on the four paths, review the diff

## 4. Artifact demotion

- [ ] 4.1 Write a test asserting the three artifacts are untracked — **XS**
  **Design decisions**: D7
  **Files**: `skills/tests/refresh-architecture-contracts/test_local_cache_artifacts.py`
  **Dependencies**: None
  Assert `git ls-files` returns nothing for the three `local-cache` paths.

- [ ] 4.2 Untrack the three local-cache artifacts — **XS**
  **Design decisions**: D7
  **Files**: `docs/architecture-analysis/treesitter_enrichment.json`, `docs/architecture-analysis/python_analysis.json`, `docs/architecture-analysis/parallel_zones.json`
  **Dependencies**: 4.1, 1.9
  `git rm --cached` only; the files stay on disk and keep being generated.

- [ ] Checkpoint: confirm the three files remain on disk while `git ls-files` no longer lists them

- [ ] 4.3 Ignore the three local-cache artifacts — **XS**
  **Files**: `.gitignore`
  **Dependencies**: 4.2

- [ ] 4.4 Regenerate the committed provenance at schema 2 — **S**
  **Spec scenarios**: architecture-refresh.16, architecture-refresh.17
  **Files**: `docs/architecture-analysis/architecture.provenance.json`
  **Dependencies**: 1.11, 1.12, 4.3
  Run `make architecture-refresh`; the resulting record must show `schema_version: 2`,
  producer `1.3.0`, and `tier` on every artifact entry.

- [ ] Checkpoint: run `make context-drift-gate`, confirm exit 0, review the diff for scope

## 5. Integration

- [ ] 5.1 Re-sync the skill mirrors — **XS**
  **Files**: `.claude/skills/**`, `.agents/skills/**`
  **Dependencies**: 2.6, 1.12
  Run `install.sh`. Required because `gate-drift-with-mirrors-hooks-and-blocking-ci`
  will fail CI on mirror drift, and every code edit in this change is under `skills/`.

- [ ] 5.2 Verify freshness on a clean clone — **S**
  **Spec scenarios**: architecture-refresh.17
  **Files**: (verification only)
  **Dependencies**: 4.4, 5.1
  Clone the branch to a scratch directory, run `make context-drift-gate`, confirm exit
  0 with no `ARTIFACT_MISSING` for any `local-cache` path.

- [ ] 5.3 Record the repository weight reduction — **XS**
  **Files**: (verification only)
  **Dependencies**: 4.4
  Confirm tracked bytes under `docs/architecture-analysis/` fall by at least 2.76 MB.

- [ ] Checkpoint: full `pytest` for the two touched skills, `openspec validate --strict`, review the cumulative diff
