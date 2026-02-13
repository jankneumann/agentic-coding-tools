-- Migration 007: Agent profiles with trust levels and resource limits
-- Dependencies: 001_core_schema.sql
-- Phase 3 feature: Configurable agent capabilities and constraints

-- =============================================================================
-- Tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS agent_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    agent_type TEXT NOT NULL,  -- 'claude_code', 'codex', 'strands', etc.
    trust_level INT NOT NULL DEFAULT 2 CHECK (trust_level >= 0 AND trust_level <= 4),
    allowed_operations TEXT[] DEFAULT '{}',
    blocked_operations TEXT[] DEFAULT '{}',
    max_file_modifications INT DEFAULT 50,
    max_execution_time_seconds INT DEFAULT 300,
    max_api_calls_per_hour INT DEFAULT 1000,
    network_policy JSONB DEFAULT '{}',  -- inline network policy overrides
    metadata JSONB DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_profile_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    profile_id UUID NOT NULL REFERENCES agent_profiles(id),
    assigned_by TEXT,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id)
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_profiles_agent_type ON agent_profiles (agent_type);
CREATE INDEX IF NOT EXISTS idx_profiles_trust_level ON agent_profiles (trust_level);
CREATE INDEX IF NOT EXISTS idx_profile_assignments_agent ON agent_profile_assignments (agent_id);
CREATE INDEX IF NOT EXISTS idx_profile_assignments_profile ON agent_profile_assignments (profile_id);

-- =============================================================================
-- Seed preconfigured profiles
-- =============================================================================

INSERT INTO agent_profiles (name, description, agent_type, trust_level, allowed_operations, max_file_modifications)
VALUES
    ('claude-code-cli', 'Local Claude Code CLI agent with full trust', 'claude_code', 3,
     ARRAY['acquire_lock', 'release_lock', 'check_locks', 'get_work', 'complete_work',
           'submit_work', 'write_handoff', 'read_handoff', 'register_session',
           'discover_agents', 'heartbeat', 'remember', 'recall', 'check_guardrails',
           'get_my_profile', 'query_audit'], 100),
    ('claude-code-web-reviewer', 'Claude Code web reviewer with read-only access', 'claude_code', 1,
     ARRAY['check_locks', 'read_handoff', 'discover_agents', 'recall',
           'check_guardrails', 'get_my_profile', 'query_audit'], 0),
    ('claude-code-web-implementer', 'Claude Code web implementer with standard trust', 'claude_code', 2,
     ARRAY['acquire_lock', 'release_lock', 'check_locks', 'get_work', 'complete_work',
           'submit_work', 'write_handoff', 'read_handoff', 'register_session',
           'discover_agents', 'heartbeat', 'remember', 'recall', 'check_guardrails',
           'get_my_profile', 'query_audit'], 50),
    ('codex-cloud-worker', 'Codex cloud worker with standard trust', 'codex', 2,
     ARRAY['acquire_lock', 'release_lock', 'check_locks', 'get_work', 'complete_work',
           'submit_work', 'register_session', 'heartbeat', 'remember', 'recall',
           'check_guardrails', 'get_my_profile'], 50),
    ('strands-orchestrator', 'Strands orchestrator with elevated trust', 'strands', 3,
     ARRAY['acquire_lock', 'release_lock', 'check_locks', 'get_work', 'complete_work',
           'submit_work', 'write_handoff', 'read_handoff', 'register_session',
           'discover_agents', 'heartbeat', 'remember', 'recall', 'check_guardrails',
           'get_my_profile', 'query_audit', 'cleanup_dead_agents'], 200)
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- Functions
-- =============================================================================

CREATE OR REPLACE FUNCTION get_agent_profile(
    p_agent_id TEXT,
    p_agent_type TEXT DEFAULT 'claude_code'
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_profile JSONB;
BEGIN
    -- Try explicit assignment first
    SELECT row_to_json(p)::jsonb INTO v_profile
    FROM agent_profiles p
    JOIN agent_profile_assignments a ON a.profile_id = p.id
    WHERE a.agent_id = p_agent_id AND p.enabled = true;

    IF v_profile IS NOT NULL THEN
        RETURN jsonb_build_object('success', true, 'profile', v_profile, 'source', 'assignment');
    END IF;

    -- Fall back to default by agent_type
    SELECT row_to_json(p)::jsonb INTO v_profile
    FROM agent_profiles p
    WHERE p.agent_type = p_agent_type AND p.enabled = true
    ORDER BY p.created_at ASC
    LIMIT 1;

    IF v_profile IS NOT NULL THEN
        RETURN jsonb_build_object('success', true, 'profile', v_profile, 'source', 'default');
    END IF;

    -- No profile found
    RETURN jsonb_build_object(
        'success', false,
        'reason', 'no_profile_found',
        'agent_id', p_agent_id,
        'agent_type', p_agent_type
    );
END;
$$;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE agent_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_profile_assignments ENABLE ROW LEVEL SECURITY;

CREATE POLICY profiles_read ON agent_profiles FOR SELECT USING (true);
CREATE POLICY profiles_write ON agent_profiles FOR ALL
    USING (current_setting('role') = 'service_role');

CREATE POLICY assignments_read ON agent_profile_assignments FOR SELECT USING (true);
CREATE POLICY assignments_write ON agent_profile_assignments FOR ALL
    USING (current_setting('role') = 'service_role');
