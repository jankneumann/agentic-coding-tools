-- Migration 033: profile assignments for the 'gx10' host
-- Dependencies: 007_agent_profiles.sql, 018_agent_profile_assignments.sql,
--               019_standardize_profile_names.sql
--
-- get_profile() resolves an explicit agent_id assignment first and only
-- then falls back to a type-based default (src/profiles.py:104). A new
-- agent_id with no assignment therefore inherits whichever profile happens
-- to sort first for its agent_type — the exact drift migration 018 was
-- written to eliminate. Every agent_id in COORDINATION_API_KEY_IDENTITIES
-- needs a row here.

-- Fail loud rather than silently inserting nothing if the template row is
-- absent: every INSERT below is a SELECT-driven copy, and a missing source
-- row would make them all no-ops that still report success.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM agent_profiles WHERE name = 'claude_code_local'
    ) THEN
        RAISE EXCEPTION 'template profile claude_code_local missing — apply migrations 007 and 019 first';
    END IF;
END $$;

-- =============================================================================
-- Bootstrap profile rows for a fresh-DB replay (content owned by sync)
-- =============================================================================
-- On the running production DB these rows already exist: the registry
-- startup sync (src/agents_config.py sync_profiles) projects agents.yaml
-- into agent_profiles on every boot and reconciles trust level and
-- operations. The clones below exist ONLY so a from-scratch migration
-- replay cannot order this file before the first sync: migrations run
-- before sync at startup, and the assignment INSERTs further down are
-- SELECT-driven — a missing profile row would turn them into silent
-- no-ops and trip the verification block. ON CONFLICT DO NOTHING keeps
-- this inert wherever sync has already materialized the row.

INSERT INTO agent_profiles (
    name, description, agent_type, trust_level,
    allowed_operations, blocked_operations, max_file_modifications,
    max_execution_time_seconds, max_api_calls_per_hour
)
SELECT
    'antigravity_local',
    'Local antigravity worker with full coordination access',
    'antigravity',
    trust_level, allowed_operations, blocked_operations,
    max_file_modifications, max_execution_time_seconds, max_api_calls_per_hour
FROM agent_profiles WHERE name = 'claude_code_local'
ON CONFLICT (name) DO NOTHING;

INSERT INTO agent_profiles (
    name, description, agent_type, trust_level,
    allowed_operations, blocked_operations, max_file_modifications,
    max_execution_time_seconds, max_api_calls_per_hour
)
SELECT
    'grok_local',
    'Local grok worker with full coordination access',
    'grok',
    trust_level, allowed_operations, blocked_operations,
    max_file_modifications, max_execution_time_seconds, max_api_calls_per_hour
FROM agent_profiles WHERE name = 'claude_code_local'
ON CONFLICT (name) DO NOTHING;

INSERT INTO agent_profiles (
    name, description, agent_type, trust_level,
    allowed_operations, blocked_operations, max_file_modifications,
    max_execution_time_seconds, max_api_calls_per_hour
)
SELECT
    'pi_local',
    'Local pi worker with full coordination access',
    'pi',
    trust_level, allowed_operations, blocked_operations,
    max_file_modifications, max_execution_time_seconds, max_api_calls_per_hour
FROM agent_profiles WHERE name = 'claude_code_local'
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- Assign each gx10 agent_id to its profile
-- =============================================================================
-- assigned_by='add_agent_keys.py' is load-bearing: the startup sync
-- garbage-collects assignments for agent_ids absent from agents.yaml, but
-- only rows stamped with its own 'registry_sync'. These agent_ids are
-- per-host *instances* of registry-declared types — deliberately not
-- registry entries — and this stamp is what exempts them from that sweep.

INSERT INTO agent_profile_assignments (agent_id, profile_id, assigned_by)
SELECT 'antigravity-gx10', id, 'add_agent_keys.py'
    FROM agent_profiles WHERE name = 'antigravity_local'
ON CONFLICT (agent_id) DO UPDATE
    SET profile_id = EXCLUDED.profile_id, assigned_at = now();

INSERT INTO agent_profile_assignments (agent_id, profile_id, assigned_by)
SELECT 'claude-gx10', id, 'add_agent_keys.py'
    FROM agent_profiles WHERE name = 'claude_code_local'
ON CONFLICT (agent_id) DO UPDATE
    SET profile_id = EXCLUDED.profile_id, assigned_at = now();

INSERT INTO agent_profile_assignments (agent_id, profile_id, assigned_by)
SELECT 'codex-gx10', id, 'add_agent_keys.py'
    FROM agent_profiles WHERE name = 'codex_local'
ON CONFLICT (agent_id) DO UPDATE
    SET profile_id = EXCLUDED.profile_id, assigned_at = now();

INSERT INTO agent_profile_assignments (agent_id, profile_id, assigned_by)
SELECT 'grok-gx10', id, 'add_agent_keys.py'
    FROM agent_profiles WHERE name = 'grok_local'
ON CONFLICT (agent_id) DO UPDATE
    SET profile_id = EXCLUDED.profile_id, assigned_at = now();

INSERT INTO agent_profile_assignments (agent_id, profile_id, assigned_by)
SELECT 'pi-gx10', id, 'add_agent_keys.py'
    FROM agent_profiles WHERE name = 'pi_local'
ON CONFLICT (agent_id) DO UPDATE
    SET profile_id = EXCLUDED.profile_id, assigned_at = now();

-- =============================================================================
-- Verify: every agent_id above resolved to a profile
-- =============================================================================
DO $$
DECLARE
    missing_count INT;
BEGIN
    SELECT count(*) INTO missing_count
    FROM unnest(ARRAY['antigravity-gx10', 'claude-gx10', 'codex-gx10', 'grok-gx10', 'pi-gx10']) AS expected(agent_id)
    WHERE NOT EXISTS (
        SELECT 1 FROM agent_profile_assignments a
        WHERE a.agent_id = expected.agent_id
    );
    IF missing_count > 0 THEN
        RAISE EXCEPTION
            '% of 5 gx10 agents have no profile assignment',
            missing_count;
    END IF;
END $$;
