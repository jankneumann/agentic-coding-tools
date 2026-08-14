# Change Context: derive-agent-identity-from-registry

Phase 1 (pre-implementation) populated. Files Changed / Evidence filled in Phases 2–3.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-identity.1 | specs/agent-identity (MODIFIED: Declarative Agent Configuration) | `agents.yaml` canonical for every agent; `transport` SHALL NOT gate identity/profile projection | --- | D5 | --- | test_agents_config.py::test_mcp_agent_receives_identity | --- |
| agent-identity.2 | specs/agent-identity (MODIFIED: API Key Identity Generation) | Identity map includes every agent with a resolvable key; duplicate resolved keys SHALL be rejected naming both agents | --- | D5, D6 | --- | test_agents_config.py::test_full_roster_identity_map, ::test_duplicate_key_rejected, ::test_openbao_resolution_preserved | --- |
| agent-identity.3 | specs/agent-identity (ADDED: Registry Profile Sync) | Startup upsert of `agent_profiles` from registry; orphans disabled (never deleted) with audit event; idempotent; advisory-lock safe; `PROFILE_SYNC_ENABLED` guard; boot fails loud on sync error | contracts/events/profile-sync-audit.schema.json, contracts/db/schema.sql | D1, D2, D8, D9 | --- | test_profile_sync.py::test_sync_creates_missing, ::test_sync_updates_drifted, ::test_orphan_disabled_with_audit, ::test_sync_idempotent, ::test_sync_disabled_via_flag, ::test_advisory_lock_second_worker_noop | --- |
| agent-identity.4 | specs/agent-identity (ADDED: Unified Trust Scale) | Single 0–4 scale module; YAML schema bounds, DB CHECK, and policy tiers all derive from it | contracts/db/schema.sql | D4 | --- | test_trust_levels.py::test_scale_matches_documented_table, ::test_yaml_schema_bounds_derived, ::test_policy_thresholds_derived, ::test_out_of_scale_rejected | --- |
| agent-identity.5 | specs/agent-identity (ADDED: Registry Projection Invariant) | CI asserts every registry agent materializes profile + identity + resolvable profile name; no enabled orphans post-sync | --- | D1, D2 | --- | test_registry_projection.py::test_every_agent_projects, ::test_no_enabled_orphans | --- |
| agent-coordinator.1 | specs/agent-coordinator (MODIFIED: Agent Profiles) | Registry-declared agent with missing/disabled profile SHALL error + audit; unknown principal keeps default trust | contracts/events/profile-sync-audit.schema.json | D3 | --- | test_coordination_api.py::test_registry_agent_broken_projection_fails_loud, ::test_unknown_principal_defaults_low | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | agent_profiles is a materialized view synced at startup | `sync_profiles()` in agents_config.py, invoked from coordination_api lifespan | Explicit seeding was specced 2026-03 and never implemented across two shipped changes |
| D2 | Orphans disabled, never deleted; every mutation audited | `enabled=false` + `log_operation(operation="profile_sync")` | Ghost profiles are live authorization state for retired principals; disabling preserves history and eases rollback |
| D3 | Fail-loud scoped to registry-declared agents | `resolve_trust_level()` registry-membership branch | A known agent with a broken projection means the projection machinery failed; unknown principals keep the low default |
| D4 | One trust-scale module | `src/trust_levels.py` TrustLevel IntEnum + bounds | YAML 1–5 vs DB 0–4 divergence was a live bug |
| D5 | Transport does not gate identity | Remove `transport == "http"` filter in `get_api_key_identities()` | MCP agents reach the HTTP API via the proxy fallback |
| D6 | Duplicate resolved keys are a load error | Raise in `get_api_key_identities()` naming both agents | Last-writer-wins misattributes audit entries |
| D7 | setup_cloud.py keeps UX, loses roster | Derive roster/flags/identities from `load_agents_config()` | Second hand-maintained roster is the drift source |
| D8 | Rollback levers ship with the change | `PROFILE_SYNC_ENABLED`, explicit identities env override, paired down migration | Breaking changes accepted only with an obvious revert path |
| D9 | Advisory lock for multi-worker startup | `pg_advisory_lock` around sync transaction | Multiple API workers boot simultaneously |
| D10 | OpenBao code untouched | No changes to `_resolve_api_key_from_openbao` / bao_seed.py | Phase 1 must ship with no OpenBao deployed (pca-02 owns that) |

## Coverage Summary

- **Requirements traced**: 6/6
- **Tests mapped**: 6 requirements have at least one test
- **Evidence collected**: 0/6 (Phase 3)
- **Gaps identified**: ---
- **Deferred items**: ---
