-- Migration 005: Verification gateway tables
-- Dependencies: 001_core_schema.sql (agent_sessions reference)
-- Phase 3 feature: Multi-tier verification for agent-generated changes

-- =============================================================================
-- Types
-- =============================================================================

DO $$ BEGIN
    CREATE TYPE verification_tier AS ENUM ('STATIC', 'UNIT', 'INTEGRATION', 'SYSTEM', 'MANUAL');
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE verification_executor AS ENUM ('inline', 'github', 'ntm', 'e2b', 'human');
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE verification_status AS ENUM ('pending', 'running', 'success', 'failure', 'cancelled');
EXCEPTION WHEN duplicate_object THEN null;
END $$;

-- =============================================================================
-- Tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS changesets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    session_id TEXT,
    branch_name TEXT,
    changed_files JSONB NOT NULL DEFAULT '[]',
    commit_sha TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS verification_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    changeset_id UUID NOT NULL REFERENCES changesets(id),
    tier verification_tier NOT NULL,
    executor verification_executor NOT NULL,
    status verification_status NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INT,
    result JSONB DEFAULT '{}',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS verification_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    file_pattern TEXT NOT NULL,  -- glob pattern
    tier verification_tier NOT NULL,
    executor verification_executor NOT NULL,
    config JSONB DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT true,
    priority INT NOT NULL DEFAULT 5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approval_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    changeset_id UUID NOT NULL REFERENCES changesets(id),
    requested_by TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'approved', 'denied'
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    review_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_changesets_agent ON changesets (agent_id);
CREATE INDEX IF NOT EXISTS idx_changesets_status ON changesets (status);
CREATE INDEX IF NOT EXISTS idx_verification_results_changeset ON verification_results (changeset_id);
CREATE INDEX IF NOT EXISTS idx_verification_results_status ON verification_results (status);
CREATE INDEX IF NOT EXISTS idx_approval_queue_status ON approval_queue (status);
CREATE INDEX IF NOT EXISTS idx_verification_policies_pattern ON verification_policies (file_pattern);

-- =============================================================================
-- Views
-- =============================================================================

CREATE OR REPLACE VIEW changeset_status AS
SELECT
    c.id AS changeset_id,
    c.agent_id,
    c.status AS changeset_status,
    c.created_at,
    COUNT(vr.id) AS total_checks,
    COUNT(CASE WHEN vr.status = 'success' THEN 1 END) AS passed,
    COUNT(CASE WHEN vr.status = 'failure' THEN 1 END) AS failed,
    COUNT(CASE WHEN vr.status = 'pending' THEN 1 END) AS pending_checks
FROM changesets c
LEFT JOIN verification_results vr ON vr.changeset_id = c.id
GROUP BY c.id, c.agent_id, c.status, c.created_at;

CREATE OR REPLACE VIEW agent_performance AS
SELECT
    c.agent_id,
    COUNT(DISTINCT c.id) AS total_changesets,
    COUNT(CASE WHEN vr.status = 'success' THEN 1 END) AS checks_passed,
    COUNT(CASE WHEN vr.status = 'failure' THEN 1 END) AS checks_failed,
    ROUND(
        COUNT(CASE WHEN vr.status = 'success' THEN 1 END)::NUMERIC /
        NULLIF(COUNT(vr.id), 0) * 100, 2
    ) AS success_rate,
    AVG(vr.duration_ms) AS avg_check_duration_ms
FROM changesets c
LEFT JOIN verification_results vr ON vr.changeset_id = c.id
GROUP BY c.agent_id;

CREATE OR REPLACE VIEW tier_metrics AS
SELECT
    vr.tier,
    vr.executor,
    COUNT(*) AS total_runs,
    COUNT(CASE WHEN vr.status = 'success' THEN 1 END) AS successes,
    COUNT(CASE WHEN vr.status = 'failure' THEN 1 END) AS failures,
    AVG(vr.duration_ms) AS avg_duration_ms,
    MAX(vr.duration_ms) AS max_duration_ms
FROM verification_results vr
GROUP BY vr.tier, vr.executor;

-- =============================================================================
-- Functions
-- =============================================================================

CREATE OR REPLACE FUNCTION get_pending_approvals()
RETURNS JSONB
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN COALESCE(
        (SELECT jsonb_agg(row_to_json(aq))
         FROM (
             SELECT aq.*, c.agent_id, c.description, c.changed_files
             FROM approval_queue aq
             JOIN changesets c ON c.id = aq.changeset_id
             WHERE aq.status = 'pending'
             ORDER BY aq.created_at ASC
         ) aq),
        '[]'::jsonb
    );
END;
$$;

CREATE OR REPLACE FUNCTION approve_changeset(
    p_approval_id UUID,
    p_reviewer TEXT,
    p_approved BOOLEAN,
    p_notes TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_changeset_id UUID;
BEGIN
    UPDATE approval_queue
    SET status = CASE WHEN p_approved THEN 'approved' ELSE 'denied' END,
        reviewed_by = p_reviewer,
        reviewed_at = now(),
        review_notes = p_notes
    WHERE id = p_approval_id AND status = 'pending'
    RETURNING changeset_id INTO v_changeset_id;

    IF v_changeset_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'reason', 'approval_not_found_or_already_reviewed');
    END IF;

    -- Update changeset status
    UPDATE changesets
    SET status = CASE WHEN p_approved THEN 'approved' ELSE 'rejected' END,
        updated_at = now()
    WHERE id = v_changeset_id;

    RETURN jsonb_build_object('success', true, 'changeset_id', v_changeset_id);
END;
$$;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE changesets ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE verification_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY changesets_read ON changesets FOR SELECT USING (true);
CREATE POLICY changesets_write ON changesets FOR ALL
    USING (current_setting('role') = 'service_role');

CREATE POLICY verification_results_read ON verification_results FOR SELECT USING (true);
CREATE POLICY verification_results_write ON verification_results FOR ALL
    USING (current_setting('role') = 'service_role');

CREATE POLICY verification_policies_read ON verification_policies FOR SELECT USING (true);
CREATE POLICY verification_policies_write ON verification_policies FOR ALL
    USING (current_setting('role') = 'service_role');

CREATE POLICY approval_queue_read ON approval_queue FOR SELECT USING (true);
CREATE POLICY approval_queue_write ON approval_queue FOR ALL
    USING (current_setting('role') = 'service_role');
