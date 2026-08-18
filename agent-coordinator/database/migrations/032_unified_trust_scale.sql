-- Migration 032: unified trust scale + registry-sync bookkeeping for agent_profiles.
-- Dependencies: 007_agent_profiles.sql
-- Change: derive-agent-identity-from-registry (design D4, D8)
--
-- The authoritative bounds live in src/trust_levels.py (TrustLevel IntEnum,
-- MIN_TRUST/MAX_TRUST). The values below are the contracted rendering of that
-- module: 0 Untrusted .. 4 Admin. tests/test_trust_levels.py parses the CHECK
-- clause below and asserts its bounds equal the module's.

-- ---------------------------------------------------------------------------
-- 1. Trust CHECK constraint: assert alignment with the unified scale.
--    007 created the constraint inline, so PostgreSQL named it automatically.
--    Re-state it under a stable name so tests and operators can address it, and
--    so any deployment where the bounds drifted is normalized. Bounds are
--    identical to 007 — no existing row can violate this.
-- ---------------------------------------------------------------------------

ALTER TABLE agent_profiles
    DROP CONSTRAINT IF EXISTS agent_profiles_trust_level_check;

ALTER TABLE agent_profiles
    ADD CONSTRAINT agent_profiles_trust_level_check
    CHECK (trust_level >= 0 AND trust_level <= 4);

COMMENT ON COLUMN agent_profiles.trust_level IS
    'Unified trust scale 0..4 (0 Untrusted, 1 Limited, 2 Standard, 3 Elevated, '
    '4 Admin). Programmatic definition: src/trust_levels.py.';

-- ---------------------------------------------------------------------------
-- 2. Registry-sync bookkeeping: when a row was last projected from agents.yaml,
--    so operators can distinguish hand-maintained rows from registry
--    projections. NULL means "never synced from the registry".
-- ---------------------------------------------------------------------------

ALTER TABLE agent_profiles
    ADD COLUMN IF NOT EXISTS synced_from_registry_at TIMESTAMPTZ;

COMMENT ON COLUMN agent_profiles.synced_from_registry_at IS
    'Timestamp of the last successful projection from the agents.yaml registry; '
    'NULL for rows never touched by profile sync.';

-- ---------------------------------------------------------------------------
-- 3. Orphan disabling relies on the existing `enabled` column; no schema change
--    here. The contract is that sync sets enabled = false (never DELETE) for
--    enabled rows whose name is not declared by any agents.yaml entry, and
--    records a profile_sync audit event.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Down migration (paired, per design D8) — run manually to roll back:
-- ---------------------------------------------------------------------------
-- ALTER TABLE agent_profiles DROP COLUMN IF EXISTS synced_from_registry_at;
-- The trust constraint is identical to the 007 original, so no down action is
-- required; to restore the unnamed inline constraint exactly:
-- ALTER TABLE agent_profiles
--     DROP CONSTRAINT IF EXISTS agent_profiles_trust_level_check;
-- Re-enable rows disabled as registry orphans, if required:
-- UPDATE agent_profiles SET enabled = true WHERE name IN ('gemini_local', '...');
