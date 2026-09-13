-- 036: make cancellation terminal against late completions
--
-- complete_task (001_core_schema.sql) updated rows by
-- `WHERE id = p_task_id AND claimed_by = p_agent_id` with no status filter.
-- Migration 035's reconcile_work_projection() cancels stale claimed/running
-- rows out from under an in-flight worker; that worker's eventual
-- complete_task call could still flip the now-terminal `cancelled` row back
-- to `completed`/`failed`. Restrict the UPDATE to the active statuses
-- ('claimed', 'running') so a cancellation can never be overwritten, and
-- surface a distinct 'task_not_active' reason (with the row's current
-- status) so callers can tell "refused because already terminal" apart
-- from "refused because not found / not claimed by this agent".

CREATE OR REPLACE FUNCTION complete_task(
    p_task_id UUID,
    p_agent_id TEXT,
    p_success BOOLEAN,
    p_result JSONB DEFAULT NULL,
    p_error_message TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_status TEXT;
    v_updated INTEGER;
    v_current_status TEXT;
BEGIN
    v_status := CASE WHEN p_success THEN 'completed' ELSE 'failed' END;

    UPDATE work_queue
    SET
        status = v_status,
        result = p_result,
        error_message = p_error_message,
        completed_at = NOW()
    WHERE id = p_task_id AND claimed_by = p_agent_id
      AND status IN ('claimed', 'running');

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated > 0 THEN
        RETURN jsonb_build_object(
            'success', true,
            'status', v_status,
            'task_id', p_task_id
        );
    END IF;

    -- The row exists and was claimed by this agent, but is no longer
    -- active (most commonly: cancelled by projection reconciliation while
    -- the worker was still running). Report the current status instead of
    -- silently no-oping.
    SELECT status INTO v_current_status
    FROM work_queue
    WHERE id = p_task_id AND claimed_by = p_agent_id;

    IF v_current_status IS NOT NULL THEN
        RETURN jsonb_build_object(
            'success', false,
            'reason', 'task_not_active',
            'status', v_current_status,
            'task_id', p_task_id
        );
    END IF;

    RETURN jsonb_build_object(
        'success', false,
        'reason', 'task_not_found_or_not_claimed_by_agent'
    );
END;
$$ LANGUAGE plpgsql;
