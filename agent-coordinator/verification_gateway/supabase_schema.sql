-- Verification Gateway Schema for Supabase
-- Tracks all agent changes and their verification results

-- =============================================================================
-- CHANGESETS: Records of agent-generated changes
-- =============================================================================

CREATE TABLE changesets (
    id TEXT PRIMARY KEY,
    branch TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_type TEXT NOT NULL CHECK (agent_type IN ('claude_code', 'codex', 'gemini_jules', 'github', 'manual')),
    commit_sha TEXT,
    changed_files JSONB NOT NULL DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Indexes for common queries
    CONSTRAINT changed_files_is_array CHECK (jsonb_typeof(changed_files) = 'array')
);

CREATE INDEX idx_changesets_agent ON changesets(agent_id, agent_type);
CREATE INDEX idx_changesets_branch ON changesets(branch);
CREATE INDEX idx_changesets_created ON changesets(created_at DESC);

-- =============================================================================
-- VERIFICATION RESULTS: Outcomes of verification runs
-- =============================================================================

CREATE TYPE verification_tier AS ENUM ('STATIC', 'UNIT', 'INTEGRATION', 'SYSTEM', 'MANUAL');
CREATE TYPE verification_executor AS ENUM ('inline', 'github', 'ntm', 'e2b', 'human');
CREATE TYPE verification_status AS ENUM ('pending', 'running', 'success', 'failure', 'cancelled');

CREATE TABLE verification_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    changeset_id TEXT NOT NULL REFERENCES changesets(id) ON DELETE CASCADE,
    policy_name TEXT NOT NULL,
    tier verification_tier NOT NULL,
    executor verification_executor NOT NULL,
    status verification_status NOT NULL DEFAULT 'pending',
    success BOOLEAN,
    duration_seconds FLOAT,
    output TEXT,
    errors JSONB DEFAULT '[]',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT errors_is_array CHECK (jsonb_typeof(errors) = 'array')
);

CREATE INDEX idx_verification_changeset ON verification_results(changeset_id);
CREATE INDEX idx_verification_status ON verification_results(status);
CREATE INDEX idx_verification_tier ON verification_results(tier);

-- =============================================================================
-- VERIFICATION POLICIES: Configurable routing rules (optional - can be in code)
-- =============================================================================

CREATE TABLE verification_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    tier verification_tier NOT NULL,
    executor verification_executor NOT NULL,
    patterns JSONB NOT NULL DEFAULT '[]',
    exclude_patterns JSONB DEFAULT '[]',
    required_env JSONB DEFAULT '[]',
    timeout_seconds INTEGER DEFAULT 300,
    requires_approval BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- APPROVAL QUEUE: Human review tracking
-- =============================================================================

CREATE TABLE approval_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    changeset_id TEXT NOT NULL REFERENCES changesets(id) ON DELETE CASCADE,
    policy_name TEXT NOT NULL,
    reason TEXT,
    requested_by TEXT,  -- Agent or system that requested approval
    approved_by TEXT,   -- Human who approved
    approved_at TIMESTAMPTZ,
    denied_by TEXT,
    denied_at TIMESTAMPTZ,
    denial_reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_approval_status ON approval_queue(status);
CREATE INDEX idx_approval_changeset ON approval_queue(changeset_id);

-- =============================================================================
-- AGENT SESSIONS: Track agent work for correlation
-- =============================================================================

CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY,
    agent_type TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    task_description TEXT,
    branch TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    changesets_produced TEXT[] DEFAULT '{}',
    total_tokens INTEGER,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_agent_sessions_type ON agent_sessions(agent_type);
CREATE INDEX idx_agent_sessions_started ON agent_sessions(started_at DESC);

-- =============================================================================
-- VIEWS: Useful aggregations
-- =============================================================================

-- Changeset verification status summary
CREATE VIEW changeset_status AS
SELECT 
    c.id,
    c.branch,
    c.agent_type,
    c.created_at,
    COUNT(v.id) AS total_verifications,
    COUNT(v.id) FILTER (WHERE v.success = true) AS passed,
    COUNT(v.id) FILTER (WHERE v.success = false) AS failed,
    COUNT(v.id) FILTER (WHERE v.status = 'pending') AS pending,
    MAX(v.tier) AS highest_tier,
    BOOL_AND(v.success) AS all_passed
FROM changesets c
LEFT JOIN verification_results v ON c.id = v.changeset_id
GROUP BY c.id;

-- Agent performance metrics
CREATE VIEW agent_performance AS
SELECT 
    agent_type,
    agent_id,
    COUNT(DISTINCT c.id) AS total_changesets,
    COUNT(v.id) AS total_verifications,
    AVG(CASE WHEN v.success THEN 1.0 ELSE 0.0 END) AS success_rate,
    AVG(v.duration_seconds) AS avg_verification_time,
    COUNT(DISTINCT c.id) FILTER (
        WHERE NOT EXISTS (
            SELECT 1 FROM verification_results vr 
            WHERE vr.changeset_id = c.id AND vr.success = false
        )
    ) AS clean_changesets
FROM changesets c
LEFT JOIN verification_results v ON c.id = v.changeset_id
GROUP BY agent_type, agent_id;

-- Verification tier distribution
CREATE VIEW tier_metrics AS
SELECT 
    tier,
    executor,
    COUNT(*) AS total_runs,
    AVG(duration_seconds) AS avg_duration,
    AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_seconds) AS p95_duration
FROM verification_results
WHERE completed_at IS NOT NULL
GROUP BY tier, executor;

-- =============================================================================
-- FUNCTIONS: Useful helpers
-- =============================================================================

-- Get all pending approvals for a reviewer
CREATE FUNCTION get_pending_approvals()
RETURNS TABLE (
    approval_id UUID,
    changeset_id TEXT,
    branch TEXT,
    agent_type TEXT,
    policy_name TEXT,
    reason TEXT,
    changed_files JSONB,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id,
        a.changeset_id,
        c.branch,
        c.agent_type,
        a.policy_name,
        a.reason,
        c.changed_files,
        a.created_at
    FROM approval_queue a
    JOIN changesets c ON a.changeset_id = c.id
    WHERE a.status = 'pending'
    AND (a.expires_at IS NULL OR a.expires_at > NOW())
    ORDER BY a.created_at;
END;
$$ LANGUAGE plpgsql;

-- Approve a changeset
CREATE FUNCTION approve_changeset(
    p_approval_id UUID,
    p_approved_by TEXT
) RETURNS BOOLEAN AS $$
DECLARE
    v_changeset_id TEXT;
BEGIN
    UPDATE approval_queue
    SET 
        status = 'approved',
        approved_by = p_approved_by,
        approved_at = NOW()
    WHERE id = p_approval_id AND status = 'pending'
    RETURNING changeset_id INTO v_changeset_id;
    
    IF v_changeset_id IS NULL THEN
        RETURN FALSE;
    END IF;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- ROW LEVEL SECURITY (RLS)
-- =============================================================================

ALTER TABLE changesets ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_queue ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to read all
CREATE POLICY "Allow read access" ON changesets FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON verification_results FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON approval_queue FOR SELECT USING (true);

-- Only service role can insert/update
CREATE POLICY "Service role insert" ON changesets FOR INSERT WITH CHECK (
    auth.role() = 'service_role'
);
CREATE POLICY "Service role insert" ON verification_results FOR INSERT WITH CHECK (
    auth.role() = 'service_role'
);
CREATE POLICY "Service role update" ON verification_results FOR UPDATE USING (
    auth.role() = 'service_role'
);

-- =============================================================================
-- REALTIME SUBSCRIPTIONS
-- =============================================================================

-- Enable realtime for verification results (useful for dashboards)
ALTER PUBLICATION supabase_realtime ADD TABLE verification_results;
ALTER PUBLICATION supabase_realtime ADD TABLE approval_queue;
