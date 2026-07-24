# Change Context: add-revision-aware-semantic-index-registry

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|-------------|-------------|--------------|-----------------|---------------|---------|----------|
| CS-ID-1 | code-search / Stable identity is reused | One natural key returns one durable identity. | DB schema; index-record schema | D1 | migration 029; `registry.py`; `registry_models.py` | `test_concurrent_ensure_returns_one_authoritative_record`; live concurrent ensure | pass 6ce11776; live PostgreSQL supplement deferred |
| CS-ID-2 | code-search / Symbolic revision is rejected | Only lowercase full Git object IDs are accepted. | index-record schema | D2 | `registry_models.py` | `test_exact_identity_rejects_refs_and_invalid_namespace_shapes` | pass 6ce11776 |
| CS-NS-1 | code-search / Storage identity is isolated | Main, feature, and work-package identities use distinct UUID-derived storage keys. | DB schema; index-record schema | D3 | migration 029; `identifiers.py`; `registry_models.py` | `test_storage_identifiers_are_uuid_derived_safe_and_isolated`; `test_storage_key_is_derived_from_index_uuid_by_trigger` | pass 6ce11776 |
| CS-LC-1 | code-search / Concurrent creation returns one record | Concurrent ensure is idempotent at the database natural key. | DB schema | D1, D4 | migration 029; `registry.py` | repository concurrent ensure; live concurrent ensure | pass 6ce11776; live PostgreSQL supplement deferred |
| CS-LC-2 | code-search / Active lease owns completion | Only the current unexpired lease may publish a terminal result. | DB schema; index-record schema | D4 | `registry.py`; `registry_models.py` | `test_lease_guarded_ready_completion_rejects_stale_workers` | pass 6ce11776 |
| CS-LC-3 | code-search / Expired lease permits takeover | Expired indexing leases can be replaced while retaining identity and incrementing attempts. | DB schema | D4 | `registry.py` | `test_expired_lease_takeover_increments_attempt_and_rejects_old_token` | pass 6ce11776 |
| CS-LC-4 | code-search / Ready completion records provenance | Ready records contain exact revision, embedding contract, chunks, and completion time without an error. | index-record schema | D2, D4 | `registry_models.py`; index-record schema | `test_record_serializes_to_the_frozen_json_shape`; lifecycle schema tests | pass 6ce11776 |
| CS-CAN-1 | code-search / Canonical promotion accepts a ready main index | Promotion atomically selects a ready same-repository main index. | DB schema | D5 | migration 029; `registry.py` | canonical repository test; live canonical trigger test | pass 6ce11776; live PostgreSQL supplement deferred |
| CS-CAN-2 | code-search / Non-main index cannot become canonical | Application and database guards reject non-main, cross-repository, incomplete, and later-invalidated targets. | DB schema | D5 | migration 029; `registry.py` | canonical repository test; structural target-trigger test; live invariant-mutation test | pass 6ce11776; live PostgreSQL supplement deferred |
| CS-CAN-3 | code-search / Stale promotion is rejected | Compare-and-swap leaves the canonical pointer unchanged on stale input. | DB schema | D5 | `registry.py` | canonical repository test; live compare-and-swap test | pass 6ce11776; live PostgreSQL supplement deferred |
| CS-GC-1 | code-search / Expired feature index is collected | Eligible storage is deleted before the record is tombstoned. | DB schema; index-record schema | D6 | `registry.py` | `test_gc_is_storage_first_excludes_protected_rows_and_retries_failures` | pass 6ce11776 |
| CS-GC-2 | code-search / Main indexes are never collected | Main, canonical, and actively leased records are excluded. | DB schema | D6 | migration 029; `registry.py` | GC exclusion test | pass 6ce11776 |
| CS-GC-3 | code-search / Failed storage deletion remains retryable | Failures remain durable, and expired deleting leases recover through an idempotent deleter. | DB schema; index-record schema | D6 | `registry.py`; `registry_models.py` | GC failure test; `test_gc_reclaims_expired_deleting_lease_after_storage_delete_crash` | pass 6ce11776 |
| CS-COMP-1 | code-search / Legacy reader remains compatible | Migration is additive and existing repo-slug imports and table naming remain available. | DB schema | D7 | migration 029; `__init__.py`; `identifiers.py` | additive migration tests; `test_legacy_repo_slug_table_naming_remains_available`; full package suite | pass 6ce11776 |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Separate repository configuration from revision lifecycle state. | Additive `code_search_indexes` table beside `code_search_registry`. | Avoids a destructive rollout and preserves current readers. |
| D2 | Store resolved object IDs rather than movable refs. | `IndexIdentity` and SQL/JSON constraints accept 40- or 64-hex lowercase IDs. | Makes freshness and provenance stable. |
| D3 | Keep human-readable namespace keys out of SQL identifiers. | UUID-derived `storage_key`. | Prevents collisions and unsafe interpolation. |
| D4 | Give one current worker ownership of lifecycle completion. | Expiring tokenized leases and guarded updates. | Prevents late workers from overwriting newer results. |
| D5 | Make canonical selection atomic and durable. | Guarded update plus repository-side and target-side deferrable triggers. | Preserves the invariant even for direct SQL callers. |
| D6 | Make cleanup conservative and crash-recoverable. | Storage-first deletion, retryable errors, expired deleting-lease takeover. | Avoids tombstoning live storage or stranding crashed operations. |
| D7 | Roll out without claiming the old search path is revision-aware. | Legacy helpers remain available and are documented as non-authoritative. | Downstream indexing and query changes can migrate independently. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| 1 | wp-migration | contract mismatch | high | fixed | Added an index-side canonical-target constraint trigger and regressions. |
| 2 | wp-registry | resilience | high | fixed | Reclaim expired deleting leases and require idempotent storage deletion. |
| 3 | wp-registry | contract mismatch | high | fixed | Changed ensure to `INSERT ... SELECT` for typed missing-repository outcomes. |
| 4 | wp-registry | contract mismatch | medium | fixed | Added deleted-state JSON Schema invariant and executable lifecycle cases. |
| 5 | wp-migration | environment evidence | low | accepted | Live PostgreSQL cases remain deferred because `POSTGRES_DSN` is unset. |
| 6 | wp-registry | security | low | accepted | Parameter binding and UUID-derived storage naming are preserved. |
| 7 | wp-migration | performance | low | accepted | Bounded deterministic GC scans retain the partial index. |

## Coverage Summary

- **Scenarios traced**: 14/14
- **Tests mapped**: 14/14
- **Local evidence collected**: 14/14
- **Review fix findings resolved**: 4/4
- **Deferred evidence**: live PostgreSQL execution for trigger and concurrency cases; structural and repository-level regressions pass
