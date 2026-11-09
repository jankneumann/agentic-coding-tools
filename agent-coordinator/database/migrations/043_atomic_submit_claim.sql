-- 043: atomically submit and claim a completion-ledger row.

BEGIN;

-- Atomically create a queue row already claimed by the authenticated caller.
--
-- This closes the submit-then-claim race for completion-ledger rows. The
-- runtime exposes this only for dependency-free, non-projection tasks without
-- agent requirements; those restrictions prevent bypassing queue eligibility.

CREATE OR REPLACE FUNCTION submit_claimed_task(
    p_task_type TEXT,
    p_description TEXT,
    p_agent_id TEXT,
    p_input_data JSONB DEFAULT NULL,
    p_priority INTEGER DEFAULT 5,
    p_deadline TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id UUID;
    v_status TEXT;
BEGIN
    IF p_agent_id IS NULL OR length(trim(p_agent_id)) = 0 THEN
        RETURN jsonb_build_object(
            'success', FALSE,
            'created', FALSE,
            'reason', 'missing_claim_identity'
        );
    END IF;

    IF p_priority < 1 OR p_priority > 10 THEN
        RETURN jsonb_build_object(
            'success', FALSE,
            'created', FALSE,
            'reason', 'invalid_priority'
        );
    END IF;

    IF p_input_data ?| ARRAY['change_id', 'phase', 'transition_sequence'] THEN
        RETURN jsonb_build_object(
            'success', FALSE,
            'created', FALSE,
            'reason', 'reserved_projection_key'
        );
    END IF;


    INSERT INTO work_queue(
        task_type,
        description,
        input_data,
        priority,
        deadline,
        status,
        claimed_by,
        claimed_at,
        attempt_count
    )
    VALUES(
        p_task_type,
        p_description,
        p_input_data,
        p_priority,
        p_deadline,
        'claimed',
        p_agent_id,
        NOW(),
        1
    )
    RETURNING id,status INTO v_id,v_status;

    RETURN jsonb_build_object(
        'success', TRUE,
        'task_id', v_id,
        'status', v_status,
        'created', TRUE,
        'deduplicated', FALSE
    );
END;
$$;

REVOKE ALL ON FUNCTION submit_claimed_task(
    TEXT, TEXT, TEXT, JSONB, INTEGER, TIMESTAMPTZ
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION submit_claimed_task(
    TEXT, TEXT, TEXT, JSONB, INTEGER, TIMESTAMPTZ
) TO service_role;

COMMIT;
