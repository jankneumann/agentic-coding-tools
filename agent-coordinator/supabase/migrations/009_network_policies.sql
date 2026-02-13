-- Migration 009: Network access policies and logging
-- Dependencies: 007_agent_profiles.sql (per-profile policies)
-- Phase 3 feature: Domain-level network access control for agents

-- =============================================================================
-- Tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS network_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID REFERENCES agent_profiles(id),
    domain_pattern TEXT NOT NULL,  -- e.g., 'github.com', '*.amazonaws.com'
    action TEXT NOT NULL DEFAULT 'allow',  -- 'allow' or 'deny'
    priority INT NOT NULL DEFAULT 5,  -- lower = higher priority
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS network_access_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    allowed BOOLEAN NOT NULL,
    policy_id UUID REFERENCES network_policies(id),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_network_policies_profile ON network_policies (profile_id);
CREATE INDEX IF NOT EXISTS idx_network_policies_domain ON network_policies (domain_pattern);
CREATE INDEX IF NOT EXISTS idx_network_access_log_agent ON network_access_log (agent_id);
CREATE INDEX IF NOT EXISTS idx_network_access_log_domain ON network_access_log (domain);
CREATE INDEX IF NOT EXISTS idx_network_access_log_created ON network_access_log (created_at DESC);

-- =============================================================================
-- Seed default network policies (global — no profile_id means applies to all)
-- =============================================================================

INSERT INTO network_policies (profile_id, domain_pattern, action, priority, description)
VALUES
    (NULL, 'github.com', 'allow', 1, 'Allow GitHub API access for all agents'),
    (NULL, '*.github.com', 'allow', 1, 'Allow GitHub subdomains for all agents'),
    (NULL, 'api.github.com', 'allow', 1, 'Allow GitHub API for all agents'),
    (NULL, 'registry.npmjs.org', 'allow', 2, 'Allow npm registry for package installs'),
    (NULL, 'pypi.org', 'allow', 2, 'Allow PyPI for package installs'),
    (NULL, 'files.pythonhosted.org', 'allow', 2, 'Allow PyPI downloads'),
    (NULL, '*.supabase.co', 'allow', 1, 'Allow Supabase API access')
ON CONFLICT DO NOTHING;

-- =============================================================================
-- Functions
-- =============================================================================

CREATE OR REPLACE FUNCTION is_domain_allowed(
    p_agent_id TEXT,
    p_domain TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_profile_id UUID;
    v_policy RECORD;
    v_allowed BOOLEAN := false;
    v_reason TEXT := 'no_matching_policy';
    v_policy_id UUID;
BEGIN
    -- Get agent's profile ID
    SELECT pa.profile_id INTO v_profile_id
    FROM agent_profile_assignments pa
    WHERE pa.agent_id = p_agent_id;

    -- Check policies: profile-specific first, then global (NULL profile_id)
    -- Higher priority (lower number) wins
    FOR v_policy IN
        SELECT np.*
        FROM network_policies np
        WHERE np.enabled = true
          AND (np.profile_id = v_profile_id OR np.profile_id IS NULL)
          AND (
              p_domain = np.domain_pattern
              OR p_domain LIKE REPLACE(np.domain_pattern, '*', '%')
          )
        ORDER BY
            CASE WHEN np.profile_id IS NOT NULL THEN 0 ELSE 1 END,  -- profile-specific first
            np.priority ASC
        LIMIT 1
    LOOP
        v_allowed := (v_policy.action = 'allow');
        v_reason := v_policy.action;
        v_policy_id := v_policy.id;
    END LOOP;

    -- Log the access attempt
    INSERT INTO network_access_log (agent_id, domain, allowed, policy_id, reason)
    VALUES (p_agent_id, p_domain, v_allowed, v_policy_id, v_reason);

    RETURN jsonb_build_object(
        'allowed', v_allowed,
        'domain', p_domain,
        'reason', v_reason,
        'policy_id', v_policy_id
    );
END;
$$;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE network_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE network_access_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY network_policies_read ON network_policies FOR SELECT USING (true);
CREATE POLICY network_policies_write ON network_policies FOR ALL
    USING (current_setting('role') = 'service_role');

CREATE POLICY network_access_log_read ON network_access_log FOR SELECT USING (true);
CREATE POLICY network_access_log_insert ON network_access_log FOR INSERT
    WITH CHECK (current_setting('role') = 'service_role');
