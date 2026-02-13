-- Migration 008: Immutable audit log for all coordination operations
-- Dependencies: 007_agent_profiles.sql (agent context)
-- Phase 3 feature: Comprehensive, immutable audit trail

-- =============================================================================
-- Tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    agent_type TEXT,
    operation TEXT NOT NULL,
    parameters JSONB DEFAULT '{}',
    result JSONB DEFAULT '{}',
    duration_ms INT,
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_agent ON audit_log (agent_id, operation);
CREATE INDEX IF NOT EXISTS idx_audit_log_operation ON audit_log (operation);

-- =============================================================================
-- Immutability enforcement
-- =============================================================================

CREATE OR REPLACE FUNCTION raise_immutable_error()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit log entries are immutable — UPDATE and DELETE are prohibited';
END;
$$ LANGUAGE plpgsql;

-- Prevent any modification of existing audit entries
DROP TRIGGER IF EXISTS prevent_audit_modification ON audit_log;
CREATE TRIGGER prevent_audit_modification
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION raise_immutable_error();

-- =============================================================================
-- Retention policy function (called by cron or application)
-- =============================================================================

CREATE OR REPLACE FUNCTION cleanup_old_audit_entries(
    p_retention_days INT DEFAULT 90
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_deleted INT;
BEGIN
    -- Temporarily disable the immutability trigger for cleanup
    ALTER TABLE audit_log DISABLE TRIGGER prevent_audit_modification;

    BEGIN
        DELETE FROM audit_log
        WHERE created_at < now() - (p_retention_days || ' days')::interval;

        GET DIAGNOSTICS v_deleted = ROW_COUNT;
    EXCEPTION WHEN OTHERS THEN
        -- Re-enable the trigger even on failure
        ALTER TABLE audit_log ENABLE TRIGGER prevent_audit_modification;
        RAISE;
    END;

    -- Re-enable the trigger
    ALTER TABLE audit_log ENABLE TRIGGER prevent_audit_modification;

    RETURN jsonb_build_object(
        'success', true,
        'entries_deleted', v_deleted,
        'retention_days', p_retention_days
    );
END;
$$;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Read access restricted to service_role (audit data may contain sensitive parameters)
CREATE POLICY audit_log_read ON audit_log FOR SELECT
    USING (current_setting('role') = 'service_role');

-- Insert only for service_role (no UPDATE or DELETE via RLS either)
CREATE POLICY audit_log_insert ON audit_log FOR INSERT
    WITH CHECK (current_setting('role') = 'service_role');
