-- 034: supervisor record on handoff documents
-- (extend-handoff-document-with-supervisor-record, supervisor roadmap ri-05)
--
-- One nullable JSONB column carrying a self-versioned SupervisorRecord
-- (contracts/schemas/supervisor-record.schema.json). Inner validation is the
-- writer's job; SQL only requires object-or-null.

ALTER TABLE handoff_documents
    ADD COLUMN IF NOT EXISTS supervisor_record JSONB DEFAULT NULL;

ALTER TABLE handoff_documents
    ADD CONSTRAINT handoff_supervisor_record_is_object
    CHECK (supervisor_record IS NULL OR jsonb_typeof(supervisor_record) = 'object');

-- Adding a defaulted ninth parameter would create a second overload and make
-- eight-argument RPC calls ambiguous; drop the old signature first.
DROP FUNCTION IF EXISTS write_handoff(TEXT, TEXT, TEXT, JSONB, JSONB, JSONB, JSONB, JSONB);
DROP FUNCTION IF EXISTS read_handoff(TEXT, INTEGER);

CREATE OR REPLACE FUNCTION write_handoff(
    p_agent_name TEXT,
    p_session_id TEXT DEFAULT NULL,
    p_summary TEXT DEFAULT NULL,
    p_completed_work JSONB DEFAULT '[]',
    p_in_progress JSONB DEFAULT '[]',
    p_decisions JSONB DEFAULT '[]',
    p_next_steps JSONB DEFAULT '[]',
    p_relevant_files JSONB DEFAULT '[]',
    p_supervisor_record JSONB DEFAULT NULL
) RETURNS JSONB
AS $$
DECLARE
    v_handoff_id UUID;
BEGIN
    IF p_summary IS NULL OR p_summary = '' THEN
        RETURN jsonb_build_object('success', false, 'error', 'summary_required');
    END IF;

    INSERT INTO handoff_documents (
        agent_name, session_id, summary,
        completed_work, in_progress, decisions, next_steps, relevant_files,
        supervisor_record
    ) VALUES (
        p_agent_name, p_session_id, p_summary,
        p_completed_work, p_in_progress, p_decisions, p_next_steps, p_relevant_files,
        p_supervisor_record
    ) RETURNING id INTO v_handoff_id;

    RETURN jsonb_build_object('success', true, 'handoff_id', v_handoff_id);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION read_handoff(
    p_agent_name TEXT DEFAULT NULL,
    p_limit INT DEFAULT 1,
    p_supervisor_only BOOLEAN DEFAULT FALSE
) RETURNS JSONB
AS $$
DECLARE
    v_handoffs JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(row_to_json(h)::jsonb ORDER BY h.created_at DESC), '[]'::jsonb) INTO v_handoffs
    FROM (
        SELECT id, agent_name, session_id, summary,
               completed_work, in_progress, decisions, next_steps, relevant_files,
               supervisor_record, created_at
        FROM handoff_documents
        WHERE (p_agent_name IS NULL OR agent_name = p_agent_name)
          AND (NOT p_supervisor_only OR supervisor_record IS NOT NULL)
        ORDER BY created_at DESC
        LIMIT p_limit
    ) h;
    RETURN jsonb_build_object('handoffs', v_handoffs);
END;
$$ LANGUAGE plpgsql;
