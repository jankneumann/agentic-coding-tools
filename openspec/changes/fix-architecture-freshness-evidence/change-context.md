# Change Context: fix-architecture-freshness-evidence

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|---|---|---|---|---|---|---|---|
| architecture-refresh.1 | specs/architecture-refresh/spec.md | Clean revision produces complete provenance | --- | D1 | --- | test_provenance.py::test_clean_revision_provenance | --- |
| architecture-refresh.2 | specs/architecture-refresh/spec.md | Dirty relevant input is represented truthfully | --- | --- | --- | test_provenance.py::test_dirty_relevant_input_is_truthful | --- |
| architecture-refresh.16 | specs/architecture-refresh/spec.md | Every recorded artifact declares its tier | --- | D1 | --- | test_architecture_provenance_contract.py::test_tier_is_required | --- |
| architecture-refresh.3 | specs/architecture-refresh/spec.md | Mtime-only change stays fresh | --- | --- | --- | test_provenance.py::test_mtime_only_change_stays_fresh | --- |
| architecture-refresh.3b | specs/architecture-refresh/spec.md | Artifact-only convergence commit does not self-invalidate | --- | --- | --- | test_provenance.py::test_artifact_only_commit_stays_fresh | --- |
| architecture-refresh.4 | specs/architecture-refresh/spec.md | Relevant input change is stale immediately | --- | --- | --- | test_provenance.py::test_relevant_input_change_is_stale | --- |
| architecture-refresh.5 | specs/architecture-refresh/spec.md | Architecture producer change invalidates freshness | --- | D6 | --- | test_provenance.py::test_producer_identity_mismatch | --- |
| architecture-refresh.6 | specs/architecture-refresh/spec.md | Invalid provenance fails closed | --- | D3 | --- | test_provenance.py::test_invalid_provenance_fails_closed | --- |
| architecture-refresh.17 | specs/architecture-refresh/spec.md | Absent local-cache artifact is not drift | --- | D1, D7 | --- | test_provenance.py::test_absent_local_cache_artifact_is_not_drift | --- |
| architecture-refresh.18 | specs/architecture-refresh/spec.md | Present local-cache artifact is still digest-verified | --- | D1 | --- | test_provenance.py::test_present_local_cache_artifact_is_digest_verified | --- |
| architecture-refresh.19 | specs/architecture-refresh/spec.md | Provenance from an earlier schema version fails closed | --- | D2, D3 | --- | test_provenance.py::test_legacy_schema_version_fails_closed | --- |
| architecture-refresh.14 | specs/architecture-refresh/spec.md | Existing caller receives additive response | --- | --- | --- | test_rpc_server.py::test_legacy_fields_remain_and_additive_fields_present | --- |
| architecture-refresh.15 | specs/architecture-refresh/spec.md | Invalid shared evidence degrades safely | --- | --- | --- | test_refresh_rpc_client.py::test_client_unavailable_degrades | --- |
| architecture-refresh.20 | specs/architecture-refresh/spec.md | Default entry point is provenance-backed | --- | D4, D5 | --- | test_rpc_server.py::test_default_entry_point_is_provenance_backed | --- |
| architecture-refresh.21 | specs/architecture-refresh/spec.md | Elapsed time alone never flips the default entry point to stale | --- | D4 | --- | test_rpc_server.py::test_elapsed_time_does_not_flip_freshness | --- |
| architecture-refresh.22 | specs/architecture-refresh/spec.md | Freshness does not depend on the working directory | --- | D4 | --- | test_rpc_server.py::test_verdict_independent_of_working_directory | --- |

## Design Decision Trace

| Decision | Summary | Requirements it governs | Verified by |
|---|---|---|---|
| D1 | `tier` is required, not optional-with-default | architecture-refresh.16, .17, .18 | test_architecture_provenance_contract.py, test_provenance.py |
| D2 | `schema_version` becomes `const: 2`, not `enum: [1, 2]` | architecture-refresh.19 | test_architecture_provenance_contract.py |
| D3 | Schema-version drift gets its own reason code | architecture-refresh.6, .19 | test_provenance.py |
| D4 | `repo_root` resolution is explicit, ordered, still allows legacy | architecture-refresh.20, .21, .22 | test_rpc_server.py |
| D5 | The server singleton gets an explicit reset seam | architecture-refresh.20 | test_rpc_server.py |
| D6 | `PRODUCER_VERSION` and `PROVENANCE_SCHEMA_VERSION` both move | architecture-refresh.5 | test_provenance.py |
| D7 | Which artifacts move, and why the graph does not | architecture-refresh.17 | test_local_cache_artifacts.py |

## Coverage Summary

- Requirements traced: 16
- Newly added scenarios: 7 (.16, .17, .18, .19, .20, .21, .22)
- Preserved scenarios requiring regression coverage: 9
- Contract Ref: generated, not hand-filled
