-- Migration 006: Guardrails tables for destructive operation detection
-- Dependencies: 001_core_schema.sql
-- Phase 3 feature: Deterministic pattern matching to block destructive operations

-- =============================================================================
-- Tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS operation_guardrails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,  -- 'git', 'file', 'database', 'credential', 'deployment'
    pattern TEXT NOT NULL,   -- regex pattern
    severity TEXT NOT NULL DEFAULT 'block',  -- 'block', 'warn', 'log'
    description TEXT,
    min_trust_level INT NOT NULL DEFAULT 3,  -- minimum trust level to bypass
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS guardrail_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    agent_type TEXT,
    pattern_name TEXT NOT NULL,
    category TEXT NOT NULL,
    operation_text TEXT NOT NULL,
    matched_text TEXT,
    blocked BOOLEAN NOT NULL DEFAULT true,
    trust_level INT,
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_guardrails_category ON operation_guardrails (category);
CREATE INDEX IF NOT EXISTS idx_guardrails_enabled ON operation_guardrails (enabled) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_violations_agent ON guardrail_violations (agent_id);
CREATE INDEX IF NOT EXISTS idx_violations_pattern ON guardrail_violations (pattern_name);
CREATE INDEX IF NOT EXISTS idx_violations_created ON guardrail_violations (created_at DESC);

-- =============================================================================
-- Seed default destructive patterns
-- =============================================================================

INSERT INTO operation_guardrails (name, category, pattern, severity, description, min_trust_level)
VALUES
    ('git_force_push', 'git', 'git\s+push\s+.*--force', 'block', 'Force push can overwrite remote history', 3),
    ('git_reset_hard', 'git', 'git\s+reset\s+--hard', 'block', 'Hard reset discards uncommitted changes', 3),
    ('git_clean_force', 'git', 'git\s+clean\s+-[fd]', 'block', 'Clean force removes untracked files', 3),
    ('git_branch_delete', 'git', 'git\s+(branch\s+-D|push\s+.*--delete)', 'warn', 'Branch deletion may lose work', 3),
    ('rm_recursive_force', 'file', 'rm\s+-r[f]?\s+/', 'block', 'Recursive delete from root is destructive', 4),
    ('rm_rf', 'file', 'rm\s+-rf\s+', 'block', 'Force recursive delete is destructive', 3),
    ('find_delete', 'file', 'find\s+.*-delete', 'warn', 'Find with delete can remove many files', 3),
    ('drop_table', 'database', 'DROP\s+TABLE', 'block', 'Dropping tables destroys data', 4),
    ('truncate_table', 'database', 'TRUNCATE\s+', 'block', 'Truncating tables destroys data', 4),
    ('delete_no_where', 'database', 'DELETE\s+FROM\s+\w+\s*;', 'block', 'DELETE without WHERE removes all rows', 3),
    ('env_file_modify', 'credential', '\.(env|env\.local|env\.production)', 'warn', 'Environment files may contain secrets', 2),
    ('credentials_file', 'credential', '(credentials|secrets|passwords)\.(json|yaml|yml|txt)', 'warn', 'Credential files should not be modified by agents', 2),
    ('ssh_key_modify', 'credential', '\.ssh/(id_rsa|id_ed25519|authorized_keys)', 'block', 'SSH key modification is security-sensitive', 4),
    ('deploy_command', 'deployment', '(kubectl\s+apply|terraform\s+apply|docker\s+push)', 'block', 'Production deployment should require approval', 3),
    ('npm_publish', 'deployment', 'npm\s+publish', 'block', 'Publishing packages should require approval', 3)
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- Functions
-- =============================================================================

CREATE OR REPLACE FUNCTION check_guardrails(
    p_operation_text TEXT,
    p_agent_id TEXT DEFAULT NULL,
    p_trust_level INT DEFAULT 2
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_violations JSONB := '[]'::jsonb;
    v_pattern RECORD;
    v_safe BOOLEAN := true;
BEGIN
    FOR v_pattern IN
        SELECT name, category, pattern, severity, min_trust_level
        FROM operation_guardrails
        WHERE enabled = true
    LOOP
        IF p_operation_text ~* v_pattern.pattern THEN
            -- Check if trust level allows bypass
            IF p_trust_level < v_pattern.min_trust_level THEN
                IF v_pattern.severity = 'block' THEN
                    v_safe := false;
                END IF;

                v_violations := v_violations || jsonb_build_object(
                    'pattern_name', v_pattern.name,
                    'category', v_pattern.category,
                    'severity', v_pattern.severity,
                    'blocked', (v_pattern.severity = 'block' AND p_trust_level < v_pattern.min_trust_level)
                );

                -- Log violation
                IF p_agent_id IS NOT NULL THEN
                    INSERT INTO guardrail_violations (
                        agent_id, pattern_name, category, operation_text,
                        blocked, trust_level
                    ) VALUES (
                        p_agent_id, v_pattern.name, v_pattern.category,
                        LEFT(p_operation_text, 500),
                        (v_pattern.severity = 'block' AND p_trust_level < v_pattern.min_trust_level),
                        p_trust_level
                    );
                END IF;
            END IF;
        END IF;
    END LOOP;

    RETURN jsonb_build_object(
        'safe', v_safe,
        'violations', v_violations
    );
END;
$$;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE operation_guardrails ENABLE ROW LEVEL SECURITY;
ALTER TABLE guardrail_violations ENABLE ROW LEVEL SECURITY;

CREATE POLICY guardrails_read ON operation_guardrails FOR SELECT USING (true);
CREATE POLICY guardrails_write ON operation_guardrails FOR ALL
    USING (current_setting('role') = 'service_role');

CREATE POLICY violations_read ON guardrail_violations FOR SELECT USING (true);
CREATE POLICY violations_write ON guardrail_violations FOR INSERT
    WITH CHECK (current_setting('role') = 'service_role');
