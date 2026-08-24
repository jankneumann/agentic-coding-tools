-- DB contract — derive-agent-identity-from-registry
-- Migration NNN (next free number at implementation time): unified trust scale +
-- registry-sync semantics for agent_profiles.
--
-- The authoritative bounds come from src/trust_levels.py (design D4); the values
-- below are the contracted rendering of that module: 0 Untrusted .. 4 Admin.

-- 1. Trust CHECK constraint: assert alignment with the unified scale.
--    (The existing 007 constraint is already 0..4; this migration re-states it
--    under a stable name so tests can assert on it, and normalizes any prior
--    deployment where the constraint drifted.)
ALTER TABLE agent_profiles
    DROP CONSTRAINT IF EXISTS agent_profiles_trust_level_check;
ALTER TABLE agent_profiles
    ADD CONSTRAINT agent_profiles_trust_level_check
    CHECK (trust_level >= 0 AND trust_level <= 4);

-- 2. Registry-sync bookkeeping: when and by what a row was last synced, so
--    operators can distinguish hand-era rows from registry projections.
ALTER TABLE agent_profiles
    ADD COLUMN IF NOT EXISTS synced_from_registry_at TIMESTAMPTZ;

-- 3. Orphan disabling relies on the existing `enabled` column; no schema change,
--    but the contract is: sync sets enabled = false (never DELETE) for enabled
--    rows whose name is not declared by any agents.yaml entry, and records a
--    profile_sync audit event (see events/profile-sync-audit.schema.json).

-- Down migration (paired, per design D8):
-- ALTER TABLE agent_profiles DROP COLUMN IF EXISTS synced_from_registry_at;
-- (The trust constraint is identical to the 007 original; no down action needed.)
-- Re-enable disabled orphans if required:
-- UPDATE agent_profiles SET enabled = true WHERE name IN ('gemini_local', ...);
