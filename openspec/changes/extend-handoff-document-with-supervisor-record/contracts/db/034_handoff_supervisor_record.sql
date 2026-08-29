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

CREATE OR REPLACE FUNCTION write_handoff(
    p_agent_name TEXT,
    p_session_id TEXT,
    p_summary TEXT,
    p_completed_work JSONB DEFAULT '[]',
    p_in_progress JSONB DEFAULT '[]',
    p_decisions JSONB DEFAULT '[]',
    p_next_steps JSONB DEFAULT '[]',
    p_relevant_files JSONB DEFAULT '[]',
    p_supervisor_record JSONB DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_id UUID;
BEGIN
    IF p_summary IS NULL OR length(trim(p_summary)) = 0 THEN
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
    ) RETURNING id INTO v_id;

    RETURN jsonb_build_object('success', true, 'handoff_id', v_id);
END;
$$;

CREATE OR REPLACE FUNCTION read_handoff(
    p_agent_name TEXT DEFAULT NULL,
    p_limit INT DEFAULT 1
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_rows JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(row_to_json(h)), '[]'::jsonb) INTO v_rows
    FROM (
        SELECT id, agent_name, session_id, summary,
               completed_work, in_progress, decisions, next_steps, relevant_files,
               supervisor_record, created_at
        FROM handoff_documents
        WHERE p_agent_name IS NULL OR agent_name = p_agent_name
        ORDER BY created_at DESC
        LIMIT p_limit
    ) h;
    RETURN jsonb_build_object('handoffs', v_rows);
END;
$$;
