# Change Context: derive-agent-identity-from-registry

Phase 1 (pre-implementation) populated. Files Changed / Evidence filled in Phases 2–3.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-identity.1 | specs/agent-identity (MODIFIED: Declarative Agent Configuration) | `agents.yaml` canonical for every agent; `transport` SHALL NOT gate identity/profile projection | --- | D5 | src/agents_config.py | test_agents_config.py::test_mcp_transport_agent_receives_identity, ::test_mcp_agent_has_no_api_key | pass afd64fa |
| agent-identity.2 | specs/agent-identity (MODIFIED: API Key Identity Generation) | Identity map includes every agent with a resolvable key; duplicate resolved keys SHALL be rejected naming both agents | --- | D5, D6 | src/agents_config.py, src/config.py | test_agents_config.py::test_full_roster_identity_map, ::test_duplicate_key_raises_naming_both_agents, ::test_explicit_env_var_overrides_registry, ::test_duplicate_key_not_swallowed_by_config, ::test_identities_with_openbao | pass afd64fa |
| agent-identity.3 | specs/agent-identity (ADDED: Registry Profile Sync) | Startup upsert of `agent_profiles` from registry; orphans disabled (never deleted) with audit event; idempotent and convergent under concurrent worker boot; `PROFILE_SYNC_ENABLED` guard; boot fails loud on sync error | contracts/events/profile-sync-audit.schema.json, contracts/db/schema.sql | D1, D2, D8, D9 | src/agents_config.py, src/coordination_api.py, src/config.py, src/profiles.py | test_profile_sync.py::test_inserts_missing_profile, ::test_updates_drifted_trust_level, ::test_disables_orphan_with_audit_event, ::test_unmanaged_role_profile_survives, ::test_idempotent_rerun, ::test_concurrent_insert_converges_via_update, ::test_disabled_by_flag_performs_no_writes, ::test_events_validate_against_contract, ::test_derived_operations_match_migrations; test_coordination_api.py::test_lifespan_runs_registry_sync, ::test_lifespan_fails_boot_when_registry_sync_fails | pass afd64fa |
| agent-identity.4 | specs/agent-identity (ADDED: Unified Trust Scale) | Single 0–4 scale module; YAML schema bounds, DB CHECK, and policy tiers all derive from it | contracts/db/schema.sql | D4 | src/trust_levels.py, src/policy_engine.py, migrations/031 | test_trust_levels.py::test_spec_table_matches_module, ::test_bounds_derive_from_enum, ::test_policy_engine_has_no_bare_trust_literals, ::test_migration_check_bounds_equal_module_bounds; test_agents_config.py::test_schema_bounds_derive_from_trust_module, ::test_out_of_scale_trust_level_rejected | pass afd64fa |
| agent-identity.5 | specs/agent-identity (ADDED: Registry Projection Invariant) | CI asserts every registry agent materializes profile + identity + resolvable profile name; no enabled orphans post-sync | --- | D1, D2 | tests/test_registry_projection.py | test_registry_projection.py::test_every_registry_agent_has_enabled_profile_with_declared_trust, ::test_no_enabled_profile_row_is_unclassified, ::test_silently_downgraded_trust_level_fails_rule_1, ::test_harness_without_a_materialized_row_fails_rules_1_and_3 | pass afd64fa |
| agent-coordinator.1 | specs/agent-coordinator (MODIFIED: Agent Profiles) | Registry-declared agent with missing/disabled profile SHALL error + audit; unknown principal keeps default trust | contracts/events/profile-sync-audit.schema.json | D3 | src/coordination_api.py | test_coordination_api.py::test_registry_agent_missing_profile_fails_loud, ::test_registry_agent_disabled_profile_fails_loud, ::test_registry_agent_lookup_error_fails_loud, ::test_unknown_principal_gets_default_trust | pass afd64fa |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | agent_profiles is a materialized view synced at startup | `sync_profiles()` in agents_config.py, invoked from coordination_api lifespan | Explicit seeding was specced 2026-03 and never implemented across two shipped changes |
| D2 (amended) | Orphans disabled, never deleted; every mutation audited; role profiles exempt | `enabled=false` + `log_operation(operation="profile_sync")`, with `UNMANAGED_PROFILES` carve-out | Ghost profiles are live authorization state for retired principals. `evaluator` is a role, not a harness identity — migration 027's `claim_task` depends on it, so blanket disabling would break evaluation task claiming |
| D3 | Fail-loud scoped to registry-declared agents | `resolve_trust_level()` registry-membership branch | A known agent with a broken projection means the projection machinery failed; unknown principals keep the low default |
| D4 | One trust-scale module | `src/trust_levels.py` TrustLevel IntEnum + bounds | YAML 1–5 vs DB 0–4 divergence was a live bug |
| D5 | Transport does not gate identity | Remove `transport == "http"` filter in `get_api_key_identities()` | MCP agents reach the HTTP API via the proxy fallback |
| D6 | Duplicate resolved keys are a load error | Raise in `get_api_key_identities()` naming both agents | Last-writer-wins misattributes audit entries |
| D7 | setup_cloud.py keeps UX, loses roster | Derive roster/flags/identities from `load_agents_config()` | Second hand-maintained roster is the drift source |
| D8 | Rollback levers ship with the change | `PROFILE_SYNC_ENABLED`, explicit identities env override, paired down migration | Breaking changes accepted only with an obvious revert path |
| D9 (amended) | Concurrency via idempotent upserts, not an advisory lock | `ON CONFLICT`-style upsert keyed on profile name; failing insert falls through to update | `pg_advisory_lock` is unreachable through `DatabaseClient`: no raw execute, `rpc()` emits named-parameter calls that Postgres built-ins reject, and pooled connections make session-scoped locks unsafe |
| D10 | OpenBao code untouched | No changes to `_resolve_api_key_from_openbao` / bao_seed.py | Phase 1 must ship with no OpenBao deployed (pca-02 owns that) |

## Coverage Summary

- **Requirements traced**: 6/6
- **Tests mapped**: 6 requirements have at least one test
- **Evidence collected**: 6/6 (full suite 2255 passed, 11 skipped, 0 failed at afd64fa; mypy --strict and ruff clean)
- **Gaps identified**: ---
- **Deferred items**: ---
