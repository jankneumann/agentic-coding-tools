-- Migration: Add p_exclude_submitted_by to claim_task() to prevent self-review.
-- Without this, an evaluator agent can claim evaluation tasks it submitted itself,
-- defeating the cross-vendor / cross-agent review intent (see GATEKEEPER policy and
-- the evaluator profile rationale in 026_evaluator_profile.sql).
--
-- src/work_queue.py sets p_exclude_submitted_by to the claiming agent's ID only for
-- task_types containing 'evaluate' / 'review'; for other task types the param is
-- NULL and behavior is unchanged.

CREATE OR REPLACE FUNCTION claim_task(
    p_agent_id TEXT,
    p_agent_type TEXT,
    p_task_types TEXT[] DEFAULT NULL,
    p_agent_archetypes TEXT[] DEFAULT NULL,
    p_agent_trust_level INTEGER DEFAULT NULL,
    p_exclude_submitted_by TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_task RECORD;
BEGIN
    SELECT * INTO v_task
    FROM work_queue
    WHERE status = 'pending'
      AND (p_task_types IS NULL OR task_type = ANY(p_task_types))
      AND (depends_on IS NULL OR NOT EXISTS (
          SELECT 1 FROM work_queue dep
          WHERE dep.id = ANY(work_queue.depends_on)
          AND dep.status NOT IN ('completed')
      ))
      AND (
          agent_requirements IS NULL
          OR agent_requirements->>'archetype' IS NULL
          OR p_agent_archetypes IS NULL
          OR agent_requirements->>'archetype' = ANY(p_agent_archetypes)
      )
      AND (
          agent_requirements IS NULL
          OR (agent_requirements->>'min_trust_level') IS NULL
          OR p_agent_trust_level IS NULL
          OR p_agent_trust_level >= (agent_requirements->>'min_trust_level')::INTEGER
      )
      -- Self-review exclusion: when the claimant is an evaluator and the task
      -- carries a submitted_by tag matching the claimant, skip it.
      AND (
          p_exclude_submitted_by IS NULL
          OR input_data IS NULL
          OR input_data->>'submitted_by' IS DISTINCT FROM p_exclude_submitted_by
      )
    ORDER BY priority ASC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'reason', 'no_tasks_available'
        );
    END IF;

    UPDATE work_queue
    SET
        status = 'claimed',
        claimed_by = p_agent_id,
        claimed_at = NOW(),
        attempt_count = attempt_count + 1
    WHERE id = v_task.id;

    RETURN jsonb_build_object(
        'success', true,
        'task_id', v_task.id,
        'task_type', v_task.task_type,
        'description', v_task.description,
        'input_data', v_task.input_data,
        'priority', v_task.priority,
        'deadline', v_task.deadline,
        'agent_requirements', v_task.agent_requirements
    );
END;
$$ LANGUAGE plpgsql;
