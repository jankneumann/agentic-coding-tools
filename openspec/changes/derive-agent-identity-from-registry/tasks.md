# Tasks — derive-agent-identity-from-registry

Sizes per the plan-feature sizing table. TDD ordering: test tasks precede the implementation
tasks they verify.

## Phase 1 — Unified trust scale

- [x] 1.1 Write tests for the trust-scale module — enum values/names match the documented
      table, bounds exported, YAML schema and policy thresholds derive from it (S)
      **Spec scenarios**: agent-identity / "Out-of-scale registry value rejected",
      "Single definition consumed everywhere"
      **Design decisions**: D4
      **Dependencies**: none
- [x] 1.2 Create `src/trust_levels.py` — `TrustLevel` IntEnum (0 Untrusted … 4 Admin),
      `MIN_TRUST`/`MAX_TRUST`; wire `AGENTS_SCHEMA` trust bounds and policy-engine
      read/write/admin thresholds to it (S)
      **Dependencies**: 1.1
- [x] 1.3 Migration: align `agent_profiles` CHECK constraint with the module's bounds and
      add the paired down migration; test asserts constraint bounds equal module bounds (S)
      **Design decisions**: D4, D8
      **Dependencies**: 1.2
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Registry projections

- [x] 2.1 Write tests for full-roster identity generation — MCP agents included, unresolved
      placeholders excluded, explicit env override wins, duplicate keys raise naming both
      agents (S)
      **Spec scenarios**: agent-identity / "MCP-transport agent receives identity
      projection", "Full-roster identity map", "Duplicate key rejected"
      **Design decisions**: D5, D6
      **Dependencies**: none
- [x] 2.2 Drop the `transport == "http"` filter in `get_api_key_identities()`; make
      duplicate resolved keys a load error (S)
      **Dependencies**: 2.1
- [x] 2.3 Write tests for `sync_profiles()` — insert missing, update drifted, disable
      orphan with audit event, idempotent re-run (second invocation converges, no
      duplicate mutations), `PROFILE_SYNC_ENABLED=false` no-op (M)
      **Spec scenarios**: agent-identity / "Sync creates missing profile", "Sync updates
      drifted profile", "Orphan profile disabled with audit trail", "Sync disabled via flag"
      **Design decisions**: D1, D2, D8, D9
      **Dependencies**: 1.2
- [x] 2.4 Implement `sync_profiles()` in `agents_config.py` (capabilities→operations
      mapping table plus trust-derived grants, idempotent upsert keyed on profile name,
      orphan disabling, audit events per the profile-sync contract) and invoke from
      coordinator startup behind `PROFILE_SYNC_ENABLED` (M)
      **Dependencies**: 2.3
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 2.5 Write regression test: derived `allowed_operations` for `claude_code_local`
      equals the operations granted by migration 007/019/022 (S)
      **Design decisions**: risk note "allowed_operations derivation"
      **Dependencies**: 2.4
- [x] 2.6 Write tests for fail-loud trust resolution — registry agent with missing/disabled
      profile errors with audit event; unknown principal still gets default trust (S)
      **Spec scenarios**: agent-coordinator / "Registry agent with broken projection fails
      loud", "Unknown principal still defaults low"
      **Design decisions**: D3
      **Dependencies**: 2.4
- [x] 2.7 Implement the fail-loud split in `resolve_trust_level()` (registry-membership
      check, 500-class error surface, audit event) (S)
      **Dependencies**: 2.6
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 3 — CLI wrapper

- [x] 3.1 Write tests for registry-derived `setup_cloud.py` — roster equals
      `load_agents_config()` names, per-agent flags generated, identities JSON matches
      `get_api_key_identities()` shape, `.env.cloud` aliases emitted per CLI-bearing agent (S)
      **Design decisions**: D7
      **Dependencies**: 2.2
- [x] 3.2 Rewrite `setup_cloud.py` roster/flag/identity derivation from the registry;
      delete the hardcoded `AGENTS` list; docstring notes pca-03 retirement (S)
      **Dependencies**: 3.1
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Invariant and integration

- [x] 4.1 Write `tests/test_registry_projection.py` — for every registry agent: enabled
      profile row with declared trust post-sync, identity entry present (or key explicitly
      unresolvable in test env), referenced profile resolves; no enabled non-registry
      profiles remain (M)
      **Spec scenarios**: agent-identity / "Half-onboarded harness caught in CI",
      "Ghost profile caught in CI"
      **Design decisions**: D1, D2
      **Dependencies**: 2.4, 2.7
- [x] 4.2 Update docs — `agent-coordinator/CLAUDE.md` env-var section
      (`PROFILE_SYNC_ENABLED`, identity auto-population semantics), rollback runbook
      snippet in `docs/` (S)
      **Design decisions**: D8
      **Dependencies**: 2.7, 3.2
- [x] 4.3 Integration: full `pytest -m "not e2e and not integration"`, `mypy --strict src/`,
      `ruff check .` in agent-coordinator; fix fallout (S)
      **Dependencies**: 4.1, 4.2
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 5 — Assignment projection (follow-up; closes the resolution gap)

Added after Phase 4. The profile projection alone did not satisfy the change's own claim:
`get_agent_profile()` reads `agent_profile_assignments` first and falls back to `agent_type`
with `ORDER BY created_at ASC LIMIT 1`, so a correct profile row can still be unreachable.
Migration 018 fixed this by hand for its contemporary roster and did not extend to later
harnesses (design D11).

- [x] 5.1 Write tests for assignment projection — assignment created per registry agent,
      re-pointed when the registry changes an agent's profile, stale assignment removed with
      audit event naming the profile it pointed at, idempotent re-run, convergent under
      concurrent boot, `PROFILE_SYNC_ENABLED=false` no-op (M)
      **Spec scenarios**: agent-identity / "Declared agent resolves to its own profile, not the
      oldest of its type", "Stale assignment removed with audit trail"
      **Contracts**: contracts/events/profile-sync-audit.schema.json (assignment actions)
      **Design decisions**: D11
      **Dependencies**: 2.4
- [x] 5.2 Project `agent_profile_assignments` in `sync_profiles()` (name→id map re-queried after
      the profile phase, upsert keyed on the table's UNIQUE (agent_id), stale-assignment removal
      with audit, extended `ProfileSyncResult`) and extend the audit contract with the assignment
      actions (M)
      **Design decisions**: D11
      **Dependencies**: 5.1
- [x] 5.3 Close the invariant blind spot — add a resolution checker to
      `tests/test_registry_projection.py` that resolves the way `get_agent_profile()` does
      (assignment first, then `agent_type` + `created_at` fallback) and assert every registry
      agent reaches its declared trust level; negative test covers two agents sharing an
      `agent_type` with the wrong-trust row older and no assignment (S)
      **Spec scenarios**: agent-identity / "Registry Projection Invariant" clause (d)
      **Design decisions**: D11
      **Dependencies**: 5.2
- [x] Checkpoint: run tests, review diff, verify scope
