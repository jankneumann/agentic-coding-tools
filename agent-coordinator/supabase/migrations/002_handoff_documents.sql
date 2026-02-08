-- Handoff Documents: Session continuity for multi-agent coordination
-- Enables agents to persist context between sessions via structured handoff documents.

-- =============================================================================
-- HANDOFF DOCUMENTS TABLE
-- =============================================================================

CREATE TABLE handoff_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name TEXT NOT NULL,
    session_id TEXT REFERENCES agent_sessions(id),
    summary TEXT NOT NULL,
    completed_work JSONB DEFAULT '[]',
    in_progress JSONB DEFAULT '[]',
    decisions JSONB DEFAULT '[]',
    next_steps JSONB DEFAULT '[]',
    relevant_files JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_handoff_agent ON handoff_documents(agent_name, created_at DESC);
CREATE INDEX idx_handoff_session ON handoff_documents(session_id);


-- =============================================================================
-- FUNCTIONS: Atomic operations for handoff documents
-- =============================================================================

-- Write a handoff document
CREATE OR REPLACE FUNCTION write_handoff(
    p_agent_name TEXT,
    p_session_id TEXT DEFAULT NULL,
    p_summary TEXT DEFAULT NULL,
    p_completed_work JSONB DEFAULT '[]',
    p_in_progress JSONB DEFAULT '[]',
    p_decisions JSONB DEFAULT '[]',
    p_next_steps JSONB DEFAULT '[]',
    p_relevant_files JSONB DEFAULT '[]'
) RETURNS JSONB AS $$
DECLARE
    v_handoff_id UUID;
BEGIN
    IF p_summary IS NULL OR p_summary = '' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'summary_required'
        );
    END IF;

    INSERT INTO handoff_documents (
        agent_name, session_id, summary,
        completed_work, in_progress, decisions, next_steps, relevant_files
    )
    VALUES (
        p_agent_name, p_session_id, p_summary,
        p_completed_work, p_in_progress, p_decisions, p_next_steps, p_relevant_files
    )
    RETURNING id INTO v_handoff_id;

    RETURN jsonb_build_object(
        'success', true,
        'handoff_id', v_handoff_id
    );
END;
$$ LANGUAGE plpgsql;


-- Read recent handoff documents
CREATE OR REPLACE FUNCTION read_handoff(
    p_agent_name TEXT DEFAULT NULL,
    p_limit INTEGER DEFAULT 1
) RETURNS JSONB AS $$
DECLARE
    v_handoffs JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(row_to_json(h)::jsonb ORDER BY h.created_at DESC), '[]'::jsonb)
    INTO v_handoffs
    FROM (
        SELECT id, agent_name, session_id, summary,
               completed_work, in_progress, decisions, next_steps,
               relevant_files, created_at
        FROM handoff_documents
        WHERE (p_agent_name IS NULL OR agent_name = p_agent_name)
        ORDER BY created_at DESC
        LIMIT p_limit
    ) h;

    RETURN jsonb_build_object(
        'handoffs', v_handoffs
    );
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- ROW LEVEL SECURITY
-- =============================================================================

ALTER TABLE handoff_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow read access" ON handoff_documents FOR SELECT USING (true);
CREATE POLICY "Service role full access" ON handoff_documents
    FOR ALL USING (auth.role() = 'service_role');
